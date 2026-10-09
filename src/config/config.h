#ifndef CONFIG_H
#define CONFIG_H

#include <Arduino.h>
#include "backend_config.h"

/**
 * ============================================================================
 * SMART PARKING IoT - SYSTEM CONFIGURATION
 * ============================================================================
 * Toàn bộ thông số cấu hình hệ thống được tập trung tại đây.
 * Không dùng magic numbers trong mã nguồn.
 * ============================================================================
 */

namespace Config {
    // --- THÔNG SỐ BÃI XE ---
    constexpr uint8_t TOTAL_SLOTS = 4;

    // --- CẤU HÌNH SERVO BARRIER ---
    // Cổng vào: Bình thường ĐÓNG (0°), Cho phép vào -> MỞ (90°)
    constexpr int ENTRY_SERVO_CLOSED = 0;
    constexpr int ENTRY_SERVO_OPEN   = 90;

    // Cổng ra: Đảo riêng chiều vật lý (Lắp ngược hướng so với cổng vào)
    // Bình thường ĐÓNG (90° dựng đứng), Cho phép ra -> MỞ (0° hạ xuống bên phải)
    constexpr int EXIT_SERVO_CLOSED  = 90;
    constexpr int EXIT_SERVO_OPEN    = 0;

    // Tốc độ mở nhanh: 5ms/độ -> 90° trong ~0.45 giây (300-500ms)
    constexpr unsigned long SERVO_OPEN_DELAY_MS  = 5;

    // Tốc độ đóng từ từ: 20ms/độ -> 90° trong ~1.80 giây (1.5-2.0s)
    constexpr unsigned long SERVO_CLOSE_DELAY_MS = 20;

    // Thời gian tối đa tự động đóng Barrier sau khi mở nếu xe không đi qua (ms)
    constexpr unsigned long BARRIER_AUTO_CLOSE_TIMEOUT_MS = 5000;

    // --- CẤU HÌNH TÍNH PHÍ ĐỖ XE DEMO (BILLING DEMO: 5 GIÂY = 1 BLOCK 5.000 VNĐ) ---
    constexpr unsigned long PARKING_BILLING_INTERVAL_MS = 5000; // Mỗi 5 giây là 1 đơn vị tính phí
    constexpr uint32_t BILLING_RATE_PER_INTERVAL       = 5000; // 5.000 VNĐ mỗi 5 giây

    // --- CẤU HÌNH THỜI GIAN CHỜ AN TOÀN FSM (TIMEOUTS) ---
    constexpr unsigned long ENTRY_RFID_TIMEOUT_MS       = 15000; // Quá 15s có xe ở cổng vào không quẹt thẻ -> Timeout
    constexpr unsigned long EXIT_RFID_TIMEOUT_MS        = 15000; // Quá 15s có xe ở cổng ra không quẹt thẻ -> Timeout
    constexpr unsigned long PAYMENT_CONFIRM_TIMEOUT_MS  = 20000; // Quá 20s hiện phí không bấm nút Exit -> Hủy phiên
    constexpr unsigned long SLOT_ASSIGN_TIMEOUT_MS      = 30000; // Quá 30s sau khi mở cổng không vào slot đỗ
    constexpr unsigned long STATUS_MSG_HOLD_MS          = 2500;  // Thời gian lưu thông báo tạm thời trên LCD

    // --- CẤU HÌNH BỘ LỌC DEBOUNCE (CHỐNG NHIỄU CẢM BIẾN QUANG HỌC) ---
    // Cảm biến vị trí đỗ: Cần tín hiệu ổn định 1500ms mới xác nhận đổi trạng thái
    constexpr unsigned long SLOT_DEBOUNCE_MS = 1500;

    // Cảm biến cổng vào/ra: Cần tín hiệu ổn định 200ms để phát hiện phương tiện
    constexpr unsigned long GATE_DEBOUNCE_MS = 200;

    // Nút bấm: Debounce ổn định 60ms (50-100ms) chống bouncing đa nhấn
    constexpr unsigned long BUTTON_DEBOUNCE_MS = 60;

    // --- CẤU HÌNH CẢM BIẾN KHÍ MQ-7 (ADC1 12-bit: 0 - 4095) ---
    // Mạch cầu phân áp: R1 = 10k (từ AO vào GPIO36), R2 = 10k (từ GPIO36 xuống GND)
    // Tỉ lệ chia áp: 2:1 (Điện áp vào GPIO36 = V_AO / 2; V_AO = V_GPIO36 * 2.0)
    constexpr float VOLTAGE_DIVIDER_RATIO = 2.0f;
    constexpr uint16_t GAS_THRESHOLD_NORMAL  = 1200; // Dưới mức này là bình thường
    constexpr uint16_t GAS_THRESHOLD_WARNING = 2200; // Trên mức này là cảnh báo
    constexpr uint16_t GAS_THRESHOLD_DANGER  = 3000; // Trên mức này là nguy hiểm

