"""
Small end-to-end runner for the question-paper pipeline.

Usage:
    python run.py
"""

from pathlib import Path
from pipeline import build_graph


def main():

    graph = build_graph()

    config = {
        "configurable": {
            "thread_id": "run-1"
        }
    }

    project_dir = Path(__file__).resolve().parent

    question_bank_path = (
        project_dir / "agents" / "question_bank.json"
    )

    initial_state = {
        "teacher_request": (
            "Create a 40 mark paper covering Algebra and Geometry, "
            "mostly medium difficulty, mix of MCQ and short answer questions."
        ),
        "question_bank_path": str(question_bank_path),
    }

    print(
        "QUESTION BANK:",
        question_bank_path
    )

    print(
        "EXISTS:",
        question_bank_path.exists()
    )

    result = graph.invoke(
        initial_state,
        config
    )

    print(
        "status:",
        result.get("status")
    )

    print(
        "pdf_path:",
        result.get("pdf_path")
    )

    print(
        "error:",
        result.get("error")
    )

    if "__interrupt__" in result:

        print(
            "STALLED ON INTERRUPT:",
            result["__interrupt__"]
        )


if __name__ == "__main__":
    main()