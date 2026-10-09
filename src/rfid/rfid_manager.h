#ifndef RFID_MANAGER_H
#define RFID_MANAGER_H

#include <Arduino.h>
#include <SPI.h>
#include <MFRC522.h>
#include "../config/pins.h"
#include "../config/config.h"

class BuzzerManager; // Forward declaration

class RFIDManager {
public:
    RFIDManager();
    void begin(BuzzerManager* buzzerPtr = nullptr);
    void update();

    bool hasNewEntryCard(String &cardUid);
    bool hasNewExitCard(String &cardUid);
    void printDebugStatus();

private:
    BuzzerManager* buzzer;
    MFRC522 rfidEntry;
    MFRC522 rfidExit;

    unsigned long lastScanTime;
    unsigned long lastEntryReadTime;
    unsigned long lastExitReadTime;

    String lastEntryUid;
    String lastExitUid;

    bool pendingEntryCard;
    bool pendingExitCard;
    String currentEntryUid;
    String currentExitUid;

    String dumpUidToString(MFRC522::Uid *uid);
    void selectEntryModule();
    void selectExitModule();
    void deselectAll();
};

#endif // RFID_MANAGER_H
