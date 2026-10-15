"""Interactive terminal entry point for the attendance management system."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from ai_handler import ai_configuration_notice, interpret_request, parse_locally
from attendance_service import AttendanceError, AttendanceService, response


def process_request(service: AttendanceService, text: str) -> dict[str, Any]:
    instruction, ai_notice, mode = interpret_request(text)
    if instruction is None:
        result = response(
            False,
            "I could not understand that request. Try a supported attendance question or command.",
        )
    else:
        try:
            result = service.execute(instruction)
        except AttendanceError as exc:
            result = response(False, str(exc))
            if mode == "ai":
                fallback_instruction = parse_locally(text)
                if fallback_instruction is not None:
                    try:
                        result = service.execute(fallback_instruction)
                        mode = "local_fallback"
                        ai_notice = (
                            "The AI instruction was invalid; the local rule-based fallback handled this request."
                        )
                    except AttendanceError as fallback_error:
                        result = response(False, str(fallback_error))
    result["mode"] = mode
    if ai_notice:
        result["ai_notice"] = ai_notice
    return result


def main() -> None:
    try:
        service = AttendanceService(Path(__file__).resolve().parent / "attendance.json")
    except AttendanceError as exc:
        print(json.dumps(response(False, str(exc)), ensure_ascii=False))
        return

    print("=== AI ATTENDANCE MANAGEMENT SYSTEM ===")
    notice = ai_configuration_notice()
    if notice:
        print(json.dumps({"success": False, "message": notice}, ensure_ascii=False))
    print("Enter your attendance request (type 'exit' to quit):")
    while True:
        try:
            request_text = input("> ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            break
        if request_text.casefold() == "exit":
            break
        if not request_text:
            print(json.dumps(response(False, "Please enter an attendance request.")))
            continue
        result = process_request(service, request_text)
        print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
