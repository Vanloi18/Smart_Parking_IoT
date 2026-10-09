import sqlite3
import os
from datetime import datetime, timedelta
from werkzeug.security import generate_password_hash, check_password_hash

DB_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "parking.db")

def get_connection():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = get_connection()
    cursor = conn.cursor()

    # 1. Bảng người dùng (Authentication & RBAC)
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS users (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        username TEXT UNIQUE NOT NULL,
        password_hash TEXT NOT NULL,
        role TEXT NOT NULL DEFAULT 'ADMIN',
        full_name TEXT,
        created_at TEXT NOT NULL
    );
    """)

    # Tạo tài khoản quản trị mặc định (admin / admin123) nếu chưa có
    cursor.execute("SELECT id FROM users WHERE username = 'admin';")
    if not cursor.fetchone():
        admin_pwd_hash = generate_password_hash("admin123")
        cursor.execute("""
        INSERT INTO users (username, password_hash, role, full_name, created_at)
        VALUES ('admin', ?, 'ADMIN', 'System Administrator', ?);
        """, (admin_pwd_hash, datetime.now().isoformat()))
        print("[DATABASE] Default ADMIN user created: admin / admin123")

    # 2. Bảng trạng thái 4 ô đỗ xe (P1 - P4)
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS slots (
        slot_id TEXT PRIMARY KEY,
        is_occupied INTEGER NOT NULL DEFAULT 0,
        updated_at TEXT NOT NULL
    );
    """)

    for s in ["P1", "P2", "P3", "P4"]:
        cursor.execute("""
        INSERT OR IGNORE INTO slots (slot_id, is_occupied, updated_at)
        VALUES (?, 0, ?);
        """, (s, datetime.now().isoformat()))

    # 3. Bảng phương tiện đăng ký (Vehicles)
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS vehicles (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        plate_number TEXT UNIQUE NOT NULL,
        rfid_uid TEXT,
        owner_name TEXT,
        vehicle_type TEXT DEFAULT 'CAR',
        registered_at TEXT NOT NULL
    );
    """)

    # 4. Bảng phiên đỗ xe hoàn chỉnh (Parking Sessions: RFID + Plate ANPR + Slots)
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS parking_sessions (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        plate_number TEXT,
        rfid_uid TEXT,
        slot_id TEXT,
        entry_time TEXT NOT NULL,
        exit_time TEXT,
        duration_seconds INTEGER DEFAULT 0,
        fee INTEGER DEFAULT 0,
        status TEXT NOT NULL CHECK(status IN ('PARKED', 'CHECKED_OUT', 'CANCELLED')),
        payment_status TEXT NOT NULL DEFAULT 'UNPAID' CHECK(payment_status IN ('UNPAID', 'PAID')),
        payment_time TEXT,
        payment_method TEXT,
        entry_camera TEXT,
        exit_camera TEXT,
        entry_image_url TEXT,
        exit_image_url TEXT
    );
    """)

    # 5. Bảng thanh toán phí đỗ xe (Payments)
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS payments (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        session_id INTEGER,
        plate_number TEXT,
        amount INTEGER NOT NULL,
        payment_status TEXT NOT NULL DEFAULT 'PAID',
        payment_method TEXT DEFAULT 'CASH',
        paid_at TEXT NOT NULL,
        FOREIGN KEY (session_id) REFERENCES parking_sessions(id)
    );
    """)

    # 6. Bảng sự kiện camera & ANPR (Camera Events)
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS camera_events (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        camera_id TEXT NOT NULL,
        camera_role TEXT NOT NULL,
        plate_number TEXT,
        confidence REAL DEFAULT 0.0,
        image_url TEXT,
        success INTEGER NOT NULL DEFAULT 1,
        reason TEXT,
        timestamp TEXT NOT NULL
    );
    """)

    # 7. Bảng trạng thái thiết bị camera (Camera Status & Heartbeats)
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS camera_status (
        camera_id TEXT PRIMARY KEY,
        camera_role TEXT NOT NULL,
        ip_address TEXT,
        last_seen TEXT,
        status TEXT DEFAULT 'OFFLINE',
        last_event TEXT
    );
    """)

    # Khởi tạo 2 camera mặc định
    for cam_id, role in [("ENTRY_CAM", "ENTRY"), ("EXIT_CAM", "EXIT")]:
        cursor.execute("""
        INSERT OR IGNORE INTO camera_status (camera_id, camera_role, ip_address, last_seen, status, last_event)
        VALUES (?, ?, 'N/A', NULL, 'OFFLINE', 'Chưa có kết nối');
        """, (cam_id, role))

    # 8. Bảng nhật ký lịch sử sự kiện hệ thống (System Events Audit Log)
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS system_events (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        event_type TEXT NOT NULL,
        description TEXT NOT NULL,
        details TEXT,
        timestamp TEXT NOT NULL
    );
    """)

    # 9. Bảng tương thích ngược cho RFID transactions
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS parking_transactions (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        card_uid TEXT NOT NULL,
        entry_time TEXT NOT NULL,
        exit_time TEXT,
        duration_seconds INTEGER,
        fee INTEGER DEFAULT 0,
        status TEXT NOT NULL CHECK(status IN ('PARKED', 'COMPLETED'))
    );
    """)

    # 10. Bảng lưu trữ chuỗi thời gian telemetry từ ESP32 (Heartbeat logs)
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS telemetry_history (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        timestamp TEXT NOT NULL,
        p1 INTEGER NOT NULL,
        p2 INTEGER NOT NULL,
        p3 INTEGER NOT NULL,
        p4 INTEGER NOT NULL,
        free_slots INTEGER NOT NULL,
        temperature REAL NOT NULL,
        humidity REAL NOT NULL,
        gas_raw INTEGER NOT NULL,
        gas_level TEXT NOT NULL,
        barrier_entry TEXT NOT NULL,
        barrier_exit TEXT NOT NULL
    );
    """)

    # 11. Bảng lưu trạng thái tức thời toàn hệ thống (Current System State Cache)
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS system_state (
        id INTEGER PRIMARY KEY CHECK (id = 1),
        last_heartbeat TEXT,
        wifi_connected INTEGER DEFAULT 0,
        barrier_entry TEXT DEFAULT 'CLOSED',
        barrier_exit TEXT DEFAULT 'CLOSED',
        last_entry_card TEXT,
        last_exit_card TEXT,
        temperature REAL DEFAULT 0.0,
        humidity REAL DEFAULT 0.0,
        gas_raw INTEGER DEFAULT 0,
        gas_level TEXT DEFAULT 'NORMAL',
        free_slots INTEGER DEFAULT 4,
        updated_at TEXT NOT NULL
    );
    """)

    # 11. Bảng hàng đợi lệnh điều khiển Barrier từ xa (Command Queue)
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS barrier_commands (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        barrier TEXT NOT NULL,
        action TEXT NOT NULL,
        device_id TEXT NOT NULL DEFAULT 'MAIN_ESP32',
        status TEXT NOT NULL DEFAULT 'PENDING',
        created_at TEXT NOT NULL,
        executed_at TEXT
    );
    """)

    # 12. Bảng hàng đợi lệnh chụp ảnh Camera từ xa (Camera Command Queue)
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS camera_commands (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        camera_id TEXT NOT NULL,
        command TEXT NOT NULL DEFAULT 'CAPTURE',
        status TEXT NOT NULL DEFAULT 'PENDING',
        created_at TEXT NOT NULL,
        executed_at TEXT
    );
    """)

    # Nâng cấp bảng camera_status để lưu trữ ảnh và biển số thật của phiên hiện tại
    # Migration bổ sung; không xóa bảng hoặc thay định danh/biển số của dữ liệu cũ.
    for table, columns in {
        "parking_sessions": {"plate_source": "TEXT", "needs_plate": "INTEGER NOT NULL DEFAULT 1",
                             "missing_entry_image": "INTEGER NOT NULL DEFAULT 1", "missing_exit_image": "INTEGER NOT NULL DEFAULT 1",
                             "ocr_confidence": "REAL"},
        "camera_commands": {"session_id": "INTEGER", "dispatched_at": "TEXT", "capture_received_at": "TEXT"}
    }.items():
        existing = {row[1] for row in cursor.execute(f'PRAGMA table_info("{table}")')}
        for name, definition in columns.items():
            if name not in existing:
                cursor.execute(f'ALTER TABLE "{table}" ADD COLUMN "{name}" {definition}')
                if name in ("missing_entry_image", "missing_exit_image"):
                    field = "entry_image_url" if name == "missing_entry_image" else "exit_image_url"
                    cursor.execute(f'UPDATE parking_sessions SET "{name}"=0 WHERE "{field}" IS NOT NULL AND "{field}" != \'\'')

    for col in ["latest_image_url", "latest_plate_number", "latest_frame_time"]:
        try:
            cursor.execute(f"ALTER TABLE camera_status ADD COLUMN {col} TEXT;")
        except Exception:
            pass

    cursor.execute("""
    INSERT OR IGNORE INTO system_state (id, last_heartbeat, wifi_connected, barrier_entry, barrier_exit,
                                       last_entry_card, last_exit_card, temperature, humidity,
                                       gas_raw, gas_level, free_slots, updated_at)
    VALUES (1, NULL, 0, 'CLOSED', 'CLOSED', NULL, NULL, 0.0, 0.0, 0, 'NORMAL', 4, ?);
    """, (datetime.now().isoformat(),))

    conn.commit()
    conn.close()
    print(f"[DATABASE] Initialized SQLite tables at: {DB_PATH}")

# ============================================================================
# BILLING CALCULATION LOGIC (DEMO RULE: 5.000 VND / 5 SECONDS)
# Synchronized with ESP32 Config::PARKING_BILLING_INTERVAL_MS & BILLING_RATE_PER_INTERVAL
# ============================================================================

BILLING_INTERVAL_SECONDS = 5
BILLING_RATE_PER_INTERVAL = 5000  # 5.000 VNĐ / 5 giây

def calculate_parking_fee(duration_seconds):
    """
    Quy tắc tính phí bãi đỗ xe (đồng bộ chính xác 100% với firmware ESP32):
    - Đơn giá: 5.000 VNĐ mỗi 5 giây (block).
    - Thời gian lẻ làm tròn lên 1 block (ceil: intervals = (duration + 4) // 5).
    - Tối thiểu 1 block = 5.000 VNĐ khi có phát sinh phiên gửi xe.
    """
    if duration_seconds is None or duration_seconds <= 0:
        return BILLING_RATE_PER_INTERVAL
    intervals = (int(duration_seconds) + BILLING_INTERVAL_SECONDS - 1) // BILLING_INTERVAL_SECONDS
    return int(max(1, intervals) * BILLING_RATE_PER_INTERVAL)

# ============================================================================
# SYSTEM EVENTS & AUDIT LOGGING
# ============================================================================

def log_system_event(event_type, description, details=None):
    now = datetime.now().isoformat()
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
    INSERT INTO system_events (event_type, description, details, timestamp)
    VALUES (?, ?, ?, ?);
    """, (event_type, description, details, now))
    conn.commit()
    conn.close()

