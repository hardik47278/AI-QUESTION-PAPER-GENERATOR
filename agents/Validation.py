from typing import Dict, List, Optional

from agents.models import Blueprint, PaperState, Question, QuestionSlot

from .text_utils import normalize_question_type
from .candidate_selection import remaining_marks


# ============================================================
# PART 2
# EXACT GENERATED QUESTION VALIDATION
# ============================================================

def validate_generated_question(
    question: Question,
    paper: PaperState,
    blueprint: Blueprint,
    slot: Optional[QuestionSlot] = None
) -> List[str]:

    errors: List[str] = []

    if not question.id:

        errors.append(
            "Question ID is empty."
        )

    if not question.question.strip():

        errors.append(
            "Question text is empty."
        )

    # ----------------------------------------------------
    # DUPLICATE QUESTION TEXT CHECK
    # ----------------------------------------------------

    new_question_text = (
        str(question.question)
        .strip()
        .lower()
    )

    for existing in paper.selected_questions:

        existing_text = (
            str(existing.question)
            .strip()
            .lower()
        )

        if new_question_text == existing_text:

            errors.append(
                "Duplicate question text detected."
            )

            break

    # ----------------------------------------------------
    # MARK VALIDATION
    # ----------------------------------------------------

    if question.marks <= 0:

        errors.append(
            "Question marks must be positive."
        )

    remaining = (
        remaining_marks(
            paper,
            blueprint
        )
    )

    if question.marks > remaining:

        errors.append(
            "Question exceeds remaining marks."
        )

    # ----------------------------------------------------
    # QUESTION TYPE VALIDATION
    # ----------------------------------------------------

    qtype = normalize_question_type(
        question.question_type
    )

    if qtype not in {
        "mcq",
        "short",
        "long"
    }:

        errors.append(
            f"Unsupported question type: {qtype}"
        )

    # ----------------------------------------------------
    # EXACT SLOT VALIDATION
    # ----------------------------------------------------

    if slot is not None:

        if (
            str(question.topic).strip().lower()
            != str(slot.topic).strip().lower()
        ):

            errors.append(
                "Generated question topic does not "
                "match the allocated slot."
            )

        if (
            str(question.difficulty).strip().lower()
            != str(slot.difficulty).strip().lower()
        ):

            errors.append(
                "Generated question difficulty does not "
                "match the allocated slot."
            )

        if (
            qtype
            != normalize_question_type(
                slot.question_type
            )
        ):

            errors.append(
                "Generated question type does not "
                "match the allocated slot."
            )

        if question.marks != slot.marks:

            errors.append(
                "Generated question marks do not "
                "match the allocated slot."
            )

    # ----------------------------------------------------
    # MCQ VALIDATION
    # ----------------------------------------------------

    if qtype == "mcq":

        if not question.options:

            errors.append(
                "MCQ must contain options."
            )

        elif len(question.options) != 4:

            errors.append(
                "MCQ must contain exactly four options."
            )

        if not question.correct_answer:

            errors.append(
                "MCQ must contain a correct answer."
            )

        elif question.options:

            answer = (
                str(
                    question.correct_answer
                )
                .strip()
                .upper()
            )

            valid_answers = {
                "A",
                "B",
                "C",
                "D"
            }

            if answer not in valid_answers:

                errors.append(
                    "MCQ correct_answer must be "
                    "A, B, C, or D."
                )

    return errors


# ============================================================
# FINAL VALIDATION
# ============================================================

def validate_final_paper(
    final_paper_state: PaperState,
    blueprint: Blueprint
) -> List[str]:

    final_errors = []

    if (
        final_paper_state.marks_used
        != blueprint.total_marks
    ):

        final_errors.append(
            "Final paper does not have exact target marks."
        )

    ids = [
        q.id
        for q in final_paper_state.selected_questions
    ]

    if len(ids) != len(set(ids)):

        final_errors.append(
            "Final paper contains duplicate question IDs."
        )

    topic_totals: Dict[str, int] = {}
    difficulty_totals: Dict[str, int] = {}
    type_totals: Dict[str, int] = {}

    for question in final_paper_state.selected_questions:

        topic = (
            str(question.topic)
            .strip()
            .lower()
        )

        difficulty = (
            str(question.difficulty)
            .strip()
            .lower()
        )

        qtype = normalize_question_type(
            question.question_type
        )

        topic_totals[topic] = (
            topic_totals.get(topic, 0)
            + question.marks
        )

        difficulty_totals[difficulty] = (
            difficulty_totals.get(
                difficulty,
                0
            )
            + question.marks
        )

        type_totals[qtype] = (
            type_totals.get(qtype, 0)
            + question.marks
        )

    expected_topics = {
        str(topic).strip().lower():
            int(round(
                blueprint.total_marks
                * float(percentage)
            ))
        for topic, percentage
        in blueprint.topic_distribution.items()
        if float(percentage) > 0
    }

    expected_difficulties = {
        str(difficulty).strip().lower():
            int(round(
                blueprint.total_marks
                * float(percentage)
            ))
        for difficulty, percentage
        in blueprint.difficulty_distribution.model_dump().items()
        if float(percentage) > 0
    }

    expected_types = {
        normalize_question_type(
            question_type
        ):
            int(round(
                blueprint.total_marks
                * float(percentage)
            ))
        for question_type, percentage
        in blueprint.question_type_distribution.items()
        if float(percentage) > 0
    }

    for topic, expected in expected_topics.items():

        actual = topic_totals.get(
            topic,
            0
        )

        if actual != expected:

            final_errors.append(
                f"Topic allocation mismatch for "
                f"{topic}: {actual} != {expected}"
            )

    for difficulty, expected in expected_difficulties.items():

        actual = difficulty_totals.get(
            difficulty,
            0
        )

        if actual != expected:

            final_errors.append(
                f"Difficulty allocation mismatch for "
                f"{difficulty}: {actual} != {expected}"
            )

    for qtype, expected in expected_types.items():

        actual = type_totals.get(
            qtype,
            0
        )

        if actual != expected:

            final_errors.append(
                f"Question type allocation mismatch for "
                f"{qtype}: {actual} != {expected}"
            )

    return final_errors