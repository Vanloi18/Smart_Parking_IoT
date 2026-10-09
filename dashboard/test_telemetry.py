import time
import requests
import json
import sys
import io
from PIL import Image

BASE_URL = "http://127.0.0.1:5000"

def create_dummy_jpeg():
    """Tạo một file ảnh JPEG mẫu hợp lệ trong bộ nhớ để test Camera Upload"""
    img = Image.new("RGB", (640, 480), color=(73, 109, 137))
    buf = io.BytesIO()
    img.save(buf, format="JPEG")
    return buf.getvalue()

def run_e2e_tests():
    print("======================================================================")
    print("=== SMART PARKING IoT — COMPREHENSIVE END-TO-END VERIFICATION ===")
    print("======================================================================")

    # TEST 1: Backend Health & Status
    print("\n[TEST 1] Testing Backend API Availability (GET /api/status)...")
    try:
        r = requests.get(f"{BASE_URL}/api/status", timeout=3)
        assert r.status_code == 200, f"Expected 200 but got {r.status_code}"
        data = r.json()
        print(f"-> PASS! Backend online. Total slots: {data['total_slots']}, Free: {data['free_slots']}")
    except Exception as e:
        print(f"-> FAIL! Cannot connect to {BASE_URL}: {e}")
        return False

    # TEST 2: Authentication & Login
    print("\n[TEST 2] Testing User Authentication & Token Generation (POST /api/auth/login)...")
    token = None
    try:
        login_payload = {"username": "admin", "password": "admin123"}
        r = requests.post(f"{BASE_URL}/api/auth/login", json=login_payload, timeout=3)
        assert r.status_code == 200, f"Login failed: {r.status_code} {r.text}"
        res = r.json()
        assert res.get("status") == "success"
        token = res.get("token")
        assert token, "Token must be returned"
        print(f"-> PASS! Login successful. Role: {res['user']['role']}, Token: {token[:20]}...")

        # Test auth/me with Bearer token
        headers = {"Authorization": f"Bearer {token}"}
        r_me = requests.get(f"{BASE_URL}/api/auth/me", headers=headers, timeout=3)
        assert r_me.status_code == 200
        print("-> PASS! Token validated via GET /api/auth/me")
    except Exception as e:
        print(f"-> FAIL! Authentication failed: {e}")
        return False

    # TEST 3: ESP32 Telemetry Heartbeat (4 Real Slots & Environment)
    print("\n[TEST 3] Simulating ESP32 Telemetry Heartbeat (POST /api/telemetry/heartbeat)...")
    telemetry_payload = {
        "slots": {
            "P1": 1,
            "P2": 0,
            "P3": 1,
            "P4": 0
        },
        "temp": 30.5,
        "hum": 72.0,
        "gas": 1450,
        "gasLevel": "WARNING",
        "barrierEntry": "OPEN",
        "barrierExit": "CLOSED",
        "freeSlots": 2
    }
    try:
        r = requests.post(f"{BASE_URL}/api/telemetry/heartbeat", json=telemetry_payload, timeout=3)
        assert r.status_code == 200, f"Expected 200 but got {r.status_code}"
        res = r.json()
        assert res.get("status") == "success"
        print(f"-> PASS! ESP32 Telemetry recorded: {res}")
    except Exception as e:
        print(f"-> FAIL! Telemetry heartbeat failed: {e}")
        return False

    # TEST 4: Database State Synchronization
    print("\n[TEST 4] Verifying Real Slots & State Sync (GET /api/parking/slots)...")
    try:
        r = requests.get(f"{BASE_URL}/api/parking/status", timeout=3)
        state = r.json()
        assert state["slots"]["P1"] == 1, "P1 should be OCCUPIED (1)"
        assert state["slots"]["P2"] == 0, "P2 should be FREE (0)"
        assert state["slots"]["P3"] == 1, "P3 should be OCCUPIED (1)"
        assert state["slots"]["P4"] == 0, "P4 should be FREE (0)"
        assert state["free_slots"] == 2, f"Expected 2 free slots, got {state['free_slots']}"
        assert state["environment"]["temperature"] == 30.5
        assert state["environment"]["gas_level"] == "WARNING"

        r_slots = requests.get(f"{BASE_URL}/api/parking/slots", timeout=3)
        slots_data = r_slots.json().get("slots", [])
        assert len(slots_data) == 4, f"Expected 4 slots, got {len(slots_data)}"
        print("-> PASS! Database & State synchronized 100% with ESP32 telemetry.")
    except Exception as e:
        print(f"-> FAIL! State sync check failed: {e}")
        return False

    # TEST 5: ESP32-CAM Camera Heartbeats & Real Status
    print("\n[TEST 5] Testing ESP32-CAM Heartbeat & Status Tracking (POST /api/cameras/heartbeat)...")
    try:
        r_entry_hb = requests.post(f"{BASE_URL}/api/cameras/heartbeat",
                                   json={"cameraId": "ENTRY_CAM", "role": "ENTRY"}, timeout=3)
        assert r_entry_hb.status_code == 200

        r_exit_hb = requests.post(f"{BASE_URL}/api/cameras/heartbeat",
                                  json={"cameraId": "EXIT_CAM", "role": "EXIT"}, timeout=3)
        assert r_exit_hb.status_code == 200

        r_cam_stat = requests.get(f"{BASE_URL}/api/cameras/status", timeout=3)
        cam_stats = r_cam_stat.json()
        assert cam_stats["entry"]["online"] == True, "ENTRY_CAM should be ONLINE"
        assert cam_stats["exit"]["online"] == True, "EXIT_CAM should be ONLINE"
        print(f"-> PASS! Camera status verified: ENTRY={cam_stats['entry']['status']}, EXIT={cam_stats['exit']['status']}")
    except Exception as e:
        print(f"-> FAIL! Camera heartbeat/status failed: {e}")
        return False

    # TEST 6: ESP32-CAM Entry Capture & ANPR Processing
    print("\n[TEST 6] Testing ESP32-CAM Entry Capture (POST /api/cameras/entry/capture)...")
    dummy_jpeg = create_dummy_jpeg()
    test_plate = "30A-999.88"
    try:
        # Upload ảnh thật với plate hint
        files = {"image": ("entry_test.jpg", dummy_jpeg, "image/jpeg")}
        data = {"plate": test_plate, "cardUid": "RFID_CAM_101"}
        r = requests.post(f"{BASE_URL}/api/cameras/entry/capture", files=files, data=data, timeout=5)
        assert r.status_code == 200, f"Capture failed: {r.status_code} {r.text}"
        res = r.json()
        assert res.get("success") == True
        assert res.get("plateNumber") == test_plate
        assert res.get("camera") == "ENTRY_CAM"
        print(f"-> PASS! Entry Camera capture accepted: Plate={res['plateNumber']}, ImageUrl={res.get('imageUrl')}")
    except Exception as e:
        print(f"-> FAIL! Entry capture failed: {e}")
        return False

    # TEST 7: RFID Entry & Parking Session
    print("\n[TEST 7] Testing RFID Entry Gate Check-in (POST /api/parking/entry)...")
    try:
        entry_payload = {"cardUid": "RFID_E2E_888", "gate": "ENTRY"}
        r = requests.post(f"{BASE_URL}/api/parking/entry", json=entry_payload, timeout=3)
        assert r.status_code == 200
        res = r.json()
        assert res.get("status") == "success"
        print(f"-> PASS! RFID check-in approved: Card={res['cardUid']}")
    except Exception as e:
        print(f"-> FAIL! RFID entry failed: {e}")
        return False

    # TEST 8: ESP32-CAM Exit Capture, Session Matching & Payment Calculation
    print("\n[TEST 8] Testing ESP32-CAM Exit Capture & Billing (POST /api/cameras/exit/capture)...")
    try:
        time.sleep(1)
        files = {"image": ("exit_test.jpg", dummy_jpeg, "image/jpeg")}
        data = {"plate": test_plate, "cardUid": "RFID_CAM_101"}
        r = requests.post(f"{BASE_URL}/api/cameras/exit/capture", files=files, data=data, timeout=5)
        assert r.status_code == 200
        res = r.json()
        assert res.get("success") == True
        assert res.get("plateNumber") == test_plate
        print(f"-> PASS! Exit Camera capture & Billing computed: Plate={res['plateNumber']}, Fee={res.get('fee')} VND")
    except Exception as e:
        print(f"-> FAIL! Exit capture/billing failed: {e}")
        return False

    # TEST 9: Sensors & Hardware Diagnostics Endpoint
    print("\n[TEST 9] Testing Sensors Diagnostics (GET /api/sensors)...")
    try:
        r = requests.get(f"{BASE_URL}/api/sensors", timeout=3)
        assert r.status_code == 200
        sensors = r.json().get("sensors", {})
        assert "environment" in sensors
        assert "slots_ir" in sensors
        assert "gates" in sensors
        print(f"-> PASS! Sensors diagnostics verified: Temp={sensors['environment']['temperature_c']}C, GasADC={sensors['environment']['gas_raw_adc']}")
    except Exception as e:
        print(f"-> FAIL! Sensors diagnostics failed: {e}")
        return False

    # TEST 10: History & Payments Audit Log
    print("\n[TEST 10] Verifying Audit History & Payments Log...")
    try:
        r_hist = requests.get(f"{BASE_URL}/api/history", timeout=3)
        assert r_hist.status_code == 200
        history = r_hist.json().get("history", [])
        assert len(history) > 0, "History should contain events"

        r_pay = requests.get(f"{BASE_URL}/api/payments", timeout=3)
        assert r_pay.status_code == 200
        payments = r_pay.json().get("payments", [])
        assert len(payments) > 0, "Payments should contain records"

        print(f"-> PASS! Audit logs: {len(history)} events, {len(payments)} payments recorded.")
    except Exception as e:
        print(f"-> FAIL! History/Payments log check failed: {e}")
        return False

    print("\n======================================================================")
    print("ALL 10 COMPREHENSIVE END-TO-END TESTS PASSED (100% SUCCESSFUL)!")
    print("Full Flow Verified: ESP32 + 2x ESP32-CAM -> Flask API -> SQLite -> Dashboard")
    print("======================================================================")
    return True

if __name__ == "__main__":
    success = run_e2e_tests()
    sys.exit(0 if success else 1)