# ============================================================================
# USER AUTHENTICATION & MANAGEMENT
# ============================================================================

def get_user_by_username(username):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT id, username, password_hash, role, full_name, created_at FROM users WHERE username = ?", (username,))
    row = cursor.fetchone()
    conn.close()
    return dict(row) if row else None

def get_user_by_id(user_id):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT id, username, role, full_name, created_at FROM users WHERE id = ?", (user_id,))
    row = cursor.fetchone()
    conn.close()
    return dict(row) if row else None

# ============================================================================
# TELEMETRY & HARDWARE INTEGRATION
# ============================================================================

def update_telemetry(p1, p2, p3, p4, temp, hum, gas_raw, gas_level, barrier_entry, barrier_exit, free_slots):
    now = datetime.now().isoformat()
    conn = get_connection()
    cursor = conn.cursor()

    # Cập nhật bảng slots
    slots_map = {"P1": p1, "P2": p2, "P3": p3, "P4": p4}
    for slot_id, occ in slots_map.items():
        cursor.execute("UPDATE slots SET is_occupied = ?, updated_at = ? WHERE slot_id = ?", (occ, now, slot_id))

    # Ghi nhận bản ghi telemetry lịch sử
    cursor.execute("""
    INSERT INTO telemetry_history (timestamp, p1, p2, p3, p4, free_slots, temperature, humidity, gas_raw, gas_level, barrier_entry, barrier_exit)
    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
    """, (now, p1, p2, p3, p4, free_slots, temp, hum, gas_raw, gas_level, barrier_entry, barrier_exit))

    # Cập nhật cache system_state
    cursor.execute("""
    UPDATE system_state
    SET last_heartbeat = ?,
        temperature = ?,
        humidity = ?,
        gas_raw = ?,
        gas_level = ?,
        barrier_entry = ?,
        barrier_exit = ?,
        free_slots = ?,
        wifi_connected = 1,
        updated_at = ?
    WHERE id = 1;
    """, (now, temp, hum, gas_raw, gas_level, barrier_entry, barrier_exit, free_slots, now))

    # Kiểm tra cảnh báo khí độc để ghi log hệ thống
    if gas_level in ("WARNING", "DANGER"):
        cursor.execute("""
        INSERT INTO system_events (event_type, description, details, timestamp)
        VALUES ('SENSOR_ALERT', ?, ?, ?);
        """, (f"MQ-7 CO Gas Alert: {gas_level}", f"ADC: {gas_raw}, Temp: {temp}C, Hum: {hum}%", now))

    conn.commit()
    conn.close()

