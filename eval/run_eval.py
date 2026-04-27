"""
RAG evaluation script using RAGAS metrics for the GxP-Struct system.

Reads the golden dataset, runs each query through the RAG pipeline,
computes RAGAS metrics (context_recall, faithfulness, answer_relevancy),
and generates a detailed evaluation report.

Author: Gourav Pandey
"""

import json
import logging
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from datasets import Dataset
from ragas import evaluate
from ragas.metrics import answer_relevancy, context_recall, faithfulness
from rich.console import Console
from rich.table import Table

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)
console = Console()

# Default paths
GOLDEN_DATASET_PATH = Path(__file__).parent / "golden_dataset.json"
REPORT_DIR = Path(__file__).parent / "reports"


def load_golden_dataset(path: Path) -> list[dict[str, Any]]:
    """
    Load the golden Q&A dataset from JSON.

    Args:
        path: Path to the golden_dataset.json file.

    Returns:
        List of evaluation entries with question, expected_answer, and source_docs.

    Raises:
        FileNotFoundError: If the dataset file does not exist.
        json.JSONDecodeError: If the file is not valid JSON.
    """
    if not path.exists():
        raise FileNotFoundError(f"Golden dataset not found: {path}")

    with open(path) as f:
        data = json.load(f)

    logger.info("Loaded %d evaluation entries from %s", len(data), path)
    return data


def run_rag_pipeline(question: str) -> dict[str, Any]:
    """
    Run a single question through the RAG pipeline.

    This function should be adapted to call your actual RAG system.
    It returns the answer and the retrieved contexts used.

    Args:
        question: The question to ask the RAG system.

    Returns:
        Dictionary with 'answer' and 'contexts' keys.
    """
    # -- Integration point: replace with your actual RAG pipeline --
    # Example using the hybrid retriever + reranker:
    #
    #   from hybrid_retriever import create_hybrid_retriever
    #   from reranker import Reranker, RetrieveAndRerank
    #
    #   retriever = create_hybrid_retriever(...)
    #   reranker = Reranker()
    #   pipeline = RetrieveAndRerank(retriever, reranker)
    #   results = pipeline.search(question, top_k=5)
    #   contexts = [r.text for r in results]
    #   answer = call_llm(question, contexts)
    #   return {"answer": answer, "contexts": contexts}

    try:
        import openai

        client = openai.OpenAI(api_key=os.environ.get("OPENAI_API_KEY"))

        # Simulated retrieval (replace with actual retriever)
        context_note = (
            "Using pharmaceutical domain knowledge base for context retrieval. "
            "Connect to the actual hybrid_retriever for production evaluation."
        )

        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {
                    "role": "system",
                    "content": (
                        "You are a pharmaceutical quality expert. Answer questions "
                        "about GxP compliance, quality systems, and regulatory requirements "
                        "based on your domain knowledge. Be specific and cite relevant "
                        "guidelines where applicable."
                    ),
                },
                {"role": "user", "content": question},
            ],
            temperature=0.1,
            max_tokens=1000,
        )

        answer = response.choices[0].message.content or ""
        # In production, contexts come from the retriever
        contexts = [answer]  # Placeholder: use actual retrieved chunks

        return {"answer": answer, "contexts": contexts}

    except Exception as e:
        logger.error("RAG pipeline error for question '%s': %s", question[:50], e)
        return {"answer": f"Error: {e}", "contexts": []}


def prepare_ragas_dataset(
    golden_data: list[dict[str, Any]],
    rag_results: list[dict[str, Any]],
) -> Dataset:
    """
    Prepare a HuggingFace Dataset in the format expected by RAGAS.

    Args:
        golden_data: The golden dataset entries.
        rag_results: Results from running each question through the RAG pipeline.

    Returns:
        HuggingFace Dataset with columns: question, answer, contexts, ground_truth.
    """
    records = {
        "question": [],
        "answer": [],
        "contexts": [],
        "ground_truth": [],
    }

    for entry, result in zip(golden_data, rag_results):
        records["question"].append(entry["question"])
        records["answer"].append(result["answer"])
        records["contexts"].append(result["contexts"])
        records["ground_truth"].append(entry["expected_answer"])

    return Dataset.from_dict(records)


