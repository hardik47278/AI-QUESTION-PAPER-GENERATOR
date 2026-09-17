
"""
Evaluation Agent

Independently verifies a generated question paper.

Responsibilities:
1. Deterministic verification of hard constraints.
2. Question-level deterministic validation.
3. LLM-based qualitative evaluation.
4. Semantic duplicate detection.
5. Confidence-based routing.
6. Exact slot / distribution validation.
7. Explicit conflict reporting.
8. Return a structured evaluation report.

The agent does NOT repair the paper.
The Paper Generation Agent owns repair/regeneration.
"""

from __future__ import annotations

from typing import Literal
import os
import json

from openai import OpenAI
from pydantic import BaseModel, Field
from dotenv import load_dotenv
load_dotenv()


# ============================================================
# CONFIGURATION
# ============================================================

HIGH_CONFIDENCE = 0.90
MEDIUM_CONFIDENCE = 0.70


# ============================================================
# NORMALIZATION HELPERS
# ============================================================

def normalize_topic(value: str) -> str:
    """
    Normalize topic names for comparison.

    Examples:
        Algebra -> algebra
        " ALGEBRA " -> algebra
    """
    return str(value).strip().lower()


def normalize_difficulty(value: str) -> str:
    """
    Normalize difficulty values.
    """
    return str(value).strip().lower()


def normalize_question_type(value: str) -> str:
    """
    Convert question-type aliases to canonical values.

    Canonical values:
        mcq
        short
        long
    """

    value = str(value).strip().lower()

    aliases = {
        "mcq": "mcq",
        "multiple choice": "mcq",
        "multiple_choice": "mcq",
        "multiple-choice": "mcq",

        "short": "short",
        "short answer": "short",
        "short_answer": "short",
        "short-answer": "short",

        "long": "long",
        "long answer": "long",
        "long_answer": "long",
        "long-answer": "long",
    }

    return aliases.get(value, value)


# ============================================================
# DATA MODELS
# ============================================================

class Question(BaseModel):
    id: str
    statement: str
    topic: str
    difficulty: Literal["easy", "medium", "hard"]
    question_type: Literal["mcq", "short", "long"]
    marks: int = Field(gt=0)
    answer: str | None = None


class QuestionSlot(BaseModel):
    """
    Exact slot that a generated question must satisfy.
    """

    topic: str
    difficulty: str
    question_type: str
    marks: int


class Blueprint(BaseModel):
    total_marks: int
    number_of_questions: int
    topic_distribution: dict[str, float] = {}
    difficulty_distribution: dict[str, float] = {}
    type_distribution: dict[str, float] = {}
    marks_tolerance: int = 0


class Paper(BaseModel):
    questions: list[Question]


# ============================================================
# EVALUATION RESULT
# ============================================================

class QuestionEvaluation(BaseModel):
    question_id: str

    # Deterministic checks
    structurally_valid: bool = True
    answer_present: bool = True
    exact_duplicate: bool = False

    # LLM checks
    relevant: bool = True
    clear: bool = True
    answerable: bool = True
    answer_correct: bool = True
    difficulty_consistent: bool = True
    semantic_duplicate: bool = False
    confidence: float = 1.0
    issues: list[str] = Field(default_factory=list)


class PaperQualityEvaluation(BaseModel):
    difficulty_progression: bool = True
    topic_spread: bool = True
    consecutive_repetition: bool = True
    question_diversity: bool = True
    section_structure: bool = True
    formatting_quality: bool = True
    overall_coherence: bool = True
    issues: list[str] = Field(default_factory=list)
    confidence: float = Field(ge=0, le=1)


