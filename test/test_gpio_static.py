#!/usr/bin/env python3
"""
===============================================================================
STATIC GPIO & FIRMWARE SAFETY VERIFICATION SCRIPT
SMART PARKING IoT - ESP32 DEVKIT V1 (30-PIN)
===============================================================================
Kiểm tra tĩnh tự động:
1. Không có chân GPIO nào bị trùng lặp (No duplicate GPIO).
2. Không gán Output cho các chân thuần Input (GPIO 34, 35, 36, 39).
3. Không gán Button (cần PULLUP) vào các chân Input-only (không có pullup nội vi).
4. Không gán ngoại vi vào các chân Boot Strapping nhạy cảm (GPIO 0, 2, 12).
5. Không xung đột bus truyền thông I2C (GPIO 21, 22) và SPI (GPIO 18, 19, 23).
6. Cảm biến Analog MQ-7 phải thuộc ADC1 (GPIO 32-39) để không xung đột WiFi.
===============================================================================
"""

import sys

# Định nghĩa bảng GPIO mới đã triển khai trong src/config/pins.h
GPIO_MAP = {
    # Cảm biến IR
    "IR_P1": {"pin": 13, "mode": "INPUT_PULLUP", "type": "DIGITAL_IN", "desc": "Slot 1 Sensor"},
    "IR_P2": {"pin": 14, "mode": "INPUT_PULLUP", "type": "DIGITAL_IN", "desc": "Slot 2 Sensor"},
    "IR_P3": {"pin": 16, "mode": "INPUT_PULLUP", "type": "DIGITAL_IN", "desc": "Slot 3 Sensor"},
    "IR_P4": {"pin": 35, "mode": "INPUT",        "type": "DIGITAL_IN", "desc": "Slot 4 Sensor"},
    "IR_ENTRY": {"pin": 39, "mode": "INPUT",     "type": "DIGITAL_IN", "desc": "Entry Gate Sensor"},
    "IR_EXIT":  {"pin": 34, "mode": "INPUT",     "type": "DIGITAL_IN", "desc": "Exit Gate Sensor"},

    # Cảm biến môi trường
    "MQ7_AO":   {"pin": 36, "mode": "ANALOG_IN", "type": "ADC1",       "desc": "CO Gas Sensor Analog"},
    "DHT_PIN":  {"pin": 33, "mode": "BIDIR",     "type": "1-WIRE",     "desc": "DHT11 Climate Sensor"},

    # Cơ cấu chấp hành
    "SERVO_ENTRY": {"pin": 25, "mode": "OUTPUT", "type": "PWM",        "desc": "Entry Barrier Servo"},
    "SERVO_EXIT":  {"pin": 26, "mode": "OUTPUT", "type": "PWM",        "desc": "Exit Barrier Servo"},
    "NEOPIXEL":    {"pin": 27, "mode": "OUTPUT", "type": "DIGITAL_OUT","desc": "RGB Status LED DIN"},
    "BUZZER":      {"pin": 32, "mode": "OUTPUT", "type": "DIGITAL_OUT","desc": "Alarm Buzzer Transistor"},

    # Nút bấm thủ công
    "BUTTON_ENTRY": {"pin": 4,  "mode": "INPUT_PULLUP", "type": "DIGITAL_IN", "desc": "Manual Entry Button"},
    "BUTTON_EXIT":  {"pin": 17, "mode": "INPUT_PULLUP", "type": "DIGITAL_IN", "desc": "Manual Exit Button"},

    # Giao tiếp I2C
    "I2C_SDA": {"pin": 21, "mode": "BIDIR",  "type": "I2C", "desc": "LCD2004 I2C Data"},
    "I2C_SCL": {"pin": 22, "mode": "OUTPUT", "type": "I2C", "desc": "LCD2004 I2C Clock"},

    # Giao tiếp SPI chung & Chip Select riêng
    "SPI_SCK":     {"pin": 18, "mode": "OUTPUT", "type": "SPI", "desc": "VSPI Clock (Shared)"},
    "SPI_MISO":    {"pin": 19, "mode": "INPUT",  "type": "SPI", "desc": "VSPI MISO (Shared)"},
    "SPI_MOSI":    {"pin": 23, "mode": "OUTPUT", "type": "SPI", "desc": "VSPI MOSI (Shared)"},
    "RFID_IN_SS":  {"pin": 5,  "mode": "OUTPUT", "type": "SPI_CS", "desc": "RC522 Entry SS (Idle HIGH)"},
    "RFID_OUT_SS": {"pin": 15, "mode": "OUTPUT", "type": "SPI_CS", "desc": "RC522 Exit SS (Idle HIGH)"},
}

INPUT_ONLY_PINS = {34, 35, 36, 39}
BOOT_SENSITIVE_PINS = {0, 2, 12}
ADC1_PINS = {32, 33, 34, 35, 36, 37, 38, 39}
ADC2_PINS = {0, 2, 4, 12, 13, 14, 15, 25, 26, 27}

