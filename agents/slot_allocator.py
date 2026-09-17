from typing import Dict, List

from agents.models import Blueprint, Question, QuestionSlot

from .text_utils import normalize_question_type


# ============================================================
# EXPLICIT QUESTION SLOT ALLOCATION
# ============================================================

def build_question_slots(
    blueprint: Blueprint,
    question_bank: List[Question]
) -> List[QuestionSlot]:

    total_marks = int(
        blueprint.total_marks
    )

    topics = [
        str(topic).strip()
        for topic in blueprint.topic_distribution.keys()
    ]

    difficulties = [
        str(diff).strip()
        for diff in ["easy", "medium", "hard"]
        if float(
            getattr(
                blueprint.difficulty_distribution,
                diff,
                0.0
            )
        ) > 0
    ]

    question_types = [
        str(qtype).strip()
        for qtype in blueprint.question_type_distribution.keys()
        if float(
            blueprint.question_type_distribution[qtype]
        ) > 0
    ]

    # ---------------------------------------------------------
    # Calculate target marks
    # ---------------------------------------------------------

    def largest_remainder_allocation(
        distribution: Dict[str, float],
        total: int
    ) -> Dict[str, int]:

        raw = {
            key: float(value) * total
            for key, value in distribution.items()
            if float(value) > 0
        }

        result = {
            key: int(value)
            for key, value in raw.items()
        }

        remainder = total - sum(
            result.values()
        )

        ranked = sorted(
            raw.keys(),
            key=lambda key: (
                raw[key] - int(raw[key])
            ),
            reverse=True
        )

        for key in ranked[:remainder]:

            result[key] += 1

        return result

    topic_targets = (
        largest_remainder_allocation(
            blueprint.topic_distribution,
            total_marks
        )
    )

    difficulty_distribution = {
        "easy": float(
            getattr(
                blueprint.difficulty_distribution,
                "easy",
                0.0
            )
        ),
        "medium": float(
            getattr(
                blueprint.difficulty_distribution,
                "medium",
                0.0
            )
        ),
        "hard": float(
            getattr(
                blueprint.difficulty_distribution,
                "hard",
                0.0
            )
        )
    }

    difficulty_targets = (
        largest_remainder_allocation(
            difficulty_distribution,
            total_marks
        )
    )

    type_targets = (
        largest_remainder_allocation(
            blueprint.question_type_distribution,
            total_marks
        )
    )

    # ---------------------------------------------------------
    # Normalize type names
    # ---------------------------------------------------------

    def canonical_type(value: str) -> str:

        return normalize_question_type(
            value
        )

    # ---------------------------------------------------------
    # Available marks from actual bank
    # ---------------------------------------------------------

    bank_marks = sorted(
        {
            int(q.marks)
            for q in question_bank
            if int(q.marks) > 0
            and int(q.marks) <= total_marks
        }
    )

    if not bank_marks:

        bank_marks = [
            1,
            2,
            3,
            4,
            5,
            8,
            10
        ]

    mark_values = bank_marks

    # ---------------------------------------------------------
    # Count existing questions for each exact slot
    # ---------------------------------------------------------

    available_counts: Dict[tuple, int] = {}

    for question in question_bank:

        key = (
            str(question.topic).strip().lower(),
            str(question.difficulty).strip().lower(),
            canonical_type(
                question.question_type
            ),
            int(question.marks)
        )

        available_counts[key] = (
            available_counts.get(key, 0)
            + 1
        )

    # ---------------------------------------------------------
    # Build all possible slot shapes
    # ---------------------------------------------------------

    shapes = []

    for topic in topics:

        for difficulty in difficulties:

            for question_type in question_types:

                shape = (
                    topic,
                    difficulty,
                    question_type
                )

                shapes.append(shape)

    # ---------------------------------------------------------
    # DP state
    # ---------------------------------------------------------

    topic_index = {
        topic.lower(): index
        for index, topic in enumerate(topics)
    }

    difficulty_index = {
        difficulty.lower(): index
        for index, difficulty in enumerate(difficulties)
    }

    type_index = {
        canonical_type(qtype): index
        for index, qtype in enumerate(question_types)
    }

    target_topic_tuple = tuple(
        topic_targets.get(topic, 0)
        for topic in topics
    )

    target_difficulty_tuple = tuple(
        difficulty_targets.get(diff, 0)
        for diff in difficulties
    )

    target_type_tuple = tuple(
        type_targets.get(qtype, 0)
        for qtype in question_types
    )

    # ---------------------------------------------------------
    # Existing-bank support
    # ---------------------------------------------------------

    def shape_bank_count(
        topic: str,
        difficulty: str,
        question_type: str,
        marks: int
    ) -> int:

        return available_counts.get(
            (
                topic.strip().lower(),
                difficulty.strip().lower(),
                canonical_type(question_type),
                int(marks)
            ),
            0
        )

    # ---------------------------------------------------------
    # BOUNDED BEAM SEARCH
    # ---------------------------------------------------------

    beam_width = 300

    initial_state = (
        tuple(0 for _ in topics),
        tuple(0 for _ in difficulties),
        tuple(0 for _ in question_types),
        0
    )

    states = {
        initial_state: []
    }

    max_questions = total_marks

    # ---------------------------------------------------------
    # State scoring
    # ---------------------------------------------------------

    def state_score(item):

        state, slots = item

        used_topic, used_diff, used_type, used_total = state

        topic_error = sum(
            abs(
                used_topic[i]
                - target_topic_tuple[i]
            )
            for i in range(len(topics))
        )

        diff_error = sum(
            abs(
                used_diff[i]
                - target_difficulty_tuple[i]
            )
            for i in range(len(difficulties))
        )

        type_error = sum(
            abs(
                used_type[i]
                - target_type_tuple[i]
            )
            for i in range(len(question_types))
        )

        total_error = abs(
            used_total - total_marks
        )

        bank_support = sum(
            shape_bank_count(
                slot.topic,
                slot.difficulty,
                slot.question_type,
                slot.marks
            )
            for slot in slots
        )

        return (
            total_error * 1000
            + topic_error * 100
            + diff_error * 100
            + type_error * 100
            - bank_support
        )

    # ---------------------------------------------------------
    # Bounded search
    # ---------------------------------------------------------

    for _step in range(max_questions):

        next_states = {}

        for state, slot_list in states.items():

            used_topic, used_diff, used_type, used_total = state

            if used_total == total_marks:
                continue

            for (
                topic,
                difficulty,
                question_type
            ) in shapes:

                topic_i = topic_index[
                    topic.lower()
                ]

                diff_i = difficulty_index[
                    difficulty.lower()
                ]

                type_i = type_index[
                    canonical_type(question_type)
                ]

                remaining_topic = (
                    topic_targets.get(topic, 0)
                    - used_topic[topic_i]
                )

                remaining_diff = (
                    difficulty_targets.get(
                        difficulty,
                        0
                    )
                    - used_diff[diff_i]
                )

                remaining_type = (
                    type_targets.get(
                        question_type,
                        type_targets.get(
                            canonical_type(
                                question_type
                            ),
                            0
                        )
                    )
                    - used_type[type_i]
                )

                if remaining_topic <= 0:
                    continue

                if remaining_diff <= 0:
                    continue

                if remaining_type <= 0:
                    continue

                for marks in mark_values:

                    new_total = (
                        used_total + marks
                    )

                    if new_total > total_marks:
                        continue

                    if marks > remaining_topic:
                        continue

                    if marks > remaining_diff:
                        continue

                    if marks > remaining_type:
                        continue

                    new_topic = list(
                        used_topic
                    )

                    new_diff = list(
                        used_diff
                    )

                    new_type = list(
                        used_type
                    )

                    new_topic[topic_i] += marks
                    new_diff[diff_i] += marks
                    new_type[type_i] += marks

                    new_state = (
                        tuple(new_topic),
                        tuple(new_diff),
                        tuple(new_type),
                        new_total
                    )

                    new_slots = (
                        slot_list
                        + [
                            QuestionSlot(
                                topic=topic,
                                difficulty=difficulty,
                                question_type=question_type,
                                marks=marks
                            )
                        ]
                    )

                    existing = next_states.get(
                        new_state
                    )

                    if existing is None:

                        next_states[
                            new_state
                        ] = new_slots

                    else:

                        new_bank_score = sum(
                            shape_bank_count(
                                slot.topic,
                                slot.difficulty,
                                slot.question_type,
                                slot.marks
                            )
                            for slot in new_slots
                        )

                        existing_bank_score = sum(
                            shape_bank_count(
                                slot.topic,
                                slot.difficulty,
                                slot.question_type,
                                slot.marks
                            )
                            for slot in existing
                        )

                        if (
                            new_bank_score
                            > existing_bank_score
                        ):

                            next_states[
                                new_state
                            ] = new_slots

        if not next_states:
            break

        ranked = sorted(
            next_states.items(),
            key=state_score
        )

        states = dict(
            ranked[:beam_width]
        )

        # ---------------------------------------------------------
        # Exact solution found
        # ---------------------------------------------------------

        exact_state = (
            target_topic_tuple,
            target_difficulty_tuple,
            target_type_tuple,
            total_marks
        )

        if exact_state in states:

            result = states[
                exact_state
            ]

            result.sort(
                key=lambda slot: (
                    0
                    if shape_bank_count(
                        slot.topic,
                        slot.difficulty,
                        slot.question_type,
                        slot.marks
                    ) > 0
                    else 1
                )
            )

            print(
                f"Built {len(result)} exact question slots.",
                flush=True
            )

            print(
                "Slot allocation:",
                [
                    (
                        slot.topic,
                        slot.difficulty,
                        slot.question_type,
                        slot.marks
                    )
                    for slot in result
                ],
                flush=True
            )

            return result

    # ---------------------------------------------------------
    # Exact allocation not found
    # ---------------------------------------------------------

    print(
        "WARNING: Exact slot allocation could not be constructed "
        "from the current blueprint and mark values.",
        flush=True
    )

    print(
        f"Target topic marks: {topic_targets}",
        flush=True
    )

    print(
        f"Target difficulty marks: {difficulty_targets}",
        flush=True
    )

    print(
        f"Target type marks: {type_targets}",
        flush=True
    )

    if states:

        best_state, best_slots = min(
            states.items(),
            key=state_score
        )

        print(
            "Returning closest bounded allocation so that "
            "the generation layer can report/resolve the conflict.",
            flush=True
        )

        return best_slots

    return []