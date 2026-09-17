from typing import Any, Dict, List, Optional, Literal

from pydantic import BaseModel, Field


class Question(BaseModel):
    id: str
    question: str
    question_type: str
    marks: int
    topic: str
    difficulty: str
    options: Optional[List[str]] = None
    correct_answer: Optional[str] = None
    explanation: Optional[str] = None


class GeneratedQuestion(BaseModel):
    id: str
    question: str
    question_type: str
    marks: int
    topic: str
    difficulty: str
    options: Optional[List[str]] = None
    correct_answer: Optional[str] = None
    explanation: Optional[str] = None


class DifficultyDistribution(BaseModel):
    easy: float = 0.0
    medium: float = 0.0
    hard: float = 0.0


class Blueprint(BaseModel):
    total_marks: int
    topic_distribution: Dict[str, float]
    difficulty_distribution: DifficultyDistribution
    question_type_distribution: Dict[str, float]
    hard_constraints: List[str] = Field(default_factory=list)
    soft_constraints: List[str] = Field(default_factory=list)
    preferences: Dict[str, Any] = Field(default_factory=dict)


class QuestionSlot(BaseModel):
    topic: str
    difficulty: str
    question_type: str
    marks: int


class TradeoffDecision(BaseModel):
    action: Literal["select", "generate", "finish"]
    question_id: Optional[str] = None
    reason: str = ""


class PaperState(BaseModel):
    selected_questions: List[Question] = Field(default_factory=list)
    marks_used: int = 0
    total_marks: int = 0
    step: int = 0
    status: str = "building"


class GenerationGraphState(BaseModel):
    question_bank: List[Question]
    blueprint: Blueprint
    paper: PaperState
    slots: List[QuestionSlot] = Field(default_factory=list)
    current_slot: Optional[QuestionSlot] = None
    candidates: List[Question] = Field(default_factory=list)
    conflicts: List[Dict[str, Any]] = Field(default_factory=list)
    last_generated_question: Optional[Question] = None
    last_decision: Optional[TradeoffDecision] = None