#ifndef NEOPIXEL_MANAGER_H
#define NEOPIXEL_MANAGER_H

#include <Arduino.h>
#include <Adafruit_NeoPixel.h>
#include "../config/pins.h"
#include "../config/config.h"

enum class NeoState {
    STARTING,        // WHITE
    CONNECTING_WIFI, // PURPLE
    NORMAL,          // GREEN
    WARNING_GAS,     // RED Blinking
    EMERGENCY,       // RED Fast Blinking / Solid
    ERROR            // RED
};

class NeoPixelManager {
public:
    NeoPixelManager();
    void begin();
    void setState(NeoState newState);
    NeoState getState() const;
    void update();
    void testSequence();

private:
    Adafruit_NeoPixel strip;
    NeoState currentState;
    unsigned long lastBlinkTime;
    bool blinkToggle;

    void setColor(uint8_t r, uint8_t g, uint8_t b);
};

#endif // NEOPIXEL_MANAGER_H