    // Số mẫu lấy trung bình động cho ADC để giảm nhiễu
    constexpr uint8_t MQ7_SAMPLE_COUNT = 8;

    // --- CẤU HÌNH CẢM BIẾN DHT11 ---
    constexpr unsigned long DHT_READ_INTERVAL_MS = 2000; // Tối thiểu 2 giây giữa các lần đọc

    // --- CẤU HÌNH RFID RC522 ---
    constexpr unsigned long RFID_SCAN_INTERVAL_MS = 100; // Quét mỗi 100ms
    constexpr unsigned long RFID_CARD_COOLDOWN_MS = 2500; // Thời gian chờ trước khi đọc lại cùng 1 thẻ

    // --- CẤU HÌNH MÀN HÌNH LCD2004 ---
    constexpr uint8_t LCD_I2C_ADDR = 0x27; // Địa chỉ I2C thông dụng (nếu chip PCF8574A thì đổi thành 0x3F)
    constexpr uint8_t LCD_COLS     = 20;
    constexpr uint8_t LCD_ROWS     = 4;
    constexpr unsigned long LCD_REFRESH_INTERVAL_MS = 500;

    // --- CẤU HÌNH NEOPIXEL RGB ---
    constexpr uint8_t NEOPIXEL_COUNT = 1;
    // Đặt độ sáng 35 (thay vì 120-255) để chống sụt áp nguồn (Brownout Prevention)
    constexpr uint8_t NEOPIXEL_BRIGHTNESS = 35; // 0 - 255
    constexpr unsigned long NEOPIXEL_BLINK_INTERVAL_MS = 300; // Nhấp nháy cảnh báo khí

    // --- CẤU HÌNH BUZZER ---
    constexpr unsigned long BEEP_SHORT_MS    = 100;
    constexpr unsigned long BEEP_LONG_MS     = 600;
    constexpr unsigned long BEEP_INTERVAL_MS = 150;

    // ========================================================================
    // WIFI & SERVER CONFIGURATION - KHU VỰC CẤU HÌNH MẠNG
    // ========================================================================
    // SỬA CÁC GIÁ TRỊ DƯỚI ĐÂY THEO MẠNG VÀ MÁY TÍNH CỦA BẠN:
    // 1. WiFi: điền wifi_ssid/wifi_password trong backend_config.json ở gốc.
    // 2. Backend host/port: sửa backend_config.json ở gốc, chạy sync_backend_config.py.
    //                                (Dùng lệnh 'ipconfig' trên Windows để xem IP LAN,
    //                                 KHÔNG DÙNG localhost hay 127.0.0.1 trên ESP32)
    // ========================================================================
    inline const char* WIFI_SSID     = BackendConfig::WIFI_SSID; // Sinh từ backend_config.json; không sửa tại đây.
    inline const char* WIFI_PASSWORD = BackendConfig::WIFI_PASSWORD; // Sinh từ backend_config.json; không sửa tại đây.

    // Dùng cấu hình được sinh từ một nguồn chung, không sửa IP tại đây.
    inline const char* SERVER_HOST   = BackendConfig::HOST;
    constexpr uint16_t SERVER_PORT   = BackendConfig::PORT;

    constexpr unsigned long WIFI_RECONNECT_INTERVAL_MS = 5000; // Thử kết nối lại mỗi 5s non-blocking
    constexpr unsigned long TELEMETRY_INTERVAL_MS      = 3000; // Gửi bản tin Heartbeat mỗi 3 giây

    // Danh mục Endpoint REST API
    inline const char* API_HEARTBEAT       = "/api/telemetry/heartbeat";
    inline const char* API_PARKING_ENTRY   = "/api/parking/entry";
    inline const char* API_PARKING_EXIT    = "/api/parking/exit";
    inline const char* API_BARRIER_CONTROL  = "/api/barrier/control";
    inline const char* API_BARRIER_COMMANDS = "/api/barrier/commands";
    inline const char* API_BARRIER_ACK      = "/api/barrier/ack";
    inline const char* API_STATUS           = "/api/parking/status";
}

#endif // CONFIG_H
