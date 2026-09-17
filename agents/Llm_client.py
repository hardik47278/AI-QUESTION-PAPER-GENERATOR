import json
import os
from typing import List, Optional

from openai import OpenAI

from agents.models import (
    Blueprint,
    GeneratedQuestion,
    PaperState,
    Question,
    QuestionSlot,
    TradeoffDecision,
)

from .text_utils import (
    normalize_options,
    normalize_question_type,
    parse_model_json,
)
from .candidate_selection import (
    remaining_marks,
    remaining_topic_marks,
    remaining_type_marks,
)


MAX_LLM_RETRIES = 3


class LLMClient:

    def __init__(
        self,
        api_key: Optional[str] = None,
        model: Optional[str] = None
    ):

        api_key = (
            api_key
            or os.getenv("OPENAI_API_KEY")
        )

        if not api_key:

            raise RuntimeError(
                "OPENAI_API_KEY is not set in the environment."
            )

        self.client = OpenAI(
            api_key=api_key
        )

        self.model = (
            model
            or os.getenv(
                "OPENAI_MODEL",
                "gpt-4o-mini"
            )
        )

        print(
            f"PaperGenerationAgent using OpenAI model: {self.model}"
        )

    # ========================================================
    # STRUCTURED LLM CALL
    # ========================================================

    def _structured_call(
        self,
        system: str,
        user: str,
        response_model,
        max_completion_tokens: int = 512
    ):

        last_error = None

        for attempt in range(
            1,
            MAX_LLM_RETRIES + 1
        ):

            print(
                f"\nSTRUCTURED LLM CALL "
                f"(attempt {attempt}/{MAX_LLM_RETRIES})"
            )

            retry_instruction = ""

            if attempt > 1:

                retry_instruction = """
IMPORTANT RETRY INSTRUCTION:

Your previous response could not be parsed.

Return ONLY ONE valid JSON object.

Do NOT use:
- Markdown
- ```json
- explanations
- comments
- trailing commas
- single quotes
- LaTeX backslashes
- extra text before or after JSON

Use double quotes around every JSON key and string.

The response must begin with { and end with }.
"""

            final_user_prompt = (
                user
                + retry_instruction
                + """

FINAL OUTPUT REQUIREMENT:

Return ONLY valid JSON.

No markdown.
No code fences.
No explanation.
No comments.

Every JSON string must use double quotes.
"""
            )

            try:

                response = (
                    self.client
                    .chat
                    .completions
                    .create(
                        model=self.model,
                        messages=[
                            {
                                "role": "system",
                                "content": system
                            },
                            {
                                "role": "user",
                                "content": final_user_prompt
                            }
                        ],
                        max_tokens=max_completion_tokens,
                        temperature=0.2
                    )
                )

                content = None

                if response.choices:

                    message = (
                        response.choices[0].message
                    )

                    if message is not None:
                        content = message.content

                if not content:

                    last_error = RuntimeError(
                        "OpenAI returned empty content."
                    )

                    continue

                content = str(
                    content
                ).strip()

                parsed_json = parse_model_json(
                    content
                )

                if isinstance(
                    parsed_json,
                    dict
                ):

                    if (
                        "question" not in parsed_json
                        and "text" in parsed_json
                    ):

                        parsed_json["question"] = (
                            parsed_json["text"]
                        )

                    if (
                        "correct_answer"
                        not in parsed_json
                        and "answer" in parsed_json
                    ):

                        parsed_json["correct_answer"] = (
                            parsed_json["answer"]
                        )

                    if (
                        "question_type"
                        not in parsed_json
                        and "type" in parsed_json
                    ):

                        parsed_json["question_type"] = (
                            parsed_json["type"]
                        )

                    if "options" in parsed_json:

                        parsed_json["options"] = (
                            normalize_options(
                                parsed_json["options"]
                            )
                        )

                    if "question_type" in parsed_json:

                        parsed_json["question_type"] = (
                            normalize_question_type(
                                parsed_json[
                                    "question_type"
                                ]
                            )
                        )

                return response_model(
                    **parsed_json
                )

            except Exception as error:

                last_error = error

                print(
                    "\nSTRUCTURED LLM CALL FAILED "
                    f"(attempt {attempt}/{MAX_LLM_RETRIES})"
                )

                print(
                    f"ERROR: {error}"
                )

        raise RuntimeError(
            "OpenAI structured call failed after "
            f"{MAX_LLM_RETRIES} attempts: "
            f"{last_error}"
        )

    # ========================================================
    # PART 4
    # AI GENERATION FOR EXACT SLOT
    # ========================================================

    def generate_question(
        self,
        blueprint: Blueprint,
        paper: PaperState,
        slot: Optional[QuestionSlot] = None,
        reason: str = ""
    ) -> Question:

        # Existing questions are passed to the LLM
        # so it does not generate duplicates.
        existing_questions = [
            q.question
            for q in paper.selected_questions
        ]

        marks_left = (
            remaining_marks(
                paper,
                blueprint
            )
        )

        remaining_topics = (
            remaining_topic_marks(
                paper,
                blueprint
            )
        )

        remaining_types = (
            remaining_type_marks(
                paper,
                blueprint
            )
        )

        remaining_ids = [
            q.id
            for q in paper.selected_questions
        ]

        if slot is not None:

            slot_instruction = f"""
EXACT REQUIRED SLOT:

Topic: {slot.topic}
Difficulty: {slot.difficulty}
Question Type: {slot.question_type}
Marks: {slot.marks}

These four fields are HARD CONSTRAINTS.

You MUST generate exactly this slot.

Do NOT change:
- topic
- difficulty
- question_type
- marks

Do NOT generate a different mark value.
Do NOT generate a different question type.
Do NOT generate a different difficulty.
Do NOT generate a different topic.
"""

        else:

            slot_instruction = """
No explicit slot was provided.

Stay within the remaining blueprint constraints.
"""

        system = f"""
You are an expert examination-question generator.

Generate exactly ONE high-quality question.

{slot_instruction}

Your output will be parsed by Python.

Return ONLY a valid JSON object.

Do not return markdown.
Do not return ```json.
Do not return explanations outside JSON.

JSON schema:

{{
  "id": "unique-id",
  "question": "question text",
  "question_type": "mcq | short | long",
  "marks": 2,
  "topic": "Algebra",
  "difficulty": "easy | medium | hard",
  "options": ["A. option", "B. option", "C. option", "D. option"],
  "correct_answer": "A",
  "explanation": "brief explanation"
}}

For short and long questions, options may be null.

For MCQ:

- provide exactly four options
- options must be strings
- correct_answer must identify one option
- do not use option objects

IMPORTANT:

Do NOT use LaTeX.

Do NOT use backslash characters anywhere.

Do NOT use LaTeX commands such as:
frac
sqrt
Rightarrow

Use plain text mathematical notation.

Example:

x^2 + 5x + 6 = 0

instead of LaTeX.

Every JSON key must use double quotes.
Every string must use double quotes.
No trailing commas.

IMPORTANT DUPLICATE PREVENTION:

The following questions are already present in the paper:

{json.dumps(existing_questions, indent=2, ensure_ascii=False)}

Do NOT generate a question that is identical or substantially similar
to any question in this list.

Generate a NEW and DISTINCT question.

The generated question must be meaningfully different from all
existing questions while still satisfying the exact slot.
"""

        user = f"""
Generate one question for this examination blueprint.

{slot_instruction}

TOTAL MARKS:

{blueprint.total_marks}

CURRENT MARKS USED:

{paper.marks_used}

REMAINING MARKS:

{marks_left}

REMAINING TOPIC MARKS:

{json.dumps(
    remaining_topics,
    indent=2
)}

REMAINING QUESTION TYPE MARKS:

{json.dumps(
    remaining_types,
    indent=2
)}

DIFFICULTY DISTRIBUTION:

{json.dumps(
    blueprint.difficulty_distribution.model_dump(),
    indent=2
)}

QUESTION IDs ALREADY USED:

{json.dumps(
    remaining_ids
)}

QUESTIONS ALREADY PRESENT:

{json.dumps(
    existing_questions,
    indent=2,
    ensure_ascii=False
)}

GENERATION REASON:

{reason}

Return ONLY JSON.
"""

        generated = self._structured_call(
            system,
            user,
            GeneratedQuestion,
            max_completion_tokens=512
        )

        generated_data = (
            generated.model_dump()
        )

        generated_data["question_type"] = (
            normalize_question_type(
                generated_data[
                    "question_type"
                ]
            )
        )

        generated_data["options"] = (
            normalize_options(
                generated_data.get(
                    "options"
                )
            )
        )

        return Question(
            **generated_data
        )

    # ========================================================
    # TRADEOFF DECISION
    # ========================================================

    def llm_tradeoff_decision(
        self,
        candidates: List[Question],
        paper: PaperState,
        blueprint: Blueprint
    ) -> TradeoffDecision:

        if not candidates:

            return TradeoffDecision(
                action="generate",
                reason=(
                    "No feasible candidates remain."
                )
            )

        candidate_summary = []

        for candidate in candidates[:10]:

            candidate_summary.append({
                "id": candidate.id,
                "question_type": (
                    normalize_question_type(
                        candidate.question_type
                    )
                ),
                "marks": candidate.marks,
                "topic": candidate.topic,
                "difficulty": candidate.difficulty,
                "question": candidate.question[:200]
            })

        system = """
You are selecting the next question for an exam paper.

Return ONLY valid JSON.

Allowed actions:

{
  "action": "select",
  "question_id": "ID",
  "reason": "brief reason"
}

or

{
  "action": "generate",
  "question_id": null,
  "reason": "brief reason"
}

or

{
  "action": "finish",
  "question_id": null,
  "reason": "brief reason"
}

Rules:

1. Never select a question ID not present in candidates.

2. Select when a suitable candidate exists.

3. Generate only when candidates are empty.

4. Finish only when there are no remaining allocated slots.

5. Return valid JSON only.
"""

        user = f"""
TOTAL MARKS:

{blueprint.total_marks}

CURRENT MARKS:

{paper.marks_used}

REMAINING MARKS:

{remaining_marks(
    paper,
    blueprint
)}

CANDIDATES:

{json.dumps(
    candidate_summary,
    indent=2
)}

Choose the next action.
"""

        try:

            decision = self._structured_call(
                system,
                user,
                TradeoffDecision,
                max_completion_tokens=512
            )

            candidate_ids = {
                q.id
                for q in candidates
            }

            if decision.action == "select":

                if (
                    not decision.question_id
                    or decision.question_id
                    not in candidate_ids
                ):

                    raise ValueError(
                        "LLM selected an invalid question ID."
                    )

            if decision.action == "finish":

                if (
                    paper.marks_used
                    != blueprint.total_marks
                ):

                    best = candidates[0]

                    return TradeoffDecision(
                        action="select",
                        question_id=best.id,
                        reason=(
                            "Deterministic safety override: "
                            "paper has not reached target marks."
                        )
                    )

            return decision

        except Exception as error:

            best = candidates[0]

            print(
                "llm_tradeoff_decision: "
                "falling back to deterministic "
                f"lowest-cost candidate: {error}"
            )

            return TradeoffDecision(
                action="select",
                question_id=best.id,
                reason=(
                    "Deterministic fallback after "
                    "LLM decision failure."
                )
            )