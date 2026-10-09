"""Kiểm thử khóa tạm độc lập; không import backend hay mở DB thật."""
import ast
import os
from pathlib import Path
import secrets
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

import jwt


class RuntimeSecretTests(unittest.TestCase):
    def setUp(self):
        # Chỉ nạp hàm cần thử để tránh khởi tạo DB/upload/OCR khi import app.
        source = Path(__file__).resolve().parents[1] / "dashboard/backend/app.py"
        tree = ast.parse(source.read_text(encoding="utf-8-sig"))
        function = next(n for n in tree.body
                        if isinstance(n, ast.FunctionDef) and n.name == "get_runtime_secret")
        self.logger = Mock()
        namespace = {"os": os, "secrets": secrets,
                     "app": SimpleNamespace(logger=self.logger)}
        exec(compile(ast.Module(body=[function], type_ignores=[]), str(source), "exec"), namespace)
        self.get_secret = namespace["get_runtime_secret"]

    def test_configured_keys_remain_stable_without_warning(self):
        with patch.dict(os.environ, {"SECRET_KEY": "test-session-key",
                                     "JWT_SECRET": "test-jwt-key"}, clear=True):
            for name in ("SECRET_KEY", "JWT_SECRET"):
                self.assertEqual(self.get_secret(name), os.environ[name])
                self.assertEqual(self.get_secret(name), os.environ[name])
        self.logger.warning.assert_not_called()

    def test_missing_and_blank_keys_generate_64_hex_characters(self):
        for name in ("SECRET_KEY", "JWT_SECRET"):
            for value in (None, "", "   "):
                with patch.dict(os.environ, {} if value is None else {name: value}, clear=True):
                    key = self.get_secret(name)
                self.assertRegex(key, r"^[0-9a-f]{64}$")
                # Cả template và đối số log đều không chứa khóa sinh ra.
                self.assertNotIn(key, str(self.logger.warning.call_args))

    def test_restart_with_missing_jwt_key_invalidates_previous_token(self):
        with patch.dict(os.environ, {}, clear=True):
            old_key = self.get_secret("JWT_SECRET")
            new_key = self.get_secret("JWT_SECRET")
        token = jwt.encode({"user_id": 1}, old_key, algorithm="HS256")
        self.assertEqual(jwt.decode(token, old_key, algorithms=["HS256"])["user_id"], 1)
        with self.assertRaises(jwt.InvalidSignatureError):
            jwt.decode(token, new_key, algorithms=["HS256"])


if __name__ == "__main__":
    unittest.main()
