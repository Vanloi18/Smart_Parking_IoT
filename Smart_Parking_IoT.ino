/**
 * ============================================================================
 * DỰ ÁN: SMART PARKING IoT - HỆ THỐNG QUẢN LÝ BÃI ĐỖ XE THÔNG MINH
 * VI ĐIỀU KHIỂN CHÍNH: ESP32 DevKit V1 (30-pin)
 * ============================================================================
 * KIẾN TRÚC FIRMWARE: Non-blocking Multitasking FSM (Finite State Machine)
 * TÁC GIẢ: AI Senior Embedded/IoT Developer
 * ============================================================================
 */

#include <Arduino.h>
#include "src/config/pins.h"
#include "src/config/config.h"
#include "src/sensors/parking_sensors.h"
#include "src/sensors/mq7.h"
#include "src/sensors/dht11.h"
#include "src/actuators/barriers.h"
#include "src/actuators/buzzer.h"
#include "src/actuators/neopixel.h"
#include "src/rfid/rfid_manager.h"
#include "src/display/lcd_manager.h"
#include "src/network/wifi_manager.h"
#include "src/parking/parking_fsm.h"

// --- KHỞI TẠO CÁC ĐỐI TƯỢNG MODULE NGOẠI VI ---
ParkingSensors      parkingSensors;
MQ7Sensor           mq7;
DHT11Sensor         dht11;
BarrierManager      barriers;
BuzzerManager       buzzer;
NeoPixelManager     neopixel;
RFIDManager         rfid;
LCDManager          lcdManager;
WiFiNetworkManager  wifiManager;
ParkingFSM          parkingFSM;

// --- BIẾN TRẠNG THÁI VÀ BỘ ĐỆM NÚT BẤM (BUTTONS) ---
struct DebouncedButton {
    uint8_t pin;
    bool lastState;
    bool stableState;
    unsigned long lastDebounceTime;
};

DebouncedButton btnEntry = { Pins::BUTTON_ENTRY, HIGH, HIGH, 0 };
DebouncedButton btnExit  = { Pins::BUTTON_EXIT,  HIGH, HIGH, 0 };

// --- BỘ ĐỊNH THỜI TELEMETRY & SYSTEM ---
unsigned long lastTelemetryMillis = 0;
bool inHardwareTestMode = false;

// Khai báo hàm prototype
void handleButtons();
void handleSafetyAndAlarm();
void updateTelemetry();
void handleRemoteBarrierCommands();
void printHardwareTestMenu();
void executeHardwareTest(char cmd);

