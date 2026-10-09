"""Kiểm thử dọn dữ liệu trên bản sao DB và ảnh, không chạm bản gốc."""
from contextlib import closing, redirect_stdout
from datetime import date, datetime, timedelta
import importlib.util
import io
import json
from pathlib import Path
import shutil
import sqlite3
import tempfile
import unittest
from unittest.mock import patch
from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("clean_sample_data", ROOT / "scripts/clean_sample_data.py")
clean = importlib.util.module_from_spec(spec)
spec.loader.exec_module(clean)


class CleanSampleDataTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.folder = Path(self.temp.name)
        self.db = self.folder / "parking.db"
        self.uploads = self.folder / "uploads"
        # SQLite backup từ mode=ro; mọi thay đổi bên dưới chỉ nằm trong Temp.
        with closing(clean.connect_readonly(ROOT / "dashboard/parking.db")) as source:
            with closing(sqlite3.connect(self.db)) as target:
                source.backup(target)
        shutil.copytree(ROOT / "dashboard/backend/uploads", self.uploads)
        # Fixture độc lập với dữ liệu mẫu còn/đã được dọn trong DB thật.
        Image.new("RGB", (640, 480), color=(73, 109, 137)).save(self.uploads / "fixture_sample.jpg", format="JPEG")
        yesterday = (datetime.now() - timedelta(days=1)).isoformat()
        with closing(sqlite3.connect(self.db)) as conn:
            for table in clean.TABLES:
                conn.execute(f'DELETE FROM "{table}"')
            conn.execute("INSERT INTO camera_events (id,camera_id,camera_role,plate_number,image_url,timestamp) VALUES (7,'ENTRY_CAM','ENTRY',?,'/uploads/fixture_sample.jpg',?)", (clean.PLATE, yesterday))
            conn.execute("INSERT INTO camera_events (id,camera_id,camera_role,plate_number,timestamp) VALUES (8,'EXIT_CAM','EXIT','REAL-PLATE',?)", (yesterday,))
            conn.execute("INSERT INTO parking_sessions (id,plate_number,rfid_uid,entry_time,status,entry_image_url) VALUES (9,?,?,?,'PARKED','/uploads/fixture_sample.jpg')", (clean.PLATE, clean.RFIDS[0], yesterday))
            conn.execute("INSERT INTO payments (id,session_id,plate_number,amount,paid_at) VALUES (6,9,?,5000,?)", (clean.PLATE, yesterday))
            conn.execute("INSERT INTO vehicles (id,plate_number,rfid_uid,registered_at) VALUES (2,?,?,?)", (clean.PLATE, clean.RFIDS[0], yesterday))
            conn.execute("INSERT INTO parking_transactions (id,card_uid,entry_time,status) VALUES (15,?,?,'PARKED')", (clean.RFIDS[1], yesterday))
            conn.execute("INSERT INTO system_events (id,event_type,description,timestamp) VALUES (3,'CAMERA_RECOGNITION',?,?)", ("Plate: " + clean.PLATE, yesterday))
            conn.commit()
        self.plan = self.build_plan()
        self.report = self.folder / "approved.json"
        self.report.write_text(json.dumps({"plan": self.plan}), encoding="utf-8")

    def build_plan(self):
        with closing(clean.connect_readonly(self.db)) as conn:
            return clean.build_plan(conn, self.db, self.uploads, date.today())

    def protected(self):
        with closing(clean.connect_readonly(self.db)) as conn:
            return {table: [tuple(row) for row in conn.execute(f'SELECT * FROM "{table}"')]
                    for table in self.plan["protected_tables"]}

    def apply(self):
        # Chỉ giả lập backend đã dừng cho DB tạm, không tắt backend thật.
        with patch.object(clean.socket, "socket") as socket_mock, redirect_stdout(io.StringIO()):
            socket_mock.return_value.__enter__.return_value.connect_ex.return_value = 111
            clean.apply_plan(self.db, self.uploads, self.report)

    def test_backup_and_dry_run_do_not_modify_source(self):
        before = clean.sha256(self.db)
        backup = clean.create_backup(self.db)
        self.assertEqual(backup["integrity_check"], "ok")
        self.assertEqual(clean.sha256(self.db), before)
        self.assertEqual(self.build_plan(), self.plan)
        self.assertEqual(clean.sha256(self.db), before)

    def test_apply_only_reviewed_rows_and_images_with_backup(self):
        protected = self.protected()
        with closing(clean.connect_readonly(self.db)) as conn:
            existing = {table: [dict(row) for row in conn.execute(f'SELECT * FROM "{table}" ORDER BY id')]
                        for table in clean.TABLES}
        self.apply()
        self.assertEqual(self.protected(), protected)
        backups = list(self.folder.glob("parking.db.bak_*"))
        backups = [path for path in backups if path.is_file() and not path.name.endswith(".json")]
        self.assertEqual(len(backups), 1)
        with closing(clean.connect_readonly(self.db)) as conn:
            for table, old_rows in existing.items():
                deleted = {row["id"] for row in self.plan["rows_to_delete"][table]}
                actual = [dict(row) for row in conn.execute(f'SELECT * FROM "{table}" ORDER BY id')]
                self.assertEqual(actual, [row for row in old_rows if row["id"] not in deleted])
        for image in self.plan["images_to_delete"]:
            self.assertFalse(Path(image["path"]).exists())
            saved = Path(str(backups[0]) + "_images") / Path(image["path"]).name
            self.assertEqual(clean.sha256(saved), clean.DUMMY_SHA256)

    def test_changed_plan_refuses_apply_without_deleting(self):
        with closing(sqlite3.connect(self.db)) as conn:
            conn.execute("INSERT INTO parking_transactions (card_uid,entry_time,status) VALUES (?,?,'PARKED')",
                         (clean.RFIDS[0], datetime.now().isoformat()))
            conn.commit()
        before = clean.sha256(self.db)
        with self.assertRaisesRegex(RuntimeError, "Danh sách khác"):
            self.apply()
        self.assertEqual(clean.sha256(self.db), before)

    def test_today_and_shared_images_and_non_sample_files_are_protected(self):
        image = self.plan["images_to_delete"][0]
        real_image = self.uploads / "real_photo.jpg"
        real_image.write_bytes(b"not the sample JPEG")
        with closing(sqlite3.connect(self.db)) as conn:
            conn.execute("INSERT INTO camera_events (camera_id,camera_role,plate_number,image_url,timestamp) VALUES ('ENTRY_CAM','ENTRY',?,?,?)",
                         (clean.PLATE, image["url"], datetime.now().isoformat()))
            conn.execute("INSERT INTO camera_events (camera_id,camera_role,plate_number,image_url,timestamp) VALUES ('ENTRY_CAM','ENTRY',?,?,'2026-10-07T12:00:00')",
                         (clean.PLATE, "/uploads/real_photo.jpg"))
            conn.commit()
        plan = self.build_plan()
        self.assertTrue(any(row["table"] == "camera_events" for row in plan["skipped_rows"]))
        self.assertFalse(any(item["url"] == image["url"] for item in plan["images_to_delete"]))
        self.assertTrue(any(item["url"] == "/uploads/real_photo.jpg" for item in plan["skipped_images"]))


if __name__ == "__main__":
    unittest.main()
