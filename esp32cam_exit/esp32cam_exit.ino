/**
 * ============================================================================
 * ESP32-CAM EXIT - CAMERA CỔNG RA & ANPR BILLING CAPTURE FIRMWARE
 * ============================================================================
 * Board: AI-Thinker ESP32-CAM (Chip ESP32-S + Sensor OV2640)
 * Chức năng:
 *  1. Khởi tạo Camera OV2640 (Độ phân giải SVGA/VGA chuẩn ANPR)
 *  2. Kết nối Wi-Fi non-blocking tới cùng mạng LAN với Backend Server
 *  3. Kiểm tra kết nối TCP/HTTP tới Endpoint Health Check (/api/status)
 *  4. Gửi bản tin Heartbeat định kỳ lên Dashboard Server để báo ONLINE
 *  5. Chụp ảnh xe ra khi nhận trigger (Nút bấm GPIO 13 / Lệnh Serial / Web Trigger)
 *  6. Gửi ảnh JPEG dạng HTTP POST tới Backend ANPR API (/api/cameras/exit/capture)
 *  7. Chẩn đoán chi tiết mã lỗi HTTP/TCP (phân biệt HTTP Status và Error Code -11)
 * ============================================================================
 */

#include "esp_camera.h"
#include <WiFi.h>
#include <HTTPClient.h>
#include "backend_config.h"

// Camera ra: đổi riêng 1 <-> 0 nếu cần đảo lại trái/phải sau khi kiểm tra ảnh.
constexpr int CAMERA_HMIRROR = 1;
constexpr int CAMERA_VFLIP = 0; // Giữ chiều dọc; đổi thành 1 nếu ảnh bị lộn ngược.

// ============================================================================
// WIFI & SERVER CONFIGURATION - SINH TỪ backend_config.json Ở GỐC
// ============================================================================
namespace CamConfig {
    const char* WIFI_SSID     = BackendConfig::WIFI_SSID; // Sinh từ backend_config.json; không sửa tại đây.
    const char* WIFI_PASSWORD = BackendConfig::WIFI_PASSWORD; // Sinh từ backend_config.json; không sửa tại đây.

    // Host/port sinh từ backend_config.json ở gốc bằng sync_backend_config.py.
    const char* SERVER_HOST   = BackendConfig::HOST;
    const uint16_t SERVER_PORT = BackendConfig::PORT;

    const char* CAMERA_ID     = "EXIT_CAM";
    const char* CAMERA_ROLE   = "EXIT";

    // Endpoint REST API
    const char* API_STATUS    = "/api/status";
    const char* API_HEARTBEAT = "/api/cameras/heartbeat";
    const char* API_CAPTURE   = "/api/cameras/exit/capture";
    const char* API_COMMANDS  = "/api/cameras/commands";

    const unsigned long HEARTBEAT_INTERVAL_MS = 5000;  // Gửi nhịp tim mỗi 5 giây
    const unsigned long WIFI_RECONNECT_MS     = 5000;  // Thử kết nối lại mỗi 5 giây

    // Chân Trigger chụp ảnh thủ công (Nút bấm hoặc Cảm biến IR phụ)
    const int TRIGGER_PIN     = 13;
    const int FLASH_LED_PIN   = 4;
}

// ============================================================================
// CẤU HÌNH GPIO CAMERA CHO AI-THINKER ESP32-CAM
// ============================================================================
#define PWDN_GPIO_NUM     32
#define RESET_GPIO_NUM    -1
#define XCLK_GPIO_NUM      0
#define SIOD_GPIO_NUM     26
#define SIOC_GPIO_NUM     27
#define Y9_GPIO_NUM       35
#define Y8_GPIO_NUM       34
#define Y7_GPIO_NUM       39
#define Y6_GPIO_NUM       36
#define Y5_GPIO_NUM       21
#define Y4_GPIO_NUM       19
#define Y3_GPIO_NUM       18
#define Y2_GPIO_NUM        5
#define VSYNC_GPIO_NUM    25
#define HREF_GPIO_NUM     23
#define PCLK_GPIO_NUM     22

// Biến quản lý trạng thái
unsigned long lastHeartbeatTime = 0;
unsigned long lastWifiAttempt   = 0;
bool cameraInitialized          = false;
bool serverReachable            = false;

