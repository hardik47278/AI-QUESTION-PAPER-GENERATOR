from pathlib import Path
from typing import Any
import re

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_LEFT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import (
    SimpleDocTemplate,
    Paragraph,
    Spacer,
    Table,
    TableStyle,
)


def _escape(text: Any) -> str:
    """Safely convert arbitrary values into ReportLab paragraph text."""

    if text is None:
        return ""

    text = str(text)

    return (
        text.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
    )


def _question_number(question_id: str, fallback: int) -> str:
    """
    Use a numeric suffix when the generated ID contains one.
    Otherwise use paper order.
    """

    match = re.search(r"(\d+)$", str(question_id))

    return match.group(1) if match else str(fallback)


def generate_paper_pdf(
    paper_state: dict[str, Any],
    output_path: str = "generated_question_paper.pdf",
    title: str = "QUESTION PAPER",
    subtitle: str | None = None,
) -> str:

    output = Path(output_path).resolve()
    output.parent.mkdir(parents=True, exist_ok=True)

    # ---------------------------------------------------------
    # READ PAPER STATE
    # ---------------------------------------------------------

    questions = paper_state.get(
        "selected_questions",
        []
    )

    sections = paper_state.get(
        "sections",
        {}
    )

    instructions = paper_state.get(
        "instructions",
        []
    )

    # ---------------------------------------------------------
    # QUESTION MAP
    # ---------------------------------------------------------

    question_map = {}

    for q in questions:

        if isinstance(q, dict):

            qid = q.get("id")

            if qid:
                question_map[qid] = q

    # ---------------------------------------------------------
    # STYLES
    # ---------------------------------------------------------

    styles = getSampleStyleSheet()

    title_style = ParagraphStyle(
        "PaperTitle",
        parent=styles["Title"],
        fontName="Helvetica-Bold",
        fontSize=18,
        leading=22,
        alignment=TA_CENTER,
        spaceAfter=5 * mm,
    )

    subtitle_style = ParagraphStyle(
        "PaperSubtitle",
        parent=styles["Normal"],
        fontName="Helvetica",
        fontSize=10,
        leading=13,
        alignment=TA_CENTER,
        spaceAfter=4 * mm,
    )

    meta_style = ParagraphStyle(
        "Meta",
        parent=styles["Normal"],
        fontName="Helvetica",
        fontSize=10,
        leading=13,
        alignment=TA_LEFT,
    )

    instruction_style = ParagraphStyle(
        "Instruction",
        parent=styles["Normal"],
        fontName="Helvetica",
        fontSize=10,
        leading=14,
        leftIndent=4 * mm,
        spaceAfter=1.5 * mm,
    )

    section_style = ParagraphStyle(
        "Section",
        parent=styles["Heading2"],
        fontName="Helvetica-Bold",
        fontSize=13,
        leading=16,
        spaceBefore=5 * mm,
        spaceAfter=3 * mm,
    )

    question_style = ParagraphStyle(
        "Question",
        parent=styles["Normal"],
        fontName="Helvetica",
        fontSize=10.5,
        leading=15,
        spaceAfter=2 * mm,
    )

    option_style = ParagraphStyle(
        "Option",
        parent=styles["Normal"],
        fontName="Helvetica",
        fontSize=10,
        leading=14,
        leftIndent=8 * mm,
        spaceAfter=1 * mm,
    )

    # ---------------------------------------------------------
    # PDF DOCUMENT
    # ---------------------------------------------------------

    doc = SimpleDocTemplate(
        str(output),
        pagesize=A4,
        rightMargin=18 * mm,
        leftMargin=18 * mm,
        topMargin=16 * mm,
        bottomMargin=16 * mm,
        title=title,
        author="Paper Generation Pipeline",
    )

    story = []

    # ---------------------------------------------------------
    # HEADER
    # ---------------------------------------------------------

    story.append(
        Paragraph(
            _escape(title),
            title_style
        )
    )

    if subtitle:

        story.append(
            Paragraph(
                _escape(subtitle),
                subtitle_style,
            )
        )

    total_marks = paper_state.get(
        "marks_used",
        0
    )

    metadata = Table(
        [
            [
                Paragraph(
                    "<b>Total Marks:</b> "
                    + _escape(total_marks),
                    meta_style,
                ),

                Paragraph(
                    "<b>Questions:</b> "
                    + _escape(len(questions)),
                    meta_style,
                ),
            ]
        ],
        colWidths=[
            85 * mm,
            85 * mm
        ],
    )

    metadata.setStyle(
        TableStyle(
            [
                (
                    "BOX",
                    (0, 0),
                    (-1, -1),
                    0.8,
                    colors.black,
                ),
                (
                    "INNERGRID",
                    (0, 0),
                    (-1, -1),
                    0.5,
                    colors.black,
                ),
                (
                    "VALIGN",
                    (0, 0),
                    (-1, -1),
                    "MIDDLE",
                ),
                (
                    "LEFTPADDING",
                    (0, 0),
                    (-1, -1),
                    4 * mm,
                ),
                (
                    "RIGHTPADDING",
                    (0, 0),
                    (-1, -1),
                    4 * mm,
                ),
                (
                    "TOPPADDING",
                    (0, 0),
                    (-1, -1),
                    3 * mm,
                ),
                (
                    "BOTTOMPADDING",
                    (0, 0),
                    (-1, -1),
                    3 * mm,
                ),
            ]
        )
    )

    story.append(metadata)

    story.append(
        Spacer(1, 5 * mm)
    )

    # ---------------------------------------------------------
    # INSTRUCTIONS
    # ---------------------------------------------------------

    if instructions:

        story.append(
            Paragraph(
                "Instructions",
                section_style,
            )
        )

        for instruction in instructions:

            story.append(
                Paragraph(
                    "• " + _escape(instruction),
                    instruction_style,
                )
            )

        story.append(
            Spacer(1, 2 * mm)
        )

    # ---------------------------------------------------------
    # BUILD ORDERED QUESTION LIST
    # ---------------------------------------------------------

    ordered_questions = []

    # First use sections if available.
    if isinstance(sections, dict):

        for section_questions in sections.values():

            if not isinstance(section_questions, list):
                continue

            for item in section_questions:

                # Case 1:
                # section contains question ID
                if isinstance(item, str):

                    question = question_map.get(item)

                    if question:
                        ordered_questions.append(
                            question
                        )

                # Case 2:
                # section contains complete question dict
                elif isinstance(item, dict):

                    qid = item.get("id")

                    if qid and qid in question_map:

                        ordered_questions.append(
                            question_map[qid]
                        )

                    else:

                        ordered_questions.append(
                            item
                        )

    # ---------------------------------------------------------
    # REMOVE DUPLICATES
    # ---------------------------------------------------------

    unique_questions = []

    seen_ids = set()

    for question in ordered_questions:

        qid = question.get("id")

        if qid:

            if qid in seen_ids:
                continue

            seen_ids.add(qid)

        unique_questions.append(
            question
        )

    ordered_questions = unique_questions

    # ---------------------------------------------------------
    # SAFETY FALLBACK
    # ---------------------------------------------------------

    if not ordered_questions:

        ordered_questions = questions

    # ---------------------------------------------------------
    # GROUP QUESTIONS BY SECTION
    # ---------------------------------------------------------

    section_groups = []

    if isinstance(sections, dict):

        used_ids = set()

        for section_title, section_questions in sections.items():

            group = []

            if not isinstance(section_questions, list):
                continue

            for item in section_questions:

                if isinstance(item, str):

                    question = question_map.get(item)

                elif isinstance(item, dict):

                    question = item

                else:

                    question = None

                if not question:
                    continue

                qid = question.get("id")

                if qid and qid in used_ids:
                    continue

                if qid:
                    used_ids.add(qid)

                group.append(question)

            if group:

                section_groups.append(
                    (
                        section_title,
                        group
                    )
                )

    # If sections were unusable, make one section.
    if not section_groups and ordered_questions:

        section_groups = [
            (
                "QUESTION PAPER",
                ordered_questions
            )
        ]

    # ---------------------------------------------------------
    # QUESTIONS
    # ---------------------------------------------------------

    number = 1

    for section_title, section_questions in section_groups:

        story.append(
            Paragraph(
                _escape(section_title),
                section_style,
            )
        )

        for question in section_questions:

            # -------------------------------------------------
            # QUESTION TEXT
            # -------------------------------------------------

            statement = question.get(
                "question",
                question.get(
                    "statement",
                    ""
                )
            )

            statement = _escape(
                statement
            )

            marks = question.get(
                "marks",
                ""
            )

            question_block = []

            question_block.append(
                Paragraph(
                    f"<b>{number}.</b> "
                    f"{statement} "
                    f"<b>[{_escape(marks)} marks]</b>",
                    question_style,
                )
            )

            # -------------------------------------------------
            # TOPIC / DIFFICULTY
            # -------------------------------------------------

            topic = question.get(
                "topic"
            )

            difficulty = question.get(
                "difficulty"
            )

            if topic or difficulty:

                details = []

                if topic:
                    details.append(
                        f"Topic: {_escape(topic)}"
                    )

                if difficulty:
                    details.append(
                        f"Difficulty: {_escape(difficulty)}"
                    )

                question_block.append(
                    Paragraph(
                        " | ".join(details),
                        option_style,
                    )
                )

            # -------------------------------------------------
            # MCQ OPTIONS
            # -------------------------------------------------

            options = question.get(
                "options"
            )

            if options:

                option_labels = [
                    "A",
                    "B",
                    "C",
                    "D",
                    "E",
                    "F",
                ]

                for index, option in enumerate(options):

                    if index < len(option_labels):

                        label = option_labels[index]

                    else:

                        label = str(
                            index + 1
                        )

                    question_block.append(
                        Paragraph(
                            f"{label}. "
                            f"{_escape(option)}",
                            option_style,
                        )
                    )

            # -------------------------------------------------
            # QUESTION BOX
            # -------------------------------------------------

            question_table = Table(
                [[question_block]],
                colWidths=[
                    170 * mm
                ],
            )

            question_table.setStyle(
                TableStyle(
                    [
                        (
                            "BOX",
                            (0, 0),
                            (-1, -1),
                            0.4,
                            colors.black,
                        ),
                        (
                            "LEFTPADDING",
                            (0, 0),
                            (-1, -1),
                            4 * mm,
                        ),
                        (
                            "RIGHTPADDING",
                            (0, 0),
                            (-1, -1),
                            4 * mm,
                        ),
                        (
                            "TOPPADDING",
                            (0, 0),
                            (-1, -1),
                            3 * mm,
                        ),
                        (
                            "BOTTOMPADDING",
                            (0, 0),
                            (-1, -1),
                            3 * mm,
                        ),
                    ]
                )
            )

            story.append(
                question_table
            )

            story.append(
                Spacer(
                    1,
                    3 * mm
                )
            )

            number += 1

    # ---------------------------------------------------------
    # FOOTER
    # ---------------------------------------------------------

    def add_page_number(
        canvas,
        doc
    ):

        canvas.saveState()

        canvas.setFont(
            "Helvetica",
            8
        )

        canvas.drawCentredString(
            A4[0] / 2,
            8 * mm,
            f"Page {doc.page}",
        )

        canvas.restoreState()

    # ---------------------------------------------------------
    # BUILD PDF
    # ---------------------------------------------------------

    doc.build(
        story,
        onFirstPage=add_page_number,
        onLaterPages=add_page_number,
    )

    return str(output)