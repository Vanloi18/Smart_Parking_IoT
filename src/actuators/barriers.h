#ifndef BARRIERS_H
#define BARRIERS_H

#include <Arduino.h>
#include <ESP32Servo.h>
#include "../config/pins.h"
#include "../config/config.h"

enum class BarrierState {
    CLOSED,
    OPENING,
    OPEN,
    CLOSING
};

class BarrierManager {
public:
    BarrierManager();
    void begin();
    void update(bool entryVehiclePresent, bool exitVehiclePresent);

    // Điều khiển barrier cổng vào
    void openEntry();
    void closeEntry();
    BarrierState getEntryState() const;
    const char* getEntryStateStr() const;

    // Điều khiển barrier cổng ra
    void openExit();
    void closeExit();
    BarrierState getExitState() const;
    const char* getExitStateStr() const;

    // Điều khiển khẩn cấp mở toàn bộ
    void forceOpenAll();
    void forceCloseAll();

    // In trạng thái phục vụ Hardware Test Mode
    void printDebugStatus() const;

private:
    Servo servoEntry;
    Servo servoExit;

    int currentEntryAngle;
    int targetEntryAngle;
    BarrierState entryState;
    unsigned long lastEntryStepTime;
    unsigned long entryOpenStartTime;
    bool entryVehiclePassedWatcher;

    int currentExitAngle;
    int targetExitAngle;
    BarrierState exitState;
    unsigned long lastExitStepTime;
    unsigned long exitOpenStartTime;
    bool exitVehiclePassedWatcher;

    void updateServoMovement();
};

#endif // BARRIERS_H
