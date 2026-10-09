"""Chạy backend thử vé trên snapshot DB/ảnh riêng, chỉ localhost:5001."""
from contextlib import closing
from pathlib import Path
import sqlite3
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "dashboard/backend"))
from dotenv import load_dotenv
load_dotenv(ROOT / ".env")  # Không in giá trị cấu hình/bí mật.


def main():
    folder = Path(tempfile.mkdtemp(prefix="parking-ticket-demo-"))
    database = folder / "parking.db"
    uploads = folder / "uploads"
    uploads.mkdir()
    with closing(sqlite3.connect((ROOT / "dashboard/parking.db").as_uri() + "?mode=ro", uri=True)) as source:
        with closing(sqlite3.connect(database)) as target:
            source.backup(target)
    import db
    db.DB_PATH = str(database)
    db.init_db()
    import anpr_engine
    anpr_engine.UPLOAD_DIR = str(uploads)
    anpr_engine.anpr_service.upload_dir = str(uploads)
    # Sao chép ảnh để chi tiết phiên cũ trong snapshot vẫn xem được.
    import shutil
    shutil.copytree(ROOT / "dashboard/backend/uploads", uploads, dirs_exist_ok=True)
    from app import app
    print("DEMO DB:", database, flush=True)
    print("DEMO UPLOADS:", uploads, flush=True)
    print("Chỉ gọi API thử tại http://127.0.0.1:5001 ; Ctrl+C để dừng.", flush=True)
    app.run(host="127.0.0.1", port=5001, debug=False, threaded=True)


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    main()
