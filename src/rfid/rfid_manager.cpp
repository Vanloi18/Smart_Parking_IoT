#include "rfid_manager.h"
#include "../actuators/buzzer.h"

RFIDManager::RFIDManager()
    : buzzer(nullptr),
      rfidEntry(Pins::RFID_IN_SS, MFRC522::UNUSED_PIN),
      rfidExit(Pins::RFID_OUT_SS, MFRC522::UNUSED_PIN),
      lastScanTime(0),
      lastEntryReadTime(0),
      lastExitReadTime(0),
      lastEntryUid(""),
      lastExitUid(""),
      pendingEntryCard(false),
      pendingExitCard(false),
      currentEntryUid(""),
      currentExitUid("") {}

void RFIDManager::begin(BuzzerManager* buzzerPtr) {
    buzzer = buzzerPtr;

    // 1. Cấu hình các chân SS (SDA) là OUTPUT và kéo HIGH (Idle state)
    pinMode(Pins::RFID_IN_SS, OUTPUT);
    digitalWrite(Pins::RFID_IN_SS, HIGH);

    pinMode(Pins::RFID_OUT_SS, OUTPUT);
    digitalWrite(Pins::RFID_OUT_SS, HIGH);

    // 2. Khởi động bus Hardware SPI với các chân định nghĩa
    SPI.begin(Pins::SPI_SCK, Pins::SPI_MISO, Pins::SPI_MOSI);
    delay(50); // Chờ ổn định nguồn 3.3V và bộ dao động thạch anh 27.12MHz trên RC522

    // 3. Khởi tạo module RC522 Cổng Vào
    selectEntryModule();
    rfidEntry.PCD_Init();
    delay(10);
    rfidEntry.PCD_SetAntennaGain(MFRC522::RxGain_max);
    byte vIn = rfidEntry.PCD_ReadRegister(MFRC522::VersionReg);
    deselectAll();

    // 4. Khởi tạo module RC522 Cổng Ra
    selectExitModule();
    rfidExit.PCD_Init();
    delay(10);
    rfidExit.PCD_SetAntennaGain(MFRC522::RxGain_max);
    byte vOut = rfidExit.PCD_ReadRegister(MFRC522::VersionReg);
    deselectAll();

    Serial.printf("[RFID] SPI Bus initialized: SCK=%d, MISO=%d, MOSI=%d\n",
                  Pins::SPI_SCK, Pins::SPI_MISO, Pins::SPI_MOSI);
    Serial.printf("[RFID] RC522 Entry SS: GPIO %d (Firmware Version: 0x%02X - %s)\n",
                  Pins::RFID_IN_SS, vIn, (vIn == 0x91 || vIn == 0x92) ? "OK" : "CHECK WIRING/POWER!");
    Serial.printf("[RFID] RC522 Exit SS:  GPIO %d (Firmware Version: 0x%02X - %s)\n",
                  Pins::RFID_OUT_SS, vOut, (vOut == 0x91 || vOut == 0x92) ? "OK" : "CHECK WIRING/POWER!");
}

void RFIDManager::selectEntryModule() {
    digitalWrite(Pins::RFID_OUT_SS, HIGH); // Tắt module OUT
    digitalWrite(Pins::RFID_IN_SS, LOW);   // Kích hoạt module IN
}

void RFIDManager::selectExitModule() {
    digitalWrite(Pins::RFID_IN_SS, HIGH);  // Tắt module IN
    digitalWrite(Pins::RFID_OUT_SS, LOW);  // Kích hoạt module OUT
}

void RFIDManager::deselectAll() {
    digitalWrite(Pins::RFID_IN_SS, HIGH);
    digitalWrite(Pins::RFID_OUT_SS, HIGH);
}

String RFIDManager::dumpUidToString(MFRC522::Uid *uid) {
    String res = "";
    for (byte i = 0; i < uid->size; i++) {
        if (uid->uidByte[i] < 0x10) res += "0";
        res += String(uid->uidByte[i], HEX);
    }
    res.toUpperCase();
    return res;
}

