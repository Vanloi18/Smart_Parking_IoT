#ifndef LCD_MANAGER_H
#define LCD_MANAGER_H

#include <Arduino.h>
#include <Wire.h>
#include <LiquidCrystal_I2C.h>
#include "../config/pins.h"
#include "../config/config.h"
#include "../sensors/mq7.h"

class LCDManager {
public:
    LCDManager();
    void begin();
    void update(uint8_t freeSlots, 
                bool p1, bool p2, bool p3, bool p4,
                const char* entryBarrierStr, 
                const char* exitBarrierStr,
                float temp, float hum,
                GasLevel gasLevel,
                bool wifiConnected);

    void showMessage(const char* line1, const char* line2, const char* line3, const char* line4);
    void lcdPrintLine(uint8_t row, const char* text);
    void testDisplay();

private:
    LiquidCrystal_I2C lcd;
    unsigned long lastRefreshTime;
    char buffer[4][21]; // Bộ đệm 4 dòng x 20 ký tự (+1 null terminator)
};

#endif // LCD_MANAGER_H
