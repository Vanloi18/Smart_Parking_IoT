#include "barriers.h"

BarrierManager::BarrierManager()
    : currentEntryAngle(Config::ENTRY_SERVO_CLOSED),
      targetEntryAngle(Config::ENTRY_SERVO_CLOSED),
      entryState(BarrierState::CLOSED),
      lastEntryStepTime(0),
      entryOpenStartTime(0),
      entryVehiclePassedWatcher(false),
      currentExitAngle(Config::EXIT_SERVO_CLOSED),
      targetExitAngle(Config::EXIT_SERVO_CLOSED),
      exitState(BarrierState::CLOSED),
      lastExitStepTime(0),
      exitOpenStartTime(0),
      exitVehiclePassedWatcher(false) {}

void BarrierManager::begin() {
    // Cấp phát timer PWM cho ESP32Servo
    ESP32PWM::allocateTimer(0);
    ESP32PWM::allocateTimer(1);
    
    // Cài đặt tần số tiêu chuẩn cho servo SG90: 50Hz (chu kỳ 20ms)
    servoEntry.setPeriodHertz(50);
    servoExit.setPeriodHertz(50);

    // SG90 xung chuẩn: 500us - 2400us
    servoEntry.attach(Pins::SERVO_ENTRY, 500, 2400);
    servoExit.attach(Pins::SERVO_EXIT, 500, 2400);

    // Đặt vị trí ban đầu
    servoEntry.write(Config::ENTRY_SERVO_CLOSED);
    servoExit.write(Config::EXIT_SERVO_CLOSED);

    currentEntryAngle = Config::ENTRY_SERVO_CLOSED;
    targetEntryAngle = Config::ENTRY_SERVO_CLOSED;
    entryState = BarrierState::CLOSED;

    currentExitAngle = Config::EXIT_SERVO_CLOSED;
    targetExitAngle = Config::EXIT_SERVO_CLOSED;
    exitState = BarrierState::CLOSED;

    Serial.println("[SERVO] Initialized");
}

void BarrierManager::openEntry() {
    targetEntryAngle = Config::ENTRY_SERVO_OPEN;
    entryState = BarrierState::OPENING;
    entryOpenStartTime = millis();
    entryVehiclePassedWatcher = false;
    Serial.println("[BARRIER] ENTRY OPENING");
}

void BarrierManager::closeEntry() {
    targetEntryAngle = Config::ENTRY_SERVO_CLOSED;
    entryState = BarrierState::CLOSING;
    Serial.println("[BARRIER] ENTRY CLOSING");
}

void BarrierManager::openExit() {
    targetExitAngle = Config::EXIT_SERVO_OPEN;
    exitState = BarrierState::OPENING;
    exitOpenStartTime = millis();
    exitVehiclePassedWatcher = false;
    Serial.println("[BARRIER] EXIT OPENING");
}

void BarrierManager::closeExit() {
    targetExitAngle = Config::EXIT_SERVO_CLOSED;
    exitState = BarrierState::CLOSING;
    Serial.println("[BARRIER] EXIT CLOSING");
}

void BarrierManager::forceOpenAll() {
    openEntry();
    openExit();
}

void BarrierManager::forceCloseAll() {
    closeEntry();
    closeExit();
}

void BarrierManager::update(bool entryVehiclePresent, bool exitVehiclePresent) {
    unsigned long now = millis();

    // 1. Cập nhật góc quay mượt mà không block CPU
    updateServoMovement();

    // 2. Logic tự động đóng cổng VÀO
    if (entryState == BarrierState::OPEN) {
        // Khi xe vào vùng cảm biến cổng vào, đánh dấu xe đang đi qua
        if (entryVehiclePresent) {
            entryVehiclePassedWatcher = true;
        }

        // Nếu xe đã vào vùng cảm biến rồi sau đó rời đi (đã qua hẳn barrier) -> đóng lại
        if (entryVehiclePassedWatcher && !entryVehiclePresent) {
            Serial.println("[BARRIER] Entry vehicle passed successfully -> Auto closing gate");
            closeEntry();
        }
        // Hoặc quá thời gian an toàn mà xe không đi qua -> tự động đóng lại
        else if (now - entryOpenStartTime >= Config::BARRIER_AUTO_CLOSE_TIMEOUT_MS) {
            Serial.println("[BARRIER] Entry Gate timeout reached -> Auto closing gate");
            closeEntry();
        }
    }

    // 3. Logic tự động đóng cổng RA
    if (exitState == BarrierState::OPEN) {
        if (exitVehiclePresent) {
            exitVehiclePassedWatcher = true;
        }

        if (exitVehiclePassedWatcher && !exitVehiclePresent) {
            Serial.println("[BARRIER] Exit vehicle passed successfully -> Auto closing gate");
            closeExit();
        }
        else if (now - exitOpenStartTime >= Config::BARRIER_AUTO_CLOSE_TIMEOUT_MS) {
            Serial.println("[BARRIER] Exit Gate timeout reached -> Auto closing gate");
            closeExit();
        }
    }
}