void RFIDManager::update() {
    unsigned long now = millis();

    // Quét non-blocking theo chu kỳ
    if (now - lastScanTime < Config::RFID_SCAN_INTERVAL_MS) {
        return;
    }
    lastScanTime = now;

    // --- 1. KIỂM TRA ĐẦU ĐỌC CỔNG VÀO (ENTRY) ---
    digitalWrite(Pins::RFID_OUT_SS, HIGH);
    digitalWrite(Pins::RFID_IN_SS, LOW);

    if (rfidEntry.PICC_IsNewCardPresent() && rfidEntry.PICC_ReadCardSerial()) {
        String uidStr = dumpUidToString(&(rfidEntry.uid));
        
        // Chống đọc lặp lại cùng một thẻ trong thời gian ngắn
        if (uidStr != lastEntryUid || (now - lastEntryReadTime >= Config::RFID_CARD_COOLDOWN_MS)) {
            lastEntryUid = uidStr;
            lastEntryReadTime = now;
            currentEntryUid = uidStr;
            pendingEntryCard = true;
            Serial.printf("[RFID] ENTRY Card detected: %s\n", uidStr.c_str());
            if (buzzer != nullptr) {
                buzzer->beepSuccess(); // Bíp ngắn 100ms phản hồi âm thanh khi nhận diện thẻ
            }
        }

        rfidEntry.PICC_HaltA();
        rfidEntry.PCD_StopCrypto1();
    }
    digitalWrite(Pins::RFID_IN_SS, HIGH);

    // --- 2. KIỂM TRA ĐẦU ĐỌC CỔNG RA (EXIT) ---
    digitalWrite(Pins::RFID_IN_SS, HIGH);
    digitalWrite(Pins::RFID_OUT_SS, LOW);

    if (rfidExit.PICC_IsNewCardPresent() && rfidExit.PICC_ReadCardSerial()) {
        String uidStr = dumpUidToString(&(rfidExit.uid));

        if (uidStr != lastExitUid || (now - lastExitReadTime >= Config::RFID_CARD_COOLDOWN_MS)) {
            lastExitUid = uidStr;
            lastExitReadTime = now;
            currentExitUid = uidStr;
            pendingExitCard = true;
            Serial.printf("[RFID] EXIT Card detected: %s\n", uidStr.c_str());
            if (buzzer != nullptr) {
                buzzer->beepSuccess(); // Bíp ngắn 100ms phản hồi âm thanh khi nhận diện thẻ
            }
        }

        rfidExit.PICC_HaltA();
        rfidExit.PCD_StopCrypto1();
    }
    digitalWrite(Pins::RFID_OUT_SS, HIGH);
}

bool RFIDManager::hasNewEntryCard(String &cardUid) {
    if (pendingEntryCard) {
        // Thẻ quẹt có hiệu lực trong 5 giây chờ xe
        if (millis() - lastEntryReadTime <= 5000) {
            cardUid = currentEntryUid;
            pendingEntryCard = false;
            return true;
        } else {
            pendingEntryCard = false; // Quá hạn chờ
        }
    }
    return false;
}

bool RFIDManager::hasNewExitCard(String &cardUid) {
    if (pendingExitCard) {
        // Thẻ quẹt có hiệu lực trong 5 giây chờ xe
        if (millis() - lastExitReadTime <= 5000) {
            cardUid = currentExitUid;
            pendingExitCard = false;
            return true;
        } else {
            pendingExitCard = false; // Quá hạn chờ
        }
    }
    return false;
}

void RFIDManager::printDebugStatus() {
    selectEntryModule();
    byte vIn = rfidEntry.PCD_ReadRegister(MFRC522::VersionReg);
    bool inCard = rfidEntry.PICC_IsNewCardPresent();
    deselectAll();

    selectExitModule();
    byte vOut = rfidExit.PCD_ReadRegister(MFRC522::VersionReg);
    bool outCard = rfidExit.PICC_IsNewCardPresent();
    deselectAll();

    Serial.println("\n--- [HARDWARE TEST] RFID RC522 ---");
    Serial.printf("SPI Bus: SCK=%d, MISO=%d, MOSI=%d\n", Pins::SPI_SCK, Pins::SPI_MISO, Pins::SPI_MOSI);
    Serial.printf("Entry RC522 (SS GPIO %d): VersionReg = 0x%02X (%s) | Card Present = %s\n",
                  Pins::RFID_IN_SS, vIn, (vIn == 0x91 || vIn == 0x92) ? "COMMUNICATION OK" : "NO RESPONSE / WIRING FAULT",
                  inCard ? "YES" : "NO");
    Serial.printf("Exit  RC522 (SS GPIO %d): VersionReg = 0x%02X (%s) | Card Present = %s\n",
                  Pins::RFID_OUT_SS, vOut, (vOut == 0x91 || vOut == 0x92) ? "COMMUNICATION OK" : "NO RESPONSE / WIRING FAULT",
                  outCard ? "YES" : "NO");
    Serial.println("----------------------------------");
}
