# RAG Pipeline Demo

A side-by-side teaching notebook that walks through every stage of a standard RAG pipeline (Word SOP → chunks → vectors → Pinecone → Claude) and contrasts it with the GxP-Struct deterministic rule engine on the same question.

## Prerequisites

- Python 3.10+ installed
- All dependencies installed via `python -m pip install ...` (see project root)
- A populated `.env` file at the project root with: `OPENAI_API_KEY`, `ANTHROPIC_API_KEY`, `PINECONE_API_KEY`, `PHOENIX_API_KEY`, `PHOENIX_COLLECTOR_ENDPOINT`
- A Pinecone serverless index named `gxp-struct-demo`, dimension `3072`, AWS `us-east-1`
- A Word SOP at `gxp-struct/Reference SOPs/Deviation SOP.docx` (or the notebook will fall back to `data/Deviation_SOP.md`)

## How to run

From the `gxp-struct/` folder:

```bash
python -m jupyter notebook demo_rag/demo_rag_vs_gxp.ipynb
```

Your browser will open the notebook. Press **Shift + Enter** in each cell, top to bottom.

## What it does, in 25 cells

1. Loads `.env`, verifies all four API keys are present
2. Enables Phoenix tracing (every step is recorded to your Phoenix Cloud workspace)
3. Reads the Word SOP, prints size + first 600 characters
4. Chunks the SOP, prints the first 3 chunks so you can see what they look like
5. Embeds one chunk and prints the first 10 numbers of the resulting 3,072-dim vector
6. Uploads all chunks to Pinecone (clears any prior demo run first)
7. Asks a question, prints the top-5 retrieved chunks with similarity scores
8. Sends chunks + question to Claude, prints the answer
9. Runs the same question 5 times to demonstrate variance
10. Runs the same question through the GxP-Struct rule engine 5 times — shows determinism + < 10ms latency
11. Side-by-side comparison
12. Phoenix trace inspection link
13. Optional cleanup cell

## Cost

About **$0.05** in API spend per full run (mostly OpenAI embeddings on first ingest; subsequent runs reuse the vectors).

## Regenerating the notebook

If you want to change the demo, edit `build_notebook.py` (the source of truth) and re-run:

```bash
python demo_rag/build_notebook.py
```

This regenerates `demo_rag_vs_gxp.ipynb` from the cell list in the script. Don't edit the `.ipynb` directly — your changes will be overwritten next time the script runs.
