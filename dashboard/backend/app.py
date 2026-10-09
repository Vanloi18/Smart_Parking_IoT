import os
import json
import time
import queue
import secrets
from datetime import datetime, timedelta
from functools import wraps
from flask import Flask, request, jsonify, Response, send_from_directory
from flask_cors import CORS
from werkzeug.security import check_password_hash
import jwt
from dotenv import load_dotenv

from db import (
    init_db,
    update_telemetry,
    record_entry,
    record_exit,
    get_current_status,
    get_slots_detail,
    get_all_vehicles,
    get_all_payments,
    get_all_history,
    get_detailed_sensors,
    get_user_by_username,
    get_user_by_id,
    update_camera_heartbeat,
    log_camera_event,
    get_camera_statuses,
    create_or_find_entry_session,
    close_exit_session,
    log_system_event,
    get_connection,
    add_barrier_command,
    get_pending_barrier_command,
    ack_barrier_command,
    add_camera_command,
    get_pending_camera_command,
    ack_camera_command,
    calculate_parking_fee,
    BILLING_RATE_PER_INTERVAL,
    BILLING_INTERVAL_SECONDS
)
from anpr_engine import anpr_service, UPLOAD_DIR
from tickets import claim_camera_capture, attach_capture, update_session_plate

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FRONTEND_DIR = os.path.join(BASE_DIR, "frontend")

app = Flask(__name__, static_folder=FRONTEND_DIR, static_url_path="")
CORS(app, resources={r"/api/*": {"origins": "*"}}, supports_credentials=True)

# Nạp .env cả khi app được import trực tiếp, không ghi đè biến môi trường.
load_dotenv(os.path.join(os.path.dirname(BASE_DIR), ".env"))

def get_runtime_secret(name):
    value = os.environ.get(name, "").strip()
    if value:
        return value
    # Khóa tạm chỉ tồn tại trong lần chạy này; tuyệt đối không ghi khóa vào log.
    app.logger.warning(
        "CẢNH BÁO: thiếu %s; dùng khóa ngẫu nhiên tạm thời. "
        "Người dùng sẽ bị đăng xuất khi backend khởi động lại.", name
    )
    return secrets.token_hex(32)

SECRET_KEY = get_runtime_secret("SECRET_KEY")
JWT_SECRET = get_runtime_secret("JWT_SECRET")
app.config["SECRET_KEY"] = SECRET_KEY

# Hàng đợi SSE để truyền dữ liệu thời gian thực tới trình duyệt
sse_listeners = []

def notify_clients(event_type, data):
    payload = json.dumps({"type": event_type, "timestamp": datetime.now().isoformat(), "data": data})
    msg = f"data: {payload}\n\n"
    dead_queues = []
    for q in sse_listeners:
        try:
            q.put_nowait(msg)
        except Exception:
            dead_queues.append(q)
    for dq in dead_queues:
        if dq in sse_listeners:
            sse_listeners.remove(dq)

# ============================================================================
# AUTHENTICATION & JWT MIDDLEWARE
# ============================================================================

def generate_jwt(user):
    payload = {
        "user_id": user["id"],
        "username": user["username"],
        "role": user["role"],
        "exp": datetime.utcnow() + timedelta(hours=24)
    }
    return jwt.encode(payload, JWT_SECRET, algorithm="HS256")

def token_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        token = None
        auth_header = request.headers.get("Authorization")
        if auth_header and auth_header.startswith("Bearer "):
            token = auth_header.split(" ")[1]
        elif "token" in request.args:
            token = request.args.get("token")

        if not token:
            return jsonify({"status": "error", "message": "Authentication token missing"}), 401

        try:
            data = jwt.decode(token, JWT_SECRET, algorithms=["HS256"])
            current_user = get_user_by_id(data["user_id"])
            if not current_user:
                return jsonify({"status": "error", "message": "User not found"}), 401
        except jwt.ExpiredSignatureError:
            return jsonify({"status": "error", "message": "Token has expired"}), 401
        except Exception:
            return jsonify({"status": "error", "message": "Invalid token"}), 401

        return f(current_user, *args, **kwargs)
    return decorated

