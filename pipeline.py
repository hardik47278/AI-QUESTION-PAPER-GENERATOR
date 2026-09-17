from typing import TypedDict, Any

from langgraph.graph import StateGraph, START, END
from langgraph.checkpoint.memory import MemorySaver

from agents.blueprint_agent import BlueprintAgent
from agents.intelligence_agent import QuestionIntelligenceAgent
from agents.paper_generation import PaperGenerationAgent
from agents.evalaution_agent import EvaluationAgent
from agents.paper_output import generate_paper_pdf


MAX_RETRIES = 3


class PaperPipelineState(TypedDict, total=False):
    teacher_request: str
    question_bank_path: str

    blueprint: dict[str, Any]

    questions: list[dict[str, Any]]
    inventory: dict[str, Any]
    invalid_questions: list[dict[str, Any]]

    paper: dict[str, Any]
    paper_state: dict[str, Any]

    evaluation: dict[str, Any]

    pdf_path: str

    retry_count: int

    status: str
    error: str


# ------------------------------------------------------------
# AGENTS
# ------------------------------------------------------------

blueprint_agent = BlueprintAgent()
question_intelligence_agent = QuestionIntelligenceAgent()
paper_generation_agent = PaperGenerationAgent()
evaluation_agent = EvaluationAgent()


# ------------------------------------------------------------
# BLUEPRINT
# ------------------------------------------------------------

def run_blueprint(state: PaperPipelineState):

    result = blueprint_agent.run(state)

    print("BLUEPRINT RESULT:", result)

    return result


# ------------------------------------------------------------
# QUESTION INTELLIGENCE
# ------------------------------------------------------------

def run_question_intelligence(state: PaperPipelineState):

    result = question_intelligence_agent.run(state)

    print(
        "QUESTION INTELLIGENCE RESULT status:",
        result.get("status")
    )

    return result


# ------------------------------------------------------------
# GENERATION
# ------------------------------------------------------------

def run_generation(state: PaperPipelineState):

    retry_count = state.get("retry_count", 0)

    print(
        f"\nQUESTION PAPER GENERATION "
        f"(attempt {retry_count + 1}/{MAX_RETRIES + 1})"
    )

    result = paper_generation_agent.run(state)

    return result


# ------------------------------------------------------------
# EVALUATION
# ------------------------------------------------------------

def run_evaluation(state: PaperPipelineState):

    result = evaluation_agent.run(state)

    print(
        "\nEVALUATION RESULT:",
        result.get("evaluation", result)
    )

    return result


# ------------------------------------------------------------
# PDF GENERATION
# ------------------------------------------------------------

def generate_pdf(state: PaperPipelineState):

    paper_state = state.get("paper_state")

    if not paper_state:
        raise ValueError(
            "paper_state is missing. Cannot generate PDF."
        )

    pdf_path = generate_paper_pdf(
        paper_state,
        output_path="generated_question_paper.pdf",
    )

    print("\nPDF GENERATED:", pdf_path)

    return {
        "pdf_path": pdf_path,
        "status": "pdf_generated",
    }


# ------------------------------------------------------------
# PIPELINE FAILURE
# ------------------------------------------------------------

def pipeline_failed(state: PaperPipelineState):

    status = state.get(
        "status",
        "pipeline_failed"
    )

    error = state.get(
        "error",
        "Pipeline failed with no error message."
    )

    print(
        "\nPIPELINE FAILED"
    )

    print(
        "STATUS:",
        status
    )

    print(
        "ERROR:",
        error
    )

    return {
        "status": status,
        "error": error,
    }


# ------------------------------------------------------------
# AUTOMATIC RETRY COUNTER
# ------------------------------------------------------------

def register_retry(state: PaperPipelineState):

    retry_count = state.get(
        "retry_count",
        0
    )

    new_retry_count = retry_count + 1

    print(
        f"\nAUTOMATIC REPAIR/REGENERATION "
        f"ATTEMPT: {new_retry_count}/{MAX_RETRIES}"
    )

    return {
        "retry_count": new_retry_count
    }


