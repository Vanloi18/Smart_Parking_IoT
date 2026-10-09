#include "mq7.h"

MQ7Sensor::MQ7Sensor() 
    : currentADC(0), currentLevel(GasLevel::NORMAL), lastReadTime(0) {}

void MQ7Sensor::begin() {
    // Cấu hình chân ADC1 GPIO 36
    pinMode(Pins::MQ7_AO, INPUT);

    // Cấu hình độ phân giải 12-bit (0 - 4095) và suy giảm 11dB (đo tới ~3.1V)
    analogReadResolution(12);
    analogSetPinAttenuation(Pins::MQ7_AO, ADC_11db);

    currentADC = readAveragedADC();
    update();

    Serial.printf("[MQ7] Initialized on GPIO %d (ADC1), Raw ADC: %d, Status: %s\n", 
                  Pins::MQ7_AO, currentADC, getGasLevelStr());
}

uint16_t MQ7Sensor::readAveragedADC() {
    uint32_t sum = 0;
    for (uint8_t i = 0; i < Config::MQ7_SAMPLE_COUNT; i++) {
        sum += analogRead(Pins::MQ7_AO);
        delayMicroseconds(50);
    }
    return static_cast<uint16_t>(sum / Config::MQ7_SAMPLE_COUNT);
}

void MQ7Sensor::update() {
    unsigned long now = millis();
    // Đọc cập nhật mỗi 500ms
    if (now - lastReadTime >= 500) {
        lastReadTime = now;
        currentADC = readAveragedADC();

        GasLevel oldLevel = currentLevel;
        if (currentADC >= Config::GAS_THRESHOLD_DANGER) {
            currentLevel = GasLevel::DANGER;
        } else if (currentADC >= Config::GAS_THRESHOLD_WARNING) {
            currentLevel = GasLevel::WARNING;
        } else {
            currentLevel = GasLevel::NORMAL;
        }

        if (oldLevel != currentLevel) {
            Serial.printf("[MQ7] ADC=%d LEVEL=%s\n", currentADC, getGasLevelStr());
        }
    }
}

uint16_t MQ7Sensor::getRawADC() const {
    return currentADC;
}

float MQ7Sensor::getVoltageADC() const {
    // ADC 12-bit (0 - 4095), mức suy giảm 11dB (khoảng 3.3V)
    return (currentADC * 3.3f) / 4095.0f;
}

float MQ7Sensor::getEstimatedAOVoltage() const {
    // Mạch cầu phân áp R1=10k, R2=10k chia đôi điện áp (V_AO = V_ADC * 2.0)
    return getVoltageADC() * Config::VOLTAGE_DIVIDER_RATIO;
}

GasLevel MQ7Sensor::getGasLevel() const {
    return currentLevel;
}

const char* MQ7Sensor::getGasLevelStr() const {
    switch (currentLevel) {
        case GasLevel::DANGER:  return "DANGER";
        case GasLevel::WARNING: return "WARNING";
        case GasLevel::NORMAL:
        default:                return "NORMAL";
    }
}

bool MQ7Sensor::isAlarmActive() const {
    return (currentLevel == GasLevel::WARNING || currentLevel == GasLevel::DANGER);
}

void MQ7Sensor::printDebugStatus() const {
    Serial.println("--- [TEST 5] MQ-7 CARBON MONOXIDE SENSOR ---");
    Serial.printf("  GPIO Pin       : %d (ADC1_CH0)\n", Pins::MQ7_AO);
    Serial.printf("  Raw ADC (12bit): %d / 4095\n", currentADC);
    Serial.printf("  Voltage at GPIO: %.3f V (Threshold safe: < 3.30V)\n", getVoltageADC());
    Serial.printf("  Estimated AO   : %.3f V (Divider 10k/10k ratio: 2.0x)\n", getEstimatedAOVoltage());
    Serial.printf("  Gas Status     : %s (Warn>=%d, Danger>=%d)\n", 
                  getGasLevelStr(), Config::GAS_THRESHOLD_WARNING, Config::GAS_THRESHOLD_DANGER);
    Serial.println("--------------------------------------------");
}