# ============================================================================
# CAMERA & ANPR EVENT HANDLING
# ============================================================================

def update_camera_heartbeat(camera_id, camera_role, ip_address=None, last_event=None):
    now = datetime.now().isoformat()
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("""
    UPDATE camera_status
    SET last_seen = ?,
        status = 'ONLINE',
        ip_address = COALESCE(?, ip_address),
        last_event = COALESCE(?, last_event)
    WHERE camera_id = ?;
    """, (now, ip_address, last_event, camera_id))

    conn.commit()
    conn.close()

def log_camera_event(camera_id, camera_role, plate_number, confidence, image_url, success, reason):
    now = datetime.now().isoformat()
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("""
    INSERT INTO camera_events (camera_id, camera_role, plate_number, confidence, image_url, success, reason, timestamp)
    VALUES (?, ?, ?, ?, ?, ?, ?, ?);
    """, (camera_id, camera_role, plate_number, confidence, image_url, 1 if success else 0, reason, now))

    # Cập nhật camera_status với ảnh chụp thật và biển số thật của phiên hiện tại
    last_event_msg = f"Captured frame" if not plate_number else f"Plate: {plate_number}"
    cursor.execute("""
    UPDATE camera_status
    SET last_seen = ?,
        status = 'ONLINE',
        last_event = ?,
        latest_image_url = ?,
        latest_plate_number = ?,
        latest_frame_time = ?
    WHERE camera_id = ?;
    """, (now, last_event_msg, image_url, plate_number, now, camera_id))

    # Ghi nhận audit log
    event_desc = f"Camera {camera_role} captured plate: {plate_number}" if success and plate_number else f"Camera {camera_role} capture: {reason}"
    cursor.execute("""
    INSERT INTO system_events (event_type, description, details, timestamp)
    VALUES ('CAMERA_RECOGNITION', ?, ?, ?);
    """, (event_desc, f"Plate: {plate_number}, Conf: {confidence}", now))

    conn.commit()
    conn.close()

