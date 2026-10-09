#include "wifi_manager.h"

WiFiNetworkManager::WiFiNetworkManager()
    : currentState(WiFiState::DISCONNECTED),
      lastReconnectAttempt(0),
      lastTelemetryTime(0),
      lastServerFailTime(0),
      serverReachable(false) {}

void WiFiNetworkManager::begin() {
    WiFi.mode(WIFI_STA);
    WiFi.setAutoReconnect(true);

    Serial.println("[WIFI] Starting WiFi...");
    Serial.printf("[WIFI] SSID: %s\n", Config::WIFI_SSID);
    Serial.println("[WIFI] Connecting...");

    WiFi.begin(Config::WIFI_SSID, Config::WIFI_PASSWORD);
    currentState = WiFiState::CONNECTING;
    lastReconnectAttempt = millis();
    serverReachable = false;
}

void WiFiNetworkManager::update() {
    handleWiFiStateMachine();
}

void WiFiNetworkManager::handleWiFiStateMachine() {
    unsigned long now = millis();
    wl_status_t status = WiFi.status();

    if (status == WL_CONNECTED) {
        if (currentState != WiFiState::CONNECTED) {
            currentState = WiFiState::CONNECTED;
            Serial.println("[WIFI] Connected");
            Serial.printf("[WIFI] IP: %s\n", WiFi.localIP().toString().c_str());
            Serial.printf("[WIFI] RSSI: %d dBm\n", WiFi.RSSI());

            // Kiểm tra kết nối tới Backend ngay khi vừa có Wi-Fi
            checkServerConnectivity();
        }
    } else {
        if (currentState == WiFiState::CONNECTED) {
            currentState = WiFiState::DISCONNECTED;
            serverReachable = false;
            Serial.println("[WIFI] Connection lost! Entering disconnected state.");
            lastReconnectAttempt = now;
        }

        // Tự động kết nối lại định kỳ mà không block FSM bãi đỗ xe
        if (now - lastReconnectAttempt >= Config::WIFI_RECONNECT_INTERVAL_MS) {
            Serial.println("[WIFI] Connection failed");
            Serial.printf("[WIFI] Retry in %lu ms\n", Config::WIFI_RECONNECT_INTERVAL_MS);

            lastReconnectAttempt = now;
            currentState = WiFiState::RECONNECTING;
            Serial.println("[WIFI] Connecting...");

            WiFi.disconnect();
            delay(50);
            WiFi.begin(Config::WIFI_SSID, Config::WIFI_PASSWORD);
        }
    }
}

bool WiFiNetworkManager::checkServerConnectivity() {
    if (!isConnected()) {
        serverReachable = false;
        return false;
    }

    Serial.println("[SERVER] Connecting...");
    HTTPClient http;
    String url = String("http://") + Config::SERVER_HOST + ":" + Config::SERVER_PORT + Config::API_STATUS;
    http.begin(url);
    http.addHeader("Connection", "close");
    http.setTimeout(3000);

    int httpCode = http.GET();
    if (httpCode > 0) {
        if (httpCode < 400) {
            serverReachable = true;
            Serial.printf("[SERVER] Server reachable (HTTP status: %d)\n", httpCode);
            String body = http.getString();
        } else {
            serverReachable = false;
            Serial.printf("[SERVER] Server reachable but returned HTTP status: %d\n", httpCode);
            String body = http.getString();
        }
    } else {
        serverReachable = false;
        Serial.println("[SERVER] Connection failed");
        Serial.printf("[SERVER] Host %s:%d unreachable (Error code: %d, meaning: %s)\n",
                      Config::SERVER_HOST, Config::SERVER_PORT, httpCode,
                      HTTPClient::errorToString(httpCode).c_str());
    }
    http.end();
    return serverReachable;
}

bool WiFiNetworkManager::isConnected() const {
    return (currentState == WiFiState::CONNECTED);
}

bool WiFiNetworkManager::isServerOnline() const {
    return serverReachable;
}

WiFiState WiFiNetworkManager::getState() const {
    return currentState;
}