// ============================================================================
// HÀM KHỞI TẠO HỆ THỐNG (SETUP) - STAGGERED SOFT-START
// ============================================================================
void setup() {
    // Khởi tạo cổng truyền thông nối tiếp Serial Debug (115200 baud)
    Serial.begin(115200);
    delay(500); // Trễ nhẹ để ổn định cổng Serial USB
    Serial.println();
    Serial.println("==================================================");
    Serial.println("[BOOT] ESP32 DevKit V1");
    Serial.println("[FIRMWARE] Version 8.1");
    Serial.println("==================================================");

    // Staggered Peripheral Soft-Start (Brownout Mitigation)
    // 1. Cấu hình GPIO cơ bản
    pinMode(Pins::BUTTON_ENTRY, INPUT_PULLUP);
    pinMode(Pins::BUTTON_EXIT,  INPUT_PULLUP);
    Serial.println("[GPIO] Initialized");
    delay(30);

    // 2. NeoPixel (độ sáng thấp hạn chế sụt áp nguồn)
    neopixel.begin();
    neopixel.setState(NeoState::STARTING);
    delay(30);

    // 3. Buzzer
    buzzer.begin();
    delay(30);

    // 4. Màn hình hiển thị LCD2004 I2C
    lcdManager.begin();
    Serial.println("[LCD] Initialized");
    delay(50);

    // 5. Cảm biến DHT11
    dht11.begin();
    Serial.println("[DHT11] Initialized");
    delay(30);

    // 6. Cảm biến MQ-7 (ADC1)
    mq7.begin();
    Serial.println("[MQ7] Initialized");
    delay(30);

    // 7. Cảm biến quang IR (6 cảm biến)
    parkingSensors.begin();
    Serial.println("[IR] Initialized");
    delay(50);

    // 8. Động cơ Servo Barrier (Cổng vào, Cổng ra)
    barriers.begin();
    delay(50);

    // 9. Đầu đọc thẻ RFID RC522 (Entry & Exit qua SPI bus chung)
    rfid.begin(&buzzer);
    Serial.println("[RFID] ENTRY initialized");
    Serial.println("[RFID] EXIT initialized");
    delay(30);

    // 10. Buzzer: Duy trì trạng thái OFF hoàn toàn khi khởi động (Silent Boot)
    // Buzzer chỉ kêu khi có sự kiện thực tế (quẹt thẻ RFID, nút bấm, cảnh báo khí MQ-7)
    // Đã loại bỏ buzzer.beepSuccess() để không gây ồn khi cắm nguồn/reset ESP32.

    // 11. Chuyển LED sang màu TÍM và kích hoạt WiFi non-blocking
    neopixel.setState(NeoState::CONNECTING_WIFI);
    wifiManager.begin();

    // 12. Khởi tạo máy trạng thái bãi đỗ xe (Parking FSM)
    parkingFSM.begin();

    Serial.println("==================================================");
    Serial.println("[SYSTEM] READY");
    Serial.println("[NOTE] Press 'T' or '?' in Serial Monitor for Hardware Test Console.");
    Serial.println("==================================================");
}

// ============================================================================
// VÒNG LẶP CHÍNH (MAIN LOOP - NON-BLOCKING MULTITASKING)
// ============================================================================
void loop() {
    // 0. Quét nhận lệnh điều khiển Hardware Test Mode qua Serial Console (115200 baud)
    if (Serial.available() > 0) {
        char incoming = (char)Serial.read();
        if (!inHardwareTestMode) {
            if (incoming == 't' || incoming == 'T' || incoming == '?') {
                inHardwareTestMode = true;
                Serial.println("\n[SYSTEM] Pausing Normal Parking FSM. Entering HARDWARE TEST MODE.");
                printHardwareTestMenu();
                return;
            }
        } else {
            executeHardwareTest(incoming);
            return;
        }
    }

    // Nếu đang trong chế độ Hardware Test -> Tạm dừng FSM tự động
    if (inHardwareTestMode) {
        delay(10);
        return;
    }

    // 1. Cập nhật các cảm biến ngoại vi
    parkingSensors.update();
    dht11.update();
    mq7.update();
    rfid.update();

    // 2. Cập nhật trạng thái và điều khiển vị trí chuyển động mượt của 2 Barrier
    barriers.update(parkingSensors.isEntryVehicleDetected(), 
                    parkingSensors.isExitVehicleDetected());

    // 3. Xử lý quét các nút bấm mở cổng khẩn cấp / xác nhận thanh toán (Debounce 50ms)
    handleButtons();

    // 4. Cập nhật Máy Trạng Thái Bãi Đỗ Xe (Real-World Parking FSM & Billing)
    parkingFSM.update(parkingSensors, barriers, rfid, lcdManager, buzzer, wifiManager,
                      dht11.getTemperature(), dht11.getHumidity(), mq7.getGasLevel());

    // 5. Xử lý logic an toàn khí độc và hệ thống cảnh báo
    handleSafetyAndAlarm();

    // 6. Cập nhật trạng thái mạng Wi-Fi và gửi dữ liệu định kỳ (Telemetry)
    wifiManager.update();
    updateTelemetry();

    // 7. Polling và thực thi lệnh điều khiển Barrier từ xa qua Web Dashboard (Non-blocking)
    handleRemoteBarrierCommands();

    // 8. Cập nhật hiệu ứng ánh sáng đèn NeoPixel RGB & Còi Buzzer
    neopixel.update();
    buzzer.update();
}