@app.route("/api/auth/login", methods=["POST"])
def auth_login():
    """Đăng nhập hệ thống Dashboard"""
    data = request.get_json(silent=True) or {}
    username = str(data.get("username", "")).strip()
    password = str(data.get("password", "")).strip()

    if not username or not password:
        return jsonify({"status": "error", "message": "Vui lòng nhập đầy đủ tên đăng nhập và mật khẩu"}), 400

    user = get_user_by_username(username)
    if not user or not check_password_hash(user["password_hash"], password):
        log_system_event("AUTH_FAILED", f"Đăng nhập thất bại: {username}", f"IP: {request.remote_addr}")
        return jsonify({"status": "error", "message": "Tên đăng nhập hoặc mật khẩu không chính xác"}), 401

    token = generate_jwt(user)
    log_system_event("AUTH_LOGIN", f"Đăng nhập thành công: {username} ({user['role']})", f"IP: {request.remote_addr}")

    return jsonify({
        "status": "success",
        "message": "Đăng nhập thành công",
        "token": token,
        "user": {
            "id": user["id"],
            "username": user["username"],
            "role": user["role"],
            "full_name": user["full_name"]
        }
    }), 200

@app.route("/api/auth/logout", methods=["POST"])
def auth_logout():
    return jsonify({"status": "success", "message": "Đăng xuất thành công"}), 200

@app.route("/api/auth/me", methods=["GET"])
@token_required
def auth_me(current_user):
    return jsonify({
        "status": "success",
        "user": {
            "id": current_user["id"],
            "username": current_user["username"],
            "role": current_user["role"],
            "full_name": current_user["full_name"]
        }
    }), 200

# ============================================================================
# API ENDPOINTS DÀNH CHO ESP32 FIRMWARE & TELEMETRY
# ============================================================================

@app.route("/api/telemetry/heartbeat", methods=["POST"])
def telemetry_heartbeat():
    """
    ESP32 DevKit gửi bản tin Telemetry Heartbeat mỗi 3 giây.
    """
    data = request.get_json(silent=True)
    if not data:
        return jsonify({"status": "error", "message": "Invalid JSON body"}), 400

    slots = data.get("slots", {})
    p1 = int(slots.get("P1", 0))
    p2 = int(slots.get("P2", 0))
    p3 = int(slots.get("P3", 0))
    p4 = int(slots.get("P4", 0))

    temp = float(data.get("temp", 0.0))
    hum = float(data.get("hum", 0.0))
    gas = int(data.get("gas", 0))
    gas_level = str(data.get("gasLevel", "NORMAL"))
    barrier_entry = str(data.get("barrierEntry", "CLOSED"))
    barrier_exit = str(data.get("barrierExit", "CLOSED"))
    free_slots = int(data.get("freeSlots", 4 - (p1 + p2 + p3 + p4)))

    # Lưu dữ liệu vào SQLite
    update_telemetry(p1, p2, p3, p4, temp, hum, gas, gas_level, barrier_entry, barrier_exit, free_slots)

    # Đẩy cập nhật realtime tới Web Dashboard
    current_status = get_current_status()
    notify_clients("telemetry", current_status)

    return jsonify({
        "status": "success",
        "message": "Telemetry received and recorded",
        "freeSlots": free_slots,
        "timestamp": datetime.now().isoformat()
    }), 200

def ticket_response(gate):
    data = request.get_json(silent=True) or {}
    if not isinstance(data, dict) or not isinstance(data.get("cardUid"), str):
        return jsonify({"status": "error", "allowed": False, "reason": "INVALID_UID",
                        "plate": None, "fee": 0, "durationMinutes": 0}), 400
    result = record_entry(data["cardUid"]) if gate == "ENTRY" else record_exit(data["cardUid"])
    result["status"] = "success" if result["allowed"] else "denied"
    notify_clients(gate.lower() + ("_granted" if result["allowed"] else "_denied"),
                   {"cardUid": result["cardUid"], "result": result})
    return jsonify(result), 200


