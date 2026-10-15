"""Natural-language interpretation using OpenAI, with a local rule-based fallback."""

from __future__ import annotations

import json
import os
import re
from datetime import date, datetime
from pathlib import Path
from typing import Any

from dotenv import load_dotenv
from openai import AuthenticationError, OpenAI, OpenAIError, PermissionDeniedError

from attendance_service import ALLOWED_OPERATIONS


PROJECT_DIR = Path(__file__).resolve().parent
load_dotenv(PROJECT_DIR / ".env")
load_dotenv(PROJECT_DIR / "api_key.env")
DATE_MONTHS = (
    "january|february|march|april|may|june|july|august|september|october|"
    "november|december|jan|feb|mar|apr|jun|jul|aug|sep|sept|oct|nov|dec"
)


def _extract_date(text: str) -> str | None:
    candidates: list[str] = []
    candidates.extend(re.findall(r"\b\d{4}-\d{2}-\d{2}\b", text))
    month_first = re.compile(
        rf"\b({DATE_MONTHS})\s+(\d{{1,2}})(?:,?\s+(\d{{4}}))?\b", re.IGNORECASE
    )
    day_first = re.compile(
        rf"\b(\d{{1,2}})\s+({DATE_MONTHS})(?:\s+(\d{{4}}))?\b", re.IGNORECASE
    )
    for match in month_first.finditer(text):
        candidates.append(
            f"{match.group(2)} {match.group(1)} {match.group(3) or '2026'}"
        )
    for match in day_first.finditer(text):
        candidates.append(
            f"{match.group(1)} {match.group(2)} {match.group(3) or '2026'}"
        )
    if len(candidates) != 1:
        return None
    candidate = candidates[0]
    try:
        if re.fullmatch(r"\d{4}-\d{2}-\d{2}", candidate):
            return date.fromisoformat(candidate).isoformat()
        for date_format in ("%d %B %Y", "%d %b %Y"):
            try:
                return datetime.strptime(candidate, date_format).date().isoformat()
            except ValueError:
                continue
    except ValueError:
        return None
    return None


def _extract_student(text: str) -> str | None:
    student_names = ("Aditya", "Sumit", "Lalit", "Anant", "Krishna")
    matches = [
        name for name in student_names if re.search(rf"\b{re.escape(name)}\b", text, re.IGNORECASE)
    ]
    if len(matches) == 1:
        return matches[0]
    if len(matches) > 1:
        return None

    for pattern in (
        r"\b(?:mark|set|remove|delete|check|show|get)\s+([A-Za-z][A-Za-z'-]*)",
        r"\b(?:was|is)\s+([A-Za-z][A-Za-z'-]*)",
    ):
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            candidate = match.group(1).rstrip("'")
            if candidate.casefold() not in {"attendance", "all", "class"}:
                return candidate
    return None


def parse_locally(text: str) -> dict[str, Any] | None:
    """Recognize the common supported requests without an AI API."""
    normalized = " ".join(text.lower().split())
    if re.search(r"\b(class|overall)\b.*\b(average|mean)\b|\b(average|mean)\b.*\bclass\b", normalized):
        return {"operation": "class_average"}
    if re.search(r"\b(show|display|list)\b.*\b(all|everyone)\b", normalized) or re.search(
        r"\battendance of all students\b", normalized
    ):
        return {"operation": "show_all"}

    student = _extract_student(text)
    parsed_date = _extract_date(text)
    if re.search(r"\b(remove|delete)\b", normalized):
        return {
            "operation": "remove_attendance",
            "student_name": student,
            "date": parsed_date,
        }

    status_match = re.search(r"\b(present|absent)\b", normalized)
    if status_match and re.search(r"\b(mark|set|record)\b", normalized):
        return {
            "operation": "mark_attendance",
            "student_name": student,
            "date": parsed_date,
            "status": status_match.group(1).capitalize(),
        }

    if re.search(r"\b(was|is|did)\b", normalized) and re.search(
        r"\b(present|absent|attend)\b", normalized
    ):
        return {"operation": "check_record", "student_name": student, "date": parsed_date}

    if student and re.search(r"\b(percentage|percent|attendance)\b", normalized):
        return {"operation": "check_percentage", "student_name": student}
    return None


def _model_instruction(text: str) -> tuple[dict[str, Any] | None, str | None]:
    api_key = os.getenv("AI_API_KEY", "").strip()
    if not api_key or api_key == "PASTE_YOUR_API_KEY_HERE":
        return None, None
    provider = os.getenv("AI_PROVIDER", "openai").strip().lower()
    if provider != "openai":
        return None, f"Unsupported AI_PROVIDER '{provider}'; set AI_PROVIDER=openai."
    prompt = f"""Interpret this attendance request and return one JSON object only.
Allowed operation values: {", ".join(sorted(ALLOWED_OPERATIONS))}.
For student operations, use the exact known student name and its roll number:
Aditya=101, Sumit=102, Lalit=103, Anant=104, Krishna=105.
For date operations, return date as YYYY-MM-DD, only within 2026-10-08 through 2026-10-14.
For mark_attendance, status must be Present or Absent.
Never calculate or return attendance statistics. Python calculates all statistics.
The JSON object shape is {{"operation":"...", "student_name":"...", "roll_no":"...", "date":"...", "status":"..."}}.
Only include fields needed by that operation. If the request is unsupported or ambiguous, return {{"operation":"unsupported"}}.
User request: {text}"""
    try:
        client = OpenAI(
            api_key=api_key,
            base_url=os.getenv("AI_BASE_URL") or None,
            max_retries=0,
            timeout=20.0,
        )
        completion = client.chat.completions.create(
            model=os.getenv("AI_MODEL", "gpt-4o-mini"),
            messages=[{"role": "user", "content": prompt}],
            response_format={"type": "json_object"},
            max_tokens=180,
        )
        content = completion.choices[0].message.content
        if not content:
            return None, "The AI returned an empty response."
        instruction = json.loads(content)
        if not isinstance(instruction, dict):
            return None, "The AI response was not a JSON instruction object."
        return instruction, None
    except (AuthenticationError, PermissionDeniedError):
        return None, "AI API authentication failed. Check AI_API_KEY in api_key.env; local fallback was tried."
    except OpenAIError:
        return None, "The AI API request failed or timed out; local fallback was tried."
    except json.JSONDecodeError:
        return None, "The AI returned invalid JSON; local fallback was tried."


def interpret_request(text: str) -> tuple[dict[str, Any] | None, str | None, str]:
    """Return instruction, optional AI notice, and the interpreter mode."""
    instruction, notice = _model_instruction(text)
    if instruction is not None:
        return instruction, None, "ai"
    fallback = parse_locally(text)
    return fallback, notice, "local_fallback"


def ai_configuration_notice() -> str | None:
    api_key = os.getenv("AI_API_KEY", "").strip()
    provider = os.getenv("AI_PROVIDER", "openai").strip().lower()
    if not api_key or api_key == "PASTE_YOUR_API_KEY_HERE":
        return (
            "AI_API_KEY is not configured. Add your OpenAI API key to api_key.env to enable AI; "
            "basic supported requests will use the local fallback."
        )
    if provider != "openai":
        return f"AI_PROVIDER '{provider}' is not supported; basic requests will use the local fallback."
    return None
