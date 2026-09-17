from copy import deepcopy
from typing import Dict, List, Optional

from agents.models import Blueprint, PaperState, Question, QuestionSlot

from .text_utils import normalize_question_type


# ============================================================
# NORMALIZED DISTRIBUTIONS
# ============================================================

def normalized_type_distribution(
    blueprint: Blueprint
) -> Dict[str, float]:

    result: Dict[str, float] = {}

    for (
        question_type,
        percentage
    ) in blueprint.question_type_distribution.items():

        normalized = normalize_question_type(
            question_type
        )

        result[normalized] = (
            result.get(normalized, 0.0)
            + float(percentage)
        )

    return result


# ============================================================
# MARK CALCULATIONS
# ============================================================

def remaining_marks(
    paper: PaperState,
    blueprint: Blueprint
) -> int:

    return max(
        0,
        blueprint.total_marks
        - paper.marks_used
    )


def remaining_type_marks(
    paper: PaperState,
    blueprint: Blueprint
) -> Dict[str, float]:

    distribution = (
        normalized_type_distribution(
            blueprint
        )
    )

    result = {
        key: float(
            blueprint.total_marks
            * percentage
        )
        for (
            key,
            percentage
        ) in distribution.items()
    }

    for question in paper.selected_questions:

        question_type = (
            normalize_question_type(
                question.question_type
            )
        )

        if question_type in result:

            result[question_type] -= (
                question.marks
            )

    for key in result:

        result[key] = max(
            0.0,
            result[key]
        )

    return result


def remaining_topic_marks(
    paper: PaperState,
    blueprint: Blueprint
) -> Dict[str, float]:

    result = {
        str(topic).strip().lower(): (
            blueprint.total_marks
            * float(percentage)
        )
        for (
            topic,
            percentage
        ) in blueprint.topic_distribution.items()
    }

    for question in paper.selected_questions:

        topic = (
            str(question.topic)
            .strip()
            .lower()
        )

        if topic in result:

            result[topic] -= (
                question.marks
            )

    for topic in result:

        result[topic] = max(
            0.0,
            result[topic]
        )

    return result


# ============================================================
# SIMULATION
# ============================================================

def simulate_add(
    paper: PaperState,
    question: Question
) -> PaperState:

    simulated = deepcopy(
        paper
    )

    simulated.selected_questions.append(
        question
    )

    simulated.marks_used += (
        question.marks
    )

    simulated.step += 1

    return simulated


# ============================================================
# HARD CONSTRAINTS
# ============================================================

def hard_constraint_check(
    paper: PaperState,
    blueprint: Blueprint
) -> List[str]:

    errors: List[str] = []

    if (
        paper.marks_used
        > blueprint.total_marks
    ):

        errors.append(
            "Paper exceeds total marks."
        )

    ids = [
        q.id
        for q in paper.selected_questions
    ]

    if len(ids) != len(set(ids)):

        errors.append(
            "Duplicate questions selected."
        )

    for constraint in blueprint.hard_constraints:

        text = constraint.lower()

        if "no duplicate" in text:

            if len(ids) != len(set(ids)):

                errors.append(
                    "Hard constraint violated: "
                    "no duplicate questions."
                )

    return errors


# ============================================================
# TRADEOFF LOGIC
# PRESERVED
# ============================================================

def topic_deviation(
    paper: PaperState,
    blueprint: Blueprint
) -> float:

    remaining = (
        remaining_topic_marks(
            paper,
            blueprint
        )
    )

    deviation = 0.0

    for value in remaining.values():

        deviation += abs(value)

    return deviation


def type_deviation(
    paper: PaperState,
    blueprint: Blueprint
) -> float:

    remaining = (
        remaining_type_marks(
            paper,
            blueprint
        )
    )

    deviation = 0.0

    for value in remaining.values():

        deviation += abs(value)

    return deviation


def future_feasibility(
    paper: PaperState,
    blueprint: Blueprint,
    question_bank: List[Question]
) -> float:

    marks_left = (
        remaining_marks(
            paper,
            blueprint
        )
    )

    if marks_left == 0:

        return 0.0

    available_marks = 0

    selected_ids = {
        q.id
        for q in paper.selected_questions
    }

    for question in question_bank:

        if question.id in selected_ids:
            continue

        if question.marks <= marks_left:

            available_marks += (
                question.marks
            )

    if available_marks == 0:

        return 1000.0

    return abs(
        marks_left
        - available_marks
    )