def get_camera_statuses():
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM camera_status;")
    rows = cursor.fetchall()

    res = {}
    now = datetime.now()
    for row in rows:
        cam_id = row["camera_id"]
        role = row["camera_role"].lower()
        last_seen = row["last_seen"]
        is_online = False

        if last_seen:
            try:
                diff = (now - datetime.fromisoformat(last_seen)).total_seconds()
                if diff <= 15.0:
                    is_online = True
            except Exception:
                is_online = False

        keys = row.keys() if hasattr(row, 'keys') else []
        img_url = row["latest_image_url"] if "latest_image_url" in keys else None
        plate = row["latest_plate_number"] if "latest_plate_number" in keys else None
        frame_time = row["latest_frame_time"] if "latest_frame_time" in keys else None

        res[role] = {
            "camera_id": cam_id,
            "role": row["camera_role"],
            "online": is_online,
            "status": "ONLINE" if is_online else "OFFLINE",
            "ip": row["ip_address"] or "N/A",
            "last_seen": last_seen,
            "last_event": row["last_event"] or "Chưa có sự kiện",
            "image_url": img_url,
            "plate_number": plate,
            "frame_time": frame_time
        }

    conn.close()
    return res

# ============================================================================
# PARKING SESSIONS & VEHICLES LOGIC
# ============================================================================

