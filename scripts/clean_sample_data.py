"""Dọn đúng dữ liệu mẫu đã duyệt; mặc định chỉ sao lưu và xuất dry-run.

Không import backend, không xóa heartbeat, trạng thái camera hay lệnh điều khiển.
--apply yêu cầu backend dừng và báo cáo dry-run đã được người dùng duyệt.
"""
import argparse
from contextlib import closing
from datetime import date, datetime
import hashlib
import json
from pathlib import Path
import re
import shutil
import socket
import sqlite3
import sys

ROOT = Path(__file__).resolve().parents[1]
PLATE = "30A-999.88"
RFIDS = ("RFID_CAM_101", "RFID_E2E_888")
MARKERS = (PLATE, *RFIDS)
# JPEG chính xác do create_dummy_jpeg() trong test_telemetry.py tạo ra.
DUMMY_SHA256 = "2daace70cf0b4b30566d07bd3c9a1e06bca8241cdc68c482823f57c7c68eee63"
TABLES = ("payments", "camera_events", "parking_sessions", "vehicles",
          "parking_transactions", "system_events")
DATES = {"payments": "paid_at", "camera_events": "timestamp",
         "parking_sessions": "entry_time", "vehicles": "registered_at",
         "parking_transactions": "entry_time", "system_events": "timestamp"}
IMAGE_FIELDS = {"camera_events": ("image_url",),
                "parking_sessions": ("entry_image_url", "exit_image_url"),
                "camera_status": ("latest_image_url",)}


