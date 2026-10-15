import json
import os
import tempfile
import unittest
from unittest.mock import patch
from pathlib import Path

from ai_handler import ai_configuration_notice, interpret_request, parse_locally
from attendance_service import AttendanceError, AttendanceService
from main import process_request


class AttendanceServiceTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.path = Path(self.temp_dir.name) / "attendance.json"
        source = Path(__file__).resolve().parents[1] / "attendance.json"
        self.path.write_text(source.read_text(encoding="utf-8"), encoding="utf-8")
        self.service = AttendanceService(self.path)

    def tearDown(self):
        self.temp_dir.cleanup()

    def execute(self, operation, **fields):
        return self.service.execute({"operation": operation, **fields})

    def test_sample_dataset_has_five_students_and_all_seven_dates(self):
        self.assertEqual(len(self.service.data["students"]), 5)
        expected_dates = {f"2026-10-{day:02}" for day in range(8, 15)}
        for student in self.service.data["students"]:
            self.assertEqual({r["date"] for r in student["attendance_records"]}, expected_dates)
            actual_present = sum(r["status"] == "Present" for r in student["attendance_records"])
            self.assertEqual(student["present_days"], actual_present)
            self.assertEqual(student["total_days"], 7)
            self.assertEqual(
                student["attendance_percentage"], round(actual_present / 7 * 100, 2)
            )

    def test_mark_updates_existing_record_and_persists(self):
        result = self.execute(
            "mark_attendance", student_name="Lalit", date="2026-10-12", status="Present"
        )
        self.assertTrue(result["success"])
        self.assertEqual(result["data"]["total_days"], 7)
        saved = json.loads(self.path.read_text(encoding="utf-8"))
        lalit = next(student for student in saved["students"] if student["name"] == "Lalit")
        records = [r for r in lalit["attendance_records"] if r["date"] == "2026-10-12"]
        self.assertEqual(len(records), 1)
        self.assertEqual(records[0]["status"], "Present")
        self.assertEqual(lalit["attendance_percentage"], 85.71)
        reloaded = AttendanceService(self.path)
        self.assertEqual(
            reloaded.execute({"operation": "check_percentage", "student_name": "Lalit"})[
                "data"
            ]["attendance_percentage"],
            85.71,
        )

    def test_mark_absent_and_remove_recalculate(self):
        marked = self.execute(
            "mark_attendance", student_name="Aditya", date="2026-10-08", status="Absent"
        )
        self.assertEqual(marked["data"]["present_days"], 5)
        removed = self.execute(
            "remove_attendance", student_name="Aditya", date="2026-10-09"
        )
        self.assertEqual(removed["data"]["total_days"], 6)
        self.assertEqual(removed["data"]["attendance_percentage"], 66.67)
        self.assertEqual(removed["data"]["class_average"], 70.48)
        saved = json.loads(self.path.read_text(encoding="utf-8"))
        aditya = next(student for student in saved["students"] if student["name"] == "Aditya")
        self.assertEqual(aditya["total_days"], 6)
        self.assertNotIn("2026-10-09", {r["date"] for r in aditya["attendance_records"]})
        with self.assertRaises(AttendanceError):
            self.execute("remove_attendance", student_name="Aditya", date="2026-10-09")

    def test_class_average_is_computed_from_student_percentages(self):
        result = self.execute("class_average")
        self.assertEqual(result["data"]["class_average"], 74.29)
        self.assertEqual(result["data"]["student_count"], 5)

    def test_invalid_name_date_and_operation_are_rejected(self):
        with self.assertRaisesRegex(AttendanceError, "was not found"):
            self.execute("check_percentage", student_name="Unknown")
        with self.assertRaisesRegex(AttendanceError, "between 2026-10-08"):
            self.execute(
                "mark_attendance",
                student_name="Aditya",
                date="2026-10-15",
                status="Present",
            )
        with self.assertRaises(AttendanceError):
            self.execute("execute arbitrary code")

    def test_rule_fallback_returns_json_errors_for_invalid_names_and_dates(self):
        unknown = process_request(
            self.service, "What is Bob's attendance percentage?"
        )
        self.assertFalse(unknown["success"])
        self.assertIn("Bob", unknown["message"])

        out_of_range = process_request(
            self.service, "Mark Aditya present on 15 October 2026."
        )
        self.assertFalse(out_of_range["success"])
        self.assertIn("between 2026-10-08 and 2026-10-14", out_of_range["message"])

    def test_zero_record_percentage_is_zero(self):
        student = self.service.data["students"][0]
        student["attendance_records"].clear()
        self.service._recalculate_student(student)
        self.assertEqual(student["attendance_percentage"], 0.0)


class LocalInterpreterTests(unittest.TestCase):
    def test_missing_api_key_uses_fallback_with_clear_notice(self):
        with patch.dict(os.environ, {"AI_API_KEY": "PASTE_YOUR_API_KEY_HERE"}):
            self.assertIn("not configured", ai_configuration_notice())
            instruction, notice, mode = interpret_request(
                "What is Aditya's attendance percentage?"
            )
        self.assertIsNone(notice)
        self.assertEqual(mode, "local_fallback")
        self.assertEqual(instruction["operation"], "check_percentage")

    def test_supported_local_requests(self):
        self.assertEqual(
            parse_locally("What is Aditya's attendance percentage?")["operation"],
            "check_percentage",
        )
        self.assertEqual(
            parse_locally("Was Sumit present on 10 October 2026?")["date"], "2026-10-10"
        )
        self.assertEqual(
            parse_locally("Mark Lalit present on 12 October 2026.")["status"], "Present"
        )
        self.assertEqual(
            parse_locally("Remove Krishna's attendance for 9 October 2026.")["operation"],
            "remove_attendance",
        )
        self.assertEqual(
            parse_locally("Calculate the class average attendance percentage.")["operation"],
            "class_average",
        )


if __name__ == "__main__":
    unittest.main()