class EvaluationResult(BaseModel):
    hard_constraints_passed: bool
    quality_passed: bool

    hard_failures: list[str] = Field(default_factory=list)
    quality_failures: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)

    affected_question_ids: list[str] = Field(default_factory=list)

    # NEW:
    # Explicit structured conflicts.
    conflicts: list[dict] = Field(default_factory=list)

    question_evaluations: list[QuestionEvaluation] = Field(
        default_factory=list
    )

    paper_quality: PaperQualityEvaluation | None = None

    confidence: float

    route: Literal[
        "PASS",
        "REPAIR_PAPER",
        "REGENERATE_QUESTION",
        "SECOND_EVALUATION",
        "HUMAN_REVIEW",
    ]


class HumanDecision(BaseModel):
    action: Literal["approve", "swap_question"]
    question_id: str | None = None
    replacement_question_id: str | None = None
    reason: str | None = None


# ============================================================
# DETERMINISTIC VERIFIER
# ============================================================

class DeterministicVerifier:
    """
    Verifies things that have an objectively correct answer.

    No LLM is used here.
    """

    # ========================================================
    # MAIN VERIFICATION
    # ========================================================

    def verify(
        self,
        paper: Paper,
        blueprint: Blueprint
    ) -> tuple[
        list[str],
        list[QuestionEvaluation],
        list[dict]
    ]:

        failures: list[str] = []
        question_results: list[QuestionEvaluation] = []
        conflicts: list[dict] = []

        # ----------------------------------------------------
        # Number of questions
        # ----------------------------------------------------

        if len(paper.questions) != blueprint.number_of_questions:

            failures.append("number_of_questions")

            conflicts.append({
                "type": "number_of_questions",
                "expected": blueprint.number_of_questions,
                "actual": len(paper.questions),
                "difference": (
                    len(paper.questions)
                    - blueprint.number_of_questions
                ),
            })

        # ----------------------------------------------------
        # Total marks
        # ----------------------------------------------------

        total_marks = sum(
            q.marks
            for q in paper.questions
        )

        min_marks = (
            blueprint.total_marks
            - blueprint.marks_tolerance
        )

        max_marks = (
            blueprint.total_marks
            + blueprint.marks_tolerance
        )

        if not min_marks <= total_marks <= max_marks:

            failures.append("total_marks")

            conflicts.append({
                "type": "total_marks",
                "expected_marks": blueprint.total_marks,
                "actual_marks": total_marks,
                "difference": (
                    total_marks
                    - blueprint.total_marks
                ),
                "tolerance": blueprint.marks_tolerance,
            })

        # ----------------------------------------------------
        # Duplicate IDs
        # ----------------------------------------------------

        ids = [
            q.id
            for q in paper.questions
        ]

        if len(ids) != len(set(ids)):

            failures.append(
                "duplicate_question_ids"
            )

            duplicate_ids = {
                question_id
                for question_id in ids
                if ids.count(question_id) > 1
            }

            conflicts.append({
                "type": "duplicate_question_ids",
                "question_ids": sorted(
                    duplicate_ids
                ),
            })

        # ----------------------------------------------------
        # Topic distribution
        # ----------------------------------------------------

        topic_ok, topic_conflicts = (
            self._distribution_ok(
                paper=paper,
                target_distribution=(
                    blueprint.topic_distribution
                ),
                attribute="topic",
                total_marks=blueprint.total_marks,
                marks_tolerance=(
                    blueprint.marks_tolerance
                ),
            )
        )

        if not topic_ok:
            failures.append(
                "topic_distribution"
            )
            conflicts.extend(topic_conflicts)

        # ----------------------------------------------------
        # Difficulty distribution
        # ----------------------------------------------------

        difficulty_ok, difficulty_conflicts = (
            self._distribution_ok(
                paper=paper,
                target_distribution=(
                    blueprint.difficulty_distribution
                ),
                attribute="difficulty",
                total_marks=blueprint.total_marks,
                marks_tolerance=(
                    blueprint.marks_tolerance
                ),
            )
        )

        if not difficulty_ok:
            failures.append(
                "difficulty_distribution"
            )
            conflicts.extend(difficulty_conflicts)

        # ----------------------------------------------------
        # Question type distribution
        # ----------------------------------------------------

        type_ok, type_conflicts = (
            self._distribution_ok(
                paper=paper,
                target_distribution=(
                    blueprint.type_distribution
                ),
                attribute="question_type",
                total_marks=blueprint.total_marks,
                marks_tolerance=(
                    blueprint.marks_tolerance
                ),
            )
        )

        if not type_ok:
            failures.append(
                "question_type_distribution"
            )
            conflicts.extend(type_conflicts)

        # ----------------------------------------------------
        # Exact duplicates
        # ----------------------------------------------------

        normalized_questions = {}

        for question in paper.questions:

            normalized = self._normalize_text(
                question.statement
            )

            if normalized in normalized_questions:

                failures.append(
                    "exact_duplicate_questions"
                )

                conflicts.append({
                    "type": "exact_duplicate_questions",
                    "question_id": question.id,
                    "duplicate_of": (
                        normalized_questions[
                            normalized
                        ]
                    ),
                })

                question_results.append(
                    QuestionEvaluation(
                        question_id=question.id,
                        exact_duplicate=True,
                        issues=[
                            "Exact duplicate question"
                        ],
                    )
                )

            else:

                normalized_questions[
                    normalized
                ] = question.id

        # ----------------------------------------------------
        # Question-level deterministic validation
        # ----------------------------------------------------

        for question in paper.questions:

            issues = []

            # Statement
            if not question.statement.strip():

                issues.append(
                    "empty_question_statement"
                )

            # Marks
            if question.marks <= 0:

                issues.append(
                    "invalid_marks"
                )

            # Answer
            if question.answer is None:

                issues.append(
                    "missing_answer"
                )

            # Difficulty
            normalized_difficulty = (
                normalize_difficulty(
                    question.difficulty
                )
            )

            if normalized_difficulty not in {
                "easy",
                "medium",
                "hard",
            }:

                issues.append(
                    "invalid_difficulty"
                )

            # Question type
            normalized_type = (
                normalize_question_type(
                    question.question_type
                )
            )

            if normalized_type not in {
                "mcq",
                "short",
                "long",
            }:

                issues.append(
                    "invalid_question_type"
                )

            question_results.append(
                QuestionEvaluation(
                    question_id=question.id,
                    structurally_valid=(
                        len(issues) == 0
                    ),
                    answer_present=(
                        question.answer is not None
                    ),
                    issues=issues,
                )
            )

            if issues:

                failures.append(
                    f"invalid_question:{question.id}"
                )

                conflicts.append({
                    "type": "invalid_question",
                    "question_id": question.id,
                    "issues": issues,
                })

        return (
            failures,
            question_results,
            conflicts,
        )

    # ========================================================
    # EXACT DISTRIBUTION VALIDATION
    # ========================================================

    def _distribution_ok(
        self,
        paper: Paper,
        target_distribution: dict[str, float],
        attribute: str,
        total_marks: int,
        marks_tolerance: int = 0,
    ) -> tuple[bool, list[dict]]:
        """
        Validate distribution using exact target marks.

        Example:

            total_marks = 40
            algebra = 0.50

        Expected algebra marks:

            40 * 0.50 = 20

        If actual algebra marks = 24 and tolerance = 0,
        validation FAILS.

        With tolerance = 4:

            abs(24 - 20) <= 4

        would PASS.
        """

        if not target_distribution:

            return True, []

        conflicts = []

        # ----------------------------------------------------
        # Normalize target distribution keys
        # ----------------------------------------------------

        normalized_targets = {}

        for value, percentage in (
            target_distribution.items()
        ):

            if attribute == "topic":

                normalized_value = (
                    normalize_topic(value)
                )

            elif attribute == "difficulty":

                normalized_value = (
                    normalize_difficulty(value)
                )

            elif attribute == "question_type":

                normalized_value = (
                    normalize_question_type(value)
                )

            else:

                normalized_value = (
                    str(value)
                    .strip()
                    .lower()
                )

            normalized_targets[
                normalized_value
            ] = percentage

        # ----------------------------------------------------
        # Calculate actual marks
        # ----------------------------------------------------

        actual_marks = {
            value: 0
            for value in normalized_targets
        }

        for question in paper.questions:

            raw_value = getattr(
                question,
                attribute
            )

            if attribute == "topic":

                value = normalize_topic(
                    raw_value
                )

            elif attribute == "difficulty":

                value = normalize_difficulty(
                    raw_value
                )

            elif attribute == "question_type":

                value = normalize_question_type(
                    raw_value
                )

            else:

                value = (
                    str(raw_value)
                    .strip()
                    .lower()
                )

            if value in actual_marks:

                actual_marks[value] += (
                    question.marks
                )

        # ----------------------------------------------------
        # Compare EXACTLY
        # ----------------------------------------------------

        passed = True

        for value, target_percentage in (
            normalized_targets.items()
        ):

            expected_marks = (
                total_marks
                * target_percentage
            )

            actual = actual_marks.get(
                value,
                0
            )

            difference = (
                actual
                - expected_marks
            )

            # Exact validation when tolerance = 0.
            if (
                abs(difference)
                > marks_tolerance
            ):

                passed = False

                conflicts.append({
                    "type": (
                        f"{attribute}_distribution"
                    ),
                    "attribute": attribute,
                    "value": value,
                    "expected_percentage": (
                        target_percentage
                    ),
                    "expected_marks": (
                        expected_marks
                    ),
                    "actual_marks": actual,
                    "difference": difference,
                    "tolerance": marks_tolerance,
                })

        return passed, conflicts

    # ========================================================
    # SLOT MATCHING
    # ========================================================

    @staticmethod
    def question_matches_slot(
        question: Question,
        slot: QuestionSlot
    ) -> bool:
        """
        Strictly validate a question against a slot.

        ALL FOUR fields must match:

            topic
            difficulty
            question_type
            marks
        """

        question_topic = normalize_topic(
            question.topic
        )

        slot_topic = normalize_topic(
            slot.topic
        )

        question_difficulty = (
            normalize_difficulty(
                question.difficulty
            )
        )

        slot_difficulty = (
            normalize_difficulty(
                slot.difficulty
            )
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
            and
            question_difficulty
            == slot_difficulty
            and
            question_type
            == slot_type
            and
            question.marks
            == slot.marks
        )

    # ========================================================
    # SLOT CONFLICT
    # ========================================================

    @staticmethod
    def slot_conflict(
        question: Question,
        slot: QuestionSlot
    ) -> dict:
        """
        Produce a structured explanation of why a question
        does not match a slot.
        """

        return {
            "type": "slot_mismatch",
            "question_id": question.id,
            "slot": {
                "topic": slot.topic,
                "difficulty": slot.difficulty,
                "question_type": (
                    slot.question_type
                ),
                "marks": slot.marks,
            },
            "question": {
                "topic": question.topic,
                "difficulty": question.difficulty,
                "question_type": (
                    question.question_type
                ),
                "marks": question.marks,
            },
        }

    # ========================================================
    # TEXT NORMALIZATION
    # ========================================================

    @staticmethod
    def _normalize_text(
        text: str
    ) -> str:

        return " ".join(
            text.lower().split()
        )