@app.route("/api/parking/entry", methods=["POST"])
def parking_entry():
    return ticket_response("ENTRY")


@app.route("/api/parking/exit", methods=["POST"])
def parking_exit():
    return ticket_response("EXIT")


@app.route("/api/parking/sessions/<int:session_id>", methods=["GET"])
def parking_session_detail(session_id):
    conn = get_connection()
    try:
        row = conn.execute("SELECT * FROM parking_sessions WHERE id=?", (session_id,)).fetchone()
        if not row:
            return jsonify({"status": "error", "message": "Không tìm thấy phiên"}), 404
        return jsonify({"status": "success", "session": dict(row)}), 200
    finally:
        conn.close()


@app.route("/api/parking/sessions/<int:session_id>/plate", methods=["PATCH"])
@token_required
def parking_session_plate(current_user, session_id):
    data = request.get_json(silent=True) or {}
    if not isinstance(data, dict) or not isinstance(data.get("plate", ""), str):
        return jsonify({"status": "error", "message": "Biển số phải là chuỗi"}), 400
    result, code = update_session_plate(session_id, data.get("plate", ""))
    if code == 200:
        log_system_event("PLATE_CONFIRMED", f"Session #{session_id} confirmed by {current_user['username']}")
        notify_clients("session_updated", result)
    return jsonify(result), code


@app.route("/api/barrier/control", methods=["POST"])
def barrier_control():
    """
    Điều khiển barrier từ xa từ Web Dashboard.
    Payload: {"barrier": "ENTRY"|"EXIT", "action": "OPEN"|"CLOSE"}
    hoặc {"gate": "ENTRY"|"EXIT", "command": "OPEN"|"CLOSE"}
    """
    data = request.get_json(silent=True) or {}
    gate = str(data.get("barrier", data.get("gate", "ENTRY"))).upper()
    cmd = str(data.get("action", data.get("command", "OPEN"))).upper()

    # Enqueue command để Main ESP32 polling thực thi phần cứng thật
    cmd_id = add_barrier_command(gate, cmd, "MAIN_ESP32")

    conn = get_connection()
    cursor = conn.cursor()
    if gate == "ENTRY":
        cursor.execute("UPDATE system_state SET barrier_entry = ?, updated_at = ? WHERE id = 1",
                       (cmd, datetime.now().isoformat()))
    else:
        cursor.execute("UPDATE system_state SET barrier_exit = ?, updated_at = ? WHERE id = 1",
                       (cmd, datetime.now().isoformat()))
    conn.commit()
    conn.close()

    status = get_current_status()
    log_system_event("BARRIER_CONTROL", f"Thao tác điều khiển barrier: {gate} -> {cmd} (Command ID: #{cmd_id})")
    notify_clients("barrier_override", {"gate": gate, "command": cmd, "state": status, "command_id": cmd_id})

    return jsonify({"status": "success", "command_id": cmd_id, "gate": gate, "state": cmd}), 200

@app.route("/api/barrier/commands", methods=["GET"])
def get_barrier_commands():
    """
    Main ESP32 polling kiểm tra lệnh điều khiển barrier đang PENDING.
    """
    device_id = request.args.get("device_id", "MAIN_ESP32")
    cmd = get_pending_barrier_command(device_id)
    return jsonify(cmd), 200

@app.route("/api/barrier/commands/<int:cmd_id>/ack", methods=["POST"])
@app.route("/api/barrier/ack", methods=["POST"])
def ack_barrier_commands(cmd_id=None):
    """
    Main ESP32 gửi ACK báo đã thực thi xong lệnh điều khiển servo.
    """
    data = request.get_json(silent=True) or {}
    cid = cmd_id or data.get("id") or data.get("command_id")
    status = data.get("status", "EXECUTED")
    device_id = data.get("device_id", "MAIN_ESP32")
    if cid:
        ack_barrier_command(cid, status, device_id)
        log_system_event("BARRIER_ACK", f"Main ESP32 hoàn thành lệnh #{cid} ({status})")
        return jsonify({"status": "success", "command_id": cid}), 200
    return jsonify({"status": "error", "message": "Missing command ID"}), 400

