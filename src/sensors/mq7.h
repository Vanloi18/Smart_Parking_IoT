#ifndef MQ7_H
#define MQ7_H

#include <Arduino.h>
#include "../config/pins.h"
#include "../config/config.h"

enum class GasLevel {
    NORMAL,
    WARNING,
    DANGER
};

class MQ7Sensor {
public:
    MQ7Sensor();
    void begin();
    void update();

    uint16_t getRawADC() const;
    float getVoltageADC() const;
    float getEstimatedAOVoltage() const;
    GasLevel getGasLevel() const;
    const char* getGasLevelStr() const;
    bool isAlarmActive() const;
    void printDebugStatus() const;

private:
    uint16_t currentADC;
    GasLevel currentLevel;
    unsigned long lastReadTime;

    uint16_t readAveragedADC();
};

#endif // MQ7_H
