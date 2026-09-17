import json
import re
from typing import Any, Dict, List, Optional


# ============================================================
# NORMALIZATION HELPERS
# ============================================================

def normalize_question_type(value: str) -> str:

    normalized = str(value or "").strip().lower()

    normalized = normalized.replace("_", " ")
    normalized = normalized.replace("-", " ")
    normalized = re.sub(r"\s+", " ", normalized)

    compact = normalized.replace(" ", "")

    aliases = {
        "mcq": "mcq",
        "multiple choice": "mcq",
        "multiplechoice": "mcq",

        "short": "short",
        "short answer": "short",
        "shortanswer": "short",

        "long": "long",
        "long answer": "long",
        "longanswer": "long",
    }

    if normalized in aliases:
        return aliases[normalized]

    if compact in aliases:
        return aliases[compact]

    return normalized


def normalize_options(options: Any) -> Optional[List[str]]:

    if options is None:
        return None

    if isinstance(options, str):

        try:
            parsed = json.loads(options)

            if isinstance(parsed, list):
                options = parsed
            else:
                options = [options]

        except Exception:
            options = [options]

    if not isinstance(options, list):
        return [str(options)]

    result: List[str] = []

    for option in options:

        if isinstance(option, str):

            result.append(option.strip())

        elif isinstance(option, dict):

            text = option.get("text")
            label = option.get("label")

            if text is not None:

                if label:
                    result.append(
                        f"{str(label).strip()}. "
                        f"{str(text).strip()}"
                    )

                else:
                    result.append(
                        str(text).strip()
                    )

            elif "value" in option:

                result.append(
                    str(option["value"]).strip()
                )

            else:

                result.append(
                    json.dumps(
                        option,
                        ensure_ascii=False
                    )
                )

        else:

            result.append(
                str(option).strip()
            )

    return result


def extract_json_object(raw_text: str) -> str:

    if not raw_text:
        raise ValueError(
            "Empty model response."
        )

    text = raw_text.strip()

    text = re.sub(
        r"^```(?:json)?\s*",
        "",
        text,
        flags=re.IGNORECASE
    )

    text = re.sub(
        r"\s*```$",
        "",
        text
    )

    text = text.strip()

    start = text.find("{")
    end = text.rfind("}")

    if start == -1 or end == -1 or end <= start:

        raise ValueError(
            "No JSON object found in model output: "
            f"{text[:500]}"
        )

    return text[start:end + 1]


def repair_invalid_json_backslashes(text: str) -> str:

    output: List[str] = []
    i = 0

    valid_simple_escapes = {
        '"',
        "\\",
        "/",
        "b",
        "f",
        "n",
        "r",
        "t",
    }

    while i < len(text):

        char = text[i]

        if char != "\\":
            output.append(char)
            i += 1
            continue

        if i + 1 >= len(text):

            output.append("\\\\")
            i += 1
            continue

        next_char = text[i + 1]

        if next_char in valid_simple_escapes:

            output.append("\\")
            output.append(next_char)

            i += 2
            continue

        if next_char == "u":

            possible_hex = text[i + 2:i + 6]

            if (
                len(possible_hex) == 4
                and re.fullmatch(
                    r"[0-9a-fA-F]{4}",
                    possible_hex
                )
            ):

                output.append(
                    text[i:i + 6]
                )

                i += 6
                continue

        output.append("\\\\")
        i += 1

    return "".join(output)


def parse_model_json(raw_text: str) -> Dict[str, Any]:

    json_text = extract_json_object(raw_text)

    try:

        parsed = json.loads(json_text)

        if not isinstance(parsed, dict):

            raise ValueError(
                "Model response must be a JSON object."
            )

        return parsed

    except json.JSONDecodeError:

        repaired = repair_invalid_json_backslashes(
            json_text
        )

        try:

            parsed = json.loads(repaired)

            if not isinstance(parsed, dict):

                raise ValueError(
                    "Model response must be a JSON object."
                )

            return parsed

        except json.JSONDecodeError as second_error:

            raise ValueError(
                "Model returned invalid JSON.\n"
                f"Original error: {second_error}\n"
                f"Output:\n{json_text[:1500]}"
            )