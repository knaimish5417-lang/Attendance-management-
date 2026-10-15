"""Validated attendance operations backed by the local JSON data file."""

from __future__ import annotations

import json
import os
import tempfile
from datetime import date
from pathlib import Path
from typing import Any


PERIOD_START = date(2026, 10, 8)
PERIOD_END = date(2026, 10, 14)
ALLOWED_OPERATIONS = {
    "check_percentage",
    "check_record",
    "mark_attendance",
    "remove_attendance",
    "show_all",
    "class_average",
}
ALLOWED_STATUSES = {"Present", "Absent"}
EXPECTED_STUDENTS = {
    "aditya": "101",
    "sumit": "102",
    "lalit": "103",
    "anant": "104",
    "krishna": "105",
}


class AttendanceError(ValueError):
    """An invalid attendance request or invalid attendance data file."""


def response(success: bool, message: str, data: Any = None) -> dict[str, Any]:
    result: dict[str, Any] = {"success": success, "message": message}
    if data is not None:
        result["data"] = data
    return result


class AttendanceService:
    def __init__(self, data_path: Path) -> None:
        self.data_path = data_path
        try:
            self.data = json.loads(data_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise AttendanceError(
                f"Could not read valid attendance data from {data_path.name}: {exc}"
            ) from exc
        self._validate_dataset()
        self._recalculate_all()

    def _validate_dataset(self) -> None:
        if not isinstance(self.data, dict) or not isinstance(self.data.get("students"), list):
            raise AttendanceError("attendance.json must contain a students list.")
        if self.data.get("period_start") != PERIOD_START.isoformat() or self.data.get(
            "period_end"
        ) != PERIOD_END.isoformat():
            raise AttendanceError("attendance.json must use the configured 2026-10-08 to 2026-10-14 period.")
        if len(self.data["students"]) != len(EXPECTED_STUDENTS):
            raise AttendanceError("attendance.json must contain the five configured students.")

        names: set[str] = set()
        rolls: set[str] = set()
        for student in self.data["students"]:
            if not isinstance(student, dict):
                raise AttendanceError("Each student entry must be a JSON object.")
            name = student.get("name")
            roll_no = str(student.get("roll_no", ""))
            records = student.get("attendance_records")
            if not isinstance(name, str) or not name.strip() or not roll_no.isdigit():
                raise AttendanceError("Each student must have a name and numeric roll_no.")
            if name.casefold() in names or roll_no in rolls:
                raise AttendanceError("Student names and roll numbers must be unique.")
            if EXPECTED_STUDENTS.get(name.casefold()) != roll_no:
                raise AttendanceError(f"{name} has an unexpected name or roll number.")
            if not isinstance(records, list):
                raise AttendanceError(f"{name}'s attendance_records must be a list.")
            names.add(name.casefold())
            rolls.add(roll_no)

            seen_dates: set[str] = set()
            for record in records:
                if not isinstance(record, dict):
                    raise AttendanceError(f"{name} has an invalid attendance record.")
                record_date = record.get("date")
                status = record.get("status")
                self._validate_date(record_date)
                if record_date in seen_dates:
                    raise AttendanceError(f"{name} has duplicate attendance for {record_date}.")
                if not isinstance(status, str) or status not in ALLOWED_STATUSES:
                    raise AttendanceError(f"{name} has an invalid status for {record_date}.")
                seen_dates.add(record_date)
        if not self.data["students"]:
            raise AttendanceError("attendance.json must contain at least one student.")

    @staticmethod
    def _validate_date(value: Any) -> date:
        if not isinstance(value, str):
            raise AttendanceError("Date must use YYYY-MM-DD format.")
        try:
            parsed = date.fromisoformat(value)
        except ValueError as exc:
            raise AttendanceError("Date must use a valid YYYY-MM-DD date.") from exc
        if parsed.isoformat() != value:
            raise AttendanceError("Date must use YYYY-MM-DD format.")
        if not PERIOD_START <= parsed <= PERIOD_END:
            raise AttendanceError("Date must be between 2026-10-08 and 2026-10-14 inclusive.")
        return parsed

    def _find_student(self, name: Any) -> dict[str, Any]:
        if not isinstance(name, str) or not name.strip():
            raise AttendanceError("A student name is required for this operation.")
        for student in self.data["students"]:
            if student["name"].casefold() == name.strip().casefold():
                return student
        raise AttendanceError(f"Student '{name}' was not found.")

    @staticmethod
    def _recalculate_student(student: dict[str, Any]) -> None:
        records = student["attendance_records"]
        present_days = sum(record["status"] == "Present" for record in records)
        total_days = len(records)
        percentage = (present_days / total_days * 100) if total_days else 0.0
        student["present_days"] = present_days
        student["total_days"] = total_days
        student["attendance_percentage"] = round(percentage, 2)

    def _recalculate_all(self) -> None:
        for student in self.data["students"]:
            self._recalculate_student(student)

    def _class_average(self) -> float:
        percentages = [student["attendance_percentage"] for student in self.data["students"]]
        return round(sum(percentages) / len(self.data["students"]), 2)

    def _save(self) -> None:
        self._recalculate_all()
        temporary_path: str | None = None
        try:
            with tempfile.NamedTemporaryFile(
                mode="w",
                encoding="utf-8",
                dir=self.data_path.parent,
                prefix=f".{self.data_path.name}.",
                suffix=".tmp",
                delete=False,
            ) as temporary_file:
                temporary_path = temporary_file.name
                json.dump(self.data, temporary_file, indent=2)
                temporary_file.write("\n")
                temporary_file.flush()
                os.fsync(temporary_file.fileno())
            os.replace(temporary_path, self.data_path)
        except OSError as exc:
            cleanup_message = ""
            if temporary_path and os.path.exists(temporary_path):
                try:
                    os.unlink(temporary_path)
                except OSError as cleanup_error:
                    cleanup_message = f" Temporary file cleanup also failed: {cleanup_error}"
            raise AttendanceError(
                f"Could not save attendance.json: {exc}.{cleanup_message}"
            ) from exc

    def execute(self, instruction: dict[str, Any]) -> dict[str, Any]:
        if not isinstance(instruction, dict):
            raise AttendanceError("Instruction must be a JSON object.")
        operation = instruction.get("operation")
        if not isinstance(operation, str) or operation not in ALLOWED_OPERATIONS:
            raise AttendanceError("Unsupported operation. No data was changed.")

        if operation == "class_average":
            return response(
                True,
                "Class average attendance calculated.",
                {"class_average": self._class_average(), "student_count": len(self.data["students"])},
            )
        if operation == "show_all":
            return response(
                True,
                "Attendance for all students.",
                {
                    "students": self.data["students"],
                    "class_average": self._class_average(),
                    "period_start": self.data["period_start"],
                    "period_end": self.data["period_end"],
                },
            )

        student = self._find_student(instruction.get("student_name"))
        supplied_roll = instruction.get("roll_no")
        if supplied_roll is not None and str(supplied_roll) != str(student["roll_no"]):
            raise AttendanceError("The supplied roll number does not match the selected student.")

        if operation == "check_percentage":
            return response(
                True,
                f"{student['name']}'s attendance percentage calculated.",
                self._student_summary(student),
            )

        if operation == "check_record":
            record_date = self._validate_date(instruction.get("date"))
            record = self._record_for_date(student, record_date.isoformat())
            return response(
                True,
                "Attendance record found." if record else "No attendance record exists for that date.",
                {
                    "student_name": student["name"],
                    "roll_no": student["roll_no"],
                    "date": record_date.isoformat(),
                    "status": record["status"] if record else None,
                    "recorded": record is not None,
                },
            )

        record_date = self._validate_date(instruction.get("date")).isoformat()
        record = self._record_for_date(student, record_date)
        if operation == "mark_attendance":
            status = instruction.get("status")
            if not isinstance(status, str) or status.casefold() not in {
                item.casefold() for item in ALLOWED_STATUSES
            }:
                raise AttendanceError("Status must be either Present or Absent.")
            normalized_status = next(
                item for item in ALLOWED_STATUSES if item.casefold() == status.casefold()
            )
            previous_status = record["status"] if record else None
            if record:
                record["status"] = normalized_status
                message = "Attendance record updated successfully."
            else:
                record = {"date": record_date, "status": normalized_status}
                student["attendance_records"].append(record)
                message = "Attendance record added successfully."
            try:
                self._save()
            except AttendanceError:
                if previous_status is not None:
                    record["status"] = previous_status
                else:
                    student["attendance_records"].remove(record)
                self._recalculate_all()
                raise
            return response(
                True,
                message,
                {
                    **self._student_summary(student),
                    "date": record_date,
                    "status": normalized_status,
                    "class_average": self._class_average(),
                },
            )

        if operation == "remove_attendance":
            if record is None:
                raise AttendanceError(
                    f"No attendance record exists for {student['name']} on {record_date}."
                )
            student["attendance_records"].remove(record)
            try:
                self._save()
            except AttendanceError:
                student["attendance_records"].append(record)
                self._recalculate_all()
                raise
            return response(
                True,
                "Attendance record removed successfully.",
                {
                    **self._student_summary(student),
                    "date": record_date,
                    "removed_status": record["status"],
                    "class_average": self._class_average(),
                },
            )

        raise AttendanceError("Unsupported operation. No data was changed.")

    @staticmethod
    def _record_for_date(student: dict[str, Any], record_date: str) -> dict[str, Any] | None:
        return next(
            (record for record in student["attendance_records"] if record["date"] == record_date),
            None,
        )

    @staticmethod
    def _student_summary(student: dict[str, Any]) -> dict[str, Any]:
        return {
            "student_name": student["name"],
            "roll_no": student["roll_no"],
            "present_days": student["present_days"],
            "total_days": student["total_days"],
            "attendance_percentage": student["attendance_percentage"],
        }