// Khai báo hàm
bool initCamera();
void handleWiFi();
bool testServerConnectivity();
bool sendHeartbeat();
bool captureAndSendImage();
void checkCameraCommands();
bool ackCameraCommand(int cmdId, const char* status);

void setup() {
    Serial.begin(115200);
    delay(500);

    Serial.println();
    Serial.println("==================================================");
    Serial.printf("[CAMERA] %s\n", CamConfig::CAMERA_ROLE);
    Serial.println("[DEVICE] ESP32-CAM AI-Thinker (OV2640)");
    Serial.printf("[SERVER] Target: %s:%d\n", CamConfig::SERVER_HOST, CamConfig::SERVER_PORT);
    Serial.println("==================================================");

    pinMode(CamConfig::TRIGGER_PIN, INPUT_PULLUP);
    pinMode(CamConfig::FLASH_LED_PIN, OUTPUT);
    digitalWrite(CamConfig::FLASH_LED_PIN, LOW);

    // Retry finitely; never report ONLINE if camera hardware failed.
    for (int attempt = 1; attempt <= 3; ++attempt) {
        Serial.printf("[CAMERA] Init attempt %d/3\n", attempt);
        if (initCamera()) {
            cameraInitialized = true;
            break;
        }
        esp_camera_deinit(); // Release resources before retrying failed init.
        if (attempt < 3) delay(1000);
    }
    if (!cameraInitialized) {
        Serial.println("[CAMERA] FATAL: init failed after 3 attempts; heartbeat/poll disabled. Check hardware and reset.");
    }

    // 2. Khởi tạo Wi-Fi non-blocking
    WiFi.mode(WIFI_STA);
    WiFi.setAutoReconnect(true);
    Serial.println("[WIFI] Connecting...");
    WiFi.begin(CamConfig::WIFI_SSID, CamConfig::WIFI_PASSWORD);
    lastWifiAttempt = millis();
}

void loop() {
    // 1. Quản lý trạng thái kết nối Wi-Fi non-blocking
    handleWiFi();

    // 2. Quét nhận lệnh qua Serial Monitor
    if (Serial.available() > 0) {
        char cmd = (char)Serial.read();
        if (cmd == 'c' || cmd == 'C') {
            Serial.println("[TRIGGER] Serial exit capture requested!");
            captureAndSendImage();
        } else if (cmd == 'h' || cmd == 'H') {
            Serial.println("[TRIGGER] Manual heartbeat requested!");
            sendHeartbeat();
        } else if (cmd == 's' || cmd == 'S') {
            Serial.println("[TRIGGER] Manual server status test requested!");
            testServerConnectivity();
        }
    }

    // 3. Quét nhận trigger từ nút bấm vật lý / IR Trigger (GPIO 13 kéo LOW)
    static bool lastTriggerState = HIGH;
    bool currentTrigger = digitalRead(CamConfig::TRIGGER_PIN);
    if (lastTriggerState == HIGH && currentTrigger == LOW) {
        delay(50);
        if (digitalRead(CamConfig::TRIGGER_PIN) == LOW) {
            Serial.println("[TRIGGER] Pin GPIO 13 activated for EXIT!");
            captureAndSendImage();
        }
    }
    lastTriggerState = currentTrigger;

    // 4. Polling và thực thi lệnh chụp ảnh từ Backend / Web Dashboard
    checkCameraCommands();

    // 5. Gửi Heartbeat định kỳ lên Backend
    unsigned long now = millis();
    if (WiFi.status() == WL_CONNECTED) {
        if (now - lastHeartbeatTime >= CamConfig::HEARTBEAT_INTERVAL_MS) {
            lastHeartbeatTime = now;
            sendHeartbeat();
        }
    }
}

