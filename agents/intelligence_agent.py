
import json
from collections import defaultdict
from typing import Any, Dict, List
from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator
class Question(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)
    id: str = Field(min_length=1)
    text: str = Field(min_length=1)
    topic: str = Field(min_length=1)
    difficulty: str = Field(min_length=1)
    question_type: str = Field(min_length=1)
    marks: int = Field(gt=0)
    @field_validator("topic", "difficulty", "question_type")
    @classmethod
    def normalize_metadata(cls, value: str) -> str:
        return value.strip().lower()
    @field_validator("difficulty")
    @classmethod
    def validate_difficulty(cls, value: str) -> str:
        allowed = {
            "easy",
            "medium",
            "hard"
        }
        if value not in allowed:
            raise ValueError(
                f"Invalid difficulty '{value}'. "
                f"Allowed values: {sorted(allowed)}"
            )
        return value
    @field_validator("question_type")
    @classmethod
    def validate_question_type(cls, value: str) -> str:

        allowed = {
            "mcq",
            "short",
            "long"
        }

        if value not in allowed:
            raise ValueError(
                f"Invalid question type '{value}'. "
                f"Allowed values: {sorted(allowed)}"
            )

        return value
class QuestionIntelligence:

    def __init__(self, questions_file: str):

        self.questions_file = questions_file

    def load_questions(
        self
    ) -> tuple[List[Question], List[Dict[str, Any]]]:
        with open(
            self.questions_file,
            "r",
            encoding="utf-8"
        ) as file:
            data = json.load(file)
        if not isinstance(data, list):
            raise ValueError(
                "questions.json must contain a list of questions."
            )

        valid_questions: List[Question] = []
        invalid_questions: List[Dict[str, Any]] = []

        seen_ids = set()
        for index, item in enumerate(data):

            try:

                question = Question(**item)
                if question.id in seen_ids:

                    raise ValueError(
                        f"Duplicate question ID: {question.id}"
                    )

                seen_ids.add(question.id)

                valid_questions.append(question)

            except (ValidationError, ValueError) as error:

                invalid_questions.append({
                    "index": index,
                    "question": item,
                    "error": str(error)
                })

        return valid_questions, invalid_questions
    
    def build_inventory(
        self,
        questions: List[Question]
    ) -> Dict[str, Any]:

        topic_inventory = defaultdict(
            lambda: {
                "count": 0,
                "marks": 0
            }
        )

        difficulty_inventory = defaultdict(
            lambda: {
                "count": 0,
                "marks": 0
            }
        )

        type_inventory = defaultdict(
            lambda: {
                "count": 0,
                "marks": 0
            }
        )

        cell_inventory = defaultdict(
            lambda: defaultdict(
                lambda: defaultdict(
                    lambda: {
                        "count": 0,
                        "marks": 0
                    }
                )
            )
        )

        mark_values = set()

        for question in questions:

            topic = question.topic
            difficulty = question.difficulty
            question_type = question.question_type
            marks = question.marks

            mark_values.add(marks)

            topic_inventory[topic]["count"] += 1
            topic_inventory[topic]["marks"] += marks

            difficulty_inventory[difficulty]["count"] += 1
            difficulty_inventory[difficulty]["marks"] += marks

            type_inventory[question_type]["count"] += 1
            type_inventory[question_type]["marks"] += marks

            cell = cell_inventory[
                topic
            ][
                difficulty
            ][
                question_type
            ]

            cell["count"] += 1
            cell["marks"] += marks

        return {
            "topic": dict(topic_inventory),
            "difficulty": dict(difficulty_inventory),
            "question_type": dict(type_inventory),
            "topic_difficulty_type": {
                topic: {
                    difficulty: {
                        question_type: dict(values)
                        for question_type, values
                        in difficulty_data.items()
                    }
                    for difficulty, difficulty_data
                    in topic_data.items()
                }
                for topic, topic_data
                in cell_inventory.items()
            },
            "mark_values": sorted(mark_values)
        }

    def find_exact_duplicates(
        self,
        questions: List[Question]
    ) -> List[List[str]]:

        text_groups = defaultdict(list)

        for question in questions:

            normalized_text = " ".join(
                question.text.lower().split()
            )

            text_groups[
                normalized_text
            ].append(question.id)

        duplicate_groups = []

        for ids in text_groups.values():

            if len(ids) > 1:

                duplicate_groups.append(ids)

        return duplicate_groups

    def calculate_reachable_marks(
        self,
        questions: List[Question]
    ) -> List[int]:

        reachable = {0}

        for question in questions:

            marks = question.marks

            new_totals = {
                total + marks
                for total in reachable
            }

            reachable.update(new_totals)

        return sorted(reachable)

    def analyze(self) -> Dict[str, Any]:

        questions, invalid_questions = (
            self.load_questions()
        )

        if not questions:

            return {
                "status": "question_bank_invalid",
                "questions": [],
                "invalid_questions": invalid_questions,
                "inventory": {},
                "exact_duplicates": [],
                "reachable_marks": [],
                "error": (
                    "No valid questions found "
                    "in the question bank."
                )
            }

        inventory = self.build_inventory(
            questions
        )

        exact_duplicates = (
            self.find_exact_duplicates(
                questions
            )
        )

        reachable_marks = (
            self.calculate_reachable_marks(
                questions
            )
        )

        return {
            "status": "question_intelligence_complete",

            "questions": [
                question.model_dump()
                for question in questions
            ],

            "invalid_questions": invalid_questions,

            "inventory": inventory,

            "exact_duplicates": exact_duplicates,

            "reachable_marks": reachable_marks
        }

class QuestionIntelligenceAgent:

    def run(self, state: Dict[str, Any]) -> Dict[str, Any]:

        questions_file = state.get("question_bank_path")

        if not questions_file:
            return {
                "error": "question_bank_path missing from state.",
                "status": "question_intelligence_failed",
            }

        try:

            result = QuestionIntelligence(
                questions_file
            ).analyze()

        except Exception as e:

            return {
                "error": str(e),
                "status": "question_intelligence_failed",
            }

        if result["status"] == "question_bank_invalid":

            return {
                "error": result["error"],
                "invalid_questions": result["invalid_questions"],
                "status": "question_intelligence_failed",
            }

        return {
            "questions": result["questions"],
            "inventory": result["inventory"],
            "invalid_questions": result["invalid_questions"],
            "status": "question_intelligence_complete",
        }