def create_or_find_entry_session(plate_number=None, rfid_uid=None, slot_id=None, entry_camera="ENTRY_CAM", image_url=None):
    now = datetime.now()
    now_str = now.isoformat()
    conn = get_connection()
    cursor = conn.cursor()

    # Kiểm tra xem có session đang mở nào trùng plate hoặc RFID không
    query = "SELECT id, plate_number, rfid_uid FROM parking_sessions WHERE status = 'PARKED' AND ("
    params = []
    conditions = []
    if plate_number:
        conditions.append("plate_number = ?")
        params.append(plate_number)
    if rfid_uid:
        conditions.append("rfid_uid = ?")
        params.append(rfid_uid)

    if conditions:
        query += " OR ".join(conditions) + ") LIMIT 1;"
        cursor.execute(query, params)
        existing = cursor.fetchone()
        if existing:
            # Nếu đã có session nhưng chưa có plate/rfid thì cập nhật bổ sung
            sess_id = existing["id"]
            if plate_number and not existing["plate_number"]:
                cursor.execute("UPDATE parking_sessions SET plate_number = ?, entry_image_url = ? WHERE id = ?",
                               (plate_number, image_url, sess_id))
            if rfid_uid and not existing["rfid_uid"]:
                cursor.execute("UPDATE parking_sessions SET rfid_uid = ? WHERE id = ?", (rfid_uid, sess_id))
            conn.commit()
            conn.close()
            return {"session_id": sess_id, "action": "UPDATED", "message": "Updated existing parking session"}

    # Tạo xe trong bảng vehicles nếu chưa có
    if plate_number:
        cursor.execute("""
        INSERT OR IGNORE INTO vehicles (plate_number, rfid_uid, registered_at)
        VALUES (?, ?, ?);
        """, (plate_number, rfid_uid, now_str))

    # Tạo phiên đỗ mới
    cursor.execute("""
    INSERT INTO parking_sessions (plate_number, rfid_uid, slot_id, entry_time, status, payment_status, entry_camera, entry_image_url)
    VALUES (?, ?, ?, ?, 'PARKED', 'UNPAID', ?, ?);
    """, (plate_number, rfid_uid, slot_id, now_str, entry_camera, image_url))
    sess_id = cursor.lastrowid

    # Cập nhật system_state và system_events
    if rfid_uid:
        cursor.execute("UPDATE system_state SET last_entry_card = ?, barrier_entry = 'OPEN', updated_at = ? WHERE id = 1;",
                       (rfid_uid, now_str))

    cursor.execute("""
    INSERT INTO system_events (event_type, description, details, timestamp)
    VALUES ('VEHICLE_ENTERED', ?, ?, ?);
    """, (f"Vehicle entered: {plate_number or rfid_uid or 'Unknown'}", f"Session ID: {sess_id}", now_str))

    conn.commit()
    conn.close()
    return {"session_id": sess_id, "action": "CREATED", "message": "Parking session created successfully"}

def close_exit_session(plate_number=None, rfid_uid=None, exit_camera="EXIT_CAM", image_url=None):
    now = datetime.now()
    now_str = now.isoformat()
    conn = get_connection()
    cursor = conn.cursor()

    query = "SELECT * FROM parking_sessions WHERE status = 'PARKED' AND ("
    params = []
    conditions = []
    if plate_number:
        conditions.append("plate_number = ?")
        params.append(plate_number)
    if rfid_uid:
        conditions.append("rfid_uid = ?")
        params.append(rfid_uid)

    sess = None
    if conditions:
        query += " OR ".join(conditions) + ") ORDER BY id DESC LIMIT 1;"
        cursor.execute(query, params)
        sess = cursor.fetchone()

    fee = BILLING_RATE_PER_INTERVAL
    duration_sec = 0

    if sess:
        sess_id = sess["id"]
        entry_time = datetime.fromisoformat(sess["entry_time"])
        duration_sec = max(0, int((now - entry_time).total_seconds()))
        # Phí đỗ xe demo: 5.000 VNĐ / 5 giây (Đồng bộ chính xác với ESP32 firmware)
        fee = calculate_parking_fee(duration_sec)

        cursor.execute("""
        UPDATE parking_sessions
        SET exit_time = ?,
            duration_seconds = ?,
            fee = ?,
            status = 'CHECKED_OUT',
            payment_status = 'PAID',
            payment_time = ?,
            payment_method = 'CASH',
            exit_camera = ?,
            exit_image_url = ?
        WHERE id = ?;
        """, (now_str, duration_sec, fee, now_str, exit_camera, image_url, sess_id))

        # Thêm bản ghi thanh toán
        cursor.execute("""
        INSERT INTO payments (session_id, plate_number, amount, payment_status, payment_method, paid_at)
        VALUES (?, ?, ?, 'PAID', 'CASH', ?);
        """, (sess_id, sess["plate_number"] or plate_number, fee, now_str))

        cursor.execute("""
        INSERT INTO system_events (event_type, description, details, timestamp)
        VALUES ('VEHICLE_EXITED', ?, ?, ?);
        """, (f"Vehicle exited: {sess['plate_number'] or sess['rfid_uid']}", f"Fee: {fee:,} VND, Duration: {duration_sec}s", now_str))

    else:
        # Trường hợp vãng lai
        cursor.execute("""
        INSERT INTO parking_sessions (plate_number, rfid_uid, entry_time, exit_time, duration_seconds, fee, status, payment_status, payment_time, payment_method, exit_camera, exit_image_url)
        VALUES (?, ?, ?, ?, 0, ?, 'CHECKED_OUT', 'PAID', ?, 'CASH', ?, ?);
        """, (plate_number, rfid_uid, now_str, now_str, fee, now_str, exit_camera, image_url))
        sess_id = cursor.lastrowid

        cursor.execute("""
        INSERT INTO payments (session_id, plate_number, amount, payment_status, payment_method, paid_at)
        VALUES (?, ?, ?, 'PAID', 'CASH', ?);
        """, (sess_id, plate_number, fee, now_str))

    # Cập nhật system_state
    if rfid_uid:
        cursor.execute("UPDATE system_state SET last_exit_card = ?, barrier_exit = 'OPEN', updated_at = ? WHERE id = 1;",
                       (rfid_uid, now_str))

    conn.commit()
    conn.close()

    return {
        "session_id": sess_id,
        "fee": fee,
        "duration_seconds": duration_sec,
        "plate_number": sess["plate_number"] if sess else plate_number,
        "rfid_uid": sess["rfid_uid"] if sess else rfid_uid
    }

