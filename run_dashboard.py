#!/usr/bin/env python3
"""
SMART PARKING IoT — ONE-CLICK DASHBOARD & BACKEND LAUNCHER
"""

import os
import sys
import webbrowser
import threading
import time

PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
BACKEND_DIR = os.path.join(PROJECT_ROOT, "dashboard", "backend")

# Thêm backend dir vào sys.path để import
sys.path.insert(0, BACKEND_DIR)

from dotenv import load_dotenv
load_dotenv(os.path.join(PROJECT_ROOT, ".env"))

from db import init_db
from app import app

def open_browser():
    time.sleep(1.2)
    print("\n[INFO] Opening Dashboard in default web browser: http://localhost:5000 ...")
    webbrowser.open("http://localhost:5000")

if __name__ == "__main__":
    init_db()
    
    # Tự động mở trình duyệt sau khi server chạy
    threading.Thread(target=open_browser, daemon=True).start()

    print("\n=======================================================")
    print("=== SMART PARKING IoT - REALTIME CONTROL DASHBOARD ===")
    print("=======================================================")
    print("Local URL:           http://localhost:5000")
    print("Network/LAN URL:     http://0.0.0.0:5000")
    print("ESP32 API Endpoint:  http://<LAN_IP>:5000/api/telemetry/heartbeat")
    print("=======================================================\n")

    app.run(host="0.0.0.0", port=5000, debug=False, threaded=True)