# ============================================================
# LLM EVALUATOR
# ============================================================

class LLMEvaluator:
    """
    Evaluates properties that are difficult to determine
    reliably using deterministic rules.

    Uses OpenAI gpt-4o-mini.
    """

    def __init__(self):

        api_key = os.getenv(
            "OPENAI_API_KEY"
        )

        if not api_key:

            raise RuntimeError(
                "OPENAI_API_KEY is not set in the environment."
            )

        self.client = OpenAI(
            api_key=api_key
        )

        self.model = os.getenv(
            "OPENAI_MODEL",
            "gpt-4o-mini"
        )

        print(
            f"LLMEvaluator using OpenAI model: {self.model}"
        )

    # ========================================================
    # QUESTION EVALUATION
    # ========================================================

    def evaluate_question(
        self,
        question: Question,
        blueprint: Blueprint
    ) -> dict:

        system_prompt ="""

You are the qualitative Evaluation Agent
for an AI question-paper generation system.

Evaluate the given question independently and objectively.

Check:

1. relevant
   - Is the question relevant to the provided blueprint?
   - Do NOT reject a question simply because its marks are large.
   - The question's marks have already been allocated by the blueprint/slot system.

2. clear
   - Is the question clearly written and understandable?

3. answerable
   - Can a student reasonably answer it using the information provided?

4. answer_correct
   - Verify the provided answer mathematically and logically.
   - Evaluate the actual correctness of the answer, not superficial text matching.

IMPORTANT MATHEMATICAL ANSWER RULE:
- For numerical and mathematical questions, independently calculate/check
  the answer.
- Equivalent mathematical representations are correct.
- Units such as cm², m², etc. should be accepted when mathematically correct.

IMPORTANT MCQ ANSWER RULE:
- For MCQ questions, correct_answer may be an option label such as
  "A", "B", "C", or "D".
- You MUST resolve the option label against the provided question/options.

Example:
options:
["A. 4", "B. 5", "C. 6", "D. 7"]

correct_answer:
"A"

This means the selected answer is 4.

Therefore, if A is the mathematically correct option,
answer_correct MUST be true.

Do NOT mark an MCQ answer incorrect merely because
correct_answer contains the option label instead of the full answer text.

5. difficulty_consistent
   - Does the actual difficulty reasonably match the stated difficulty?
   - Judge the complexity of solving the individual question.
   - Do not judge difficulty based only on marks.

6. semantic_duplicate
   - Determine whether this question is semantically duplicating another
     question ONLY if another question is explicitly provided for comparison.
   - If no comparison question is provided, set semantic_duplicate to false.

7. confidence
   - Your confidence in this evaluation from 0 to 1.

8. issues
   - List only concrete and meaningful problems.
   - Return an empty list if there are no problems.

IMPORTANT:
Do not invent problems.
Do not mark a mathematically correct answer as incorrect.
Do not confuse an MCQ option label with the answer text.
Do not penalize a question simply because several questions in the paper
have the same difficulty; paper-level distribution is evaluated separately.

Return ONLY valid JSON.

Required format:

{
  "relevant": true,
  "clear": true,
  "answerable": true,
  "answer_correct": true,
  "difficulty_consistent": true,
  "semantic_duplicate": false,
  "confidence": 0.95,
  "issues": []
}


"""

        user_prompt = f"""
BLUEPRINT:

{json.dumps(
    blueprint.model_dump(),
    indent=2
)}

QUESTION:

{json.dumps(
    question.model_dump(),
    indent=2
)}
"""

        response = (
            self.client
            .chat
            .completions
            .create(
                model=self.model,
                response_format={
                    "type": "json_object"
                },
                messages=[
                    {
                        "role": "system",
                        "content": system_prompt,
                    },
                    {
                        "role": "user",
                        "content": user_prompt,
                    },
                ],
                temperature=0.2,
            )
        )

        raw_content = (
            response
            .choices[0]
            .message
            .content
        )

        if raw_content is None:

            raise ValueError(
                "OpenAI returned no content during question evaluation."
            )

        try:

            result = json.loads(
                raw_content
            )

        except json.JSONDecodeError as e:

            raise ValueError(
                "OpenAI returned invalid JSON "
                "during question evaluation: "
                f"{e}\nRaw content: {raw_content}"
            )

        return result

    # ========================================================
    # PAPER EVALUATION
    # ========================================================

    def evaluate_paper(
        self,
        paper: Paper,
        blueprint: Blueprint
    ) -> PaperQualityEvaluation:

        system_prompt = """
You are the qualitative Paper Evaluation Agent
for an AI question-paper generation system.

Evaluate the generated paper as a whole.

Check:

1. difficulty_progression
2. topic_spread
3. consecutive_repetition
4. question_diversity
5. section_structure
6. formatting_quality
7. overall_coherence
8. issues
9. confidence

The evaluation should determine whether the paper
reads like a coherent real examination paper rather
than a random collection of questions.

Return ONLY valid JSON.

Required format:

{
  "difficulty_progression": true,
  "topic_spread": true,
  "consecutive_repetition": true,
  "question_diversity": true,
  "section_structure": true,
  "formatting_quality": true,
  "overall_coherence": true,
  "issues": [],
  "confidence": 0.95
}
"""

        user_prompt = f"""
BLUEPRINT:

{json.dumps(
    blueprint.model_dump(),
    indent=2
)}

GENERATED PAPER:

{json.dumps(
    paper.model_dump(),
    indent=2
)}
"""

        response = (
            self.client
            .chat
            .completions
            .create(
                model=self.model,
                response_format={
                    "type": "json_object"
                },
                messages=[
                    {
                        "role": "system",
                        "content": system_prompt,
                    },
                    {
                        "role": "user",
                        "content": user_prompt,
                    },
                ],
                temperature=0.2,
            )
        )

        raw_content = (
            response
            .choices[0]
            .message
            .content
        )

        if raw_content is None:

            raise ValueError(
                "OpenAI returned no content during paper evaluation."
            )

        try:

            result = json.loads(
                raw_content
            )

        except json.JSONDecodeError as e:

            raise ValueError(
                "OpenAI returned invalid JSON "
                "during paper evaluation: "
                f"{e}\nRaw content: {raw_content}"
            )

        return PaperQualityEvaluation(
            **result
        )


