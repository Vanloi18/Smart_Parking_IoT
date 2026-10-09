"""Benchmark OCR offline độc lập: không import backend, không truy cập DB.

Labels chỉ dùng để chấm điểm SAU nhận diện, tuyệt đối không làm plate hint.
"""
import argparse
from contextlib import contextmanager
import csv
from dataclasses import dataclass
import importlib.util
import json
from pathlib import Path
import re
import shutil
import socket
import sys
import time
from unittest.mock import patch

from PIL import Image, ImageEnhance, ImageOps

ROOT = Path(__file__).resolve().parents[1]
EXTENSIONS = {".jpg", ".jpeg", ".png", ".bmp", ".webp", ".tif", ".tiff"}


def normalize_plate(text):
    # Biển phổ thông ô tô/xe máy: không tự đổi O->0, không cắt chuỗi dư.
    compact = re.sub(r"[\s._\-–—]+", "", text.upper())
    # Khi không có dấu phân cách, ưu tiên ô tô 30A12345 -> 30A-123.45,
    # tránh regex tham lam biến thành 30A1-2345.
    separated = re.fullmatch(r"\s*([0-9]{2}[A-Z][A-Z0-9]?)\s*[-–—]\s*([0-9\s.]{4,})\s*", text.upper())
    if separated:
        digits = re.sub(r"[\s.]", "", separated.group(2))
        if len(digits) not in (4, 5):
            return ""
        suffix = digits[:3] + "." + digits[3:] if len(digits) == 5 else digits
        return separated.group(1) + "-" + suffix
    else:
        match = re.fullmatch(r"([0-9]{2}[A-Z]{1,2})([0-9]{4,5})", compact)
        if not match:
            match = re.fullmatch(r"([0-9]{2}[A-Z][0-9])([0-9]{4,5})", compact)
    if not match:
        return ""
    prefix, digits = match.groups()
    if len(digits) == 5:
        digits = digits[:3] + "." + digits[3:]
    return prefix + "-" + digits


@dataclass
class Token:
    text: str
    confidence: float
    x: float
    y: float
    height: float


@dataclass
class Candidate:
    plate: str = ""
    confidence: float = 0.0
    raw: str = ""
    method: str = ""


@contextmanager
def offline_only():
    # Thiếu model thì báo lỗi; benchmark không tự tải model hay gửi ảnh ra mạng.
    def blocked(*args, **kwargs):
        raise RuntimeError("Benchmark offline: kết nối mạng bị chặn; hãy tải model trước bằng công cụ của engine")
    with patch.object(socket.socket, "connect", blocked), patch.object(socket.socket, "connect_ex", blocked):
        yield


def ordered_lines(tokens):
    lines = []
    for token in sorted(tokens, key=lambda t: (t.y, t.x)):
        line = next((line for line in lines if abs(line[0].y - token.y) <= max(line[0].height, token.height) * 0.6), None)
        if line is None:
            lines.append([token])
        else:
            line.append(token)
    return [sorted(line, key=lambda t: t.x) for line in lines]


def candidates(tokens, method):
    lines = ordered_lines(tokens)
    results = []
    # Ghép các từ liền nhau trong một dòng hoặc hai dòng kề nhau, không ghép cả cảnh tùy ý.
    groups = lines + [lines[i] + lines[i + 1] for i in range(len(lines) - 1)]
    for group in groups:
        for start in range(len(group)):
            for end in range(start + 1, min(len(group), start + 5) + 1):
                chosen = group[start:end]
                text = " ".join(token.text for token in chosen)
                plate = normalize_plate(text)
                if plate:
                    # Điểm thấp nhất trong các phần: không che khuất một dòng đọc yếu.
                    results.append(Candidate(plate, min(t.confidence for t in chosen), text, method))
    return results


class TesseractEngine:
    def __init__(self, executable):
        import pytesseract
        self.module = pytesseract
        if executable:
            if not Path(executable).is_file():
                raise RuntimeError("Không tìm thấy --tesseract-cmd")
            self.module.pytesseract.tesseract_cmd = executable
        self.module.get_tesseract_version()

    def read(self, image, single_line=False):
        psm = 7 if single_line else 6
        data = self.module.image_to_data(image, lang="eng", output_type=self.module.Output.DICT,
                                        config=f"--psm {psm}", timeout=15)
        result = []
        for i, text in enumerate(data["text"]):
            confidence = float(data["conf"][i])
            if text.strip() and confidence >= 0:
                result.append(Token(text.strip(), min(1.0, confidence / 100), data["left"][i],
                                    data["top"][i] + data["height"][i] / 2, max(1, data["height"][i])))
        return result


