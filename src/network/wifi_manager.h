#ifndef WIFI_MANAGER_H
#define WIFI_MANAGER_H

#include <Arduino.h>
#include <WiFi.h>
#include <HTTPClient.h>
#include <ArduinoJson.h>
#include "../config/config.h"

enum class WiFiState {
    DISCONNECTED,
    CONNECTING,
    CONNECTED,
    RECONNECTING
};

class WiFiNetworkManager {
public:
    WiFiNetworkManager();
    void begin();
    void update();

    bool isConnected() const;
    bool isServerOnline() const;
    bool checkServerConnectivity();
    WiFiState getState() const;
    const char* getStateStr() const;
    void printDebugStatus() const;

    // Gửi bản tin nhịp tim telemetry lên server định kỳ
    bool sendTelemetry(bool p1, bool p2, bool p3, bool p4,
                       float temp, float hum,
                       uint16_t gasRaw, const char* gasLevelStr,
                       const char* barrierEntryState,
                       const char* barrierExitState,
                       uint8_t freeSlots);

    // Gửi sự kiện quẹt thẻ vào
    bool postCardEntry(const String &cardUid, String &serverMsg);

    // Gửi sự kiện quẹt thẻ ra
    bool postCardExit(const String &cardUid, String &serverMsg);

    // Polling và xác nhận lệnh điều khiển Barrier từ xa
    bool pollBarrierCommand(int &cmdId, String &barrier, String &action);
    bool ackBarrierCommand(int cmdId, const char* status);

private:
    WiFiState currentState;
    unsigned long lastReconnectAttempt;
    unsigned long lastTelemetryTime;
    unsigned long lastServerFailTime;
    bool serverReachable;

    void handleWiFiStateMachine();
};

#endif // WIFI_MANAGER_H
