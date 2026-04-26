"""Generates demo_rag_vs_gxp.ipynb — the side-by-side teaching notebook.

Run once:  python demo_rag/build_notebook.py
"""
from __future__ import annotations

import json
from pathlib import Path

# Each entry is (cell_type, source_text). Code cells run; markdown cells render.
CELLS: list[tuple[str, str]] = [
    ("md", """\
# RAG Pipeline Demo — Standard RAG vs GxP-Struct

This notebook walks through every stage of a RAG pipeline against a pharmaceutical SOP, then runs the **same question** through the deterministic GxP-Struct rule engine. The point is to *see* the difference, not just hear about it.

**What you'll see, cell by cell:**

1. Open a Word SOP, count its size
2. Chunk it (where tables get tested)
3. Convert one chunk to a vector and look at the actual numbers
4. Upload all vectors to Pinecone
5. Ask a question — see Pinecone retrieve top-5 chunks with similarity scores
6. Send chunks + question to Claude, see the answer
7. **Run the same question 5 times** — watch the variance
8. Run the same question through the GxP-Struct rule engine — see the consistency
9. Side-by-side comparison

**Time:** about 5 minutes to step through. **API cost:** about $0.05 total.

> Press **Shift + Enter** in each cell to run it. Run cells in order.
"""),

    ("md", "## Setup — load API keys and turn on Phoenix tracing\n\nThis cell loads your `.env` file and confirms the four keys are present."),

    ("code", """\
import os
import sys
import time
from pathlib import Path
from dotenv import load_dotenv
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

console = Console()

# Find the project root (gxp-struct/) by walking up from CWD until we see .env.
# This makes the notebook work whether you launch Jupyter from gxp-struct/ or
# from demo_rag/.
def find_project_root() -> Path:
    here = Path.cwd().resolve()
    for candidate in [here, *here.parents]:
        if (candidate / ".env").exists():
            return candidate
    raise FileNotFoundError(
        "Could not find .env in the current folder or any parent. "
        "Launch Jupyter from inside the gxp-struct/ folder."
    )

PROJECT_ROOT = find_project_root()
print(f"Project root: {PROJECT_ROOT}")
# override=True so .env wins over any pre-existing shell env vars (including
# accidentally-empty ones).
load_dotenv(PROJECT_ROOT / ".env", override=True)

required = ["OPENAI_API_KEY", "ANTHROPIC_API_KEY", "PINECONE_API_KEY", "PHOENIX_API_KEY", "PHOENIX_COLLECTOR_ENDPOINT"]
missing = [k for k in required if not os.environ.get(k)]
if missing:
    raise SystemExit(f"Missing keys in .env: {missing}")
print("Keys loaded:", ", ".join(required))
"""),

    ("md", "Now turn on **Phoenix tracing** — this captures every LlamaIndex step (chunking, embedding, retrieval, LLM call) and ships it to your Phoenix Cloud workspace, where you can click through the trace afterwards."),

    ("code", """\
from phoenix.otel import register

tracer_provider = register(
    project_name="gxp-struct-demo",
    endpoint=f"{os.environ['PHOENIX_COLLECTOR_ENDPOINT']}/v1/traces",
    headers={"authorization": f"Bearer {os.environ['PHOENIX_API_KEY']}"},
    auto_instrument=True,  # auto-instrument LlamaIndex
)
print("Phoenix tracing enabled.")
print(f"Open this URL in another tab to watch traces appear live:")
print(f"  {os.environ['PHOENIX_COLLECTOR_ENDPOINT']}")
"""),

    ("md", """\
## Step 1 — Read the Word SOP

LlamaIndex's `DocxReader` opens the `.docx` file and extracts text. (Tables in Word are flattened into text rows; this is one of the failure modes the GxP-Struct paper talks about.)
"""),

    ("code", """\
from llama_index.readers.file import DocxReader

# Pick the first .docx in Reference SOPs/ (handles renames automatically).
# Falls back to the markdown SOP that ships in the repo if no .docx is found.
docx_candidates = sorted((PROJECT_ROOT / "Reference SOPs").glob("*.docx")) if (PROJECT_ROOT / "Reference SOPs").exists() else []
if docx_candidates:
    SOP_PATH = docx_candidates[0]
else:
    SOP_PATH = PROJECT_ROOT / "data" / "Deviation_SOP.md"
    print(f"No .docx in Reference SOPs/, falling back to: {SOP_PATH.name}")

if SOP_PATH.suffix == ".docx":
    docs = DocxReader().load_data(SOP_PATH)
else:
    from llama_index.core import SimpleDirectoryReader
    docs = SimpleDirectoryReader(input_files=[SOP_PATH]).load_data()

total_chars = sum(len(d.text) for d in docs)
total_words = sum(len(d.text.split()) for d in docs)

print(f"File:       {SOP_PATH.name}")
print(f"Documents:  {len(docs)}")
print(f"Characters: {total_chars:,}")
print(f"Words:      {total_words:,}  (~{total_words // 250} 'pages')")
print()
console.print(Panel(docs[0].text[:600] + ("..." if len(docs[0].text) > 600 else ""),
                    title="First 600 characters of the SOP"))
"""),

    ("md", """\
## Step 2 — Chunk the SOP

The SOP is too big to send to an LLM in one shot, and we want to retrieve only the *relevant* parts. So we split it into chunks. `chunk_size=512` means each chunk is roughly 512 tokens (~2,000 characters); `chunk_overlap=50` means consecutive chunks share 50 tokens, which preserves context across boundaries.

**Why this is the first failure point in pharma:** if your responsibilities table gets split mid-row, the AI mixes up who's allowed to do what. Watch the chunks below — see if any look like fragments of a table.
"""),

    ("code", """\
from llama_index.core.node_parser import SentenceSplitter

splitter = SentenceSplitter(chunk_size=512, chunk_overlap=50)
nodes = splitter.get_nodes_from_documents(docs)

chunk_lens = [len(n.text) for n in nodes]
print(f"Total chunks: {len(nodes)}")
print(f"Chunk size — min: {min(chunk_lens):>4}, avg: {sum(chunk_lens)//len(chunk_lens):>4}, max: {max(chunk_lens):>4} chars")
print()
print("First 3 chunks (so you can see what they look like):")
print()
for i, n in enumerate(nodes[:3]):
    snippet = n.text[:280] + ("..." if len(n.text) > 280 else "")
    console.print(Panel(snippet, title=f"Chunk #{i} ({len(n.text)} chars)"))
"""),

    ("md", """\
## Step 3 — Turn one chunk into a vector

A "vector" is just a list of numbers. The OpenAI `text-embedding-3-large` model converts a piece of text into a list of **3,072 numbers** that captures its meaning. Two chunks about Level 2 investigations will have vectors that are close to each other (mathematically); two chunks about unrelated topics will have vectors far apart.

This is what makes "find the most similar chunk" possible.
"""),

    ("code", """\
from llama_index.embeddings.openai import OpenAIEmbedding

embedder = OpenAIEmbedding(
    model="text-embedding-3-large",
    api_key=os.environ["OPENAI_API_KEY"],
)

# Embed just the first chunk so you can see what comes back
sample_vector = embedder.get_text_embedding(nodes[0].text)

print(f"Vector length: {len(sample_vector):,} numbers")
print(f"First 10:  {sample_vector[:10]}")
print(f"Last 10:   {sample_vector[-10:]}")
print()
print(f"All {len(sample_vector):,} numbers represent ONE chunk. Multiply that by")
print(f"{len(nodes)} chunks for this SOP, and you have why we need a vector database.")
"""),

    ("md", """\
## Step 4 — Upload all vectors to Pinecone

Pinecone is a database designed specifically for storing and searching millions of vectors quickly. We connect to your Pinecone account, hand it our chunks, and it embeds them and stores them under a "namespace" so we can clear them later without affecting other experiments.

After this cell runs, open https://app.pinecone.io in another tab — you'll see the vectors appear in your `gxp-struct-demo` index.
"""),

    ("code", """\
from pinecone import Pinecone
from llama_index.vector_stores.pinecone import PineconeVectorStore
from llama_index.core import StorageContext, VectorStoreIndex, Settings

Settings.embed_model = embedder

pc = Pinecone(api_key=os.environ["PINECONE_API_KEY"])
index_name = os.environ.get("PINECONE_INDEX_NAME", "gxp-struct-demo")

desc = pc.describe_index(index_name)
print(f"Pinecone index '{index_name}'")
print(f"  Dimension:  {desc.dimension}")
print(f"  Status:     {desc.status['state']}")
print(f"  Cloud:      {desc.spec.serverless.cloud}/{desc.spec.serverless.region}")
print()

pinecone_index = pc.Index(index_name)
namespace = os.environ.get("PINECONE_NAMESPACE", "demo-v1")

# Clear any prior demo run from the same namespace so we start clean
try:
    pinecone_index.delete(delete_all=True, namespace=namespace)
    print(f"Cleared old vectors in namespace '{namespace}'")
except Exception:
    pass  # namespace might not exist yet — that's fine

vector_store = PineconeVectorStore(pinecone_index=pinecone_index, namespace=namespace)
storage_context = StorageContext.from_defaults(vector_store=vector_store)

print(f"Uploading {len(nodes)} vectors to Pinecone...")
index = VectorStoreIndex(nodes=nodes, storage_context=storage_context, show_progress=True)
print()
print("Done. Open https://app.pinecone.io to see the vectors.")
"""),

    ("md", """\
## Step 5 — Ask a question, watch Pinecone retrieve

Now we ask a question. Pinecone embeds the question into a vector the same way it embedded the chunks, then returns the **top 5 chunks** whose vectors are mathematically closest to the question's vector. Each comes back with a *similarity score* between 0 and 1.

The question we'll use:
"""),

    ("code", """\
QUESTION = "A sterility breach occurred during fill. What level should this deviation be classified as?"

retriever = index.as_retriever(similarity_top_k=5)
retrieved = retriever.retrieve(QUESTION)

print(f"Question: {QUESTION}")
print()
table = Table(title="Top 5 chunks Pinecone returned")
table.add_column("#", justify="right", style="dim")
table.add_column("Score", justify="right")
table.add_column("Chunk preview")
for i, r in enumerate(retrieved, 1):
    snippet = r.node.text[:140].replace("\\n", " ").strip()
    table.add_row(str(i), f"{(r.score or 0):.3f}", snippet + "...")
console.print(table)
"""),

    ("md", """\
## Step 6 — Send chunks + question to Claude

The retrieved chunks plus the question get bundled into a prompt and sent to Claude. Claude reads them and writes the answer. This is the "G" (generation) in RAG.

We're using Claude with `temperature=0.0`, which means "be as deterministic as you can." Even with that setting, you'll see in the next step that the answer can still vary across runs.
"""),

    ("code", """\
from llama_index.llms.anthropic import Anthropic

llm = Anthropic(
    model=os.environ.get("ANTHROPIC_MODEL", "claude-sonnet-4-5"),
    api_key=os.environ["ANTHROPIC_API_KEY"],
    temperature=0.6,  # bump from 0.0 — at temp=0 modern Claude is too consistent
                       # to expose the variance. 0.6 is realistic for production LLMs.
    max_tokens=600,
)
Settings.llm = llm

query_engine = index.as_query_engine(similarity_top_k=5)
response = query_engine.query(QUESTION)

console.print(Panel(str(response).strip(), title="Claude's answer (Standard RAG)"))
print()
print("Source chunks Claude used:")
for i, src in enumerate(response.source_nodes, 1):
    print(f"  [{i}] score={src.score:.3f}, length={len(src.node.text)} chars")
"""),

    ("md", """\
## Step 7 — Run the same question 5 times. Look at the variance.

This is the punchline of standard RAG in regulated environments. We ask **the same question, with the same SOP, at temperature=0**, five times in a row. In a deterministic system the answer would be byte-identical every time. In RAG it usually isn't, because:

- The retrieval step can return slightly different chunks if any happen to be near a similarity tie
- The LLM, even at temperature 0, has subtle non-determinism on long outputs
- The wording, citations, and even the *number* in the answer can drift

Watch what happens.
"""),

    ("code", """\
print(f"Asking 5 times: {QUESTION}\\n")
print("=" * 80)
results = []
for i in range(1, 6):
    resp = query_engine.query(QUESTION)
    text = str(resp).strip()
    results.append(text)
    console.print(f"\\n[bold cyan]Run {i}:[/bold cyan]")
    console.print(text[:400] + ("..." if len(text) > 400 else ""))
print()
print("=" * 80)
unique = len(set(results))
print(f"\\nDistinct answers across 5 runs: {unique} / 5")
if unique == 1:
    print("All 5 answers were byte-identical.")
else:
    print(f"The system produced {unique} different answers to the same question.")
    print("In a regulated environment, this variance is the failure mode.")
"""),

    ("md", """\
## Step 8 — Now the same question, through the GxP-Struct rule engine

No LLM. No retrieval. No vectors. The rule engine looks at the question, matches it against the rules parsed from the `.gxp` companion file, and returns a cited answer in milliseconds.

We run it 5 times so you can see the consistency directly.
"""),

    ("code", """\
sys.path.insert(0, str(PROJECT_ROOT))
import rules

print(f"Question: {QUESTION}\\n")
print("=" * 80)
gxp_results = []
gxp_latencies = []
for i in range(1, 6):
    start = time.perf_counter()
    r = rules.evaluate(QUESTION)
    elapsed_ms = (time.perf_counter() - start) * 1000
    gxp_results.append(r.answer)
    gxp_latencies.append(elapsed_ms)
    print(f"\\nRun {i}  ({elapsed_ms:.2f} ms)")
    print(f"  Rule fired:  {r.fired}")
    print(f"  Rule ID:     {r.rule_id}")
    print(f"  Answer:      {r.answer}")
print()
print("=" * 80)
unique = len(set(gxp_results))
print(f"\\nDistinct answers across 5 runs: {unique} / 5")
print(f"Average latency: {sum(gxp_latencies)/len(gxp_latencies):.2f} ms")
print(f"API calls made:  0")
"""),

    ("md", """\
## Step 9 — Side-by-side

| | Standard RAG (Path A) | GxP-Struct rule engine (Path B) |
|---|---|---|
| **What it touches** | OpenAI (embeddings) + Pinecone (search) + Claude (synthesis) | A `.gxp` file and a Python function |
| **Latency per query** | 1–3 seconds | < 10 milliseconds |
| **Cost per query** | ~$0.005 – $0.02 | $0.00 |
| **Determinism** | Best-effort, often varies | Guaranteed identical every time |
| **Citation** | "Based on retrieved chunks" | Specific rule ID + SOP section number |
| **Failure mode** | Hallucination, table-shredding, default-rule violations | Returns "no rule fires" → falls back to RAG only when truly open-ended |
| **What an auditor sees** | A prompt with chunks and a generated answer | A direct chain: SOP → rule → answer |

The whole point of GxP-Struct is **not** to replace RAG — it's to put a deterministic layer in *front* of RAG so the dangerous decisions never reach the LLM.
"""),

    ("md", """\
## Step 10 — Inspect the trace in Phoenix

Every step you just ran was traced. Open your Phoenix Cloud workspace:

🔗 https://app.phoenix.arize.com/s/chotupandey616/projects

Click into the **gxp-struct-demo** project. You should see entries for each query, expandable into:
- The chunks that were retrieved (and their scores)
- The exact prompt sent to Claude (system message + chunks + question)
- Claude's response
- The latency of each stage

This is what an auditor would expect: every step of the AI's reasoning, recorded and inspectable.
"""),

    ("md", """\
## Cleanup (optional)

If you want to clear the vectors out of Pinecone after you're done (so they don't sit there occupying your free tier), run this cell.
"""),

    ("code", """\
# Uncomment the line below to delete the demo vectors:
# pinecone_index.delete(delete_all=True, namespace=namespace)
# print(f"Cleared namespace '{namespace}' in Pinecone.")
print("Cleanup cell — uncomment the delete line if you want to wipe the demo vectors.")
"""),
]


def make_notebook() -> dict:
    cells = []
    for kind, src in CELLS:
        if kind == "md":
            cells.append({
                "cell_type": "markdown",
                "metadata": {},
                "source": src.splitlines(keepends=True),
            })
        else:
            cells.append({
                "cell_type": "code",
                "execution_count": None,
                "metadata": {},
                "outputs": [],
                "source": src.splitlines(keepends=True),
            })
    return {
        "cells": cells,
        "metadata": {
            "kernelspec": {
                "display_name": "Python 3",
                "language": "python",
                "name": "python3",
            },
            "language_info": {
                "name": "python",
                "version": "3.14",
            },
        },
        "nbformat": 4,
        "nbformat_minor": 5,
    }


def main() -> None:
    nb = make_notebook()
    out = Path(__file__).resolve().parent / "demo_rag_vs_gxp.ipynb"
    out.write_text(json.dumps(nb, indent=1), encoding="utf-8")
    print(f"Wrote {out} ({len(nb['cells'])} cells)")


if __name__ == "__main__":
    main()
