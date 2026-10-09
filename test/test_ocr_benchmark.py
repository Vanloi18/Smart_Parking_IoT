"""Kiểm tra pipeline bằng mock OCR; không đo độ chính xác OCR thật, không dùng DB."""
from contextlib import redirect_stdout
import importlib.util
import io
from pathlib import Path
import sys
import tempfile
import unittest
from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("ocr_benchmark", ROOT / "scripts/ocr_benchmark.py")
ocr = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = ocr
spec.loader.exec_module(ocr)


class OCRBenchmarkTest(unittest.TestCase):
    def test_normalization(self):
        for raw, expected in [("30A12345", "30A-123.45"), ("30A-123.45", "30A-123.45"),
                              ("30AB 12345", "30AB-123.45"), ("59X1\n12345", "59X1-123.45"),
                              ("59X1-1234", "59X1-1234"), ("30A-1234", "30A-1234")]:
            self.assertEqual(ocr.normalize_plate(raw), expected)
        for invalid in ("text 30A-123.45 text", "30A-123456", "3OA-123.45", "30A-12", ""):
            self.assertEqual(ocr.normalize_plate(invalid), "")

    def test_two_lines_join_and_confidence(self):
        class Engine:
            def __init__(self):
                self.calls = 0

            def read(self, image, single_line=False):
                self.calls += 1
                if not single_line:
                    return []
                if self.calls == 2:
                    return [ocr.Token("59X1", 0.9, 2, 5, 10)]
                return [ocr.Token("12345", 0.6, 2, 5, 10)]
        engine = Engine()
        result = ocr.recognize(engine, Image.new("RGB", (200, 100)))
        self.assertEqual(result.plate, "59X1-123.45")
        self.assertEqual(result.confidence, 0.6)
        self.assertEqual(result.method, "split_2_lines")
        self.assertEqual(engine.calls, 3)

    def test_variants_and_roi_validation(self):
        image = Image.new("RGB", (100, 80))
        prepared = list(ocr.variants(image, (10, 20, 40, 30)))
        self.assertEqual([name for name, _ in prepared], ["original", "crop", "crop_gray", "crop_contrast_2x"])
        self.assertEqual(prepared[-1][1].size, (80, 60))
        with self.assertRaises(ValueError):
            list(ocr.variants(image, (90, 0, 50, 40)))

    def test_labels_do_not_become_predictions_and_errors_count_wrong(self):
        class EmptyEngine:
            def read(self, image, single_line=False):
                return []
        with tempfile.TemporaryDirectory() as temp:
            folder = Path(temp)
            image = folder / "plate.jpg"
            broken = folder / "broken.jpg"
            Image.new("RGB", (80, 40)).save(image)
            broken.write_bytes(b"broken")
            labels = {"plate.jpg": "30A-123.45", "broken.jpg": "30A-123.45"}
            output = folder / "results.csv"
            log = io.StringIO()
            with redirect_stdout(log):
                records = ocr.benchmark(EmptyEngine(), [image, broken], folder, labels, {}, None, output)
            self.assertTrue(all(row["plate"] == "" and row["correct"] is False for row in records))
            self.assertIn("original: 0/2", log.getvalue())
            self.assertTrue(output.is_file())
            self.assertEqual(broken.read_bytes(), b"broken")

    def test_preprocessing_comparison_math_with_mock_not_actual_ocr(self):
        class FakeEngine:
            def read(self, image, single_line=False):
                if image.mode == "L":
                    return [ocr.Token("30A-123.45", 0.7, 0, 5, 10)]
                return []
        with tempfile.TemporaryDirectory() as temp:
            folder = Path(temp)
            image = folder / "plate.png"
            Image.new("RGB", (80, 40)).save(image)
            log = io.StringIO()
            with redirect_stdout(log):
                ocr.benchmark(FakeEngine(), [image], folder, {"plate.png": "30A-123.45"}, {}, None, None)
            self.assertIn("gray: 1/1 = 100.0%", log.getvalue())
            self.assertIn("+100.0", log.getvalue())

    def test_network_is_blocked(self):
        with ocr.offline_only(), self.assertRaisesRegex(RuntimeError, "offline"):
            with ocr.socket.socket() as connection:
                connection.connect(("127.0.0.1", 1))

    def test_labels_header_and_duplicates(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "labels.csv"
            path.write_text("filename,plate\nimage.jpg,59X1-12345\n", encoding="utf-8-sig")
            self.assertEqual(ocr.load_labels(path), {"image.jpg": "59X1-123.45"})
            path.write_text("a.jpg,30A12345\na.jpg,30A12345\n", encoding="utf8")
            with self.assertRaises(ValueError):
                ocr.load_labels(path)


if __name__ == "__main__":
    unittest.main()