bool initCamera() {
    camera_config_t config = {}; // Initialize every driver field.
    config.ledc_channel = LEDC_CHANNEL_0;
    config.ledc_timer   = LEDC_TIMER_0;
    config.pin_d0       = Y2_GPIO_NUM;
    config.pin_d1       = Y3_GPIO_NUM;
    config.pin_d2       = Y4_GPIO_NUM;
    config.pin_d3       = Y5_GPIO_NUM;
    config.pin_d4       = Y6_GPIO_NUM;
    config.pin_d5       = Y7_GPIO_NUM;
    config.pin_d6       = Y8_GPIO_NUM;
    config.pin_d7       = Y9_GPIO_NUM;
    config.pin_xclk     = XCLK_GPIO_NUM;
    config.pin_pclk     = PCLK_GPIO_NUM;
    config.pin_vsync    = VSYNC_GPIO_NUM;
    config.pin_href     = HREF_GPIO_NUM;
    config.pin_sccb_sda = SIOD_GPIO_NUM;
    config.pin_sccb_scl = SIOC_GPIO_NUM;
    config.pin_pwdn     = PWDN_GPIO_NUM;
    config.pin_reset    = RESET_GPIO_NUM;
    config.xclk_freq_hz = 20000000;
    config.pixel_format = PIXFORMAT_JPEG;

    const bool hasPsram = psramFound();
    Serial.printf("[CAMERA] PSRAM: %s\n", hasPsram ? "YES" : "NO");
    if (hasPsram) {
        config.frame_size = FRAMESIZE_SVGA; // 800x600
        config.jpeg_quality = 12;
        config.fb_count = 2;
        config.fb_location = CAMERA_FB_IN_PSRAM;
        config.grab_mode = CAMERA_GRAB_LATEST; // Prefer latest frame with multiple buffers.
    } else {
        config.frame_size = FRAMESIZE_VGA;  // 640x480
        config.jpeg_quality = 14;
        config.fb_count = 1;
        config.fb_location = CAMERA_FB_IN_DRAM;
        config.grab_mode = CAMERA_GRAB_WHEN_EMPTY;
    }

    esp_err_t err = esp_camera_init(&config);
    Serial.printf("[CAMERA] esp_camera_init: 0x%x (%s)\n", (unsigned int)err, esp_err_to_name(err));
    if (err != ESP_OK) return false;

    // Áp dụng trước khi initCamera trả thành công và cho phép chụp/gửi ảnh.
    sensor_t* s = esp_camera_sensor_get();
    if (s == nullptr) {
        Serial.println("[CAMERA] Sensor unavailable; orientation not applied");
        return false;
    }
    const int mirrorResult = s->set_hmirror(s, CAMERA_HMIRROR);
    const int flipResult = s->set_vflip(s, CAMERA_VFLIP);
    if (mirrorResult != 0 || flipResult != 0) {
        Serial.printf("[CAMERA] Orientation FAILED: hmirror_rc=%d vflip_rc=%d\n", mirrorResult, flipResult);
        return false; // Dùng cơ chế retry init hiện có, không báo thành công giả.
    }
    Serial.printf("[CAMERA] hmirror=%d vflip=%d\n", CAMERA_HMIRROR, CAMERA_VFLIP);
    return true;
}

void handleWiFi() {
    static bool wasConnected = false;
    unsigned long now = millis();

    if (WiFi.status() == WL_CONNECTED) {
        if (!wasConnected) {
            wasConnected = true;
            Serial.println("[WIFI] Connected");
            Serial.printf("[WIFI] IP: %s\n", WiFi.localIP().toString().c_str());
            Serial.printf("[WIFI] RSSI: %d dBm\n", WiFi.RSSI());

            // Chẩn đoán server và gửi heartbeat đầu tiên
            testServerConnectivity();
            sendHeartbeat();
        }
    } else {
        if (wasConnected) {
            wasConnected = false;
            Serial.println("[WIFI] Disconnected!");
            lastWifiAttempt = now;
        }

        if (now - lastWifiAttempt >= CamConfig::WIFI_RECONNECT_MS) {
            lastWifiAttempt = now;
            Serial.println("[WIFI] Reconnecting...");
            WiFi.disconnect();
            delay(50);
            WiFi.begin(CamConfig::WIFI_SSID, CamConfig::WIFI_PASSWORD);
        }
    }
}

