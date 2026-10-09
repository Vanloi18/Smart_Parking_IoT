"""Vé RFID theo lượt: một transaction cho phiên, phí và lệnh chụp liên quan."""
from contextlib import closing
from datetime import datetime, timedelta
import re


def process_ticket(card_uid, gate):
    from db import get_connection, calculate_parking_fee
    uid = str(card_uid or "").strip().upper()
    result = {"allowed": False, "success": False, "action": "ACCESS_DENIED",
              "reason": "INVALID_UID", "plate": None, "fee": 0, "durationMinutes": 0,
              "duration_seconds": 0, "cardUid": uid}
    if not re.fullmatch(r"[A-Z0-9_-]{1,64}", uid):
        return result
    now = datetime.now()
    stamp = now.isoformat()
    with closing(get_connection()) as conn, conn:
        # Khóa writer để hai lần quẹt đồng thời không tạo hai phiên cho cùng UID.
        conn.execute("BEGIN IMMEDIATE")
        session = conn.execute("SELECT * FROM parking_sessions WHERE rfid_uid=? AND status='PARKED' ORDER BY id DESC LIMIT 1", (uid,)).fetchone()
        if gate == "ENTRY":
            if session:
                return dict(result, reason="ALREADY_PARKED", session_id=session["id"])
            if conn.execute("SELECT count(*) FROM slots WHERE is_occupied=0").fetchone()[0] == 0:
                return dict(result, reason="PARKING_FULL")
            cursor = conn.execute("""INSERT INTO parking_sessions (rfid_uid,entry_time,status,payment_status,entry_camera)
                                     VALUES (?,?,'PARKED','UNPAID','ENTRY_CAM')""", (uid, stamp))
            session_id = cursor.lastrowid
            conn.execute("INSERT INTO parking_transactions (card_uid,entry_time,status) VALUES (?,?,'PARKED')", (uid, stamp))
            camera = "ENTRY_CAM"
        else:
            if not session:
                return dict(result, reason="NO_OPEN_SESSION")
            session_id = session["id"]
            # Một mốc giờ ra và một kết quả phí dùng cho cả JSON, session và payment.
            duration = max(0, int((now - datetime.fromisoformat(session["entry_time"])).total_seconds()))
            fee = calculate_parking_fee(duration)
            conn.execute("""UPDATE parking_sessions SET exit_time=?,duration_seconds=?,fee=?,status='CHECKED_OUT',
                            payment_status='PAID',payment_time=?,payment_method='CASH',exit_camera='EXIT_CAM' WHERE id=?""",
                         (stamp, duration, fee, stamp, session_id))
            conn.execute("""UPDATE parking_transactions SET exit_time=?,duration_seconds=?,fee=?,status='COMPLETED'
                            WHERE card_uid=? AND status='PARKED'""", (stamp, duration, fee, uid))
            conn.execute("INSERT INTO payments (session_id,plate_number,amount,paid_at) VALUES (?,?,?,?)",
                         (session_id, session["plate_number"], fee, stamp))
            result.update(plate=session["plate_number"], fee=fee, duration_seconds=duration, durationMinutes=round(duration / 60, 2))
            camera = "EXIT_CAM"
        command = conn.execute("INSERT INTO camera_commands (camera_id,command,status,created_at,session_id) VALUES (?,'CAPTURE','PENDING',?,?)",
                               (camera, stamp, session_id))
        # Ghi nhận RFID; trạng thái barie thực tế vẫn do telemetry/ACK cập nhật.
        field = "last_entry_card" if gate == "ENTRY" else "last_exit_card"
        conn.execute(f"UPDATE system_state SET {field}=?,updated_at=? WHERE id=1", (uid, stamp))
        conn.execute("INSERT INTO system_events (event_type,description,details,timestamp) VALUES (?,?,?,?)",
                     ("VEHICLE_ENTERED" if gate == "ENTRY" else "VEHICLE_EXITED", f"Ticket {gate}: {uid}", f"Session ID: {session_id}", stamp))
        return dict(result, allowed=True, success=True, action="ACCESS_GRANTED", reason="OK",
                    session_id=session_id, command_id=command.lastrowid, message="Ticket accepted")


def claim_camera_capture(camera_id, max_age_seconds=60):
    from db import get_connection
    cutoff = (datetime.now() - timedelta(seconds=max_age_seconds)).isoformat()
    with closing(get_connection()) as conn, conn:
        conn.execute("BEGIN IMMEDIATE")
        row = conn.execute("""SELECT id,session_id FROM camera_commands WHERE camera_id=? AND status='DISPATCHED'
                              AND created_at>=? AND capture_received_at IS NULL ORDER BY id LIMIT 1""", (camera_id, cutoff)).fetchone()
        if not row:
            return None
        # Claim trước OCR để hai upload trùng không gắn ảnh vào phiên khác.
        conn.execute("UPDATE camera_commands SET capture_received_at=? WHERE id=?", (datetime.now().isoformat(), row["id"]))
        return dict(row)


def attach_capture(claim, role, result):
    from db import get_connection
    if not claim or not claim.get("session_id"):
        return None  # Chụp thủ công không tạo/đóng vé, không thu tiền.
    with closing(get_connection()) as conn, conn:
        conn.execute("BEGIN IMMEDIATE")  # OCR đến trễ không đè thao tác nhập tay đồng thời.
        session = conn.execute("SELECT * FROM parking_sessions WHERE id=?", (claim["session_id"],)).fetchone()
        if not session:
            return None
        image = result.get("image_url") if result.get("image_valid") else None
        image_field = "entry_image_url" if role == "ENTRY" else "exit_image_url"
        missing_field = "missing_entry_image" if role == "ENTRY" else "missing_exit_image"
        conn.execute(f"UPDATE parking_sessions SET {image_field}=?,{missing_field}=? WHERE id=?",
                     (image, int(not image), session["id"]))
        # Ảnh ra chỉ để đối chiếu; không ghi đè biển đã được bảo vệ xác nhận.
        if role == "ENTRY" and session["needs_plate"] and not session["plate_number"] and result.get("plateNumber"):
            conn.execute("UPDATE parking_sessions SET plate_number=?,plate_source='OCR',ocr_confidence=? WHERE id=?",
                         (result["plateNumber"], result.get("confidence"), session["id"]))
        return session["id"]


def update_session_plate(session_id, plate):
    from db import get_connection
    from plate_ocr import normalize_plate
    raw = str(plate or "").strip()
    normalized = normalize_plate(raw) if raw else None
    if raw and not normalized:
        return {"status": "error", "message": "Biển số không đúng định dạng phổ thông"}, 400
    with closing(get_connection()) as conn, conn:
        conn.execute("BEGIN IMMEDIATE")
        session = conn.execute("SELECT * FROM parking_sessions WHERE id=?", (session_id,)).fetchone()
        if not session:
            return {"status": "error", "message": "Không tìm thấy phiên"}, 404
        if session["status"] != "PARKED":
            return {"status": "error", "message": "Chỉ sửa biển số phiên đang mở"}, 409
        source = "OCR" if normalized and normalized == session["plate_number"] and session["plate_source"] == "OCR" else "MANUAL" if normalized else None
        conn.execute("UPDATE parking_sessions SET plate_number=?,plate_source=?,needs_plate=? WHERE id=?",
                     (normalized, source, int(not normalized), session_id))
        return {"status": "success", "session_id": session_id, "plate": normalized, "plate_source": source}, 200
