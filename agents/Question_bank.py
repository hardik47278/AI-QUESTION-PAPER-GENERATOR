import json
from copy import deepcopy
from typing import Any, Dict, List

from pydantic import ValidationError

from agents.models import Question

from .text_utils import normalize_question_type, normalize_options


# ============================================================
# QUESTION NORMALIZATION
# ============================================================

def normalize_question(question_data: Dict[str, Any]) -> Question:

    question_copy = deepcopy(
        question_data
    )

    if (
        "question" not in question_copy
        and "text" in question_copy
    ):

        question_copy["question"] = (
            question_copy["text"]
        )

    if (
        "correct_answer" not in question_copy
        and "answer" in question_copy
    ):

        question_copy["correct_answer"] = (
            question_copy["answer"]
        )

    if (
        "question_type" not in question_copy
        and "type" in question_copy
    ):

        question_copy["question_type"] = (
            question_copy["type"]
        )

    question_copy.setdefault(
        "question_type",
        ""
    )

    question_copy.setdefault(
        "marks",
        0
    )

    question_copy.setdefault(
        "topic",
        "General"
    )

    question_copy.setdefault(
        "difficulty",
        "medium"
    )

    question_copy.setdefault(
        "options",
        None
    )

    question_copy.setdefault(
        "correct_answer",
        None
    )

    question_copy.setdefault(
        "explanation",
        None
    )

    question_copy["question_type"] = (
        normalize_question_type(
            question_copy.get(
                "question_type",
                ""
            )
        )
    )

    question_copy["options"] = (
        normalize_options(
            question_copy.get("options")
        )
    )

    try:

        question_copy["marks"] = int(
            question_copy.get(
                "marks",
                0
            )
        )

    except (
        TypeError,
        ValueError
    ):

        question_copy["marks"] = 0

    return Question(
        **question_copy
    )


# ============================================================
# QUESTION BANK
# ============================================================

def load_question_bank(path: str) -> List[Question]:

    with open(
        path,
        "r",
        encoding="utf-8"
    ) as file:

        data = json.load(file)

    if isinstance(data, dict):

        if "questions" in data:

            data = data["questions"]

        else:

            data = list(
                data.values()
            )

    if not isinstance(data, list):

        raise ValueError(
            "Question bank must contain a list of questions."
        )

    questions: List[Question] = []

    for item in data:

        try:

            questions.append(
                normalize_question(
                    item
                )
            )

        except ValidationError as error:

            print(
                "Skipping invalid question:",
                error
            )

        except Exception as error:

            print(
                "Skipping invalid question:",
                error
            )

    print(
        f"Loaded {len(questions)} valid questions "
        f"from question bank."
    )

    if not questions:

        raise ValueError(
            "Question bank contains no valid questions."
        )

    return questions


# ============================================================
# SECTION
# ============================================================

def section_for_question_type(
    question_type: str
) -> str:

    normalized = normalize_question_type(
        question_type
    )

    if normalized == "mcq":
        return "MCQ"

    if normalized == "short":
        return "Short Answer"

    if normalized == "long":
        return "Long Answer"

    return str(
        question_type
    ).title()