# ============================================================
# EVALUATION AGENT
# ============================================================

class EvaluationAgent:
    """
    Independent verification agent.

    Generation Agent:
        creates / repairs

    Evaluation Agent:
        verifies / routes
    """

    def __init__(self):

        self.deterministic_verifier = (
            DeterministicVerifier()
        )

        self.llm_evaluator = (
            LLMEvaluator()
        )

        # ========================================================
    # RUN
    # ========================================================

    def run(
        self,
        state: dict
    ) -> dict:

        bp = state["blueprint"]

        paper_data = state.get(
            "paper_state"
        )

        if paper_data is None:
            paper_data = state.get(
                "paper"
            )

        if paper_data is None:
            raise ValueError(
                "EvaluationAgent could not find "
            "`paper_state` or `paper` in pipeline state."
        )





                



        

        # ----------------------------------------------------
        # Support both:
        #   1. PaperState / Pydantic object
        #   2. dictionary representation
        # ----------------------------------------------------

        if hasattr(
            paper_data,
            "selected_questions"
        ):

            selected_questions = (
                paper_data.selected_questions
            )

        else:

            selected_questions = (
                paper_data.get(
                    "selected_questions",
                    []
                )
            )

        # ----------------------------------------------------
        # Convert Pydantic Question objects to dictionaries
        # when necessary.
        # ----------------------------------------------------

        normalized_questions = []

        for q in selected_questions:

            if hasattr(q, "model_dump"):

                normalized_questions.append(
                    q.model_dump()
                )

            else:

                normalized_questions.append(q)

        selected_questions = (
            normalized_questions
        )

        # ----------------------------------------------------
        # `number_of_questions` is not produced by
        # the blueprint-building step upstream.
        # Fall back to actual generated question count.
        # ----------------------------------------------------

        number_of_questions = bp.get(
            "number_of_questions",
            len(selected_questions)
        )

        blueprint = Blueprint(
            total_marks=bp["total_marks"],
            number_of_questions=number_of_questions,
            topic_distribution=bp.get(
                "topic_distribution",
                {}
            ),
            difficulty_distribution=bp.get(
                "difficulty_distribution",
                {}
            ),
            type_distribution=bp.get(
                "question_type_distribution",
                bp.get(
                    "type_distribution",
                    {}
                )
            ),
            marks_tolerance=bp.get(
                "marks_tolerance",
                0
            ),
        )

        # ----------------------------------------------------
        # Build evaluator Paper
        # ----------------------------------------------------

        paper = Paper(
            questions=[
                Question(
                    id=q["id"],
                    statement=q.get(
                        "question",
                        q.get(
                            "statement",
                            ""
                        )
                    ),
                    topic=q["topic"],
                    difficulty=(
                        normalize_difficulty(
                            q["difficulty"]
                        )
                    ),
                    question_type=(
                        normalize_question_type(
                            q["question_type"]
                        )
                    ),
                    marks=q["marks"],
                    answer=q.get(
                        "correct_answer",
                        q.get(
                            "answer"
                        )
                    ),
                )
                for q in selected_questions
            ]
        )

        # ----------------------------------------------------
        # Evaluate
        # ----------------------------------------------------

        result = self.evaluate(
            paper,
            blueprint
        )

        return {
            "evaluation": (
                result.model_dump()
            ),
            "retry_count": (
                state.get(
                    "retry_count",
                    0
                ) + 1
            ),
            "status": "evaluation_complete",
        }    




    # ========================================================
    # RUN
    # ========================================================

    
    # ========================================================
    # MAIN ENTRY POINT
    # ========================================================

    def evaluate(
        self,
        paper: Paper,
        blueprint: Blueprint
    ) -> EvaluationResult:

        # ----------------------------------------------------
        # STEP 1:
        # Deterministic verification
        # ----------------------------------------------------

        (
            hard_failures,
            question_results,
            conflicts,
        ) = (
            self.deterministic_verifier.verify(
                paper,
                blueprint
            )
        )

        # ----------------------------------------------------
        # STEP 2:
        # LLM evaluation
        # ----------------------------------------------------

        quality_failures = []

        affected_questions = []

        llm_confidences = []

        for question in paper.questions:

            llm_result = (
                self.llm_evaluator.evaluate_question(
                    question,
                    blueprint
                )
            )

            evaluation = next(
                (
                    x
                    for x in question_results
                    if x.question_id
                    == question.id
                ),
                None
            )

            if evaluation is None:

                evaluation = QuestionEvaluation(
                    question_id=question.id
                )

                question_results.append(
                    evaluation
                )

            evaluation.relevant = (
                llm_result["relevant"]
            )

            evaluation.clear = (
                llm_result["clear"]
            )

            evaluation.answerable = (
                llm_result["answerable"]
            )

            evaluation.answer_correct = (
                llm_result["answer_correct"]
            )

            evaluation.difficulty_consistent = (
                llm_result[
                    "difficulty_consistent"
                ]
            )

            evaluation.semantic_duplicate = (
                llm_result[
                    "semantic_duplicate"
                ]
            )

            evaluation.confidence = (
                llm_result["confidence"]
            )

            evaluation.issues.extend(
                llm_result["issues"]
            )

            llm_confidences.append(
                llm_result["confidence"]
            )

            quality_problem = (
                not evaluation.relevant
                or not evaluation.clear
                or not evaluation.answerable
                or not evaluation.answer_correct
                or not evaluation.difficulty_consistent
                or evaluation.semantic_duplicate
            )

            if quality_problem:

                quality_failures.append(
                    f"question_quality:{question.id}"
                )

                affected_questions.append(
                    question.id
                )

        # ----------------------------------------------------
        # STEP 2.5:
        # Paper-level LLM evaluation
        # ----------------------------------------------------

        paper_quality = (
            self.llm_evaluator.evaluate_paper(
                paper,
                blueprint
            )
        )

        # Add paper-level quality issues.
        if not paper_quality.difficulty_progression:
            quality_failures.append(
                "paper_quality:difficulty_progression"
            )

        if not paper_quality.topic_spread:
            quality_failures.append(
                "paper_quality:topic_spread"
            )

        if not paper_quality.consecutive_repetition:
            quality_failures.append(
                "paper_quality:consecutive_repetition"
            )

        if not paper_quality.question_diversity:
            quality_failures.append(
                "paper_quality:question_diversity"
            )

        if not paper_quality.section_structure:
            quality_failures.append(
                "paper_quality:section_structure"
            )

        if not paper_quality.formatting_quality:
            quality_failures.append(
                "paper_quality:formatting_quality"
            )

        if not paper_quality.overall_coherence:
            quality_failures.append(
                "paper_quality:overall_coherence"
            )

        # ----------------------------------------------------
        # STEP 3:
        # Confidence
        # ----------------------------------------------------

        overall_confidence = (
            sum(llm_confidences)
            / len(llm_confidences)
            if llm_confidences
            else 1.0
        )

        # Combine paper confidence into overall confidence.
        if paper_quality is not None:

            if llm_confidences:

                overall_confidence = (
                    overall_confidence
                    + paper_quality.confidence
                ) / 2

            else:

                overall_confidence = (
                    paper_quality.confidence
                )

        quality_passed = (
            len(quality_failures) == 0
        )

        hard_passed = (
            len(hard_failures) == 0
        )

        # ----------------------------------------------------
        # STEP 4:
        # Routing
        # ----------------------------------------------------

        route = self._determine_route(
            hard_failures=hard_failures,
            quality_failures=quality_failures,
            confidence=overall_confidence
        )

        return EvaluationResult(
            hard_constraints_passed=hard_passed,
            quality_passed=quality_passed,
            hard_failures=hard_failures,
            quality_failures=quality_failures,
            affected_question_ids=(
                affected_questions
            ),
            conflicts=conflicts,
            question_evaluations=(
                question_results
            ),
            paper_quality=paper_quality,
            confidence=overall_confidence,
            route=route,
        )

    # ========================================================
    # ROUTING
    # ========================================================

    @staticmethod
    def _determine_route(
        hard_failures: list[str],
        quality_failures: list[str],
        confidence: float
    ) -> str:

        # Hard constraint failure always goes back
        # to Paper Generation Agent.
        if hard_failures:

            return "REPAIR_PAPER"

        # Qualitative failures.
        if quality_failures:

            if confidence >= HIGH_CONFIDENCE:

                return "REGENERATE_QUESTION"

            if confidence >= MEDIUM_CONFIDENCE:

                return "SECOND_EVALUATION"

            return "HUMAN_REVIEW"

        return "PASS"


# ============================================================
# TEST
# ============================================================

if __name__ == "__main__":

    blueprint = Blueprint(
        total_marks=40,
        number_of_questions=8,
        marks_tolerance=0,
        topic_distribution={
            "algebra": 0.50,
            "geometry": 0.50,
        },
        difficulty_distribution={
            "easy": 0.25,
            "medium": 0.50,
            "hard": 0.25,
        },
        type_distribution={
            "mcq": 0.50,
            "short": 0.25,
            "long": 0.25,
        },
    )

    paper = Paper(
        questions=[
            Question(
                id="Q1",
                statement="Solve x + 2 = 5.",
                topic="algebra",
                difficulty="easy",
                question_type="mcq",
                marks=5,
                answer="3",
            ),
        ]
    )

    agent = EvaluationAgent()

    result = agent.evaluate(
        paper,
        blueprint
    )

    print(
        result.model_dump_json(
            indent=2
        )
    )