// ============================================================================
// HARDWARE TEST CONSOLE FUNCTIONS
// ============================================================================
void printHardwareTestMenu() {
    Serial.println();
    Serial.println("==================================================");
    Serial.println("=== SMART PARKING IoT - HARDWARE TEST CONSOLE  ===");
    Serial.println("==================================================");
    Serial.println(" [1] Test 6x IR Sensors (P1-P4, Entry, Exit)");
    Serial.println(" [2] Test 2x SG90 Servos / Barriers (Entry & Exit)");
    Serial.println(" [3] Test 2x RC522 RFID Readers (SPI Bus & SS)");
    Serial.println(" [4] Test DHT11 Temperature & Humidity Sensor");
    Serial.println(" [5] Test MQ-7 Gas Sensor (ADC1 GPIO36 / VP)");
    Serial.println(" [6] Test LCD2004 I2C Display (4 Rows x 20 Chars)");
    Serial.println(" [7] Test NeoPixel RGB LED (Color Cycle Pattern)");
    Serial.println(" [8] Test Buzzer (Beep Pattern on GPIO32)");
    Serial.println(" [9] Test WiFi & Server Network Connectivity");
    Serial.println(" [0] Exit Test Mode -> Resume Normal Parking FSM");
    Serial.println(" [?] Show This Test Menu Again");
    Serial.println("==================================================");
    Serial.print("Select test option [0-9, ?]: ");
}

void executeHardwareTest(char cmd) {
    switch (cmd) {
        case '1':
            Serial.println("\n>>> [TEST 1] IR PARKING & GATE SENSORS");
            parkingSensors.printDebugStatus();
            break;

        case '2':
            Serial.println("\n>>> [TEST 2] SG90 SERVO BARRIERS TEST");
            barriers.printDebugStatus();
            Serial.println("[TEST] Opening Entry Gate (Fast ~0.45s)...");
            barriers.openEntry();
            {
                unsigned long testStart = millis();
                while (millis() - testStart < 600) {
                    barriers.update(false, false);
                    delay(1);
                }
            }
            delay(1000);
            Serial.println("[TEST] Closing Entry Gate (Slow ~1.8s)...");
            barriers.closeEntry();
            {
                unsigned long testStart = millis();
                while (millis() - testStart < 2100) {
                    barriers.update(false, false);
                    delay(1);
                }
            }
            delay(500);
            Serial.println("[TEST] Opening Exit Gate (Fast ~0.45s)...");
            barriers.openExit();
            {
                unsigned long testStart = millis();
                while (millis() - testStart < 600) {
                    barriers.update(false, false);
                    delay(1);
                }
            }
            delay(1000);
            Serial.println("[TEST] Closing Exit Gate (Slow ~1.8s)...");
            barriers.closeExit();
            {
                unsigned long testStart = millis();
                while (millis() - testStart < 2100) {
                    barriers.update(false, false);
                    delay(1);
                }
            }
            Serial.println("[TEST] Servo Barrier test completed.");
            break;

        case '3':
            Serial.println("\n>>> [TEST 3] RC522 RFID READERS (SPI BUS)");
            rfid.printDebugStatus();
            break;

        case '4':
            Serial.println("\n>>> [TEST 4] DHT11 TEMPERATURE & HUMIDITY");
            dht11.update();
            dht11.printDebugStatus();
            break;

        case '5':
            Serial.println("\n>>> [TEST 5] MQ-7 CARBON MONOXIDE SENSOR");
            mq7.update();
            mq7.printDebugStatus();
            break;

        case '6':
            Serial.println("\n>>> [TEST 6] LCD2004 I2C DISPLAY");
            lcdManager.testDisplay();
            break;

        case '7':
            Serial.println("\n>>> [TEST 7] NEOPIXEL RGB LED");
            neopixel.testSequence();
            break;

        case '8':
            Serial.println("\n>>> [TEST 8] BUZZER ALARM");
            buzzer.testPattern();
            break;

        case '9':
            Serial.println("\n>>> [TEST 9] WIFI & SERVER CONNECTIVITY");
            wifiManager.printDebugStatus();
            break;

        case '0':
        case 'x':
        case 'X':
            Serial.println("\n[TEST MODE] Exiting Hardware Test Console. Resuming Normal Parking FSM...");
            inHardwareTestMode = false;
            lcdManager.showMessage("SMART PARKING IoT", "  SYSTEM RESUMED", "ESP32 DevKit V1", "  FIRMWARE V8.1");
            neopixel.setState(NeoState::NORMAL);
            break;

        case 't':
        case 'T':
        case '?':
            printHardwareTestMenu();
            break;

        case '\r':
        case '\n':
            // Bỏ qua ký tự xuống dòng
            break;

        default:
            Serial.printf("\n[ERROR] Unknown command '%c'. Press '?' for menu, '0' to exit.\n", cmd);
            break;
    }
}

