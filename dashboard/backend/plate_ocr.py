"""Chuẩn hóa biển phổ thông; không tự sửa ký tự O/0/I/1 hoặc dùng hint."""
import re


def normalize_plate(text):
    text = str(text or "").upper().strip()
    separated = re.fullmatch(r"([0-9]{2}[A-Z][A-Z0-9]?)\s*[-–—]\s*([0-9\s.]{4,})", text)
    if separated:
        prefix = separated.group(1)
        digits = re.sub(r"[\s.]", "", separated.group(2))
        if len(digits) not in (4, 5):
            return None
    else:
        compact = re.sub(r"[\s._-]+", "", text)
        match = re.fullmatch(r"([0-9]{2}[A-Z]{1,2})([0-9]{4,5})", compact)
        if not match:
            match = re.fullmatch(r"([0-9]{2}[A-Z][0-9])([0-9]{4,5})", compact)
        if not match:
            return None
        prefix, digits = match.groups()
    return prefix + "-" + (digits[:3] + "." + digits[3:] if len(digits) == 5 else digits)