class RapidEngine:
    def __init__(self):
        import rapidocr
        # API và tên model đã kiểm tra với RapidOCR 3.10.0; không dùng gói 1.x cũ.
        folder = Path(rapidocr.__file__).resolve().parent / "models"
        paths = {"Det": folder / "PP-OCRv6_det_small.onnx",
                 "Cls": folder / "ch_ppocr_mobile_v2.0_cls_mobile.onnx",
                 "Rec": folder / "PP-OCRv6_rec_small.onnx"}
        missing = [str(path) for path in paths.values() if not path.is_file()]
        if missing:
            raise RuntimeError("Thiếu model local: " + ", ".join(missing) + ". Chạy rapidocr download_models trước khi dùng offline.")
        self.engine = rapidocr.RapidOCR(params={name + ".model_path": str(path) for name, path in paths.items()})

    def read(self, image, single_line=False):
        import numpy as np
        # Input ndarray RapidOCR là BGR, trong khi Pillow là RGB.
        result = self.engine(np.asarray(image.convert("RGB"))[:, :, ::-1].copy())
        if result.txts is None:
            return []
        tokens = []
        for box, text, confidence in zip(result.boxes, result.txts, result.scores):
            xs, ys = [float(point[0]) for point in box], [float(point[1]) for point in box]
            tokens.append(Token(text, max(0.0, min(1.0, float(confidence))), min(xs),
                                sum(ys) / len(ys), max(1.0, max(ys) - min(ys))))
        return tokens


def variants(image, roi=None):
    yield "original", image
    source = image
    prefix = ""
    if roi:
        x, y, width, height = roi
        if min(x, y) < 0 or min(width, height) <= 0 or x + width > image.width or y + height > image.height:
            raise ValueError("ROI nằm ngoài ảnh hoặc kích thước không hợp lệ")
        source = image.crop((x, y, x + width, y + height))
        prefix = "crop_"
        yield "crop", source
    gray = ImageOps.grayscale(source)
    yield prefix + "gray", gray
    # Tách phép so sánh: ảnh gốc -> xám -> tăng tương phản/phóng 2x.
    enhanced = ImageEnhance.Contrast(ImageOps.autocontrast(gray)).enhance(1.6)
    enhanced = enhanced.resize((enhanced.width * 2, enhanced.height * 2), Image.Resampling.LANCZOS)
    yield prefix + "contrast_2x", enhanced


def recognize(engine, image):
    found = candidates(engine.read(image), "whole")
    midpoint = image.height // 2
    if midpoint > 0:
        # Biển hai dòng: cắt ngang giữa ảnh ROI, trả tọa độ dòng dưới về ảnh chung.
        top = engine.read(image.crop((0, 0, image.width, midpoint)), single_line=True)
        bottom = engine.read(image.crop((0, midpoint, image.width, image.height)), single_line=True)
        for token in bottom:
            token.y += midpoint
        found += candidates(top + bottom, "split_2_lines")
    if not found:
        return Candidate()
    return max(found, key=lambda c: c.confidence)


def load_labels(path):
    if not path.is_file():
        return {}
    with path.open(encoding="utf-8-sig", newline="") as handle:
        rows = list(csv.reader(handle))
    if rows and rows[0] and rows[0][0].strip().lower() in ("filename", "file", "ten_anh", "tên ảnh"):
        rows = rows[1:]
    labels = {}
    for row in rows:
        if not row or all(not cell.strip() for cell in row):
            continue
        if len(row) != 2:
            raise ValueError("labels.csv cần đúng hai cột filename,plate")
        filename, raw = (cell.strip() for cell in row)
        plate = normalize_plate(raw)
        if not plate or filename in labels:
            raise ValueError("Nhãn không hợp lệ hoặc trùng filename: " + filename)
        labels[filename] = plate
    return labels