const char* WiFiNetworkManager::getStateStr() const {
    switch (currentState) {
        case WiFiState::CONNECTED:    return "CONNECTED";
        case WiFiState::CONNECTING:   return "CONNECTING";
        case WiFiState::RECONNECTING: return "RECONNECTING";
        case WiFiState::DISCONNECTED:
        default:                      return "DISCONNECTED";
    }
}

void WiFiNetworkManager::printDebugStatus() const {
    Serial.println("\n--- [HARDWARE TEST] WIFI & NETWORK ---");
    Serial.printf("Status     : %s\n", getStateStr());
    Serial.printf("SSID       : %s\n", Config::WIFI_SSID);
    if (isConnected()) {
        Serial.printf("IP Address : %s\n", WiFi.localIP().toString().c_str());
        Serial.printf("RSSI       : %d dBm\n", WiFi.RSSI());
        Serial.printf("Gateway    : %s\n", WiFi.gatewayIP().toString().c_str());
    } else {
        Serial.println("IP Address : (Not Connected)");
    }
    Serial.printf("Server Host: %s:%d\n", Config::SERVER_HOST, Config::SERVER_PORT);
    Serial.printf("Server Stat: %s\n", serverReachable ? "ONLINE/REACHABLE" : "OFFLINE/UNREACHABLE");
    Serial.println("--------------------------------------");
}

bool WiFiNetworkManager::sendTelemetry(bool p1, bool p2, bool p3, bool p4,
                                       float temp, float hum,
                                       uint16_t gasRaw, const char* gasLevelStr,
                                       const char* barrierEntryState,
                                       const char* barrierExitState,
                                       uint8_t freeSlots) {
    if (!isConnected()) {
        return false;
    }

    unsigned long now = millis();
    // Nếu server vừa báo lỗi kết nối, hoãn gửi trong 10 giây để không block loop
    if (!serverReachable && (now - lastServerFailTime < 10000)) {
        return false;
    }

    HTTPClient http;
    String url = String("http://") + Config::SERVER_HOST + ":" + Config::SERVER_PORT + Config::API_HEARTBEAT;
    http.begin(url);
    http.addHeader("Content-Type", "application/json");
    http.addHeader("Connection", "close");
    http.setTimeout(3500); // 3500ms timeout đảm bảo tránh -11 read timeout do Flask I/O latency

    JsonDocument doc;
    JsonObject slotsObj = doc["slots"].to<JsonObject>();
    slotsObj["P1"] = p1 ? 1 : 0;
    slotsObj["P2"] = p2 ? 1 : 0;
    slotsObj["P3"] = p3 ? 1 : 0;
    slotsObj["P4"] = p4 ? 1 : 0;

    doc["temp"] = temp;
    doc["hum"] = hum;
    doc["gas"] = gasRaw;
    doc["gasLevel"] = gasLevelStr;
    doc["barrierEntry"] = barrierEntryState;
    doc["barrierExit"] = barrierExitState;
    doc["freeSlots"] = freeSlots;

    String jsonPayload;
    serializeJson(doc, jsonPayload);

    int httpCode = http.POST(jsonPayload);
    bool success = (httpCode > 0 && httpCode < 300);
    
    if (success) {
        if (!serverReachable) {
            serverReachable = true;
            Serial.printf("[SERVER] Server reachable (HTTP status: %d)\n", httpCode);
        }
        String body = http.getString();
    } else {
        if (serverReachable) {
            serverReachable = false;
            if (httpCode > 0) {
                Serial.printf("[SERVER] Telemetry failed (HTTP status: %d)\n", httpCode);
            } else {
                Serial.printf("[SERVER] Connection failed (Error code: %d, meaning: %s)\n",
                              httpCode, HTTPClient::errorToString(httpCode).c_str());
            }
        }
        lastServerFailTime = now;
    }

    http.end();
    return success;
}

