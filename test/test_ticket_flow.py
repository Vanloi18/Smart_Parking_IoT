"""Luồng vé chỉ chạy trên snapshot DB và uploads Temp; không gửi phần cứng."""
from contextlib import closing
from datetime import datetime, timedelta
import importlib.util
import io
from pathlib import Path
import sqlite3
import sys
import tempfile
import unittest
from unittest.mock import patch
from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "dashboard/backend"))
import db
import app as backend
from anpr_engine import ANPREngine


class TicketFlowTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        copy = Path(self.temp.name) / "parking.db"
        with closing(sqlite3.connect((ROOT / "dashboard/parking.db").as_uri() + "?mode=ro", uri=True)) as source:
            with closing(sqlite3.connect(copy)) as target:
                source.backup(target)
                target.execute("DELETE FROM camera_commands")
                target.execute("UPDATE slots SET is_occupied=0")
                target.commit()
        self.db_patch = patch.object(db, "DB_PATH", str(copy))
        self.db_patch.start()
        self.addCleanup(self.db_patch.stop)
        db.init_db()
        self.client = backend.app.test_client()
        self.uid = "TICKET_TEST_UNIQUE"

    def rows(self, sql, params=()):
        with closing(db.get_connection()) as conn:
            return [dict(row) for row in conn.execute(sql, params)]

    def entry(self):
        return self.client.post("/api/parking/entry", json={"cardUid": self.uid}).json

    def exit(self, uid=None):
        return self.client.post("/api/parking/exit", json={"cardUid": uid or self.uid}).json

    def capture(self, role, result=None, broken=False):
        command = self.client.get("/api/cameras/commands?camera_id=" + role.upper() + "_CAM").json
        self.assertTrue(command["has_command"])
        result = result or {"success": False, "plateNumber": None, "confidence": None,
                            "reason": "PLATE_NOT_DETECTED", "image_valid": True, "image_url": "/uploads/test_capture.jpg"}
        with patch.object(backend.anpr_service, "process_capture", return_value=result):
            response = self.client.post("/api/cameras/" + role + "/capture", data=b"bad" if broken else b"x" * 200, content_type="image/jpeg")
        self.client.post(f"/api/cameras/commands/{command['command_id']}/ack", json={"status": "EXECUTED"})
        return response.json

    def test_normal_ticket_images_fee_and_no_duplicate_payment(self):
        entered = self.entry()
        self.assertTrue(entered["allowed"])
        session_id = entered["session_id"]
        self.assertEqual(self.capture("entry")["session_id"], session_id)
        with closing(db.get_connection()) as conn:
            conn.execute("UPDATE parking_sessions SET entry_time=? WHERE id=?", ((datetime.now() - timedelta(seconds=11)).isoformat(), session_id))
            conn.commit()
        exited = self.exit()
        self.assertTrue(exited["allowed"])
        self.assertEqual(exited["fee"], 15000)
        self.assertEqual(self.capture("exit")["session_id"], session_id)
        session = self.rows("SELECT * FROM parking_sessions WHERE id=?", (session_id,))[0]
        self.assertEqual(session["status"], "CHECKED_OUT")
        self.assertEqual(session["missing_entry_image"], 0)
        self.assertEqual(session["missing_exit_image"], 0)
        self.assertFalse(self.exit()["allowed"])
        self.assertEqual(len(self.rows("SELECT * FROM payments WHERE session_id=?", (session_id,))), 1)

    def test_unknown_exit_duplicate_entry_and_invalid_uid(self):
        self.assertEqual(self.exit("UNKNOWN_UID")["reason"], "NO_OPEN_SESSION")
        self.assertTrue(self.entry()["allowed"])  # Thẻ vé không cần đăng ký phương tiện trước.
        denied = self.entry()
        self.assertFalse(denied["allowed"])
        self.assertEqual(denied["reason"], "ALREADY_PARKED")
        self.assertEqual(len(self.rows("SELECT * FROM parking_sessions WHERE rfid_uid=?", (self.uid,))), 1)
        self.assertEqual(len(self.rows("SELECT * FROM camera_commands WHERE session_id=?", (denied["session_id"],))), 1)
        self.assertEqual(self.client.post("/api/parking/entry", json={"cardUid": ""}).json["reason"], "INVALID_UID")

    def test_bad_image_and_blank_plate_do_not_block_exit(self):
        entered = self.entry()
        self.capture("entry", broken=True)
        session = self.rows("SELECT * FROM parking_sessions WHERE id=?", (entered["session_id"],))[0]
        self.assertIsNone(session["plate_number"])
        self.assertEqual(session["needs_plate"], 1)
        self.assertEqual(session["missing_entry_image"], 1)
        self.assertTrue(self.exit()["allowed"])

    def test_ocr_failure_and_manual_capture_cannot_create_or_close_session(self):
        entered = self.entry()
        self.capture("entry", {"success": False, "plateNumber": None, "confidence": None,
                               "image_valid": True, "image_url": "/uploads/valid.jpg", "reason": "OCR_ERROR"})
        before = len(self.rows("SELECT * FROM parking_sessions"))
        with patch.object(backend.anpr_service, "process_capture", return_value={"success": True, "plateNumber": "30A-123.45", "confidence": .9, "image_valid": True}):
            response = self.client.post("/api/cameras/exit/capture?plate=30A-999.88&cardUid=" + self.uid, data=b"x" * 200)
        self.assertIsNone(response.json["session_id"])
        self.assertEqual(len(self.rows("SELECT * FROM parking_sessions")), before)
        self.assertEqual(self.rows("SELECT status FROM parking_sessions WHERE id=?", (entered["session_id"],))[0]["status"], "PARKED")

    def test_confirm_ocr_and_manual_edit_then_no_closed_edit(self):
        entered = self.entry()
        session_id = entered["session_id"]
        self.capture("entry", {"success": True, "plateNumber": "59X1-123.45", "confidence": .85,
                               "image_valid": True, "image_url": "/uploads/ocr.jpg", "reason": "OK"})
        session = self.rows("SELECT * FROM parking_sessions WHERE id=?", (session_id,))[0]
        self.assertEqual(session["plate_source"], "OCR")
        self.assertEqual(session["needs_plate"], 1)
        token = backend.generate_jwt(db.get_user_by_username("admin"))
        headers = {"Authorization": "Bearer " + token}
        url = f"/api/parking/sessions/{session_id}/plate"
        self.assertEqual(self.client.patch(url, json={"plate": "59X1-12345"}, headers=headers).json["plate_source"], "OCR")
        response = self.client.patch(url, json={"plate": "30A-12345"}, headers=headers)
        self.assertEqual(response.json["plate_source"], "MANUAL")
        self.assertEqual(self.exit()["plate"], "30A-123.45")
        self.assertEqual(self.client.patch(url, json={"plate": "30A-88888"}, headers=headers).status_code, 409)

    def test_serialized_camera_commands_and_expired_capture_never_binds_new_uid(self):
        first = self.entry()
        self.uid = "TICKET_TEST_SECOND"
        second = self.entry()
        command = self.client.get("/api/cameras/commands?camera_id=ENTRY_CAM").json
        self.assertFalse(self.client.get("/api/cameras/commands?camera_id=ENTRY_CAM").json["has_command"])
        with closing(db.get_connection()) as conn:
            conn.execute("UPDATE camera_commands SET created_at=? WHERE id=?", ((datetime.now() - timedelta(seconds=120)).isoformat(), command["command_id"]))
            conn.commit()
        with patch.object(backend.anpr_service, "process_capture", return_value={"image_valid": True, "image_url": "/uploads/late.jpg"}):
            self.assertIsNone(self.client.post("/api/cameras/entry/capture", data=b"x" * 200).json["session_id"])
        self.assertEqual(self.capture("entry")["session_id"], second["session_id"])
        self.assertEqual(self.rows("SELECT missing_entry_image FROM parking_sessions WHERE id=?", (first["session_id"],))[0]["missing_entry_image"], 1)

    def test_late_ocr_does_not_overwrite_confirmed_manual_plate(self):
        entered = self.entry()
        token = backend.generate_jwt(db.get_user_by_username("admin"))
        response = self.client.patch(f"/api/parking/sessions/{entered['session_id']}/plate",
                                     json={"plate": "30A-12345"}, headers={"Authorization": "Bearer " + token})
        self.assertEqual(response.status_code, 200)
        self.capture("entry", {"success": True, "plateNumber": "59X1-123.45", "confidence": .95,
                               "image_valid": True, "image_url": "/uploads/late_ocr.jpg"})
        session = self.rows("SELECT * FROM parking_sessions WHERE id=?", (entered["session_id"],))[0]
        self.assertEqual(session["plate_number"], "30A-123.45")
        self.assertEqual(session["plate_source"], "MANUAL")

    def test_migration_preserves_existing_values_and_is_idempotent(self):
        before = self.rows("SELECT id,rfid_uid,plate_number,entry_time,fee,status FROM parking_sessions")
        db.init_db()
        self.assertEqual(self.rows("SELECT id,rfid_uid,plate_number,entry_time,fee,status FROM parking_sessions"), before)

    def test_real_engine_ignores_hint_and_low_confidence(self):
        folder = Path(self.temp.name) / "uploads"
        folder.mkdir()
        engine = ANPREngine(str(folder))
        engine.ocr_available = False
        image = io.BytesIO()
        Image.new("RGB", (120, 60)).save(image, format="JPEG")
        result = engine.process_capture(image.getvalue(), client_plate_hint="30A-999.88")
        self.assertIsNone(result["plateNumber"])
        engine.ocr_available = True
        with patch.object(engine, "_extract_plate_from_image", return_value=("30A-123.45", .3)):
            result = engine.process_capture(image.getvalue())
        self.assertEqual(result["reason"], "LOW_CONFIDENCE")
        self.assertIsNone(result["plateNumber"])
        self.assertEqual(result["confidence"], .3)
        with patch.object(engine, "_extract_plate_from_image", side_effect=RuntimeError("OCR failed")):
            self.assertEqual(engine.process_capture(image.getvalue())["reason"], "OCR_ERROR")


if __name__ == "__main__":
    unittest.main()