def run_checks():
    print("=" * 70)
    print("STARTING STATIC GPIO & FIRMWARE SAFETY CHECKS")
    print("=" * 70)

    errors = []
    warnings = []

    # Check 1: Duplicate GPIO
    used_pins = {}
    for name, info in GPIO_MAP.items():
        pin = info["pin"]
        if pin in used_pins:
            errors.append(f"DUPLICATE GPIO CONFLICT: Pin GPIO{pin} is assigned to both '{used_pins[pin]}' and '{name}'!")
        else:
            used_pins[pin] = name

    print(f"[CHECK 1] Duplicate GPIO Check: {len(used_pins)} unique pins allocated -> "
          f"{'PASS' if not errors else 'FAIL'}")

    # Check 2: Output on Input-Only Pins
    for name, info in GPIO_MAP.items():
        pin = info["pin"]
        mode = info["mode"]
        if pin in INPUT_ONLY_PINS and mode in ("OUTPUT", "BIDIR", "PWM"):
            errors.append(f"INVALID PIN MODE: GPIO{pin} ('{name}') is INPUT-ONLY in silicon, cannot be set as {mode}!")

    print(f"[CHECK 2] Input-Only Output Capability Check: "
          f"{'PASS' if not any('INPUT-ONLY' in e for e in errors) else 'FAIL'}")

    # Check 3: Buttons on Input-Only Pins (Lack of internal pull-up)
    for name, info in GPIO_MAP.items():
        pin = info["pin"]
        mode = info["mode"]
        if "BUTTON" in name and pin in INPUT_ONLY_PINS:
            errors.append(f"FLOATING BUTTON RISK: GPIO{pin} ('{name}') has NO internal pull-up resistor in hardware!")

    print(f"[CHECK 3] Button Internal Pull-up Check: "
          f"{'PASS' if not any('FLOATING BUTTON' in e for e in errors) else 'FAIL'}")

    # Check 4: Boot Sensitive / Strapping Pins (GPIO 0, 2, 12)
    for name, info in GPIO_MAP.items():
        pin = info["pin"]
        if pin in BOOT_SENSITIVE_PINS:
            errors.append(f"DANGEROUS BOOT PIN ASSIGNED: GPIO{pin} ('{name}') is a critical strapping pin (Boot/MTDI/LED)!")

    print(f"[CHECK 4] Critical Boot Strapping Pin Isolation: "
          f"{'PASS' if not any('BOOT PIN' in e for e in errors) else 'FAIL'}")

    # Check 5: ADC1 vs ADC2 with WiFi
    mq7_pin = GPIO_MAP["MQ7_AO"]["pin"]
    if mq7_pin not in ADC1_PINS:
        errors.append(f"ADC WIFI CONFLICT: MQ-7 on GPIO{mq7_pin} is on ADC2, which is disabled when WiFi is active!")
    else:
        print(f"[CHECK 5] MQ-7 ADC1 vs WiFi Isolation: PASS (GPIO{mq7_pin} is on ADC1_CH0)")

    # Check 6: SPI bus integrity
    spi_pins = {GPIO_MAP["SPI_SCK"]["pin"], GPIO_MAP["SPI_MISO"]["pin"], GPIO_MAP["SPI_MOSI"]["pin"]}
    if len(spi_pins) != 3:
        errors.append("SPI BUS CONFLICT: SCK, MISO, MOSI must be distinct pins!")
    else:
        print("[CHECK 6] Hardware VSPI Bus Integrity: PASS (SCK=18, MISO=19, MOSI=23)")

    # Check 7: I2C bus integrity
    i2c_pins = {GPIO_MAP["I2C_SDA"]["pin"], GPIO_MAP["I2C_SCL"]["pin"]}
    if len(i2c_pins) != 2:
        errors.append("I2C BUS CONFLICT: SDA and SCL must be distinct pins!")
    else:
        print("[CHECK 7] Hardware I2C Bus Integrity: PASS (SDA=21, SCL=22)")

    # Summary
    print("=" * 70)
    if errors:
        print("VERIFICATION FAILED! Found errors:")
        for err in errors:
            print(f"  [!] {err}")
        return False
    else:
        print("ALL STATIC GPIO & SAFETY VERIFICATIONS PASSED SUCCESSFULLY (100% CLEAN)")
        print(f"Total functional GPIOs utilized: {len(GPIO_MAP)}")
        print("Isolated boot pins: GPIO 0 (Boot), GPIO 2 (LED/Strap), GPIO 12 (MTDI/Flash Voltage)")
        print("Dedicated Serial pins: GPIO 1 (TX0), GPIO 3 (RX0)")
        print("=" * 70)
        return True

if __name__ == "__main__":
    success = run_checks()
    sys.exit(0 if success else 1)
