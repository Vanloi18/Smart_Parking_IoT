#ifndef BUZZER_H
#define BUZZER_H

#include <Arduino.h>
#include "../config/pins.h"
#include "../config/config.h"

enum class BuzzerMode {
    IDLE,
    SINGLE_BEEP,
    DOUBLE_BEEP,
    WARNING_GAS,
    ALARM_EMERGENCY
};

class BuzzerManager {
public:
    BuzzerManager();
    void begin();
    void update();

    void beepSuccess();
    void beepError();
    void setWarningGas(bool active);
    void setAlarmEmergency(bool active);
    void testPattern();

private:
    BuzzerMode currentMode;
    unsigned long stateStartTime;
    uint8_t step;
    bool gasWarningActive;
    bool emergencyActive;

    void setOutput(bool state);
};

#endif // BUZZER_H
