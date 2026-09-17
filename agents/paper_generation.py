from typing import Any, Dict, List, Optional

from langgraph.graph import StateGraph, START, END

from agents.models import (
    Question,
    Blueprint,
    QuestionSlot,
    TradeoffDecision,
    PaperState,
    GenerationGraphState,
)

from agents.text_utils import normalize_question_type
from agents.Question_bank import load_question_bank, section_for_question_type
from .slot_allocator import build_question_slots
from .candidate_selection import get_candidates, question_matches_slot
from agents.Validation import validate_generated_question, validate_final_paper
from agents.Llm_client import LLMClient


MAX_GENERATION_STEPS = 30
MAX_LLM_RETRIES = 3


class PaperGenerationAgent:

    def __init__(self, api_key=None, model=None):
        self.llm = LLMClient(api_key=api_key, model=model)

    def detect_conflicts(self, paper, blueprint, current_slot=None, question_bank=None):

        conflicts = []

        if paper.marks_used > blueprint.total_marks:
            conflicts.append({
                "type": "total_marks",
                "message": "Total marks exceeded."
            })

        if current_slot is not None:

            matching_count = 0

            if question_bank is not None:

                selected_ids = {q.id for q in paper.selected_questions}

                matching_count = sum(
                    1 for q in question_bank
                    if q.id not in selected_ids
                    and question_matches_slot(q, current_slot)
                )

            if matching_count == 0:
                conflicts.append({
                    "type": "slot_gap",
                    "topic": current_slot.topic,
                    "difficulty": current_slot.difficulty,
                    "question_type": current_slot.question_type,
                    "marks": current_slot.marks,
                    "message": "No exact question-bank question exists for the current allocated slot.",
                    "resolution": "Generate exactly this slot using AI."
                })

        return conflicts

    def organize_paper(self, paper, blueprint):

        sections = {}

        for question in paper.selected_questions:
            section = section_for_question_type(question.question_type)
            if section not in sections:
                sections[section] = []
            sections[section].append(question.model_dump())

        return {
            "title": "Generated Question Paper",
            "total_marks": paper.marks_used,
            "target_marks": blueprint.total_marks,
            "sections": sections,
            "questions": [q.model_dump() for q in paper.selected_questions]
        }

    def initialize_node(self, state):

        state.paper.total_marks = state.blueprint.total_marks

        slots = build_question_slots(state.blueprint, state.question_bank)

        current_slot = slots[0] if slots else None

        return {"paper": state.paper, "slots": slots, "current_slot": current_slot}

    def candidates_node(self, state):

        candidates = get_candidates(
            state.paper, state.blueprint, state.question_bank, state.current_slot
        )

        print("\nCURRENT SLOT:", state.current_slot)
        print("EXACT CANDIDATES:", [q.id for q in candidates])

        return {"candidates": candidates}

    def make_decision_node(self, state):

        if state.current_slot is None:
            return {"last_decision": TradeoffDecision(
                action="finish",
                reason="All allocated slots have been processed."
            )}

        if state.candidates:
            decision = self.llm.llm_tradeoff_decision(state.candidates, state.paper, state.blueprint)
        else:
            decision = TradeoffDecision(
                action="generate",
                reason="No exact question-bank candidate exists for the current allocated slot."
            )

        return {"last_decision": decision}

    def advance_slot(self, state):

        if state.slots:
            state.slots.pop(0)

        state.current_slot = state.slots[0] if state.slots else None

    def select_question_node(self, state):

        decision = state.last_decision

        if decision is None or decision.question_id is None:
            return {}

        selected = None

        for question in state.candidates:
            if question.id == decision.question_id:
                selected = question
                break

        if selected is None:
            return {}

        if state.current_slot is not None:
            if not question_matches_slot(selected, state.current_slot):
                raise RuntimeError("Safety violation: selected question does not match current slot.")

        state.paper.selected_questions.append(selected)
        state.paper.marks_used += selected.marks
        state.paper.step += 1

        self.advance_slot(state)

        return {"paper": state.paper, "slots": state.slots, "current_slot": state.current_slot}

    def generate_missing_question_node(self, state):

        if state.current_slot is None:
            return {}

        slot = state.current_slot

        reason = (
            state.last_decision.reason
            if state.last_decision
            else "Question bank has no exact candidate for this allocated slot."
        )

        generated_question = None
        last_error = None

        for attempt in range(1, MAX_LLM_RETRIES + 1):

            try:

                generated_question = self.llm.generate_question(
                    state.blueprint, state.paper, slot=slot, reason=reason
                )

                errors = validate_generated_question(
                    generated_question, state.paper, state.blueprint, slot=slot
                )

                if errors:
                    raise ValueError("; ".join(errors))

                existing_ids = {q.id for q in state.question_bank}
                existing_ids.update(q.id for q in state.paper.selected_questions)

                base = f"{slot.topic[:3].upper()}-AI"
                counter = 1
                new_id = f"{base}-{counter:03d}"

                while new_id in existing_ids:
                    counter += 1
                    new_id = f"{base}-{counter:03d}"

                generated_question.id = new_id

                break

            except Exception as error:
                last_error = error
                generated_question = None
                print(f"Generation attempt {attempt}/{MAX_LLM_RETRIES} failed: {error}")

        if generated_question is None:
            raise RuntimeError(
                f"Unable to generate an exact-slot question after {MAX_LLM_RETRIES} attempts: {last_error}"
            )

        state.question_bank.append(generated_question)
        state.paper.selected_questions.append(generated_question)
        state.paper.marks_used += generated_question.marks
        state.paper.step += 1

        self.advance_slot(state)

        return {
            "paper": state.paper,
            "question_bank": state.question_bank,
            "last_generated_question": generated_question,
            "slots": state.slots,
            "current_slot": state.current_slot
        }

    def conflict_analysis_node(self, state):

        conflicts = self.detect_conflicts(
            state.paper, state.blueprint, state.current_slot, state.question_bank
        )

        print("\n========== CONFLICT ANALYSIS ==========")
        if conflicts:
            for conflict in conflicts:
                print(conflict)
        else:
            print("No explicit conflicts detected.")
        print("========================================\n")

        return {"conflicts": conflicts}

    def relaxation_node(self, state):

        conflicts = list(state.conflicts)

        conflicts.append({
            "type": "controlled_resolution",
            "message": "The exact allocated slot cannot be satisfied from the question bank.",
            "action": "Keep topic, difficulty, question type, and marks strict; use AI generation for the exact missing slot."
        })

        return {"conflicts": conflicts}

    def route_after_candidates(self, state):

        if state.current_slot is None:
            if state.paper.marks_used == state.blueprint.total_marks:
                return "organize"
            return "conflict"

        if state.paper.step >= MAX_GENERATION_STEPS:
            print("WARNING: Maximum generation steps reached.")
            return "organize"

        if state.candidates:
            return "decision"

        return "conflict"

    def route_after_decision(self, state):

        decision = state.last_decision

        if decision is None:
            return "candidates"

        if (
            decision.action == "finish"
            and state.current_slot is None
            and state.paper.marks_used == state.blueprint.total_marks
        ):
            return "organize"

        if decision.action == "select":
            return "select"

        if decision.action == "generate":
            return "generate"

        return "candidates"

    def route_after_conflict(self, state):
        return "relax"

    def route_after_relaxation(self, state):
        return "generate"

    def build_graph(self):

        graph = StateGraph(GenerationGraphState)

        graph.add_node("initialize", self.initialize_node)
        graph.add_node("candidates", self.candidates_node)
        graph.add_node("decision", self.make_decision_node)
        graph.add_node("select", self.select_question_node)
        graph.add_node("generate", self.generate_missing_question_node)
        graph.add_node("conflict", self.conflict_analysis_node)
        graph.add_node("relax", self.relaxation_node)
        graph.add_node("organize", lambda state: state)

        graph.add_edge(START, "initialize")
        graph.add_edge("initialize", "candidates")

        graph.add_conditional_edges(
            "candidates", self.route_after_candidates,
            {"decision": "decision", "conflict": "conflict", "organize": "organize"}
        )

        graph.add_conditional_edges(
            "decision", self.route_after_decision,
            {"select": "select", "generate": "generate", "organize": "organize", "candidates": "candidates"}
        )

        graph.add_edge("select", "candidates")
        graph.add_edge("generate", "candidates")

        graph.add_conditional_edges("conflict", self.route_after_conflict, {"relax": "relax"})
        graph.add_conditional_edges("relax", self.route_after_relaxation, {"generate": "generate"})

        graph.add_edge("organize", END)

        return graph.compile()

    def run(self, state):

        question_bank_path = state.get("question_bank_path")

        if not question_bank_path:
            raise ValueError("question_bank_path is missing from pipeline state.")

        blueprint_data = state.get("blueprint")

        if not blueprint_data:
            raise ValueError("blueprint is missing from pipeline state.")

        if isinstance(blueprint_data, dict):
            if "blueprint" in blueprint_data:
                blueprint_data = blueprint_data["blueprint"]

        question_bank = load_question_bank(question_bank_path)
        blueprint = Blueprint(**blueprint_data)
        paper = PaperState(total_marks=blueprint.total_marks)

        initial_state = GenerationGraphState(
            question_bank=question_bank, blueprint=blueprint, paper=paper
        )

        graph = self.build_graph()
        result = graph.invoke(initial_state)

        final_paper_state = result["paper"]
        paper_output = self.organize_paper(final_paper_state, blueprint)

        final_errors = validate_final_paper(final_paper_state, blueprint)

        if result.get("current_slot") is not None:
            final_errors.append("Some allocated question slots remain unfilled.")

        if final_errors:
            paper_output["generation_errors"] = final_errors
            return {
                "paper": paper_output,
                "paper_state": final_paper_state.model_dump(),
                "status": "generation_incomplete",
                "conflicts": result.get("conflicts", [])
            }

        return {
            "paper": paper_output,
            "paper_state": final_paper_state.model_dump(),
            "status": "generation_complete",
            "conflicts": result.get("conflicts", [])
        }


PaperGenerator = PaperGenerationAgent