def connect_readonly(path):
    conn = sqlite3.connect(path.resolve().as_uri() + "?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    return conn


def sha256(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def create_backup(db_path):
    # SQLite backup tạo snapshot nhất quán, kể cả khi backend đang nhận heartbeat.
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
    backup = db_path.with_name(db_path.name + ".bak_" + stamp)
    with closing(connect_readonly(db_path)) as source:
        with closing(sqlite3.connect(backup)) as target:
            source.backup(target)
            integrity = [row[0] for row in target.execute("PRAGMA integrity_check")]
            if integrity != ["ok"]:
                raise RuntimeError(f"Backup integrity failed: {integrity}")
            foreign_keys = [list(row) for row in target.execute("PRAGMA foreign_key_check")]
    return {"path": str(backup), "integrity_check": "ok", "sha256": sha256(backup),
            "foreign_key_issues": foreign_keys}


def is_sample(table, row):
    if table in ("payments", "camera_events", "parking_sessions", "vehicles"):
        return row.get("plate_number") == PLATE or row.get("rfid_uid") in RFIDS
    if table == "parking_transactions":
        return row.get("card_uid") in RFIDS
    if table == "system_events":
        # Khớp cả mã định danh, không khớp RFID_CAM_101_EXTRA hoặc biển số dài hơn.
        text = str(row.get("description") or "") + " " + str(row.get("details") or "")
        return row.get("event_type") in ("CAMERA_RECOGNITION", "VEHICLE_ENTERED", "VEHICLE_EXITED") and any(
            re.search(r"(?<![A-Za-z0-9_.-])" + re.escape(marker) + r"(?![A-Za-z0-9_.-])", text)
            for marker in MARKERS)
    return False


def build_plan(conn, db_path, uploads, before):
    rows = {table: [dict(row) for row in conn.execute(f'SELECT * FROM "{table}" ORDER BY id')]
            for table in TABLES}
    selected = {table: [] for table in TABLES}
    skipped = []
    for table, values in rows.items():
        for row in values:
            if not is_sample(table, row):
                continue
            try:
                old = date.fromisoformat(str(row[DATES[table]])[:10]) < before
            except (ValueError, TypeError):
                old = False
            # Giữ mọi dòng có ngày hôm nay / ngày không rõ, dù trùng mã mẫu.
            if old:
                selected[table].append(row)
            else:
                skipped.append({"table": table, "row": row, "reason": "Ngày hôm nay hoặc thời gian không rõ"})

    # Thanh toán phải được xóa trước session; không tạo tham chiếu mồ côi mới.
    session_ids = {row["id"] for row in selected["parking_sessions"]}
    payment_ids = {row["id"] for row in selected["payments"]}
    if any(row["session_id"] in session_ids and row["id"] not in payment_ids for row in rows["payments"]):
        raise RuntimeError("Có thanh toán được giữ lại tham chiếu session mẫu; cần xem xét thủ công")

    candidate_urls = set()
    protected_urls = set()
    for table, fields in IMAGE_FIELDS.items():
        values = rows[table] if table != "camera_status" else [dict(row) for row in conn.execute("SELECT * FROM camera_status")]
        selected_ids = {row["id"] for row in selected.get(table, [])}
        for row in values:
            for field in fields:
                url = row.get(field)
                if url:
                    (candidate_urls if row.get("id") in selected_ids else protected_urls).add(url)

    images, skipped_images = [], []
    for url in sorted(candidate_urls):
        filename = url.removeprefix("/uploads/")
        image = (uploads / filename).resolve()
        reason = None
        if not url.startswith("/uploads/") or Path(filename).name != filename or image.parent != uploads.resolve():
            reason = "Đường dẫn không thuộc thư mục uploads"
        elif url in protected_urls:
            reason = "Đang được dữ liệu giữ lại hoặc camera_status tham chiếu"
        elif not image.is_file():
            reason = "File không tồn tại"
        elif sha256(image) != DUMMY_SHA256:
            reason = "Không trùng fingerprint JPEG mẫu; giữ ảnh có thể là ảnh thật"
        if reason:
            skipped_images.append({"url": url, "path": str(image), "reason": reason})
        else:
            images.append({"url": url, "path": str(image), "size_bytes": image.stat().st_size,
                           "sha256": DUMMY_SHA256})
    return {"database": str(db_path.resolve()), "uploads": str(uploads.resolve()),
            "before_date": before.isoformat(), "rows_to_delete": selected, "images_to_delete": images,
            "skipped_rows": skipped, "skipped_images": skipped_images,
            "protected_tables": ["telemetry_history", "system_state", "slots", "camera_status",
                                 "camera_commands", "barrier_commands", "users"]}


def write_report(plan, backup, report_path):
    report = {"mode": "dry-run", "backup": backup, "plan": plan}
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    lines = ["# Dry-run dọn dữ liệu mẫu — CHƯA XÓA", "", f"DB: `{plan['database']}`",
             f"Backup: `{backup['path']}`", f"Integrity: {backup['integrity_check']}",
             f"Backup SHA-256: `{backup['sha256']}`",
             f"Foreign-key issues có sẵn: `{backup['foreign_key_issues']}`", "",
             "Chỉ xét dữ liệu trước " + plan["before_date"] + "; giữ nguyên các bảng trạng thái/heartbeat/lệnh."]
    for table, rows in plan["rows_to_delete"].items():
        lines += ["", f"## {table}: {len(rows)} dòng"]
        for row in rows:
            lines += ["", f"### id={row['id']}", "", "```json", json.dumps(row, ensure_ascii=False, indent=2), "```"]
    lines += ["", f"## Ảnh sẽ xóa: {len(plan['images_to_delete'])}"]
    for item in plan["images_to_delete"]:
        lines += ["", "```json", json.dumps(item, ensure_ascii=False, indent=2), "```"]
    lines += ["", "## Các mục giữ lại / bỏ qua", "", "```json",
              json.dumps({"rows": plan["skipped_rows"], "images": plan["skipped_images"],
                          "protected_tables": plan["protected_tables"]}, ensure_ascii=False, indent=2), "```"]
    report_path.with_suffix(".md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))
    print("REPORT:", report_path)


def apply_plan(db_path, uploads, approved_path):
    approved = json.loads(approved_path.read_text(encoding="utf-8"))["plan"]
    before = date.fromisoformat(approved["before_date"])
    if before > date.today():
        raise RuntimeError("Không được dọn dữ liệu hôm nay hoặc tương lai")
    with closing(socket.socket()) as probe:
        probe.settimeout(1)
        if probe.connect_ex(("127.0.0.1", 5000)) == 0:
            raise RuntimeError("Backend/cổng 5000 còn chạy. Dừng backend trước --apply; khởi động lại sau khi dọn.")
    with closing(sqlite3.connect(db_path, timeout=5)) as conn:
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        # Khóa writer khác trong toàn bộ kiểm tra, sao lưu và xóa.
        conn.execute("BEGIN IMMEDIATE")
        try:
            current = build_plan(conn, db_path, uploads, before)
            if current != approved:
                raise RuntimeError("Danh sách khác báo cáo đã duyệt. Chạy lại --dry-run và duyệt lại trước khi xóa.")
            # In đầy đủ từng dòng/ảnh trước khi thực hiện xóa theo danh sách đã duyệt.
            print(json.dumps(current, ensure_ascii=False, indent=2))
            backup = create_backup(db_path)
            print("BACKUP:", json.dumps(backup, ensure_ascii=False))
            archive = Path(backup["path"] + "_images")
            if current["images_to_delete"]:
                archive.mkdir()
            for image in current["images_to_delete"]:
                original = Path(image["path"])
                copied = archive / original.name
                shutil.copy2(original, copied)
                if sha256(copied) != image["sha256"]:
                    raise RuntimeError("Sao lưu ảnh không khớp; hủy xóa DB")
            for table, rows in current["rows_to_delete"].items():
                for row in rows:
                    cursor = conn.execute(f'DELETE FROM "{table}" WHERE id = ?', (row["id"],))
                    if cursor.rowcount != 1:
                        raise RuntimeError("Số dòng xóa không khớp báo cáo")
            if [row[0] for row in conn.execute("PRAGMA integrity_check")] != ["ok"]:
                raise RuntimeError("Integrity check lỗi; rollback")
            conn.commit()
        except Exception:
            conn.rollback()
            raise
    # Xóa ảnh sau commit; lỗi file không gây rollback DB giả hoặc xóa mất bản sao.
    failures = []
    for image in current["images_to_delete"]:
        original = Path(image["path"])
        try:
            if sha256(original) != image["sha256"]:
                raise RuntimeError("File đã thay đổi; giữ lại")
            original.unlink()
        except (OSError, RuntimeError) as error:
            failures.append({"path": str(original), "error": str(error)})
    result = {"backup": backup, "deleted_rows": {table: [row["id"] for row in rows]
              for table, rows in current["rows_to_delete"].items()}, "image_delete_failures": failures,
              "images_backup": str(archive), "restart_backend": "python -B -u run_dashboard.py"}
    Path(backup["path"] + "_cleanup_result.json").write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False, indent=2))
    if failures:
        raise RuntimeError("DB đã dọn nhưng có ảnh chưa xóa; xem báo cáo kết quả")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--dry-run", action="store_true", help="Mặc định: chỉ sao lưu và liệt kê")
    mode.add_argument("--apply", action="store_true", help="Xóa theo đúng báo cáo đã duyệt")
    parser.add_argument("--db", type=Path, default=ROOT / "dashboard/parking.db")
    parser.add_argument("--uploads", type=Path, default=ROOT / "dashboard/backend/uploads")
    parser.add_argument("--approved-report", type=Path, help="JSON dry-run đã được người dùng duyệt; bắt buộc cho --apply")
    args = parser.parse_args()
    db_path, uploads = args.db.resolve(), args.uploads.resolve()
    if not db_path.is_file():
        parser.error("DB không tồn tại; không tự tạo DB rỗng")
    if args.apply:
        if not args.approved_report:
            parser.error("--apply cần --approved-report <file JSON đã duyệt>")
        apply_plan(db_path, uploads, args.approved_report)
    else:
        backup = create_backup(db_path)
        # Lập danh sách từ chính snapshot vừa kiểm tra, không trộn các lần đọc DB live.
        with closing(connect_readonly(Path(backup["path"]))) as conn:
            plan = build_plan(conn, db_path, uploads, date.today())
        report = db_path.parent / ("sample_cleanup_plan_" + datetime.now().strftime("%Y%m%d_%H%M%S_%f") + ".json")
        write_report(plan, backup, report)


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    try:
        main()
    except (OSError, RuntimeError, sqlite3.Error, ValueError, KeyError) as error:
        print("ERROR:", error, file=sys.stderr)
        raise SystemExit(1)