@app.route("/api/cameras/<role_or_id>/command", methods=["POST"])
@app.route("/api/cameras/command", methods=["POST"])
def camera_trigger_command(role_or_id=None):
    """
    Web Dashboard hoặc hệ thống phát lệnh chụp ảnh cho ESP32-CAM.
    Payload: {"command": "CAPTURE"} hoặc {"camera": "ENTRY", "action": "CAPTURE"}
    """
    data = request.get_json(silent=True) or {}
    cam = role_or_id or data.get("camera", data.get("camera_id", "ENTRY"))
    cam_upper = str(cam).upper()
    if "ENTRY" in cam_upper:
        target_cam = "ENTRY_CAM"
    elif "EXIT" in cam_upper:
        target_cam = "EXIT_CAM"
    else:
        target_cam = cam_upper

    action = str(data.get("action", data.get("command", "CAPTURE"))).upper()
    cmd_id = add_camera_command(target_cam, action)
    log_system_event("CAMERA_COMMAND", f"Lệnh gửi tới {target_cam}: {action} (Command ID: #{cmd_id})")
    return jsonify({"status": "success", "command_id": cmd_id, "camera": target_cam, "action": action}), 200

def camera_command_ttl():
    # Cấu hình sai không làm route lỗi; mặc định lệnh có hạn 60 giây.
    try:
        ttl = int(os.environ.get("CAMERA_COMMAND_TTL_SECONDS", "60"))
        if ttl <= 0:
            raise ValueError("TTL must be positive")
    except ValueError:
        app.logger.warning("Invalid CAMERA_COMMAND_TTL_SECONDS; using 60")
        ttl = 60
    return ttl


@app.route("/api/cameras/commands", methods=["GET"])
def get_camera_pending_commands():
    """
    ESP32-CAM polling kiểm tra có lệnh chụp ảnh đang chờ không.
    Query param: ?camera_id=ENTRY_CAM hoặc ?camera_id=EXIT_CAM
    """
    cam_id = request.args.get("camera_id", "ENTRY_CAM").upper()
    ttl = camera_command_ttl()
    cmd = get_pending_camera_command(cam_id, max_age_seconds=ttl)
    return jsonify(cmd), 200

@app.route("/api/cameras/commands/<int:cmd_id>/ack", methods=["POST"])
@app.route("/api/cameras/ack", methods=["POST"])
def ack_camera_pending_command(cmd_id=None):
    """
    ESP32-CAM gửi ACK báo đã thực hiện xong lệnh chụp ảnh.
    """
    data = request.get_json(silent=True) or {}
    cid = cmd_id or data.get("id") or data.get("command_id")
    status = data.get("status", "EXECUTED")
    if cid:
        # ACK đến muộn không được hồi sinh lệnh EXPIRED.
        if not ack_camera_command(cid, status):
            return jsonify({"status": "error", "message": "Command is no longer pending"}), 409
        return jsonify({"status": "success", "command_id": cid}), 200
    return jsonify({"status": "error", "message": "Missing command ID"}), 400

# ============================================================================
# API ENDPOINTS CHO 2 ESP32-CAM & ANPR SERVICE
# ============================================================================

@app.route("/api/cameras/heartbeat", methods=["POST"])
def camera_heartbeat():
    """Heartbeat định kỳ từ ESP32-CAM (ENTRY hoặc EXIT)"""
    data = request.get_json(silent=True) or {}
    cam_id = data.get("cameraId", "ENTRY_CAM").upper()
    role = data.get("role", "ENTRY").upper()
    ip_addr = request.remote_addr

    update_camera_heartbeat(cam_id, role, ip_addr, "Heartbeat OK")
    return jsonify({"status": "success", "camera": cam_id, "timestamp": datetime.now().isoformat()}), 200

@app.route("/api/cameras/status", methods=["GET"])
def camera_status_endpoint():
    """Lấy trạng thái thực tế của cả 2 Camera"""
    return jsonify(get_camera_statuses()), 200