# ============================================================================
# TƯƠNG THÍCH NGƯỢC: RECORD_ENTRY & RECORD_EXIT (CHO ESP32 RFID & TESTS)
# ============================================================================

def record_entry(card_uid):
    # Backend là nguồn quyết định vé và phí; giữ tên hàm tương thích API cũ.
    from tickets import process_ticket
    return process_ticket(card_uid, "ENTRY")


def record_exit(card_uid):
    from tickets import process_ticket
    return process_ticket(card_uid, "EXIT")

# ============================================================================
# COMMAND QUEUE LOGIC (BARRIERS & CAMERAS REMOTE CONTROL)
# ============================================================================

def add_barrier_command(barrier, action, device_id="MAIN_ESP32"):
    now = datetime.now().isoformat()
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
    INSERT INTO barrier_commands (barrier, action, device_id, status, created_at)
    VALUES (?, ?, ?, 'PENDING', ?);
    """, (barrier.upper(), action.upper(), device_id, now))
    cmd_id = cursor.lastrowid
    conn.commit()
    conn.close()
    return cmd_id

def get_pending_barrier_command(device_id="MAIN_ESP32"):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
    SELECT id, barrier, action FROM barrier_commands
    WHERE status = 'PENDING' AND device_id = ?
    ORDER BY id ASC LIMIT 1;
    """, (device_id,))
    row = cursor.fetchone()
    conn.close()
    if row:
        return {"has_command": True, "command_id": row["id"], "barrier": row["barrier"], "action": row["action"]}
    return {"has_command": False}

def ack_barrier_command(cmd_id, status="EXECUTED", device_id="MAIN_ESP32"):
    now = datetime.now().isoformat()
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
    UPDATE barrier_commands
    SET status = ?, executed_at = ?
    WHERE id = ?;
    """, (status, now, cmd_id))
    conn.commit()
    conn.close()
    return True

def add_camera_command(camera_id, command="CAPTURE"):
    now = datetime.now().isoformat()
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
    INSERT INTO camera_commands (camera_id, command, status, created_at)
    VALUES (?, ?, 'PENDING', ?);
    """, (camera_id.upper(), command.upper(), now))
    cmd_id = cursor.lastrowid
    conn.commit()
    conn.close()
    return cmd_id

def get_pending_camera_command(camera_id, max_age_seconds=60):
    conn = get_connection()
    cursor = conn.cursor()
    conn.execute("BEGIN IMMEDIATE")
    # Chỉ đổi trạng thái khi poll; giữ nguyên lệnh và lịch sử đã thực thi.
    cutoff = (datetime.now() - timedelta(seconds=max_age_seconds)).isoformat()
    cursor.execute("""
    UPDATE camera_commands SET status = 'EXPIRED'
    WHERE status IN ('PENDING', 'DISPATCHED') AND camera_id = ?
      AND julianday(created_at) < julianday(?);
    """, (camera_id.upper(), cutoff))
    # Một camera chỉ nhận một lệnh đang xử lý; không đưa upload thẻ trước sang thẻ sau.
    busy = cursor.execute("SELECT 1 FROM camera_commands WHERE camera_id=? AND status='DISPATCHED' LIMIT 1", (camera_id.upper(),)).fetchone()
    if busy:
        conn.commit()
        conn.close()
        return {"has_command": False}
    cursor.execute("""
    SELECT id, command FROM camera_commands
    WHERE status = 'PENDING' AND camera_id = ?
    ORDER BY id ASC LIMIT 1;
    """, (camera_id.upper(),))
    row = cursor.fetchone()
    if row:
        cursor.execute("UPDATE camera_commands SET status='DISPATCHED',dispatched_at=? WHERE id=?", (datetime.now().isoformat(), row["id"]))
    conn.commit()
    conn.close()
    if row:
        return {"has_command": True, "command_id": row["id"], "command": row["command"]}
    return {"has_command": False}

