#include "parking_sensors.h"

ParkingSensors::ParkingSensors() : slotsChangedFlag(false) {
    // Khởi tạo danh sách 4 chân cảm biến slot
    slots[0].pin = Pins::IR_P1;
    slots[1].pin = Pins::IR_P2;
    slots[2].pin = Pins::IR_P3;
    slots[3].pin = Pins::IR_P4;

    for (int i = 0; i < Config::TOTAL_SLOTS; i++) {
        slots[i].rawState = true;        // Mặc định ban đầu HIGH (trống)
        slots[i].debouncedState = false;  // false = không có xe
        slots[i].lastDebounceTime = 0;
    }

    entrySensor.pin = Pins::IR_ENTRY;
    entrySensor.rawState = true;
    entrySensor.debouncedState = false;
    entrySensor.lastDebounceTime = 0;

    exitSensor.pin = Pins::IR_EXIT;
    exitSensor.rawState = true;
    exitSensor.debouncedState = false;
    exitSensor.lastDebounceTime = 0;
}

void ParkingSensors::begin() {
    // Với các chân thông thường: dùng INPUT_PULLUP
    // Với các chân Input-Only (GPIO 34, 35, 39): dùng INPUT vì module LM393 đã có pull-up ngoài
    pinMode(Pins::IR_P1, INPUT_PULLUP);
    pinMode(Pins::IR_P2, INPUT_PULLUP);
    pinMode(Pins::IR_P3, INPUT_PULLUP);
    pinMode(Pins::IR_P4, INPUT); // GPIO35: Input-only pin

    pinMode(Pins::IR_ENTRY, INPUT); // GPIO39: Input-only pin
    pinMode(Pins::IR_EXIT, INPUT);  // GPIO34: Input-only pin

    // Đọc khởi tạo ban đầu
    unsigned long now = millis();
    for (int i = 0; i < Config::TOTAL_SLOTS; i++) {
        bool reading = digitalRead(slots[i].pin);
        slots[i].rawState = reading;
        // LM393: LOW = có vật cản (xe đỗ), HIGH = không có vật cản
        slots[i].debouncedState = (reading == LOW);
        slots[i].lastDebounceTime = now;
    }

    entrySensor.rawState = digitalRead(entrySensor.pin);
    entrySensor.debouncedState = (entrySensor.rawState == LOW);
    entrySensor.lastDebounceTime = now;

    exitSensor.rawState = digitalRead(exitSensor.pin);
    exitSensor.debouncedState = (exitSensor.rawState == LOW);
    exitSensor.lastDebounceTime = now;

    Serial.println("[GPIO] 6x IR Sensors initialized (P1-P4, Entry, Exit)");
}

void ParkingSensors::update() {
    unsigned long now = millis();

    // 1. Quét và lọc Debounce cho 4 cảm biến ô đỗ (SLOT_DEBOUNCE_MS = 1500ms)
    for (int i = 0; i < Config::TOTAL_SLOTS; i++) {
        bool currentReading = digitalRead(slots[i].pin);

        // Nếu giá trị thô thay đổi so với lần đọc trước
        if (currentReading != slots[i].rawState) {
            slots[i].rawState = currentReading;
            slots[i].lastDebounceTime = now;
        }

        // Nếu giữ nguyên trạng thái đủ lâu
        if ((now - slots[i].lastDebounceTime) >= Config::SLOT_DEBOUNCE_MS) {
            bool newState = (slots[i].rawState == LOW); // LOW = occupied
            if (newState != slots[i].debouncedState) {
                slots[i].debouncedState = newState;
                slotsChangedFlag = true;
                Serial.printf("[IR] P%d = %s\n", i + 1, newState ? "OCCUPIED" : "FREE");
            }
        }
    }

    // 2. Quét cảm biến Cổng Vào (GATE_DEBOUNCE_MS = 200ms)
    bool entryReading = digitalRead(entrySensor.pin);
    if (entryReading != entrySensor.rawState) {
        entrySensor.rawState = entryReading;
        entrySensor.lastDebounceTime = now;
    }
    if ((now - entrySensor.lastDebounceTime) >= Config::GATE_DEBOUNCE_MS) {
        bool newState = (entrySensor.rawState == LOW);
        if (newState != entrySensor.debouncedState) {
            entrySensor.debouncedState = newState;
            Serial.printf("[IR] Entry IR = %s\n", newState ? "DETECTED" : "CLEAR");
        }
    }

    // 3. Quét cảm biến Cổng Ra (GATE_DEBOUNCE_MS = 200ms)
    bool exitReading = digitalRead(exitSensor.pin);
    if (exitReading != exitSensor.rawState) {
        exitSensor.rawState = exitReading;
        exitSensor.lastDebounceTime = now;
    }
    if ((now - exitSensor.lastDebounceTime) >= Config::GATE_DEBOUNCE_MS) {
        bool newState = (exitSensor.rawState == LOW);
        if (newState != exitSensor.debouncedState) {
            exitSensor.debouncedState = newState;
            Serial.printf("[IR] Exit IR = %s\n", newState ? "DETECTED" : "CLEAR");
        }
    }
}

