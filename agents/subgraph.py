from typing import TypedDict, Any

from langgraph.graph import StateGraph, START, END
from langgraph.types import interrupt
from langgraph.checkpoint.memory import MemorySaver

from agents.blueprint_agent import BlueprintAgent
from agents.intelligence_agent import QuestionIntelligenceAgent
from agents.paper_generation import PaperGenerationAgent
from agents.evaluation_agent import EvaluationAgent
from agents.paper_output import generate_paper_pdf


MAX_RETRIES = 3


class PaperPipelineState(TypedDict, total=False):

    # Input
    teacher_request: str
    question_bank_path: str

    # Blueprint
    blueprint: dict[str, Any]

    # Question Intelligence
    questions: list[dict[str, Any]]
    inventory: dict[str, Any]
    invalid_questions: list[dict[str, Any]]

    # Generation
    paper: dict[str, Any]
    paper_state: dict[str, Any]

    # Evaluation
    evaluation: dict[str, Any]

    # Human Review
    human_decision: dict[str, Any]

    # Output
    pdf_path: str

    # Control
    retry_count: int
    status: str
    error: str


# ------------------------------------------------------------
# Agents
# ------------------------------------------------------------

blueprint_agent = BlueprintAgent()

question_intelligence_agent = (
    QuestionIntelligenceAgent()
)

paper_generation_agent = (
    PaperGenerationAgent()
)

evaluation_agent = (
    EvaluationAgent()
)


# ------------------------------------------------------------
# Nodes
# ------------------------------------------------------------

def run_blueprint(
    state: PaperPipelineState
):

    return blueprint_agent.run(state)


def run_question_intelligence(
    state: PaperPipelineState
):

    return question_intelligence_agent.run(
        state
    )


def run_generation(
    state: PaperPipelineState
):

    return paper_generation_agent.run(
        state
    )


def run_evaluation(
    state: PaperPipelineState
):

    return evaluation_agent.run(
        state
    )


# ------------------------------------------------------------
# PDF GENERATION
# ------------------------------------------------------------

def generate_pdf(
    state: PaperPipelineState
):

    paper_state = state.get(
        "paper_state"
    )

    if not paper_state:

        raise ValueError(
            "paper_state is missing. "
            "Cannot generate PDF."
        )

    pdf_path = generate_paper_pdf(
        paper_state,
        output_path="generated_question_paper.pdf",
    )

    return {
        "pdf_path": pdf_path,
        "status": "pdf_generated",
    }


# ------------------------------------------------------------
# Human Review
# ------------------------------------------------------------

def human_review(
    state: PaperPipelineState
):

    decision = interrupt({

        "type": "paper_review",

        "message": (
            "Automatic evaluation could not "
            "approve the paper. Teacher review "
            "is required."
        ),

        "paper": state.get(
            "paper"
        ),

        "paper_state": state.get(
            "paper_state"
        ),

        "evaluation": state.get(
            "evaluation"
        ),
    })

    return {

        "status": (
            "human_review_completed"
        ),

        "human_decision": decision,
    }


# ------------------------------------------------------------
# Routing after evaluation
# ------------------------------------------------------------

def route_after_evaluation(
    state: PaperPipelineState
):

    evaluation = state.get(
        "evaluation",
        {}
    )

    route = evaluation.get(
        "route"
    )

    retry_count = state.get(
        "retry_count",
        0
    )

    if route == "PASS":

        return "generate_pdf"

    if retry_count >= MAX_RETRIES:

        return "human_review"

    if route == "REGENERATE_QUESTION":

        return "generation"
    if route == "REPAIR_PAPER":

        return "generation"


    if route == "SECOND_EVALUATION":

        return "evaluation"

    # --------------------------------------------------------
    # Unknown / unexpected route
    # --------------------------------------------------------

    return "human_review"


# ------------------------------------------------------------
# Build Graph
# ------------------------------------------------------------

def build_graph():

    graph = StateGraph(
        PaperPipelineState
    )

    # --------------------------------------------------------
    # Nodes
    # --------------------------------------------------------

    graph.add_node(
        "blueprint",
        run_blueprint
    )

    graph.add_node(
        "question_intelligence",
        run_question_intelligence
    )

    graph.add_node(
        "generation",
        run_generation
    )

    graph.add_node(
        "evaluation",
        run_evaluation
    )

    graph.add_node(
        "human_review",
        human_review
    )

    graph.add_node(
        "generate_pdf",
        generate_pdf
    )

    # --------------------------------------------------------
    # Forward Pipeline
    # --------------------------------------------------------

    graph.add_edge(
        START,
        "blueprint"
    )

    graph.add_edge(
        "blueprint",
        "question_intelligence"
    )

    graph.add_edge(
        "question_intelligence",
        "generation"
    )

    graph.add_edge(
        "generation",
        "evaluation"
    )

    # --------------------------------------------------------
    # Evaluation Routing
    # --------------------------------------------------------

    graph.add_conditional_edges(

        "evaluation",

        route_after_evaluation,

        {
            "generate_pdf":
                "generate_pdf",

            "generation":
                "generation",

            "evaluation":
                "evaluation",

            "human_review":
                "human_review",
        }
    )


    graph.add_edge(
        "human_review",
        END
    )
    graph.add_edge(
        "generate_pdf",
        END
    )
    checkpointer = MemorySaver()
    return graph.compile(
        checkpointer=checkpointer
    )