def capture_for_ticket(role):
    camera_id = role + "_CAM"
    # Sketch hiện tại gửi raw JPEG, không có session ID. Gắn bằng lệnh vừa giao,
    # không suy đoán phiên theo biển số/hint hoặc lấy phiên RFID mới nhất.
    claim = claim_camera_capture(camera_id, camera_command_ttl())
    image_file = request.files.get("file") or request.files.get("image")
    image_bytes = image_file.read() if image_file else request.get_data()
    if not image_bytes or len(image_bytes) < 100:
        result = {"success": False, "plateNumber": None, "confidence": None,
                  "reason": "EMPTY_OR_INVALID_IMAGE", "image_valid": False}
    else:
        try:
            result = anpr_service.process_capture(image_bytes, camera_id=camera_id, camera_role=role)
        except Exception:
            app.logger.exception("Camera processing failed for %s", camera_id)
            result = {"success": False, "plateNumber": None, "confidence": None,
                      "reason": "OCR_OR_IMAGE_ERROR", "image_valid": False}
    session_id = attach_capture(claim, role, result)
    update_camera_heartbeat(camera_id, role, request.remote_addr, "Capture received")
    log_camera_event(camera_id, role, result.get("plateNumber"), result.get("confidence"),
                     result.get("image_url") if result.get("image_valid") else None,
                     result.get("success", False), result.get("reason", "OK"))
    notify_clients("camera_capture", {"camera": camera_id, "role": role, "result": result, "session_id": session_id})
    # OCR thất bại vẫn ACK upload ảnh hợp lệ; vé/tiền đã được xử lý bằng RFID.
    return jsonify({"success": result.get("success", False), "plateNumber": result.get("plateNumber"),
                    "confidence": result.get("confidence"), "camera": camera_id,
                    "imageUrl": result.get("image_url"), "reason": result.get("reason"),
                    "session_id": session_id, "timestamp": datetime.now().isoformat()}), 200


@app.route("/api/cameras/entry/capture", methods=["POST"])
def camera_entry_capture():
    return capture_for_ticket("ENTRY")


@app.route("/api/cameras/exit/capture", methods=["POST"])
def camera_exit_capture():
    return capture_for_ticket("EXIT")


# ============================================================================
# API ENDPOINTS DÀNH CHO DASHBOARD PAGES (STATUS, SLOTS, VEHICLES, ETC.)
# ============================================================================

@app.route("/api/status", methods=["GET"])
@app.route("/api/parking/status", methods=["GET"])
def get_status():
    """Trả về toàn bộ trạng thái hiện tại của hệ thống"""
    status = get_current_status()
    return jsonify(status), 200

@app.route("/api/parking/slots", methods=["GET"])
def get_slots():
    """Danh sách chi tiết 4 ô đỗ xe P1..P4"""
    slots = get_slots_detail()
    return jsonify({"status": "success", "slots": slots}), 200

@app.route("/api/parking/fee", methods=["GET"])
def get_calculated_fee():
    """
    Tính toán phí đỗ xe theo quy tắc đồng bộ 5.000 VNĐ / 5 giây.
    Query param: ?duration=<seconds> (mặc định 0)
    """
    duration = request.args.get("duration", default=0, type=int)
    fee = calculate_parking_fee(duration)
    return jsonify({
        "status": "success",
        "duration_seconds": duration,
        "fee": fee,
        "rate_per_interval": BILLING_RATE_PER_INTERVAL,
        "interval_seconds": BILLING_INTERVAL_SECONDS
    }), 200

@app.route("/api/vehicles", methods=["GET"])
def get_vehicles():
    """Quản lý danh sách phương tiện"""
    q = request.args.get("q")
    vehicles = get_all_vehicles(search_query=q)
    return jsonify({"status": "success", "vehicles": vehicles, "total": len(vehicles)}), 200

@app.route("/api/vehicles/<int:v_id>", methods=["GET"])
def get_vehicle_detail(v_id):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM vehicles WHERE id = ?", (v_id,))
    v = cursor.fetchone()
    conn.close()
    if not v:
        return jsonify({"status": "error", "message": "Vehicle not found"}), 404
    return jsonify({"status": "success", "vehicle": dict(v)}), 200