// ============================================================================
// HÀM XỬ LÝ 2 NÚT BẤM (BUTTON ENTRY & BUTTON EXIT)
// ============================================================================
void handleButtons() {
    unsigned long now = millis();

    // --- Nút bấm Mở Cổng Vào (GPIO 4) ---
    bool readEntry = digitalRead(btnEntry.pin);
    if (readEntry != btnEntry.lastState) {
        btnEntry.lastState = readEntry;
        btnEntry.lastDebounceTime = now;
    }
    if ((now - btnEntry.lastDebounceTime) >= Config::BUTTON_DEBOUNCE_MS) {
        if (readEntry != btnEntry.stableState) {
            btnEntry.stableState = readEntry;
            if (btnEntry.stableState == LOW) { // Nhấn nút (Active LOW do dùng INPUT_PULLUP)
                Serial.println("[BUTTON] ENTRY pressed");
                parkingFSM.onEntryButtonPressed(barriers, buzzer, parkingSensors);
            }
        }
    }

    // --- Nút bấm Xác Nhận Thanh Toán / Mở Cổng Ra (GPIO 17) ---
    bool readExit = digitalRead(btnExit.pin);
    if (readExit != btnExit.lastState) {
        btnExit.lastState = readExit;
        btnExit.lastDebounceTime = now;
    }
    if ((now - btnExit.lastDebounceTime) >= Config::BUTTON_DEBOUNCE_MS) {
        if (readExit != btnExit.stableState) {
            btnExit.stableState = readExit;
            if (btnExit.stableState == LOW) { // Nhấn nút (Active LOW do dùng INPUT_PULLUP)
                Serial.println("[BUTTON] EXIT pressed");
                parkingFSM.onExitButtonPressed(barriers, buzzer, wifiManager, lcdManager);
            }
        }
    }
}

// ============================================================================
// HÀM XỬ LÝ AN TOÀN & BÁO ĐỘNG KHÍ ĐỘC MQ-7
// ============================================================================
void handleSafetyAndAlarm() {
    GasLevel gasLvl = mq7.getGasLevel();

    // Bỏ qua cảnh báo âm thanh trong 15 giây đầu khởi động (giai đoạn Warm-up/sấy cảm biến MQ-7)
    // để triệt tiêu hoàn toàn hiện tượng còi kêu liên hồi lúc vừa nạp code / reset ESP32
    bool inWarmup = (millis() < 15000);

    if (!inWarmup && (gasLvl == GasLevel::DANGER || gasLvl == GasLevel::WARNING)) {
        // Có nguy cơ khí độc: Bật còi cảnh báo ngắt quãng, nhấp nháy ĐỎ NeoPixel
        buzzer.setWarningGas(true);
        neopixel.setState(NeoState::WARNING_GAS);
    } else {
        buzzer.setWarningGas(false);

        // Nếu bình thường: Đặt màu NeoPixel theo trạng thái mạng
        if (!wifiManager.isConnected()) {
            neopixel.setState(NeoState::CONNECTING_WIFI); // Màu Tím
        } else {
            neopixel.setState(NeoState::NORMAL);          // Màu Xanh lá
        }
    }
}

