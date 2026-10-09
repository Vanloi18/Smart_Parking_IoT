#ifndef PINS_H
#define PINS_H

#include <Arduino.h>

/**
 * ============================================================================
 * SMART PARKING IoT - ESP32 DevKit V1 GPIO MAPPING
 * ============================================================================
 * Bản ánh xạ GPIO chuẩn hóa, an toàn tuyệt đối cho ESP32 DevKit V1 (30-pin).
 * 
 * NGUYÊN TẮC THIẾT KẾ:
 * 1. KHÔNG sử dụng các chân Boot Strapping nhạy cảm (GPIO 0, GPIO 2, GPIO 12).
 * 2. Tận dụng tối đa các chân INPUT-ONLY (GPIO 34, 35, 36, 39) cho Sensor không cần trở kéo nội vi.
 * 3. Tuyệt đối KHÔNG dùng chân INPUT-ONLY cho Button hoặc Output.
 * 4. Chân Button (GPIO 4, 17) có hỗ trợ điện trở kéo lên nội vi INPUT_PULLUP.
 * 5. Cảm biến khí MQ-7 đặt tại GPIO 36 thuộc bộ ADC1 (hoạt động tốt cùng WiFi).
 * 6. Hai module RC522 dùng chung phần cứng SPI (GPIO 18, 19, 23); Chip Select riêng tại GPIO 5 & 15.
 * 7. Hai module RC522 chân RST nối chung nguồn 3.3V hoặc EN của ESP32 (Software Reset qua SPI).
 * ============================================================================
 */

namespace Pins {
    // --- CẢM BIẾN HỒNG NGOẠI Ô ĐỖ (PARKING SLOTS IR LM393) ---
    // Đầu ra số OUT tích cực mức LOW khi có xe đỗ, HIGH khi ô trống
    constexpr uint8_t IR_P1 = 13;      // Slot 1 (Digital Input, RTC)
    constexpr uint8_t IR_P2 = 14;      // Slot 2 (Digital Input, RTC)
    constexpr uint8_t IR_P3 = 16;      // Slot 3 (Digital Input, UART2 RX pin tự do)
    constexpr uint8_t IR_P4 = 35;      // Slot 4 (Input-only, module có trở kéo sẵn)

    // --- CẢM BIẾN HỒNG NGOẠI CỔNG (GATE BARRIER IR LM393) ---
    constexpr uint8_t IR_ENTRY = 39;   // IR Cổng Vào (SENSOR_VN, Input-only, module có trở kéo sẵn)
    constexpr uint8_t IR_EXIT  = 34;   // IR Cổng Ra (Input-only, module có trở kéo sẵn)

    // --- CẢM BIẾN MÔI TRƯỜNG & KHÍ ĐỘC ---
    // MQ-7 AO: Bắt buộc dùng ADC1 để không bị xung đột khi bật Wi-Fi.
    // LƯU Ý PHẦN CỨNG: Cần cầu phân áp (ví dụ 10k/20k) nếu điện áp AO vượt quá 3.3V!
    constexpr uint8_t MQ7_AO = 36;     // SENSOR_VP, ADC1_CH0 (Analog Input)
    constexpr uint8_t DHT_PIN = 33;    // DHT11 1-Wire Data (Bidirectional I/O)

    // --- CƠ CẤU CHẤP HÀNH (ACTUATORS) ---
    // Động cơ Servo Barrier SG90 (Cấp nguồn 5V từ mạch XL4005, GND chung)
    constexpr uint8_t SERVO_ENTRY = 25; // Servo Cổng Vào (Output PWM LEDC)
    constexpr uint8_t SERVO_EXIT  = 26; // Servo Cổng Ra (Output PWM LEDC)

    // Thiết bị hiển thị & cảnh báo
    constexpr uint8_t NEOPIXEL = 27;    // Đèn LED RGB WS2812B DIN (Output)
    constexpr uint8_t BUZZER   = 32;    // Còi chíp Buzzer qua NPN Transistor (Output)

    // --- NÚT NHẤN ĐIỀU KHIỂN (BUTTONS - INPUT_PULLUP) ---
    // Bình thường HIGH, khi nhấn kéo xuống GND (LOW). Có debounce.
    constexpr uint8_t BUTTON_ENTRY = 4;  // Nút mở cổng vào thủ công
    constexpr uint8_t BUTTON_EXIT  = 17; // Nút mở cổng ra thủ công (UART2 TX pin tự do)

    // --- GIAO TIẾP I2C (MÀN HÌNH LCD2004) ---
    constexpr uint8_t I2C_SDA = 21;     // I2C Data LCD2004
    constexpr uint8_t I2C_SCL = 22;     // I2C Clock LCD2004

    // --- GIAO TIẾP SPI DÙNG CHUNG (2x MODULE RFID RC522) ---
    constexpr uint8_t SPI_SCK  = 18;    // VSPI Clock (Nối chung cả 2 RC522)
    constexpr uint8_t SPI_MISO = 19;    // VSPI MISO  (Nối chung cả 2 RC522)
    constexpr uint8_t SPI_MOSI = 23;    // VSPI MOSI  (Nối chung cả 2 RC522)

    // Chip Select (SS/SDA) riêng cho từng module RC522
    // Cả hai chân GPIO 5 và 15 đều có pull-up nội vi lúc boot -> Idle HIGH an toàn cho SPI CS!
    constexpr uint8_t RFID_IN_SS  = 5;  // RC522 Cổng Vào SS (Active LOW)
    constexpr uint8_t RFID_OUT_SS = 15; // RC522 Cổng Ra SS (Active LOW)

    // Chân Reset RC522:
    // Khuyến nghị đấu chân RST của cả 2 module RC522 vào 3.3V hoặc chân EN của ESP32.
    // Khi đặt là -1 (255), thư viện MFRC522 sử dụng Software Reset qua SPI.
    constexpr int8_t RFID_RST_PIN = -1; // -1: Soft-reset qua SPI, phần cứng nối 3.3V/EN

    // --- CÁC CHÂN ĐƯỢC BẢO VỆ TUYỆT ĐỐI (KHÔNG SỬ DỤNG CHO NGOẠI VI) ---
    // GPIO 0  : Chân Boot/Flashing Mode -> Không đấu để tránh treo bootloader
    // GPIO 2  : Strapping Pin & On-board LED -> Không đấu để tránh lỗi nạp
    // GPIO 12 : MTDI Strapping Pin -> Không đấu để tránh lỗi chọn sai áp Flash 1.8V
    // GPIO 1  : Serial TX0 -> Dành riêng in Serial Log (115200 baud)
    // GPIO 3  : Serial RX0 -> Dành riêng nhận Serial Debug
}

#endif // PINS_H
