# agents/blueprint_agent.py

import os
import json
from typing import Dict, List, TypedDict, Any

from openai import OpenAI
from pydantic import BaseModel, Field, field_validator, model_validator
from langgraph.graph import StateGraph, START, END
from dotenv import load_dotenv

load_dotenv()


# ============================================================
# PYDANTIC BLUEPRINT SCHEMAS
# ============================================================

class DifficultyDistribution(BaseModel):
    easy: float = Field(ge=0, le=1)
    medium: float = Field(ge=0, le=1)
    hard: float = Field(ge=0, le=1)

    @model_validator(mode="after")
    def validate_total(self):
        total = self.easy + self.medium + self.hard

        if abs(total - 1.0) > 0.001:
            raise ValueError(
                f"Difficulty distribution must total 100%, "
                f"got {total * 100:.2f}%"
            )

        return self


class Blueprint(BaseModel):
    total_marks: int = Field(gt=0)

    topic_distribution: Dict[str, float]

    difficulty_distribution: DifficultyDistribution

    question_type_distribution: Dict[str, float]

    hard_constraints: List[str] = Field(
        default_factory=list
    )

    soft_constraints: List[str] = Field(
        default_factory=list
    )

    # Flexible preferences
    # Allows strings, numbers, booleans, lists, etc.
    preferences: Dict[str, Any] = Field(
        default_factory=dict
    )

    @field_validator(
        "topic_distribution",
        "question_type_distribution"
    )
    @classmethod
    def validate_distribution(cls, value):

        if not value:
            raise ValueError(
                "Distribution cannot be empty"
            )

        for name, percentage in value.items():

            if not 0 <= percentage <= 1:
                raise ValueError(
                    f"{name} percentage must be between 0 and 1"
                )

        total = sum(value.values())

        if abs(total - 1.0) > 0.001:
            raise ValueError(
                f"Distribution must total 100%, "
                f"got {total * 100:.2f}%"
            )

        return value


# ============================================================
# LANGGRAPH STATE
# ============================================================

class PaperState(TypedDict, total=False):

    teacher_request: str

    blueprint: Dict[str, Any]

    error: str

    status: str


# ============================================================
# BLUEPRINT AGENT
# ============================================================

class BlueprintAgent:

    def __init__(self):

        api_key = os.getenv("OPENAI_API_KEY")

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
            f"BlueprintAgent using OpenAI model: {self.model}"
        )

    # ========================================================
    # CREATE BLUEPRINT
    # ========================================================

    def create_blueprint(
        self,
        teacher_request: str
    ) -> Blueprint:

        response = self.client.chat.completions.create(

            model=self.model,

            response_format={
                "type": "json_object"
            },

            messages=[
                {
                    "role": "system",
                    "content": """
You are the Blueprint Agent for an AI
question-paper generation system.

Your responsibility is to understand the
teacher's natural-language requirements and
convert them into a structured blueprint.

You are responsible for INTERPRETATION.

You are NOT responsible for:

- checking question-bank availability
- generating questions
- selecting questions
- calculating repair cost
- performing fallback
- solving constraint conflicts
- running optimization

Extract the following:

1. total_marks

2. topic_distribution

3. difficulty_distribution

4. question_type_distribution

5. hard_constraints

6. soft_constraints

7. preferences

IMPORTANT:

If the teacher explicitly says something
"MUST", "REQUIRED", "MANDATORY", or
"EXACTLY", treat it as a hard constraint.

If the teacher says "prefer", "ideally",
"mostly", "around", or similar language,
treat it as a soft constraint or preference.

Do not invent requirements that the teacher
did not provide.

For distributions, use decimal values.

Example:

40% -> 0.40
30% -> 0.30
20% -> 0.20

Preferences may contain values of different
JSON types, including strings, numbers,
booleans, lists, or other simple JSON values.

For example:

"preferences": {
    "topic_focus": ["Algebra", "Geometry"],
    "prefer_medium": true
}

You must respond with ONLY a single valid JSON
object and nothing else.

No markdown.
No code fences.
No commentary.
No explanation.

The JSON object must match this shape:

{
  "total_marks": <int>,
  "topic_distribution": {
    "<topic name>": <float 0-1>
  },
  "difficulty_distribution": {
    "easy": <float 0-1>,
    "medium": <float 0-1>,
    "hard": <float 0-1>
  },
  "question_type_distribution": {
    "<type name>": <float 0-1>
  },
  "hard_constraints": [],
  "soft_constraints": [],
  "preferences": {}
}

Each of topic_distribution,
difficulty_distribution,
and question_type_distribution must have
values that sum to 1.0.
"""
                },

                {
                    "role": "user",
                    "content": teacher_request
                }
            ],

            temperature=0.2
        )

        raw_content = response.choices[0].message.content

        if raw_content is None:
            raise ValueError(
                "OpenAI did not return any content"
            )

        try:

            parsed_json = json.loads(
                raw_content
            )

        except json.JSONDecodeError as e:

            raise ValueError(
                f"OpenAI returned invalid JSON: {e}\n"
                f"Raw content: {raw_content}"
            )

        try:

            blueprint = Blueprint.model_validate(
                parsed_json
            )

        except Exception as e:

            raise ValueError(
                f"Blueprint failed schema validation: "
                f"{e}\nRaw JSON: {parsed_json}"
            )

        return blueprint

    # ========================================================
    # LANGGRAPH NODE
    # ========================================================

    def run(
        self,
        state: PaperState
    ) -> PaperState:

        teacher_request = state[
            "teacher_request"
        ]

        try:

            blueprint = self.create_blueprint(
                teacher_request
            )

            return {
                "blueprint": blueprint.model_dump(),
                "status": "blueprint_created"
            }

        except Exception as e:

            return {
                "error": str(e),
                "status": "blueprint_failed"
            }


# ============================================================
# BUILD BLUEPRINT GRAPH
# ============================================================

def build_blueprint_graph():

    agent = BlueprintAgent()

    graph = StateGraph(
        PaperState
    )

    graph.add_node(
        "blueprint_agent",
        agent.run
    )

    graph.add_edge(
        START,
        "blueprint_agent"
    )

    graph.add_edge(
        "blueprint_agent",
        END
    )

    return graph.compile()