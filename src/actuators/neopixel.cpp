#include "neopixel.h"

NeoPixelManager::NeoPixelManager()
    : strip(Config::NEOPIXEL_COUNT, Pins::NEOPIXEL, NEO_GRB + NEO_KHZ800),
      currentState(NeoState::STARTING),
      lastBlinkTime(0),
      blinkToggle(false) {}

void NeoPixelManager::begin() {
    strip.begin();
    strip.setBrightness(Config::NEOPIXEL_BRIGHTNESS);
    setState(NeoState::STARTING);
    Serial.printf("[NEOPIXEL] Initialized on GPIO %d\n", Pins::NEOPIXEL);
}

void NeoPixelManager::setColor(uint8_t r, uint8_t g, uint8_t b) {
    strip.setPixelColor(0, strip.Color(r, g, b));
    strip.show();
}

void NeoPixelManager::setState(NeoState newState) {
    currentState = newState;
    switch (currentState) {
        case NeoState::STARTING:
            // Màu TRẮNG: Khởi động hệ thống
            setColor(255, 255, 255);
            break;

        case NeoState::CONNECTING_WIFI:
            // Màu TÍM: Đang kết nối WiFi / Server
            setColor(180, 0, 255);
            break;

        case NeoState::NORMAL:
            // Màu XANH LÁ: Hệ thống bình thường
            setColor(0, 255, 0);
            break;

        case NeoState::WARNING_GAS:
            // Sẽ được xử lý nhấp nháy trong update()
            blinkToggle = true;
            setColor(255, 0, 0);
            lastBlinkTime = millis();
            break;

        case NeoState::EMERGENCY:
        case NeoState::ERROR:
            // Màu ĐỎ: Lỗi hoặc sự cố khẩn cấp
            setColor(255, 0, 0);
            break;
    }
}

NeoState NeoPixelManager::getState() const {
    return currentState;
}

void NeoPixelManager::update() {
    unsigned long now = millis();

    // Nhấp nháy ĐỎ khi cảnh báo khí gas
    if (currentState == NeoState::WARNING_GAS) {
        if (now - lastBlinkTime >= Config::NEOPIXEL_BLINK_INTERVAL_MS) {
            lastBlinkTime = now;
            blinkToggle = !blinkToggle;
            if (blinkToggle) {
                setColor(255, 0, 0);
            } else {
                setColor(0, 0, 0); // Tắt
            }
        }
    }
}

void NeoPixelManager::testSequence() {
    Serial.println("[NEOPIXEL] Testing color sequence: White -> Purple -> Green -> Red -> Off...");
    setColor(255, 255, 255); delay(400); // White
    setColor(180, 0, 255); delay(400);   // Purple
    setColor(0, 255, 0); delay(400);     // Green
    setColor(255, 0, 0); delay(400);     // Red
    setColor(0, 0, 0); delay(200);       // Off
    setState(currentState);              // Restore
    Serial.println("[NEOPIXEL] Test complete.");
}