bool testServerConnectivity() {
    if (WiFi.status() != WL_CONNECTED) {
        Serial.println("[SERVER] Cannot test: WiFi not connected");
        return false;
    }

    String url = String("http://") + CamConfig::SERVER_HOST + ":" + CamConfig::SERVER_PORT + CamConfig::API_STATUS;
    Serial.println("\n[SERVER] Testing:");
    Serial.println(url);

    // 1. Kiểm tra TCP socket tới Server
    WiFiClient tcpClient;
    tcpClient.setTimeout(3000);
    if (tcpClient.connect(CamConfig::SERVER_HOST, CamConfig::SERVER_PORT)) {
        Serial.println("[SERVER] TCP reachable: YES");
        tcpClient.stop();
    } else {
        Serial.println("[SERVER] TCP reachable: NO");
        serverReachable = false;
        return false;
    }

    // 2. Kiểm tra HTTP GET request
    Serial.println("[HTTP] Request started");
    HTTPClient http;
    http.begin(url);
    http.addHeader("Connection", "close");
    http.setTimeout(5000);

    int httpCode = http.GET();
    if (httpCode > 0) {
        Serial.printf("[HTTP] Response code: %d\n", httpCode);
        String body = http.getString();
        if (body.length() > 60) {
            Serial.printf("[HTTP] Response body: %s...\n", body.substring(0, 60).c_str());
        } else {
            Serial.printf("[HTTP] Response body: %s\n", body.c_str());
        }
        serverReachable = (httpCode >= 200 && httpCode < 400);
        if (serverReachable) {
            Serial.println("[SERVER] Server reachable");
        }
    } else {
        Serial.println("[HTTP] Request failed");
        Serial.printf("[HTTP] Error code: %d\n", httpCode);
        Serial.printf("[HTTP] Error meaning: %s\n", HTTPClient::errorToString(httpCode).c_str());
        serverReachable = false;
    }
    http.end();
    return serverReachable;
}

bool sendHeartbeat() {
    if (!cameraInitialized) {
        Serial.println("[HEARTBEAT] Skipped: camera init failed; cannot report ONLINE");
        return false;
    }
    if (WiFi.status() != WL_CONNECTED) return false;

    String url = String("http://") + CamConfig::SERVER_HOST + ":" + CamConfig::SERVER_PORT + CamConfig::API_HEARTBEAT;
    HTTPClient http;
    http.begin(url);
    http.addHeader("Content-Type", "application/json");
    http.addHeader("Connection", "close");
    http.setTimeout(5000);

    String payload = String("{\"cameraId\":\"") + CamConfig::CAMERA_ID + "\",\"role\":\"" + CamConfig::CAMERA_ROLE + "\"}";
    int httpCode = http.POST(payload);
    bool success = false;

    if (httpCode > 0) {
        Serial.printf("[HTTP] Response code: %d\n", httpCode);
        String resp = http.getString();
        if (httpCode == 200) {
            serverReachable = true;
            Serial.println("[HEARTBEAT] Sent successfully");
            Serial.printf("[HEARTBEAT] Payload response: %s\n", resp.c_str());
            success = true;
        } else {
            Serial.printf("[HEARTBEAT] Response status: %d - %s\n", httpCode, resp.c_str());
        }
    } else {
        serverReachable = false;
        Serial.println("[HTTP] Request failed");
        Serial.printf("[HTTP] Error code: %d\n", httpCode);
        Serial.printf("[HTTP] Error meaning: %s\n", HTTPClient::errorToString(httpCode).c_str());
    }
    http.end();
    return success;
}