def scarcity_penalty(
    question: Question,
    paper: PaperState,
    blueprint: Blueprint,
    question_bank: List[Question]
) -> float:

    penalty = 0.0

    remaining_types = (
        remaining_type_marks(
            paper,
            blueprint
        )
    )

    qtype = normalize_question_type(
        question.question_type
    )

    selected_ids = {
        x.id
        for x in paper.selected_questions
    }

    matching_type_count = sum(
        1
        for q in question_bank
        if (
            normalize_question_type(
                q.question_type
            ) == qtype
            and q.id not in selected_ids
        )
    )

    if matching_type_count <= 2:

        penalty -= 2.0

    if qtype in remaining_types:

        if (
            remaining_types[qtype]
            >= question.marks
        ):

            penalty -= 1.0

    return penalty


def question_cost(
    question: Question,
    paper: PaperState,
    blueprint: Blueprint,
    question_bank: List[Question]
) -> float:

    marks_left = (
        remaining_marks(
            paper,
            blueprint
        )
    )

    mark_distance = abs(
        marks_left
        - question.marks
    )

    cost = float(
        mark_distance
    )

    topic_remaining = (
        remaining_topic_marks(
            paper,
            blueprint
        )
    )

    question_topic = (
        str(question.topic)
        .strip()
        .lower()
    )

    if question_topic in topic_remaining:

        if (
            topic_remaining[
                question_topic
            ]
            >= question.marks
        ):

            cost -= 2.0

    difficulty_remaining = (
        blueprint.difficulty_distribution
    )

    difficulty = str(
        question.difficulty
    ).lower()

    if hasattr(
        difficulty_remaining,
        difficulty
    ):

        expected = getattr(
            difficulty_remaining,
            difficulty
        )

        if expected > 0:

            cost -= 1.0

    type_remaining = (
        remaining_type_marks(
            paper,
            blueprint
        )
    )

    qtype = normalize_question_type(
        question.question_type
    )

    if qtype in type_remaining:

        if (
            type_remaining[qtype]
            >= question.marks
        ):

            cost -= 2.0

    cost += scarcity_penalty(
        question,
        paper,
        blueprint,
        question_bank
    )

    return cost


# ============================================================
# STRICT SLOT MATCHING
# ============================================================

def question_matches_slot(
    question: Question,
    slot: QuestionSlot
) -> bool:

    question_topic = (
        str(question.topic)
        .strip()
        .lower()
    )

    slot_topic = (
        str(slot.topic)
        .strip()
        .lower()
    )

    question_difficulty = (
        str(question.difficulty)
        .strip()
        .lower()
    )

    slot_difficulty = (
        str(slot.difficulty)
        .strip()
        .lower()
    )

    question_type = (
        normalize_question_type(
            question.question_type
        )
    )

    slot_type = (
        normalize_question_type(
            slot.question_type
        )
    )

    return (
        question_topic == slot_topic
        and question_difficulty == slot_difficulty
        and question_type == slot_type
        and question.marks == slot.marks
    )


# ============================================================
# PART 1
# STRICT CANDIDATE SELECTION
# ============================================================

def get_candidates(
    paper: PaperState,
    blueprint: Blueprint,
    question_bank: List[Question],
    current_slot: Optional[QuestionSlot] = None
) -> List[Question]:

    selected_ids = {
        q.id
        for q in paper.selected_questions
    }

    marks_left = (
        remaining_marks(
            paper,
            blueprint
        )
    )

    candidates: List[Question] = []

    for question in question_bank:

        if question.id in selected_ids:
            continue

        if question.marks > marks_left:
            continue

        if current_slot is not None:

            if not question_matches_slot(
                question,
                current_slot
            ):

                continue

        simulated = simulate_add(
            paper,
            question
        )

        hard_errors = (
            hard_constraint_check(
                simulated,
                blueprint
            )
        )

        if hard_errors:
            continue

        candidates.append(
            question
        )

    # Existing tradeoff-cost logic remains the
    # optimizer among valid exact-slot candidates.
    candidates.sort(
        key=lambda q: question_cost(
            q,
            paper,
            blueprint,
            question_bank
        )
    )

    return candidates