// ============================================================================
// HÀM ĐÓNG GÓI VÀ TRUYỀN DỮ LIỆU TELEMETRY (HEARTBEAT)
// ============================================================================
void updateTelemetry() {
    unsigned long now = millis();
    if (now - lastTelemetryMillis >= Config::TELEMETRY_INTERVAL_MS) {
        lastTelemetryMillis = now;

        wifiManager.sendTelemetry(parkingSensors.isSlotOccupied(1),
                                  parkingSensors.isSlotOccupied(2),
                                  parkingSensors.isSlotOccupied(3),
                                  parkingSensors.isSlotOccupied(4),
                                  dht11.getTemperature(),
                                  dht11.getHumidity(),
                                  mq7.getRawADC(),
                                  mq7.getGasLevelStr(),
                                  barriers.getEntryStateStr(),
                                  barriers.getExitStateStr(),
                                  parkingSensors.getAvailableSlotsCount());
    }
}

// ============================================================================
// HÀM XỬ LÝ LỆNH ĐIỀU KHIỂN BARRIER TỪ XA TỪ WEB DASHBOARD
// ============================================================================
void handleRemoteBarrierCommands() {
    static unsigned long lastBarrierPollMillis = 0;
    unsigned long now = millis();

    // Polling Backend mỗi 1.2 giây một lần để phản hồi nhanh mà không làm nghẽn bus
    if (now - lastBarrierPollMillis < 1200) {
        return;
    }
    lastBarrierPollMillis = now;

    if (!wifiManager.isConnected()) {
        return;
    }

    int cmdId = 0;
    String barrier = "";
    String action = "";

    if (wifiManager.pollBarrierCommand(cmdId, barrier, action)) {
        Serial.printf("[REMOTE] >>> Barrier Command #%d: [%s] -> [%s]\n", cmdId, barrier.c_str(), action.c_str());
        barrier.toUpperCase();
        action.toUpperCase();

        if (barrier == "ENTRY") {
            if (action == "OPEN") {
                Serial.println("[REMOTE] Opening ENTRY barrier via Web command");
                barriers.openEntry();
                buzzer.beepSuccess();
                wifiManager.ackBarrierCommand(cmdId, "EXECUTED");
            } else if (action == "CLOSE") {
                // Kiểm tra an toàn cảm biến quang học cổng vào
                if (parkingSensors.isEntryVehicleDetected()) {
                    Serial.println("[SAFETY WARNING] Obstacle detected under ENTRY gate! Rejecting close command.");
                    buzzer.beepError();
                    wifiManager.ackBarrierCommand(cmdId, "REJECTED_SAFETY_OBSTACLE");
                } else {
                    Serial.println("[REMOTE] Closing ENTRY barrier via Web command");
                    barriers.closeEntry();
                    wifiManager.ackBarrierCommand(cmdId, "EXECUTED");
                }
            }
        } else if (barrier == "EXIT") {
            if (action == "OPEN") {
                Serial.println("[REMOTE] Opening EXIT barrier via Web command");
                barriers.openExit();
                buzzer.beepSuccess();
                wifiManager.ackBarrierCommand(cmdId, "EXECUTED");
            } else if (action == "CLOSE") {
                // Kiểm tra an toàn cảm biến quang học cổng ra
                if (parkingSensors.isExitVehicleDetected()) {
                    Serial.println("[SAFETY WARNING] Obstacle detected under EXIT gate! Rejecting close command.");
                    buzzer.beepError();
                    wifiManager.ackBarrierCommand(cmdId, "REJECTED_SAFETY_OBSTACLE");
                } else {
                    Serial.println("[REMOTE] Closing EXIT barrier via Web command");
                    barriers.closeExit();
                    wifiManager.ackBarrierCommand(cmdId, "EXECUTED");
                }
            }
        }
    }
}