bool captureAndSendImage() {
    if (!cameraInitialized) {
        Serial.println("[ERROR] Camera not initialized!");
        return false;
    }
    if (WiFi.status() != WL_CONNECTED) {
        Serial.println("[ERROR] WiFi not connected. Cannot send image!");
        return false;
    }

    Serial.println("[CAMERA] Capturing exit frame...");

    // Return both stale frames before acquiring the frame to upload.
    for (int i = 0; i < 2; ++i) {
        camera_fb_t *discard = esp_camera_fb_get();
        if (!discard) {
            Serial.printf("[CAMERA] Warm-up frame %d failed; upload cancelled\n", i + 1);
            return false;
        }
        esp_camera_fb_return(discard);
    }
    camera_fb_t *fb = esp_camera_fb_get();
    if (!fb) {
        Serial.println("[ERROR] Frame buffer capture failed!");
        return false;
    }

    Serial.printf("[CAMERA] Frame: %ux%u, %u bytes. Uploading to ANPR...\n", (unsigned int)fb->width, (unsigned int)fb->height, (unsigned int)fb->len);

    HTTPClient http;
    String url = String("http://") + CamConfig::SERVER_HOST + ":" + CamConfig::SERVER_PORT + CamConfig::API_CAPTURE;
    http.begin(url);
    http.addHeader("Content-Type", "image/jpeg");
    http.addHeader("Connection", "close");
    http.addHeader("X-Camera-ID", CamConfig::CAMERA_ID);
    http.addHeader("X-Camera-Role", CamConfig::CAMERA_ROLE);
    http.setTimeout(8000);

    int httpCode = http.POST(fb->buf, fb->len);
    bool success = false;

    if (httpCode > 0) {
        Serial.printf("[HTTP] Response code: %d\n", httpCode);
        String resp = http.getString();
        if (httpCode >= 200 && httpCode < 300) {
            Serial.printf("[ANPR] Checkout capture success: %s\n", resp.c_str());
            success = true;
        } else {
            Serial.printf("[ANPR] Checkout capture failed (HTTP %d): %s\n", httpCode, resp.c_str());
        }
    } else {
        Serial.println("[HTTP] Request failed");
        Serial.printf("[HTTP] Error code: %d\n", httpCode);
        Serial.printf("[HTTP] Error meaning: %s\n", HTTPClient::errorToString(httpCode).c_str());
    }

    http.end();
    esp_camera_fb_return(fb);
    return success;
}

void checkCameraCommands() {
    static unsigned long lastCmdCheck = 0;
    unsigned long now = millis();
    if (now - lastCmdCheck < 1500) return;
    lastCmdCheck = now;

    if (!cameraInitialized || WiFi.status() != WL_CONNECTED) return;

    String url = String("http://") + CamConfig::SERVER_HOST + ":" + CamConfig::SERVER_PORT + CamConfig::API_COMMANDS + "?camera_id=" + CamConfig::CAMERA_ID;
    HTTPClient http;
    http.begin(url);
    http.addHeader("Connection", "close");
    http.setTimeout(2000);

    int httpCode = http.GET();
    Serial.printf("[POLL] HTTP %d\n", httpCode);
    if (httpCode == 200) {
        String resp = http.getString();
        Serial.printf("[POLL] Response: %s\n", resp.c_str());
        if (resp.indexOf("\"has_command\":true") >= 0 || resp.indexOf("\"has_command\": true") >= 0) {
            int idIdx = resp.indexOf("\"command_id\":");
            int cmdId = 0;
            if (idIdx > 0) {
                cmdId = resp.substring(idIdx + 13).toInt();
            }
            Serial.printf("[COMMAND] Received remote CAPTURE request (ID: #%d)!\n", cmdId);
            bool success = captureAndSendImage();
            if (cmdId > 0) {
                ackCameraCommand(cmdId, success ? "EXECUTED" : "FAILED");
            }
        }
    }
    if (httpCode != 200) {
        Serial.printf("[POLL] FAILED: %s\n", httpCode <= 0 ? HTTPClient::errorToString(httpCode).c_str() : http.getString().c_str());
    }
    http.end();
}

bool ackCameraCommand(int cmdId, const char* status) {
    if (WiFi.status() != WL_CONNECTED) return false;
    String url = String("http://") + CamConfig::SERVER_HOST + ":" + CamConfig::SERVER_PORT + CamConfig::API_COMMANDS + "/" + String(cmdId) + "/ack";
    HTTPClient http;
    http.begin(url);
    http.addHeader("Content-Type", "application/json");
    http.addHeader("Connection", "close");
    http.setTimeout(2500);

    String payload = String("{\"status\":\"") + status + "\"}";
    int httpCode = http.POST(payload);
    Serial.printf("[ACK] ID #%d status=%s HTTP=%d response=%s\n", cmdId, status, httpCode, httpCode <= 0 ? HTTPClient::errorToString(httpCode).c_str() : http.getString().c_str());
    http.end();
    return (httpCode == 200 || httpCode == 201);
}
