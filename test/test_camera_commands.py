"""Kiểm thử lệnh camera trên bản sao DB; không ghi DB thật."""
import os
from pathlib import Path
import sqlite3
import sys
import tempfile
import unittest
from datetime import datetime, timedelta
from unittest.mock import patch
from contextlib import closing

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "dashboard" / "backend"))
import db
from app import app


class CameraCommandsTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.copy = Path(self.temp.name) / "parking.db"
        # SQLite backup tạo snapshot nhất quán khi backend vẫn đang chạy.
        with closing(sqlite3.connect((ROOT / "dashboard" / "parking.db").as_uri() + "?mode=ro", uri=True)) as source:
            with closing(sqlite3.connect(self.copy)) as target:
                source.backup(target)
                target.execute("DELETE FROM camera_commands")
                target.commit()
        self.db_patch = patch.object(db, "DB_PATH", str(self.copy))
        self.db_patch.start()
        db.init_db()  # Migration chỉ chạy trên snapshot Temp.
        self.client = app.test_client()

    def tearDown(self):
        self.db_patch.stop()
        self.temp.cleanup()

    def command(self, age, camera="ENTRY_CAM", status="PENDING"):
        with closing(db.get_connection()) as conn:
            cursor = conn.execute("INSERT INTO camera_commands (camera_id, command, status, created_at) VALUES (?, 'CAPTURE', ?, ?)",
                                  (camera, status, (datetime.now() - timedelta(seconds=age)).isoformat()))
            conn.commit()
            return cursor.lastrowid

    def status(self, command_id):
        with closing(db.get_connection()) as conn:
            return conn.execute("SELECT status FROM camera_commands WHERE id=?", (command_id,)).fetchone()[0]

    def test_expire_only_old_pending_for_polled_camera(self):
        old = self.command(61)
        fresh = self.command(30)
        other = self.command(120, camera="EXIT_CAM")
        done = self.command(120, status="EXECUTED")
        response = self.client.get("/api/cameras/commands?camera_id=ENTRY_CAM")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json["command_id"], fresh)
        self.assertEqual(self.status(old), "EXPIRED")
        self.assertEqual(self.status(other), "PENDING")
        self.assertEqual(self.status(done), "EXECUTED")
        self.assertEqual(self.client.post(f"/api/cameras/commands/{old}/ack", json={"status": "EXECUTED"}).status_code, 409)
        self.assertEqual(self.status(old), "EXPIRED")
        self.assertEqual(self.client.post(f"/api/cameras/commands/{fresh}/ack", json={"status": "EXECUTED"}).status_code, 200)

    def test_custom_ttl(self):
        command = self.command(10)
        with patch.dict(os.environ, {"CAMERA_COMMAND_TTL_SECONDS": "5"}):
            self.assertFalse(self.client.get("/api/cameras/commands").json["has_command"])
        self.assertEqual(self.status(command), "EXPIRED")

    def test_invalid_ttl_falls_back_without_error(self):
        command = self.command(30)
        for value in ("bad", "0", "-1"):
            with patch.dict(os.environ, {"CAMERA_COMMAND_TTL_SECONDS": value}):
                response = self.client.get("/api/cameras/commands")
                self.assertEqual(response.status_code, 200)
                self.assertEqual(response.json["command_id"], command)
                self.client.post(f"/api/cameras/commands/{command}/ack", json={"status": "EXECUTED"})
                command = self.command(30)


if __name__ == "__main__":
    unittest.main()
