#ifndef PARKING_SENSORS_H
#define PARKING_SENSORS_H

#include <Arduino.h>
#include "../config/pins.h"
#include "../config/config.h"

class ParkingSensors {
public:
    ParkingSensors();
    void begin();
    void update();

    // Trạng thái ô đỗ (1-indexed: 1, 2, 3, 4)
    bool isSlotOccupied(uint8_t slot) const; // true: có xe, false: trống
    uint8_t getAvailableSlotsCount() const;
    uint8_t getOccupiedSlotsCount() const;

    // Trạng thái cổng vào và ra
    bool isEntryVehicleDetected() const;
    bool isExitVehicleDetected() const;

    // Kiểm tra có thay đổi trạng thái ô đỗ trong chu kỳ vừa qua không
    bool hasSlotsChanged();

    // In trạng thái chi tiết 6 cảm biến phục vụ Hardware Test Mode
    void printDebugStatus() const;

private:
    struct SlotSensor {
        uint8_t pin;
        bool rawState;
        bool debouncedState; // true: có xe (LOW), false: trống (HIGH)
        unsigned long lastDebounceTime;
    };

    struct GateSensor {
        uint8_t pin;
        bool rawState;
        bool debouncedState;
        unsigned long lastDebounceTime;
    };

    SlotSensor slots[Config::TOTAL_SLOTS];
    GateSensor entrySensor;
    GateSensor exitSensor;

    bool slotsChangedFlag;
};

#endif // PARKING_SENSORS_H