def benchmark(engine, files, folder, labels, roi_map, default_roi, output):
    records = []
    print("Tên ảnh | Biến thể | Kết quả | Confidence | Đúng nhãn | ms | Cách đọc / lỗi")
    for file in files:
        name = file.relative_to(folder).as_posix()
        try:
            with Image.open(file) as opened:
                image = ImageOps.exif_transpose(opened).convert("RGB")
            prepared = list(variants(image, roi_map.get(name, default_roi)))
        except Exception as error:
            prepared = [("original", None)]
            image_error = str(error)
        for variant, processed in prepared:
            started = time.perf_counter()
            error = ""
            try:
                if processed is None:
                    raise ValueError(image_error)
                prediction = recognize(engine, processed)
            except Exception as exc:
                prediction, error = Candidate(), str(exc)
            # Nhãn chỉ được đọc ở đây, sau khi OCR đã kết thúc.
            expected = labels.get(name)
            correct = prediction.plate == expected if expected is not None else None
            record = {"filename": name, "variant": variant, "plate": prediction.plate,
                      "confidence": round(prediction.confidence, 4), "expected": expected or "",
                      "correct": correct, "elapsed_ms": round((time.perf_counter() - started) * 1000, 1),
                      "method": prediction.method, "raw_text": prediction.raw, "error": error}
            records.append(record)
            print(f"{name} | {variant} | {prediction.plate or '(trống)'} | {prediction.confidence:.3f} | "
                  f"{str(correct) if correct is not None else '-'} | {record['elapsed_ms']} | {error or prediction.method}")
    print("\nSo sánh trên cùng ảnh có nhãn; ảnh lỗi/không đọc được vẫn tính là sai:")
    baseline = {r["filename"]: r for r in records if r["variant"] == "original"}
    for variant in dict.fromkeys(r["variant"] for r in records):
        group = [r for r in records if r["variant"] == variant]
        labeled = [r for r in group if r["correct"] is not None]
        if not labeled:
            print(variant + ": chưa có nhãn, không thể kết luận cải thiện")
            continue
        right = sum(r["correct"] for r in labeled)
        base_right = sum(baseline[r["filename"]]["correct"] for r in labeled)
        gain = 100 * (right - base_right) / len(labeled)
        print(f"{variant}: {right}/{len(labeled)} = {100 * right / len(labeled):.1f}% ; "
              f"chênh so với ảnh gốc cùng tập: {gain:+.1f} điểm phần trăm")
    unread = sorted(set(labels) - set(baseline))
    if unread:
        print("Nhãn không có ảnh tương ứng (không chấm):", ", ".join(unread))
    if output:
        output.parent.mkdir(parents=True, exist_ok=True)
        with output.open("w", encoding="utf-8-sig", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=list(records[0]))
            writer.writeheader()
            writer.writerows(records)
        print("CSV:", output.resolve())
    return records


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--engine", choices=("tesseract", "rapidocr"), default="tesseract")
    parser.add_argument("--samples", type=Path, default=ROOT / "samples/plates")
    parser.add_argument("--labels", type=Path, help="Mặc định samples/plates/labels.csv")
    parser.add_argument("--roi", type=int, nargs=4, metavar=("X", "Y", "W", "H"), help="Vùng biển số chung cho các ảnh")
    parser.add_argument("--roi-json", type=Path, help='JSON: {"image.jpg": [x,y,w,h]}')
    parser.add_argument("--tesseract-cmd", help="Đường dẫn tesseract.exe nếu chưa nằm trong PATH")
    parser.add_argument("--output", type=Path, help="Lưu bảng chi tiết CSV; không sửa ảnh nguồn")
    args = parser.parse_args()
    folder = args.samples.resolve()
    if args.output and (args.output.suffix.lower() != ".csv" or args.output.resolve() == (args.labels or folder / "labels.csv").resolve()):
        parser.error("--output phải là CSV riêng, không được ghi đè labels.csv")
    files = sorted(path for path in folder.rglob("*") if path.is_file() and path.suffix.lower() in EXTENSIONS)
    if not files:
        print("Chưa có ảnh. Thêm ảnh thật hoặc ảnh ROI biển số vào:", folder)
        return 0
    labels = load_labels(args.labels or folder / "labels.csv")
    roi_map = json.loads(args.roi_json.read_text(encoding="utf-8-sig")) if args.roi_json else {}
    module = "pytesseract" if args.engine == "tesseract" else "rapidocr"
    if importlib.util.find_spec(module) is None:
        raise RuntimeError("Chưa cài " + module + "; xem samples/plates/README.md để cài thủ công")
    executable = args.tesseract_cmd or shutil.which("tesseract")
    if args.engine == "tesseract" and not executable:
        usual = Path(r"C:\Program Files\Tesseract-OCR\tesseract.exe")
        executable = str(usual) if usual.is_file() else None
        if not executable:
            raise RuntimeError("Chưa có Tesseract executable; pip pytesseract không cài tesseract.exe")
    with offline_only():
        engine = TesseractEngine(executable) if args.engine == "tesseract" else RapidEngine()
        records = benchmark(engine, files, folder, labels, roi_map, args.roi, args.output)
    return 1 if all(record["error"] for record in records) else 0


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    try:
        raise SystemExit(main())
    except Exception as exc:
        print("ERROR:", exc, file=sys.stderr)
        raise SystemExit(2)