bool ParkingSensors::isSlotOccupied(uint8_t slot) const {
    if (slot >= 1 && slot <= Config::TOTAL_SLOTS) {
        return slots[slot - 1].debouncedState;
    }
    return false;
}

uint8_t ParkingSensors::getAvailableSlotsCount() const {
    uint8_t count = 0;
    for (int i = 0; i < Config::TOTAL_SLOTS; i++) {
        if (!slots[i].debouncedState) {
            count++;
        }
    }
    return count;
}

uint8_t ParkingSensors::getOccupiedSlotsCount() const {
    return Config::TOTAL_SLOTS - getAvailableSlotsCount();
}

bool ParkingSensors::isEntryVehicleDetected() const {
    return entrySensor.debouncedState;
}

bool ParkingSensors::isExitVehicleDetected() const {
    return exitSensor.debouncedState;
}

bool ParkingSensors::hasSlotsChanged() {
    bool temp = slotsChangedFlag;
    slotsChangedFlag = false;
    return temp;
}

void ParkingSensors::printDebugStatus() const {
    Serial.println("--- [TEST 1] 6x IR SENSORS REALTIME STATUS ---");
    Serial.printf("  Slot P1 (GPIO %2d): Raw=%d -> State=%s\n", slots[0].pin, digitalRead(slots[0].pin), slots[0].debouncedState ? "OCCUPIED" : "FREE");
    Serial.printf("  Slot P2 (GPIO %2d): Raw=%d -> State=%s\n", slots[1].pin, digitalRead(slots[1].pin), slots[1].debouncedState ? "OCCUPIED" : "FREE");
    Serial.printf("  Slot P3 (GPIO %2d): Raw=%d -> State=%s\n", slots[2].pin, digitalRead(slots[2].pin), slots[2].debouncedState ? "OCCUPIED" : "FREE");
    Serial.printf("  Slot P4 (GPIO %2d): Raw=%d -> State=%s\n", slots[3].pin, digitalRead(slots[3].pin), slots[3].debouncedState ? "OCCUPIED" : "FREE");
    Serial.printf("  Gate IN (GPIO %2d): Raw=%d -> State=%s\n", entrySensor.pin, digitalRead(entrySensor.pin), entrySensor.debouncedState ? "DETECTED" : "CLEAR");
    Serial.printf("  Gate OUT(GPIO %2d): Raw=%d -> State=%s\n", exitSensor.pin, digitalRead(exitSensor.pin), exitSensor.debouncedState ? "DETECTED" : "CLEAR");
    Serial.printf("  Summary: Available Free Slots = %d / %d\n", getAvailableSlotsCount(), Config::TOTAL_SLOTS);
    Serial.println("----------------------------------------------");
}