void BarrierManager::updateServoMovement() {
    unsigned long now = millis();

    // --- Điều khiển servo Cổng Vào ---
    if (currentEntryAngle != targetEntryAngle) {
        // Tách biệt tốc độ: Mở NHANH (~0.45s: 5ms/độ), Đóng TỪ TỪ (~1.8s: 20ms/độ)
        unsigned long entryStepDelay = (entryState == BarrierState::OPENING)
                                       ? Config::SERVO_OPEN_DELAY_MS
                                       : Config::SERVO_CLOSE_DELAY_MS;

        if (now - lastEntryStepTime >= entryStepDelay) {
            lastEntryStepTime = now;
            if (currentEntryAngle < targetEntryAngle) {
                currentEntryAngle++;
            } else {
                currentEntryAngle--;
            }
            servoEntry.write(currentEntryAngle);

            if (currentEntryAngle == targetEntryAngle) {
                if (currentEntryAngle == Config::ENTRY_SERVO_OPEN) {
                    entryState = BarrierState::OPEN;
                    entryOpenStartTime = now;
                    Serial.println("[BARRIER] ENTRY OPEN");
                } else if (currentEntryAngle == Config::ENTRY_SERVO_CLOSED) {
                    entryState = BarrierState::CLOSED;
                    Serial.println("[BARRIER] ENTRY CLOSED");
                }
            }
        }
    }

    // --- Điều khiển servo Cổng Ra ---
    if (currentExitAngle != targetExitAngle) {
        // Tách biệt tốc độ: Mở NHANH (~0.45s: 5ms/độ), Đóng TỪ TỪ (~1.8s: 20ms/độ)
        unsigned long exitStepDelay = (exitState == BarrierState::OPENING)
                                      ? Config::SERVO_OPEN_DELAY_MS
                                      : Config::SERVO_CLOSE_DELAY_MS;

        if (now - lastExitStepTime >= exitStepDelay) {
            lastExitStepTime = now;
            if (currentExitAngle < targetExitAngle) {
                currentExitAngle++;
            } else {
                currentExitAngle--;
            }
            servoExit.write(currentExitAngle);

            if (currentExitAngle == targetExitAngle) {
                if (currentExitAngle == Config::EXIT_SERVO_OPEN) {
                    exitState = BarrierState::OPEN;
                    exitOpenStartTime = now;
                    Serial.println("[BARRIER] EXIT OPEN");
                } else if (currentExitAngle == Config::EXIT_SERVO_CLOSED) {
                    exitState = BarrierState::CLOSED;
                    Serial.println("[BARRIER] EXIT CLOSED");
                }
            }
        }
    }
}

BarrierState BarrierManager::getEntryState() const {
    return entryState;
}

const char* BarrierManager::getEntryStateStr() const {
    switch (entryState) {
        case BarrierState::OPEN:    return "OPEN";
        case BarrierState::OPENING: return "OPENING";
        case BarrierState::CLOSING: return "CLOSING";
        case BarrierState::CLOSED:
        default:                    return "CLOSED";
    }
}

BarrierState BarrierManager::getExitState() const {
    return exitState;
}

const char* BarrierManager::getExitStateStr() const {
    switch (exitState) {
        case BarrierState::OPEN:    return "OPEN";
        case BarrierState::OPENING: return "OPENING";
        case BarrierState::CLOSING: return "CLOSING";
        case BarrierState::CLOSED:
        default:                    return "CLOSED";
    }
}

void BarrierManager::printDebugStatus() const {
    Serial.println("\n--- [HARDWARE TEST] BARRIERS / SERVOS ---");
    Serial.printf("Entry Barrier: State = %s | Angle = %d | Target = %d (Open=%d, Closed=%d)\n",
                  getEntryStateStr(), currentEntryAngle, targetEntryAngle, Config::ENTRY_SERVO_OPEN, Config::ENTRY_SERVO_CLOSED);
    Serial.printf("Exit Barrier : State = %s | Angle = %d | Target = %d (Open=%d, Closed=%d)\n",
                  getExitStateStr(), currentExitAngle, targetExitAngle, Config::EXIT_SERVO_OPEN, Config::EXIT_SERVO_CLOSED);
    Serial.println("------------------------------------------");
}
