#include "lcd_manager.h"

LCDManager::LCDManager()
    : lcd(Config::LCD_I2C_ADDR, Config::LCD_COLS, Config::LCD_ROWS),
      lastRefreshTime(0) {
    for (int i = 0; i < 4; i++) {
        buffer[i][0] = '\0';
    }
}

void LCDManager::begin() {
    Wire.begin(Pins::I2C_SDA, Pins::I2C_SCL);
    lcd.init();
    lcd.backlight();
    lcd.clear();
    for (int row = 0; row < 4; ++row) {
        memset(buffer[row], 0, sizeof(buffer[row]));
    }

    // Màn hình kiểm tra phần cứng chuẩn ASCII theo yêu cầu
    showMessage("SMART PARKING", "LCD2004 TEST", "I2C: 0x27", "SYSTEM OK");
    Serial.printf("[LCD] Initialized I2C address 0x%02X\n", Config::LCD_I2C_ADDR);
    Serial.println("[LCD] ASCII mode enabled");
}

void LCDManager::testDisplay() {
    Serial.println("[LCD] Testing 2004 LCD display (4 rows)...");
    showMessage("SMART PARKING", "LCD2004 TEST", "I2C: 0x27", "SYSTEM OK");
    Serial.println("[LCD] Test pattern displayed.");
}

void LCDManager::lcdPrintLine(uint8_t row, const char* text) {
    if (row >= 4) return;

    char sanitized[21];
    uint8_t idx = 0;

    // LCD2004/HD44780 is not UTF-8 aware. Keep printable ASCII only.
    if (text != nullptr) {
        while (*text && idx < 20) {
            unsigned char c = (unsigned char)*text++;
            if (c >= 32 && c <= 126) {
                sanitized[idx++] = (char)c;
            }
        }
    }

    // Always overwrite all 20 columns to remove stale characters.
    while (idx < 20) {
        sanitized[idx++] = ' ';
    }
    sanitized[20] = '\0';

    // Chỉ ghi xuống LCD nếu dòng có sự thay đổi (chống nháy màn hình)
    if (strcmp(buffer[row], sanitized) != 0) {
        strcpy(buffer[row], sanitized);
        lcd.setCursor(0, row);
        lcd.print(sanitized);
    }
}

void LCDManager::showMessage(const char* line1, const char* line2, const char* line3, const char* line4) {
    lcdPrintLine(0, line1);
    lcdPrintLine(1, line2);
    lcdPrintLine(2, line3);
    lcdPrintLine(3, line4);
}

void LCDManager::update(uint8_t freeSlots, 
                        bool p1, bool p2, bool p3, bool p4,
                        const char* entryBarrierStr, 
                        const char* exitBarrierStr,
                        float temp, float hum,
                        GasLevel gasLevel,
                        bool wifiConnected) {
    unsigned long now = millis();
    if (now - lastRefreshTime < Config::LCD_REFRESH_INTERVAL_MS) {
        return;
    }
    lastRefreshTime = now;

    // --- DÒNG 0: Tiêu đề + Trạng thái WiFi ---
    char line0[21];
    snprintf(line0, sizeof(line0), "PARKING [%s]", wifiConnected ? "WIFI:OK" : "WIFI:--");
    lcdPrintLine(0, line0);

    // --- DÒNG 1: Chỗ trống + Trạng thái từng ô (X: có xe, _: trống) ---
    char line1[21];
    snprintf(line1, sizeof(line1), "FREE:%d/4 [%c %c %c %c]", 
             freeSlots,
             p1 ? 'X' : '_',
             p2 ? 'X' : '_',
             p3 ? 'X' : '_',
             p4 ? 'X' : '_');
    lcdPrintLine(1, line1);

    // --- DÒNG 2: Trạng thái Barrier Vào / Ra ---
    char line2[21];
    snprintf(line2, sizeof(line2), "IN:%-4s | OUT:%-4s", entryBarrierStr, exitBarrierStr);
    lcdPrintLine(2, line2);

    // --- DÒNG 3: Môi trường (Nhiệt, Ẩm) & Cảnh báo khí ---
    char line3[21];
    if (gasLevel == GasLevel::DANGER) {
        snprintf(line3, sizeof(line3), "!GAS DANGER! T:%.0fC", temp);
    } else if (gasLevel == GasLevel::WARNING) {
        snprintf(line3, sizeof(line3), "!GAS WARN!   T:%.0fC", temp);
    } else {
        snprintf(line3, sizeof(line3), "T:%.0fC H:%.0f%% G:OK", temp, hum);
    }
    lcdPrintLine(3, line3);
}