def ack_camera_command(cmd_id, status="EXECUTED"):
    now = datetime.now().isoformat()
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
    UPDATE camera_commands
    SET status = ?, executed_at = ?
    WHERE id = ? AND status IN ('PENDING', 'DISPATCHED');
    """, (status, now, cmd_id))
    updated = cursor.rowcount > 0
    conn.commit()
    conn.close()
    return updated

# ============================================================================
# QUERY HELPERS DÀNH CHO DASHBOARD & APIS
# ============================================================================

def get_current_status():
    conn = get_connection()
    cursor = conn.cursor()

    # Lấy trạng thái 4 ô đỗ
    cursor.execute("SELECT slot_id, is_occupied, updated_at FROM slots ORDER BY slot_id;")
    slots_rows = cursor.fetchall()
    slots_dict = {row["slot_id"]: row["is_occupied"] for row in slots_rows}

    # Lấy system_state
    cursor.execute("SELECT * FROM system_state WHERE id = 1;")
    state_row = cursor.fetchone()
    state = dict(state_row) if state_row else {}

    # Lấy 10 giao dịch gần nhất
    cursor.execute("""
    SELECT id, card_uid, entry_time, exit_time, duration_seconds, fee, status
    FROM parking_transactions ORDER BY id DESC LIMIT 10;
    """)
    txns = [dict(r) for r in cursor.fetchall()]

    # Lấy 10 phiên đỗ gần nhất (tính toán phí realtime nếu xe đang đỗ theo quy tắc 5.000đ / 5s)
    cursor.execute("""
    SELECT * FROM parking_sessions
    WHERE status='PARKED' OR id IN (SELECT id FROM parking_sessions ORDER BY id DESC LIMIT 10)
    ORDER BY id DESC;
    """)
    raw_sessions = [dict(r) for r in cursor.fetchall()]
    sessions = []
    now_dt = datetime.now()
    for s in raw_sessions:
        if s.get("status") == "PARKED" and s.get("entry_time"):
            try:
                e_dt = datetime.fromisoformat(s["entry_time"])
                dur = max(0, int((now_dt - e_dt).total_seconds()))
                s["duration_seconds"] = dur
                s["fee"] = calculate_parking_fee(dur)
            except Exception:
                pass
        sessions.append(s)

    conn.close()

    total_slots = 4
    occupied_slots = sum(slots_dict.values())
    free_slots = total_slots - occupied_slots

    # Kiểm tra ESP32 Main status dựa trên heartbeat thực tế
    last_hb_str = state.get("last_heartbeat")
    esp32_status = "OFFLINE"
    is_esp32_online = False
    if last_hb_str:
        try:
            last_hb_dt = datetime.fromisoformat(last_hb_str)
            diff_sec = (datetime.now() - last_hb_dt).total_seconds()
            if diff_sec <= 10.0:
                esp32_status = "CONNECTED"
                is_esp32_online = True
            else:
                esp32_status = "OFFLINE"
        except Exception:
            esp32_status = "OFFLINE"

    cameras = get_camera_statuses()

    return {
        "slots": slots_dict,
        "total_slots": total_slots,
        "occupied_slots": occupied_slots,
        "free_slots": free_slots,
        "environment": {
            "temperature": state.get("temperature", 0.0),
            "humidity": state.get("humidity", 0.0),
            "gas_raw": state.get("gas_raw", 0),
            "gas_level": state.get("gas_level", "NORMAL"),
        },
        "barriers": {
            "entry": state.get("barrier_entry", "CLOSED"),
            "exit": state.get("barrier_exit", "CLOSED")
        },
        "rfid": {
            "last_entry_card": state.get("last_entry_card"),
            "last_exit_card": state.get("last_exit_card")
        },
        "system": {
            "last_heartbeat": last_hb_str,
            "wifi_connected": is_esp32_online,
            "esp32_status": esp32_status,
            "backend_online": True
        },
        "cameras": cameras,
        "recent_transactions": txns,
        "recent_sessions": sessions
    }

def get_slots_detail():
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT slot_id, is_occupied, updated_at FROM slots ORDER BY slot_id;")
    slots_rows = cursor.fetchall()
    
    slots_list = []
    for r in slots_rows:
        slot_id = r["slot_id"]
        is_occ = bool(r["is_occupied"])
        
        # Tìm session đang chiếm slot này nếu có
        cursor.execute("""
        SELECT id, plate_number, rfid_uid, entry_time
        FROM parking_sessions
        WHERE slot_id = ? AND status = 'PARKED'
        ORDER BY id DESC LIMIT 1;
        """, (slot_id,))
        sess = cursor.fetchone()

        vehicle_info = None
        duration_sec = 0
        if sess:
            try:
                entry_dt = datetime.fromisoformat(sess["entry_time"])
                duration_sec = max(0, int((datetime.now() - entry_dt).total_seconds()))
            except Exception:
                duration_sec = 0
            vehicle_info = {
                "session_id": sess["id"],
                "plate_number": sess["plate_number"] or "N/A",
                "rfid_uid": sess["rfid_uid"] or "N/A",
                "entry_time": sess["entry_time"],
                "duration_seconds": duration_sec,
                "current_fee": calculate_parking_fee(duration_sec)
            }

        slots_list.append({
            "slot_id": slot_id,
            "is_occupied": is_occ,
            "status": "OCCUPIED" if is_occ else "AVAILABLE",
            "updated_at": r["updated_at"],
            "vehicle": vehicle_info
        })

    conn.close()
    return slots_list

def get_all_vehicles(search_query=None):
    conn = get_connection()
    cursor = conn.cursor()
    if search_query:
        param = f"%{search_query.strip().upper()}%"
        cursor.execute("""
        SELECT v.*, 
               (SELECT status FROM parking_sessions s WHERE (s.plate_number = v.plate_number OR s.rfid_uid = v.rfid_uid) ORDER BY s.id DESC LIMIT 1) as current_status,
               (SELECT slot_id FROM parking_sessions s WHERE (s.plate_number = v.plate_number OR s.rfid_uid = v.rfid_uid) AND s.status = 'PARKED' LIMIT 1) as current_slot
        FROM vehicles v
        WHERE v.plate_number LIKE ? OR v.rfid_uid LIKE ? OR v.owner_name LIKE ?
        ORDER BY v.id DESC;
        """, (param, param, param))
    else:
        cursor.execute("""
        SELECT v.*, 
               (SELECT status FROM parking_sessions s WHERE (s.plate_number = v.plate_number OR s.rfid_uid = v.rfid_uid) ORDER BY s.id DESC LIMIT 1) as current_status,
               (SELECT slot_id FROM parking_sessions s WHERE (s.plate_number = v.plate_number OR s.rfid_uid = v.rfid_uid) AND s.status = 'PARKED' LIMIT 1) as current_slot
        FROM vehicles v
        ORDER BY v.id DESC;
        """)
    rows = [dict(r) for r in cursor.fetchall()]
    conn.close()
    return rows

def get_all_payments(limit=100):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
    SELECT p.*, s.entry_time, s.exit_time, s.duration_seconds
    FROM payments p
    LEFT JOIN parking_sessions s ON p.session_id = s.id
    ORDER BY p.id DESC LIMIT ?;
    """, (limit,))
    rows = [dict(r) for r in cursor.fetchall()]
    conn.close()
    return rows

