import json
import re

with open("questions.json", "r", encoding="utf-8") as f:
    pages = json.load(f)

full_text = "\n".join(p["text"] for p in pages)
lines = [l.strip() for l in full_text.splitlines() if l.strip()]

id_meta_pattern = re.compile(
    r"^id:\s*(\S+)\s*\|\s*difficulty:\s*(\w+)\s*\|\s*type:\s*(\w+)$"
)
statement_pattern = re.compile(r"^(.*?)\[(\d+)\s*marks?\]$")
answer_row_pattern = re.compile(
    r"^([A-Z]{3}-[A-Z0-9]+)\s+(\w+)\s+(easy|medium|hard)\s+(mcq|short|long)\s+(\d+)\s+(.*)$"
)
option_pattern = re.compile(r"^([A-F])\.\s*(.+)$")

# ---- Pass 1: parse question statements + options from pages 2-6 ----
questions = {}
i = 0
while i < len(lines):
    m = statement_pattern.match(lines[i])
    if m and i + 1 < len(lines) and id_meta_pattern.match(lines[i + 1]):
        statement_text = m.group(1).strip()
        marks = int(m.group(2))
        meta = id_meta_pattern.match(lines[i + 1])
        qid, difficulty, qtype = meta.group(1), meta.group(2).lower(), meta.group(3).lower()

        options = []
        j = i + 2
        while j < len(lines):
            om = option_pattern.match(lines[j])
            if om:
                options.append(om.group(2).strip())
                j += 1
            else:
                break

        questions[qid] = {
            "id": qid,
            "text": statement_text,
            "topic": None,  # filled from answer key
            "difficulty": difficulty,
            "question_type": qtype,
            "marks": marks,
            "options": options if options else None,
            "answer": None,
        }
        i = j
    else:
        i += 1

# ---- Pass 2: parse Answer Key table for topic + answer (source of truth) ----
for line in lines:
    m = answer_row_pattern.match(line)
    if m:
        qid, topic, difficulty, qtype, marks, answer = m.groups()
        answer = re.sub(r"Page \d+.*$", "", answer).strip()  # strip page-break junk
        if qid in questions:
            questions[qid]["topic"] = topic
            questions[qid]["answer"] = answer
        else:
            # answer key had a row not matched in pass 1 - keep it anyway
            questions[qid] = {
                "id": qid,
                "text": f"{qid} question",
                "topic": topic,
                "difficulty": difficulty.lower(),
                "question_type": qtype.lower(),
                "marks": int(marks),
                "options": None,
                "answer": answer,
            }

result = list(questions.values())
with open("question_bank.json", "w", encoding="utf-8") as f:
    json.dump(result, f, indent=2, ensure_ascii=False)

print(f"Parsed {len(result)} questions -> question_bank.json")
missing_topic = [q["id"] for q in result if not q["topic"]]
if missing_topic:
    print("WARNING - missing topic for:", missing_topic)