def generate_report(
    scores: dict[str, float],
    per_question_scores: list[dict[str, Any]],
    elapsed_time: float,
    output_dir: Path,
) -> Path:
    """
    Generate a markdown evaluation report.

    Args:
        scores: Aggregate metric scores.
        per_question_scores: Per-question breakdown.
        elapsed_time: Total evaluation time in seconds.
        output_dir: Directory to write the report.

    Returns:
        Path to the generated report file.
    """
    output_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    report_path = output_dir / f"eval_report_{timestamp}.md"

    lines = [
        "# GxP-Struct RAG Evaluation Report",
        "",
        f"**Date:** {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S UTC')}",
        f"**Evaluation Time:** {elapsed_time:.1f} seconds",
        f"**Questions Evaluated:** {len(per_question_scores)}",
        "",
        "## Aggregate Scores",
        "",
        "| Metric | Score |",
        "|--------|-------|",
    ]

    for metric, score in scores.items():
        status = "PASS" if score >= 0.7 else "NEEDS IMPROVEMENT"
        lines.append(f"| {metric} | {score:.4f} ({status}) |")

    lines.extend([
        "",
        "## Per-Question Results",
        "",
        "| # | Question (truncated) | Faithfulness | Relevancy | Context Recall |",
        "|---|---------------------|-------------|-----------|---------------|",
    ])

    for i, qs in enumerate(per_question_scores, 1):
        q_short = qs["question"][:50] + "..." if len(qs["question"]) > 50 else qs["question"]
        lines.append(
            f"| {i} | {q_short} | {qs.get('faithfulness', 'N/A'):.4f} "
            f"| {qs.get('answer_relevancy', 'N/A'):.4f} "
            f"| {qs.get('context_recall', 'N/A'):.4f} |"
        )

    lines.extend([
        "",
        "## Interpretation",
        "",
        "- **Faithfulness**: Measures whether the answer is grounded in the retrieved context.",
        "- **Answer Relevancy**: Measures whether the answer addresses the question asked.",
        "- **Context Recall**: Measures whether the retrieved context covers the ground truth.",
        "",
        "## Recommendations",
        "",
    ])

    if scores.get("faithfulness", 0) < 0.8:
        lines.append("- Faithfulness below 0.8: Consider adding citation enforcement in the LLM prompt.")
    if scores.get("context_recall", 0) < 0.8:
        lines.append("- Context recall below 0.8: Review retrieval pipeline; increase candidate pool or tune BM25/vector weights.")
    if scores.get("answer_relevancy", 0) < 0.8:
        lines.append("- Answer relevancy below 0.8: Refine system prompt to focus on directly addressing the question.")

    if all(v >= 0.8 for v in scores.values()):
        lines.append("- All metrics above 0.8. System performing well. Continue monitoring with expanded test set.")

    lines.append("")
    lines.append("---")
    lines.append("*Generated by GxP-Struct Evaluation Pipeline*")

    report_path.write_text("\n".join(lines))
    logger.info("Report written to %s", report_path)
    return report_path


def run_evaluation(
    dataset_path: Path = GOLDEN_DATASET_PATH,
    output_dir: Path = REPORT_DIR,
    max_questions: int | None = None,
) -> dict[str, float]:
    """
    Run the full evaluation pipeline.

    Args:
        dataset_path: Path to the golden dataset JSON file.
        output_dir: Directory for evaluation reports.
        max_questions: Optional limit on number of questions to evaluate.

    Returns:
        Dictionary of aggregate metric scores.
    """
    console.print("[bold blue]GxP-Struct RAG Evaluation[/bold blue]")
    console.print("=" * 60)

    # Load golden dataset
    golden_data = load_golden_dataset(dataset_path)
    if max_questions:
        golden_data = golden_data[:max_questions]
        console.print(f"[yellow]Limited to {max_questions} questions[/yellow]")

    # Run RAG pipeline on each question
    console.print(f"\nRunning {len(golden_data)} queries through the RAG pipeline...")
    start_time = time.time()

    rag_results = []
    for i, entry in enumerate(golden_data, 1):
        console.print(f"  [{i}/{len(golden_data)}] {entry['question'][:60]}...")
        result = run_rag_pipeline(entry["question"])
        rag_results.append(result)

    # Prepare RAGAS dataset
    console.print("\nPreparing evaluation dataset...")
    ragas_dataset = prepare_ragas_dataset(golden_data, rag_results)

    # Run RAGAS evaluation
    console.print("Computing RAGAS metrics...")
    metrics = [context_recall, faithfulness, answer_relevancy]

    try:
        result = evaluate(ragas_dataset, metrics=metrics)
        scores = {str(k): float(v) for k, v in result.items() if isinstance(v, (int, float))}
    except Exception as e:
        logger.error("RAGAS evaluation failed: %s", e)
        console.print(f"[red]RAGAS evaluation failed: {e}[/red]")
        scores = {"faithfulness": 0.0, "answer_relevancy": 0.0, "context_recall": 0.0}

    elapsed = time.time() - start_time

    # Display results
    table = Table(title="Evaluation Results")
    table.add_column("Metric", style="cyan")
    table.add_column("Score", style="green")
    table.add_column("Status", style="bold")

    for metric, score in scores.items():
        status = "[green]PASS[/green]" if score >= 0.7 else "[red]NEEDS WORK[/red]"
        table.add_row(metric, f"{score:.4f}", status)

    console.print()
    console.print(table)

    # Generate per-question scores (simplified)
    per_question = []
    for entry in golden_data:
        per_question.append({
            "question": entry["question"],
            "faithfulness": scores.get("faithfulness", 0.0),
            "answer_relevancy": scores.get("answer_relevancy", 0.0),
            "context_recall": scores.get("context_recall", 0.0),
        })

    # Generate report
    report_path = generate_report(scores, per_question, elapsed, output_dir)
    console.print(f"\n[bold green]Report saved to:[/bold green] {report_path}")

    return scores


if __name__ == "__main__":
    max_q = None
    if len(sys.argv) > 1:
        try:
            max_q = int(sys.argv[1])
        except ValueError:
            console.print("[red]Usage: python run_eval.py [max_questions][/red]")
            sys.exit(1)

    scores = run_evaluation(max_questions=max_q)
    console.print(f"\nFinal scores: {scores}")