# ------------------------------------------------------------
# ROUTING AFTER BLUEPRINT
# ------------------------------------------------------------

def route_after_blueprint(
    state: PaperPipelineState
):

    if (
        state.get("status") == "blueprint_failed"
        or "blueprint" not in state
    ):
        return "failed"

    return "question_intelligence"


# ------------------------------------------------------------
# ROUTING AFTER QUESTION INTELLIGENCE
# ------------------------------------------------------------

def route_after_intelligence(
    state: PaperPipelineState
):

    if (
        state.get("status")
        == "question_intelligence_failed"
    ):
        return "failed"

    return "generation"


# ------------------------------------------------------------
# ROUTING AFTER EVALUATION
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

    # --------------------------------------------------------
    # PAPER PASSED
    # --------------------------------------------------------

    if route == "PASS":

        print(
            "\nEVALUATION PASSED."
        )

        return "generate_pdf"

    # --------------------------------------------------------
    # RETRY LIMIT REACHED
    # --------------------------------------------------------

    if retry_count >= MAX_RETRIES:
        print("\nMAXIMUM AUTOMATIC RETRIES REACHED.")
        print("Generating PDF with the latest generated paper.")
        return "generate_pdf"

        

       

    # --------------------------------------------------------
    # REGENERATE QUESTION
    # --------------------------------------------------------

    if route == "REGENERATE_QUESTION":

        return "retry"

    # --------------------------------------------------------
    # REPAIR PAPER
    # --------------------------------------------------------

    if route == "REPAIR_PAPER":

        return "retry"

    # --------------------------------------------------------
    # SECOND EVALUATION
    # --------------------------------------------------------

    if route == "SECOND_EVALUATION":

        return "evaluation"

    # --------------------------------------------------------
    # UNKNOWN ROUTE
    # --------------------------------------------------------

    print(
        "\nUNKNOWN EVALUATION ROUTE:",
        route
    )

    return "failed"


# ------------------------------------------------------------
# BUILD GRAPH
# ------------------------------------------------------------

def build_graph():

    graph = StateGraph(
        PaperPipelineState
    )

    # --------------------------------------------------------
    # NODES
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
        "register_retry",
        register_retry
    )

    graph.add_node(
        "generate_pdf",
        generate_pdf
    )

    graph.add_node(
        "failed",
        pipeline_failed
    )

    # --------------------------------------------------------
    # START
    # --------------------------------------------------------

    graph.add_edge(
        START,
        "blueprint"
    )

    # --------------------------------------------------------
    # BLUEPRINT
    # --------------------------------------------------------

    graph.add_conditional_edges(
        "blueprint",
        route_after_blueprint,
        {
            "question_intelligence":
                "question_intelligence",

            "failed":
                "failed",
        },
    )

    # --------------------------------------------------------
    # QUESTION INTELLIGENCE
    # --------------------------------------------------------

    graph.add_conditional_edges(
        "question_intelligence",
        route_after_intelligence,
        {
            "generation":
                "generation",

            "failed":
                "failed",
        },
    )

    # --------------------------------------------------------
    # GENERATION → EVALUATION
    # --------------------------------------------------------

    graph.add_edge(
        "generation",
        "evaluation"
    )

    # --------------------------------------------------------
    # EVALUATION ROUTING
    # --------------------------------------------------------

    graph.add_conditional_edges(
        "evaluation",
        route_after_evaluation,
        {
            "generate_pdf":
                "generate_pdf",

            "retry":
                "register_retry",

            "evaluation":
                "evaluation",

            "failed":
                "failed",
        },
    )

    # --------------------------------------------------------
    # RETRY → GENERATION
    # --------------------------------------------------------

    graph.add_edge(
        "register_retry",
        "generation"
    )

    # --------------------------------------------------------
    # END STATES
    # --------------------------------------------------------

    graph.add_edge(
        "generate_pdf",
        END
    )

    graph.add_edge(
        "failed",
        END
    )

    # --------------------------------------------------------
    # CHECKPOINTING
    # --------------------------------------------------------

    checkpointer = MemorySaver()

    return graph.compile(
        checkpointer=checkpointer
    )