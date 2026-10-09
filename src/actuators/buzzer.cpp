#include "buzzer.h"

BuzzerManager::BuzzerManager()
    : currentMode(BuzzerMode::IDLE),
      stateStartTime(0),
      step(0),
      gasWarningActive(false),
      emergencyActive(false) {}

void BuzzerManager::begin() {
    // Xác lập mức LOW trước khi đặt OUTPUT để triệt tiêu mọi xung nhiễu floating khi boot
    digitalWrite(Pins::BUZZER, LOW);
    pinMode(Pins::BUZZER, OUTPUT);
    digitalWrite(Pins::BUZZER, LOW);

    currentMode = BuzzerMode::IDLE;
    gasWarningActive = false;
    emergencyActive = false;
    step = 0;
    stateStartTime = 0;
    setOutput(false);

    Serial.printf("[BUZZER] Initialized on GPIO %d (Default: OFF, Silent Boot)\n", Pins::BUZZER);
}

void BuzzerManager::setOutput(bool state) {
    digitalWrite(Pins::BUZZER, state ? HIGH : LOW);
}

void BuzzerManager::beepSuccess() {
    // Quẹt thẻ thành công: 1 bíp ngắn 100ms
    if (currentMode != BuzzerMode::ALARM_EMERGENCY) {
        currentMode = BuzzerMode::SINGLE_BEEP;
        stateStartTime = millis();
        step = 0;
        setOutput(true);
    }
}

void BuzzerManager::beepError() {
    // Thẻ không hợp lệ hoặc bãi đầy: 2 bíp dồn dập
    if (currentMode != BuzzerMode::ALARM_EMERGENCY) {
        currentMode = BuzzerMode::DOUBLE_BEEP;
        stateStartTime = millis();
        step = 0;
        setOutput(true);
    }
}

void BuzzerManager::setWarningGas(bool active) {
    if (gasWarningActive != active) {
        gasWarningActive = active;
        // Khi MQ-7 ở mức NORMAL (active = false), lập tức ngắt còi nếu không có cảnh báo khác
        if (!active && !emergencyActive && currentMode == BuzzerMode::IDLE) {
            setOutput(false);
        }
    }
}

void BuzzerManager::setAlarmEmergency(bool active) {
    emergencyActive = active;
    if (active) {
        currentMode = BuzzerMode::ALARM_EMERGENCY;
        setOutput(true);
    } else {
        if (currentMode == BuzzerMode::ALARM_EMERGENCY) {
            currentMode = BuzzerMode::IDLE;
        }
        if (!gasWarningActive) {
            setOutput(false);
        }
    }
}

void BuzzerManager::update() {
    unsigned long now = millis();

    // Ưu tiên 1: Báo động khẩn cấp
    if (emergencyActive) {
        // Còi kêu liên tục
        setOutput(true);
        return;
    }

    // Ưu tiên 2: Cảnh báo khí độc Gas (Bíp ngắt quãng liên tục)
    if (gasWarningActive) {
        unsigned long cycle = (now / 300) % 2;
        setOutput(cycle == 0);
        return;
    }

    // Xử lý các mẫu âm thanh một lần
    switch (currentMode) {
        case BuzzerMode::SINGLE_BEEP:
            if (now - stateStartTime >= Config::BEEP_SHORT_MS) {
                setOutput(false);
                currentMode = BuzzerMode::IDLE;
            }
            break;

        case BuzzerMode::DOUBLE_BEEP:
            if (step == 0 && (now - stateStartTime >= Config::BEEP_SHORT_MS)) {
                setOutput(false);
                step = 1;
                stateStartTime = now;
            } else if (step == 1 && (now - stateStartTime >= Config::BEEP_INTERVAL_MS)) {
                setOutput(true);
                step = 2;
                stateStartTime = now;
            } else if (step == 2 && (now - stateStartTime >= Config::BEEP_SHORT_MS)) {
                setOutput(false);
                step = 0;
                currentMode = BuzzerMode::IDLE;
            }
            break;

        case BuzzerMode::IDLE:
        default:
            setOutput(false);
            break;
    }
}

void BuzzerManager::testPattern() {
    Serial.println("[BUZZER] Testing buzzer pattern (3 short beeps)...");
    for (int i = 0; i < 3; i++) {
        setOutput(true);
        delay(100);
        setOutput(false);
        delay(100);
    }
    currentMode = BuzzerMode::IDLE;
    setOutput(false);
    Serial.println("[BUZZER] Test complete.");
}