def get_all_history(limit=100):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
    SELECT id, event_type, description, details, timestamp
    FROM system_events
    ORDER BY id DESC LIMIT ?;
    """, (limit,))
    rows = [dict(r) for r in cursor.fetchall()]
    conn.close()
    return rows

def get_detailed_sensors():
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("SELECT * FROM system_state WHERE id = 1;")
    state = dict(cursor.fetchone())

    cursor.execute("SELECT slot_id, is_occupied, updated_at FROM slots ORDER BY slot_id;")
    slots = [dict(r) for r in cursor.fetchall()]

    conn.close()

    # Tính toán điện áp MQ-7
    gas_raw = state.get("gas_raw", 0)
    v_adc = gas_raw * 3.3 / 4095.0
    v_ao = v_adc * 2.0

    return {
        "timestamp": state.get("updated_at"),
        "esp32_online": state.get("wifi_connected", 0) == 1,
        "environment": {
            "temperature_c": state.get("temperature", 0.0),
            "humidity_percent": state.get("humidity", 0.0),
            "gas_raw_adc": gas_raw,
            "gas_v_adc": round(v_adc, 2),
            "gas_v_ao": round(v_ao, 2),
            "gas_level": state.get("gas_level", "NORMAL")
        },
        "slots_ir": {r["slot_id"]: {"occupied": bool(r["is_occupied"]), "updated_at": r["updated_at"]} for r in slots},
        "gates": {
            "barrier_entry": state.get("barrier_entry", "CLOSED"),
            "barrier_exit": state.get("barrier_exit", "CLOSED"),
            "rfid_entry_last": state.get("last_entry_card", "N/A"),
            "rfid_exit_last": state.get("last_exit_card", "N/A")
        }
    }

if __name__ == "__main__":
    init_db()