bool WiFiNetworkManager::postCardEntry(const String &cardUid, String &serverMsg) {
    if (!isConnected() || !serverReachable) {
        serverMsg = "OFFLINE_LOCAL_FALLBACK";
        return true; // Cho phép mở cổng tức thì ở chế độ local offline
    }

    HTTPClient http;
    String url = String("http://") + Config::SERVER_HOST + ":" + Config::SERVER_PORT + Config::API_PARKING_ENTRY;
    http.begin(url);
    http.addHeader("Content-Type", "application/json");
    http.addHeader("Connection", "close");
    http.setTimeout(3000);

    JsonDocument doc;
    doc["cardUid"] = cardUid;
    doc["gate"] = "ENTRY";

    String jsonPayload;
    serializeJson(doc, jsonPayload);

    int httpCode = http.POST(jsonPayload);
    bool success = false;

    if (httpCode == HTTP_CODE_OK || httpCode == HTTP_CODE_CREATED) {
        serverMsg = http.getString();
        serverReachable = true;
        success = true;
    } else {
        serverMsg = "HTTP_FAIL_LOCAL_OK";
        serverReachable = false;
        lastServerFailTime = millis();
        success = true; // Fallback cho phép vào
    }

    http.end();
    return success;
}

bool WiFiNetworkManager::postCardExit(const String &cardUid, String &serverMsg) {
    if (!isConnected() || !serverReachable) {
        serverMsg = "OFFLINE_LOCAL_FALLBACK";
        return true;
    }

    HTTPClient http;
    String url = String("http://") + Config::SERVER_HOST + ":" + Config::SERVER_PORT + Config::API_PARKING_EXIT;
    http.begin(url);
    http.addHeader("Content-Type", "application/json");
    http.addHeader("Connection", "close");
    http.setTimeout(3000);

    JsonDocument doc;
    doc["cardUid"] = cardUid;
    doc["gate"] = "EXIT";

    String jsonPayload;
    serializeJson(doc, jsonPayload);

    int httpCode = http.POST(jsonPayload);
    bool success = false;

    if (httpCode == HTTP_CODE_OK || httpCode == HTTP_CODE_ACCEPTED) {
        serverMsg = http.getString();
        serverReachable = true;
        success = true;
    } else {
        serverMsg = "HTTP_FAIL_LOCAL_OK";
        serverReachable = false;
        lastServerFailTime = millis();
        success = true; // Fallback cho phép ra
    }

    http.end();
    return success;
}

bool WiFiNetworkManager::pollBarrierCommand(int &cmdId, String &barrier, String &action) {
    if (!isConnected()) {
        return false;
    }

    HTTPClient http;
    String url = String("http://") + Config::SERVER_HOST + ":" + Config::SERVER_PORT + Config::API_BARRIER_COMMANDS + "?device_id=MAIN_ESP32";
    http.begin(url);
    http.addHeader("Connection", "close");
    http.setTimeout(1500);

    int httpCode = http.GET();
    bool hasCommand = false;
    if (httpCode == HTTP_CODE_OK) {
        String payload = http.getString();
        JsonDocument doc;
        DeserializationError err = deserializeJson(doc, payload);
        if (!err && doc["has_command"].as<bool>()) {
            cmdId = doc["command_id"].as<int>();
            barrier = doc["barrier"].as<String>();
            action = doc["action"].as<String>();
            hasCommand = true;
        }
    }
    http.end();
    return hasCommand;
}

bool WiFiNetworkManager::ackBarrierCommand(int cmdId, const char* status) {
    if (!isConnected()) {
        return false;
    }

    HTTPClient http;
    String url = String("http://") + Config::SERVER_HOST + ":" + Config::SERVER_PORT + Config::API_BARRIER_ACK;
    http.begin(url);
    http.addHeader("Content-Type", "application/json");
    http.addHeader("Connection", "close");
    http.setTimeout(1500);

    JsonDocument doc;
    doc["id"] = cmdId;
    doc["status"] = status;
    doc["device_id"] = "MAIN_ESP32";

    String jsonPayload;
    serializeJson(doc, jsonPayload);

    int httpCode = http.POST(jsonPayload);
    http.end();
    return (httpCode == HTTP_CODE_OK || httpCode == HTTP_CODE_CREATED);
}
