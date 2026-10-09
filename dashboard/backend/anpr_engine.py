"""OCR thật chỉ tạo gợi ý; không dùng plate hint để tạo/đóng vé RFID."""
import os
from datetime import datetime
from PIL import Image
from plate_ocr import normalize_plate

UPLOAD_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "uploads")
os.makedirs(UPLOAD_DIR, exist_ok=True)


class ANPREngine:
    def __init__(self, upload_dir=UPLOAD_DIR):
        self.upload_dir = upload_dir
        self.pytesseract = None
        self.ocr_available = False
        try:
            import pytesseract
            cmd = os.environ.get("TESSERACT_CMD")
            if cmd:
                pytesseract.pytesseract.tesseract_cmd = cmd
            elif os.path.isfile(r"C:\Program Files\Tesseract-OCR\tesseract.exe"):
                pytesseract.pytesseract.tesseract_cmd = r"C:\Program Files\Tesseract-OCR\tesseract.exe"
            pytesseract.get_tesseract_version()
            self.pytesseract = pytesseract
            self.ocr_available = True
        except Exception:
            print("[ANPR] Tesseract unavailable; tickets still work with empty plates")
        try:
            self.min_confidence = float(os.environ.get("OCR_MIN_CONFIDENCE", "0.70"))
            if not 0 <= self.min_confidence <= 1:
                raise ValueError()
        except ValueError:
            self.min_confidence = 0.70

    def save_image_bytes(self, image_bytes, camera_id="CAM", ext=".jpg"):
        # Microseconds tránh ghi đè hai ảnh cùng millisecond.
        filename = camera_id.lower() + "_" + datetime.now().strftime("%Y%m%d_%H%M%S_%f") + ext
        filepath = os.path.join(self.upload_dir, filename)
        with open(filepath, "wb") as handle:
            handle.write(image_bytes)
        return filepath, "/uploads/" + filename

    def process_capture(self, image_data, camera_id="ENTRY_CAM", camera_role="ENTRY", client_plate_hint=None):
        result = {"success": False, "plateNumber": None, "confidence": None, "camera": camera_id,
                  "camera_role": camera_role, "image_valid": False, "timestamp": datetime.now().isoformat()}
        # Tham số cũ chỉ giữ tương thích chữ ký; hint không tham gia OCR.
        if client_plate_hint:
            result["test_hint_ignored"] = True
        try:
            if isinstance(image_data, bytes):
                filepath, result["image_url"] = self.save_image_bytes(image_data, camera_id)
            elif isinstance(image_data, str) and os.path.isfile(image_data):
                filepath = image_data
                result["image_url"] = "/uploads/" + os.path.basename(filepath)
            else:
                return dict(result, reason="INVALID_IMAGE_DATA")
            with Image.open(filepath) as image:
                image.verify()
            result["image_valid"] = True
        except Exception:
            return dict(result, reason="CORRUPTED_OR_UNSAVED_IMAGE")
        if not self.ocr_available:
            return dict(result, reason="ANPR_UNAVAILABLE")
        try:
            plate, confidence = self._extract_plate_from_image(filepath)
        except Exception:
            return dict(result, reason="OCR_ERROR")
        result["confidence"] = confidence
        if not plate:
            return dict(result, reason="PLATE_NOT_DETECTED")
        if confidence is None or confidence < self.min_confidence:
            return dict(result, reason="LOW_CONFIDENCE")
        return dict(result, success=True, plateNumber=plate, reason="OK")

    def _read_parts(self, image, psm):
        data = self.pytesseract.image_to_data(image, lang="eng", output_type=self.pytesseract.Output.DICT,
                                            config=f"--psm {psm}", timeout=2)
        return [(text.strip(), float(conf) / 100) for text, conf in zip(data["text"], data["conf"])
                if text.strip() and float(conf) >= 0]

    def _extract_plate_from_image(self, filepath):
        with Image.open(filepath) as opened:
            image = opened.convert("RGB")
        # Chưa có bằng chứng tiền xử lý cải thiện ảnh thật: giữ nguyên ảnh màu.
        groups = [self._read_parts(image, 6)]
        midpoint = image.height // 2
        if midpoint > 0:
            top = self._read_parts(image.crop((0, 0, image.width, midpoint)), 7)
            bottom = self._read_parts(image.crop((0, midpoint, image.width, image.height)), 7)
            groups.append(top + bottom)  # Biển hai dòng, đọc trên trước dưới.
        choices = []
        for tokens in groups:
            for start in range(len(tokens)):
                for stop in range(start + 1, min(len(tokens), start + 5) + 1):
                    selected = tokens[start:stop]
                    plate = normalize_plate(" ".join(text for text, _ in selected))
                    if plate:
                        choices.append((plate, min(conf for _, conf in selected)))
        return max(choices, key=lambda item: item[1]) if choices else (None, None)

    def _format_plate(self, raw_str):
        return normalize_plate(raw_str)


anpr_service = ANPREngine()