@app.route("/api/payments", methods=["GET", "POST"])
def handle_payments():
    """Xem và xử lý thanh toán"""
    if request.method == "GET":
        payments = get_all_payments()
        return jsonify({"status": "success", "payments": payments, "total": len(payments)}), 200
    else:
        # Xác nhận thanh toán thủ công
        data = request.get_json(silent=True) or {}
        session_id = data.get("session_id")
        plate = data.get("plate_number")
        amount = int(data.get("amount", 10000))
        method = data.get("payment_method", "CASH")

        conn = get_connection()
        cursor = conn.cursor()
        now_str = datetime.now().isoformat()
        cursor.execute("""
        INSERT INTO payments (session_id, plate_number, amount, payment_status, payment_method, paid_at)
        VALUES (?, ?, ?, 'PAID', ?, ?);
        """, (session_id, plate, amount, method, now_str))

        if session_id:
            cursor.execute("UPDATE parking_sessions SET payment_status = 'PAID', payment_time = ? WHERE id = ?",
                           (now_str, session_id))

        conn.commit()
        conn.close()

        log_system_event("PAYMENT_CONFIRMED", f"Thanh toán {amount:,} VND cho xe {plate}", f"Phương thức: {method}")
        notify_clients("payment_success", {"plate": plate, "amount": amount, "method": method})

        return jsonify({"status": "success", "message": "Payment recorded successfully"}), 201

@app.route("/api/history", methods=["GET"])
def get_history():
    """Lịch sử toàn bộ sự kiện hệ thống"""
    history = get_all_history()
    return jsonify({"status": "success", "history": history, "total": len(history)}), 200

@app.route("/api/sensors", methods=["GET"])
def get_sensors():
    """Trang thông số cảm biến chi tiết"""
    sensors = get_detailed_sensors()
    return jsonify({"status": "success", "sensors": sensors}), 200

@app.route("/api/events", methods=["GET"])
def sse_events():
    """Server-Sent Events endpoint dành cho Web Dashboard Realtime"""
    def event_stream():
        q = queue.Queue(maxsize=50)
        sse_listeners.append(q)
        try:
            init_payload = json.dumps({"type": "init", "data": get_current_status()})
            yield f"data: {init_payload}\n\n"

            while True:
                try:
                    msg = q.get(timeout=25)
                    yield msg
                except queue.Empty:
                    yield ": keep-alive\n\n"
        except GeneratorExit:
            if q in sse_listeners:
                sse_listeners.remove(q)

    return Response(event_stream(), mimetype="text/event-stream")

# ============================================================================
# PHỤC VỤ STATIC FILES & UPLOADED IMAGES
# ============================================================================

@app.route("/uploads/<path:filename>")
def serve_uploads(filename):
    return send_from_directory(UPLOAD_DIR, filename)

@app.route("/")
def index():
    return send_from_directory(FRONTEND_DIR, "index.html")

@app.route("/<path:path>")
def static_files(path):
    # Nếu file tồn tại trong frontend dir thì serve, ngược lại trả về index.html cho SPA client routing
    full_path = os.path.join(FRONTEND_DIR, path)
    if os.path.isfile(full_path):
        return send_from_directory(FRONTEND_DIR, path)
    return send_from_directory(FRONTEND_DIR, "index.html")

if __name__ == "__main__":
    init_db()
    port = int(os.environ.get("PORT", 5000))
    print(f"\n=======================================================")
    print(f"=== SMART PARKING IoT - DASHBOARD BACKEND SERVER ===")
    print(f"=======================================================")
    print(f"Server running at:   http://0.0.0.0:{port}")
    print(f"Local URL:           http://localhost:{port}")
    print(f"ESP32 API Endpoint:  http://<LAN_IP>:{port}/api/telemetry/heartbeat")
    print(f"Cameras API:         http://<LAN_IP>:{port}/api/cameras/[entry|exit]/capture")
    print(f"=======================================================\n")
    app.run(host="0.0.0.0", port=port, debug=False, threaded=True)
