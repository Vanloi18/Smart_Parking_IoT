#include "parking_fsm.h"

ParkingFSM::ParkingFSM()
    : state(ParkingSystemState::IDLE),
      stateStartTime(0),
      activeExitSlotIndex(-1),
      activeExitUid(""),
      currentFee(0),
      currentParkDurationSec(0),
      prevEntryDetected(false),
      prevExitDetected(false),
      temporaryMessageActive(false),
      temporaryMessageStartTime(0) {
    for (int i = 0; i < Config::TOTAL_SLOTS; i++) {
        sessions[i].active = false;
        sessions[i].slot = i + 1;
        sessions[i].cardUid = "";
        sessions[i].parkStartTime = 0;
        sessions[i].entryGateTime = 0;
        sessions[i].calculatedFee = 0;
        prevSlotOccupied[i] = false;
    }
    pendingEntrySession.active = false;
    pendingEntrySession.slot = 0;
    pendingEntrySession.cardUid = "";
    pendingEntrySession.parkStartTime = 0;
    pendingEntrySession.entryGateTime = 0;
    pendingEntrySession.calculatedFee = 0;
}

void ParkingFSM::begin() {
    state = ParkingSystemState::IDLE;
    stateStartTime = millis();
    Serial.println("[FSM] Parking Finite State Machine initialized: IDLE");
}

ParkingSystemState ParkingFSM::getState() const {
    return state;
}

const char* ParkingFSM::getStateStr() const {
    switch (state) {
        case ParkingSystemState::IDLE:                             return "IDLE";
        case ParkingSystemState::WAITING_FOR_ENTRY_RFID:          return "WAIT_ENTRY_RFID";
        case ParkingSystemState::ENTRY_AUTHORIZED:                return "ENTRY_AUTHORIZED";
        case ParkingSystemState::ENTRY_GATE_OPEN:                 return "ENTRY_GATE_OPEN";
        case ParkingSystemState::WAITING_FOR_PARKING_SLOT:        return "WAIT_PARK_SLOT";
        case ParkingSystemState::PARKING_ACTIVE:                  return "PARKING_ACTIVE";
        case ParkingSystemState::WAITING_FOR_EXIT_RFID:           return "WAIT_EXIT_RFID";
        case ParkingSystemState::CALCULATING_FEE:                 return "CALCULATING_FEE";
        case ParkingSystemState::WAITING_FOR_PAYMENT_CONFIRMATION:return "WAIT_PAYMENT_CONFIRM";
        case ParkingSystemState::EXIT_GATE_OPEN:                  return "EXIT_GATE_OPEN";
        case ParkingSystemState::CHECKOUT_COMPLETE:               return "CHECKOUT_COMPLETE";
        case ParkingSystemState::ERROR_TIMEOUT:                   return "ERROR_TIMEOUT";
        default:                                                  return "UNKNOWN";
    }
}

uint32_t ParkingFSM::getCurrentFee() const {
    return currentFee;
}

String ParkingFSM::getActiveExitCard() const {
    return activeExitUid;
}

bool ParkingFSM::isSessionActiveInSlot(uint8_t slot) const {
    if (slot >= 1 && slot <= Config::TOTAL_SLOTS) {
        return sessions[slot - 1].active;
    }
    return false;
}

bool ParkingFSM::hasActiveSessionForUid(const String &uid) const {
    if (uid.length() == 0) {
        return false;
    }
    // Kiểm tra trong danh sách các ô đỗ P1..P4 đang active
    for (int i = 0; i < Config::TOTAL_SLOTS; i++) {
        if (sessions[i].active && sessions[i].cardUid.equalsIgnoreCase(uid)) {
            return true;
        }
    }
    // Kiểm tra phiên đang chờ xe vào ô đỗ (vừa qua cổng vào)
    if (pendingEntrySession.active && pendingEntrySession.cardUid.equalsIgnoreCase(uid)) {
        return true;
    }
    return false;
}

const ParkingSession* ParkingFSM::getSessions() const {
    return sessions;
}

// ============================================================================
// VÒNG LẶP CHÍNH CẬP NHẬT MÁY TRẠNG THÁI (UPDATE)
// ============================================================================
void ParkingFSM::update(ParkingSensors &sensors,
                        BarrierManager &barriers,
                        RFIDManager &rfid,
                        LCDManager &lcd,
                        BuzzerManager &buzzer,
                        WiFiNetworkManager &wifi,
                        float temp, float hum, GasLevel gasLevel) {
    unsigned long now = millis();

    // 1. Theo dõi trạng thái thay đổi vật lý của 4 ô đỗ P1..P4
    handleSlotOccupancyTracking(sensors, lcd);

    // 2. Xử lý luồng xe vào (Entry Gate)
    handleEntryFlow(sensors, barriers, rfid, lcd, buzzer, wifi);

    // 3. Xử lý luồng xe ra (Exit Gate)
    handleExitFlow(sensors, barriers, rfid, lcd, buzzer, wifi);

    // 4. Cập nhật hiển thị màn hình LCD2004
    updateLCDDisplay(lcd, sensors, temp, hum, gasLevel);
}

// ============================================================================
// QUẢN LÝ Ô ĐỖ XE (SLOTS P1..P4 TRACKING & BILLING ACTIVATION)
// ============================================================================
void ParkingFSM::handleSlotOccupancyTracking(ParkingSensors &sensors, LCDManager &lcd) {
    unsigned long now = millis();

    for (int i = 0; i < Config::TOTAL_SLOTS; i++) {
        uint8_t slotNum = i + 1;
        bool isOccupiedNow = sensors.isSlotOccupied(slotNum);

        // Phát hiện thời điểm xe bắt đầu chiếm ô đỗ (FREE -> OCCUPIED)
        if (isOccupiedNow && !prevSlotOccupied[i]) {
            Serial.printf("[IR] P%d = OCCUPIED\n", slotNum);

            // Nếu đang có xe vừa qua cổng vào (pendingEntrySession), gắn xe này vào slot!
            if (pendingEntrySession.active) {
                sessions[i].active = true;
                sessions[i].slot = slotNum;
                sessions[i].cardUid = pendingEntrySession.cardUid;
                // BẮT ĐẦU TÍNH PHÍ TỪ THỜI ĐIỂM XE VÀO Ô ĐỖ
                sessions[i].parkStartTime = now;
                sessions[i].entryGateTime = pendingEntrySession.entryGateTime;
                sessions[i].calculatedFee = 0;

                pendingEntrySession.active = false;

                Serial.printf("[FSM] Car UID %s assigned to Slot P%d. Park start time recorded (%lu ms). Billing active!\n",
                              sessions[i].cardUid.c_str(), slotNum, now);

                if (state == ParkingSystemState::WAITING_FOR_PARKING_SLOT) {
                    state = ParkingSystemState::PARKING_ACTIVE;
                    stateStartTime = now;
                }

                char line1[21];
                snprintf(line1, sizeof(line1), "SLOT P%d OCCUPIED", slotNum);
                char line3[21];
                snprintf(line3, sizeof(line3), "FREE:%d/4", sensors.getAvailableSlotsCount());
                lcd.showMessage("PARKED AT SLOT", line1, "BILLING STARTED", line3);

                temporaryMessageActive = true;
                temporaryMessageStartTime = now;
            } else if (state == ParkingSystemState::WAITING_FOR_PARKING_SLOT) {
                Serial.printf("[FSM] P%d occupied without valid entry card/session -> ignored.\n", slotNum);
            }
        }
        // Phát hiện thời điểm xe rời ô đỗ (OCCUPIED -> FREE)
        else if (!isOccupiedNow && prevSlotOccupied[i]) {
            Serial.printf("[IR] P%d = FREE\n", slotNum);
            // Lưu ý: Không xóa session ngay nếu xe đang trên đường tiến ra cổng quét thẻ Exit!
            // Session chỉ bị hủy sau khi xe đã hoàn tất thanh toán và đi qua cổng ra.
        }

        prevSlotOccupied[i] = isOccupiedNow;
    }
}

// ============================================================================
// LUỒNG XE VÀO (ENTRY FLOW)
// ============================================================================
void ParkingFSM::handleEntryFlow(ParkingSensors &sensors,
                                 BarrierManager &barriers,
                                 RFIDManager &rfid,
                                 LCDManager &lcd,
                                 BuzzerManager &buzzer,
                                 WiFiNetworkManager &wifi) {
    unsigned long now = millis();
    bool carAtEntry = sensors.isEntryVehicleDetected();

    // 1. Phát hiện xe tiến đến cổng vào (IR Entry = VEHICLE PRESENT)
    if (carAtEntry && !prevEntryDetected) {
        Serial.println("[IR] ENTRY = VEHICLE PRESENT");
        if (state == ParkingSystemState::IDLE || state == ParkingSystemState::PARKING_ACTIVE) {
            state = ParkingSystemState::WAITING_FOR_ENTRY_RFID;
            stateStartTime = now;
            Serial.println("[FSM] State -> WAITING_FOR_ENTRY_RFID (Car detected at Entry gate)");
        }
    } else if (!carAtEntry && prevEntryDetected) {
        Serial.println("[IR] ENTRY = FREE");
    }
    prevEntryDetected = carAtEntry;

    // 2. Trạng thái WAITING_FOR_ENTRY_RFID
    if (state == ParkingSystemState::WAITING_FOR_ENTRY_RFID) {
        // Nếu xe lùi lại bỏ đi khỏi vùng cảm biến cổng vào
        if (!carAtEntry) {
            Serial.println("[FSM] Vehicle backed away from Entry gate -> Returning to IDLE");
            state = ParkingSystemState::IDLE;
            return;
        }

        // Hết thời gian chờ quẹt thẻ (Timeout an toàn)
        if (now - stateStartTime >= Config::ENTRY_RFID_TIMEOUT_MS) {
            Serial.println("[FSM] Entry RFID wait timeout reached -> Resetting to IDLE");
            buzzer.beepError();
            state = ParkingSystemState::IDLE;
            return;
        }

        // Quét thẻ RFID tại cổng vào
        String entryUid;
        if (rfid.hasNewEntryCard(entryUid)) {
            // QUAN TRỌNG: RFID KHÔNG được tự mở Entry barrier nếu IR Entry không phát hiện xe!
            if (!carAtEntry) {
                Serial.println("[RFID] Ignored: no vehicle at Entry gate");
                return;
            }

            Serial.printf("[RFID ENTRY] UID scanned: %s\n", entryUid.c_str());
            Serial.println("[RFID ENTRY] Checking active parking sessions...");

            // BẢO VỆ CHỐNG DÙNG LẠI THẺ ĐANG PARKING:
            // Mỗi RFID UID chỉ được phép có MỘT session active tại một thời điểm
            if (hasActiveSessionForUid(entryUid)) {
                Serial.println("[RFID ENTRY] UID already has active session");
                Serial.println("[ENTRY] ACCESS DENIED - CARD ALREADY PARKING");
                buzzer.beepError();
                lcd.showMessage("ENTRY - DENIED", "CARD ALREADY", "PARKING", "PLEASE GO BACK");
                temporaryMessageActive = true;
                temporaryMessageStartTime = now;
                return;
            }

            uint8_t freeSlots = sensors.getAvailableSlotsCount();
            Serial.printf("[GATE-IN] Card valid: %s | Available slots: %d/%d\n",
                          entryUid.c_str(), freeSlots, Config::TOTAL_SLOTS);

            // KIỂM TRA BÃI CÒN CHỖ KHÔNG
            if (freeSlots == 0) {
                // BÃI ĐÃ ĐẦY (PARKING FULL):
                // - Không mở barrier
                // - Buzzer báo lỗi
                // - LCD báo PARKING FULL
                // - Giữ xe ở trạng thái chờ
                buzzer.beepError();
                Serial.println("[GATE-IN] Access DENIED -> PARKING IS FULL!");
                lcd.showMessage("ENTRY - DENIED", "PARKING FULL", "NO SLOT AVAILABLE", "PLEASE GO BACK");
                temporaryMessageActive = true;
                temporaryMessageStartTime = now;
                return;
            }

            // CÒN CHỖ: CHO PHÉP VÀO
            buzzer.beepSuccess();

            pendingEntrySession.active = true;
            pendingEntrySession.slot = 0; // Chưa chiếm slot
            pendingEntrySession.cardUid = entryUid;
            pendingEntrySession.entryGateTime = now;
            pendingEntrySession.parkStartTime = 0; // Sẽ bắt đầu tính khi xe vào slot thực tế
            pendingEntrySession.calculatedFee = 0;

            // MỞ ENTRY BARRIER
            barriers.openEntry();

            // Gửi bản tin backend không chặn luồng
            String srvMsg;
            wifi.postCardEntry(entryUid, srvMsg);

            state = ParkingSystemState::ENTRY_AUTHORIZED;
            stateStartTime = now;

            Serial.printf("[FSM] State -> ENTRY_AUTHORIZED: Opening Entry Barrier for card %s\n", entryUid.c_str());
            char uidLine[21];
            snprintf(uidLine, sizeof(uidLine), "UID: %s", entryUid.c_str());
            lcd.showMessage("ENTRY - RFID OK", uidLine, "BARRIER OPENING", "PLEASE ENTER");

            temporaryMessageActive = true;
            temporaryMessageStartTime = now;
        }
    }

    // 3. Trạng thái ENTRY_AUTHORIZED -> Chờ barrier bắt đầu mở
    else if (state == ParkingSystemState::ENTRY_AUTHORIZED) {
        if (barriers.getEntryState() == BarrierState::OPEN || barriers.getEntryState() == BarrierState::OPENING) {
            state = ParkingSystemState::ENTRY_GATE_OPEN;
            stateStartTime = now;
            Serial.println("[FSM] State -> ENTRY_GATE_OPEN: Waiting for vehicle to pass");
        }
    }

    // 4. Trạng thái ENTRY_GATE_OPEN -> Chờ xe đi qua barrier cổng vào
    else if (state == ParkingSystemState::ENTRY_GATE_OPEN) {
        // Khi xe đã đi qua và IR Entry trở lại FREE (hoặc barrier đã tự đóng do timeout an toàn):
        if (!carAtEntry || barriers.getEntryState() == BarrierState::CLOSED) {
            if (barriers.getEntryState() != BarrierState::CLOSED) {
                Serial.println("[FSM] Vehicle passed Entry gate -> Closing Entry Barrier");
                barriers.closeEntry();
            }

            state = ParkingSystemState::WAITING_FOR_PARKING_SLOT;
            stateStartTime = now;
            Serial.println("[FSM] State -> WAITING_FOR_PARKING_SLOT: Waiting for car to park in P1..P4");

            char freeStr[21];
            snprintf(freeStr, sizeof(freeStr), "FREE:%d/4", sensors.getAvailableSlotsCount());
            lcd.showMessage("ENTRY - GATE OPEN", "CHOOSE SLOT", "P1 - P4", freeStr);

            temporaryMessageActive = true;
            temporaryMessageStartTime = now;
        }
    }

    // 5. Trạng thái WAITING_FOR_PARKING_SLOT -> Chờ xe vào ô đỗ
    else if (state == ParkingSystemState::WAITING_FOR_PARKING_SLOT) {
        // Nếu quá thời gian an toàn mà xe không kích hoạt slot nào:
        // Hủy hoàn toàn pending entry để UID cũ không thể bị gắn vào xe/slot của phiên sau.
        if (now - stateStartTime >= Config::SLOT_ASSIGN_TIMEOUT_MS) {
            Serial.println("[FSM] Slot assign timeout reached -> Cancel pending entry session and return to IDLE.");
            pendingEntrySession.active = false;
            pendingEntrySession.slot = 0;
            pendingEntrySession.cardUid = "";
            pendingEntrySession.parkStartTime = 0;
            pendingEntrySession.entryGateTime = 0;
            pendingEntrySession.calculatedFee = 0;
            state = ParkingSystemState::IDLE;
        }
    }
}

// ============================================================================
// LUỒNG XE RA (EXIT FLOW)
// ============================================================================
void ParkingFSM::handleExitFlow(ParkingSensors &sensors,
                                BarrierManager &barriers,
                                RFIDManager &rfid,
                                LCDManager &lcd,
                                BuzzerManager &buzzer,
                                WiFiNetworkManager &wifi) {
    unsigned long now = millis();
    bool carAtExit = sensors.isExitVehicleDetected();

    // 1. Phát hiện xe tiến đến cổng ra (IR Exit = VEHICLE PRESENT)
    if (carAtExit && !prevExitDetected) {
        Serial.println("[IR] EXIT = VEHICLE PRESENT");
        if (state == ParkingSystemState::IDLE || state == ParkingSystemState::PARKING_ACTIVE) {
            state = ParkingSystemState::WAITING_FOR_EXIT_RFID;
            stateStartTime = now;
            Serial.println("[FSM] State -> WAITING_FOR_EXIT_RFID (Car detected at Exit gate)");
        }
    } else if (!carAtExit && prevExitDetected) {
        Serial.println("[IR] EXIT = FREE");
    }
    prevExitDetected = carAtExit;

    // 2. Trạng thái WAITING_FOR_EXIT_RFID
    if (state == ParkingSystemState::WAITING_FOR_EXIT_RFID) {
        // Nếu xe lùi lại bỏ đi khỏi vùng cảm biến cổng ra
        if (!carAtExit) {
            Serial.println("[FSM] Vehicle backed away from Exit gate -> Returning to IDLE");
            state = ParkingSystemState::IDLE;
            return;
        }

        // Hết thời gian chờ quẹt thẻ ra
        if (now - stateStartTime >= Config::EXIT_RFID_TIMEOUT_MS) {
            Serial.println("[FSM] Exit RFID wait timeout reached -> Resetting to IDLE");
            buzzer.beepError();
            state = ParkingSystemState::IDLE;
            return;
        }

        // Quét thẻ RFID tại cổng ra
        String exitUid;
        if (rfid.hasNewExitCard(exitUid)) {
            // QUAN TRỌNG: RFID EXIT chỉ được xử lý khi IR Exit = VEHICLE PRESENT
            if (!carAtExit) {
                Serial.println("[RFID] Ignored: no vehicle at Exit gate");
                return;
            }

            Serial.printf("[GATE-OUT] Exit Card presented: %s\n", exitUid.c_str());

            // TÌM PHIÊN GỬI XE THEO UID
            int foundIdx = -1;
            for (int i = 0; i < Config::TOTAL_SLOTS; i++) {
                if (sessions[i].active && sessions[i].cardUid == exitUid) {
                    foundIdx = i;
                    break;
                }
            }

            // NẾU KHÔNG TÌM THẤY:
            if (foundIdx == -1) {
                // - Không mở barrier
                // - Buzzer báo lỗi
                // - LCD báo thẻ/xe không hợp lệ
                buzzer.beepError();
                Serial.printf("[GATE-OUT] CARD NOT FOUND -> No active session for UID %s!\n", exitUid.c_str());
                lcd.showMessage("RFID NOT FOUND", "NO ACTIVE SESSION", "CARD NOT VALID", "GATE CLOSED");
                temporaryMessageActive = true;
                temporaryMessageStartTime = now;
                return;
            }

            // NẾU TÌM THẤY: TÍNH THỜI GIAN VÀ PHÍ ĐỖ
            state = ParkingSystemState::CALCULATING_FEE;
            stateStartTime = now;
            activeExitSlotIndex = foundIdx;
            activeExitUid = exitUid;

            unsigned long parkStart = sessions[foundIdx].parkStartTime;
            unsigned long elapsedMs = now - parkStart;
            currentParkDurationSec = elapsedMs / 1000;

            // Tính phí đỗ xe theo mô hình Demo: Mỗi 5 giây là 1 block (5.000 VNĐ)
            unsigned long intervals = elapsedMs / Config::PARKING_BILLING_INTERVAL_MS;
            if (elapsedMs % Config::PARKING_BILLING_INTERVAL_MS != 0 || intervals == 0) {
                intervals += 1;
            }
            currentFee = intervals * Config::BILLING_RATE_PER_INTERVAL;
            sessions[foundIdx].calculatedFee = currentFee;

            Serial.printf("[FSM] Session found for UID %s: Parked %lu ms (%lu s) -> %lu intervals -> Fee: %lu VND\n",
                          exitUid.c_str(), elapsedMs, currentParkDurationSec, intervals, (unsigned long)currentFee);

            // CHUYỂN SANG WAITING_FOR_PAYMENT_CONFIRMATION
            // QUAN TRỌNG: CHƯA ĐƯỢC MỞ BARRIER!
            state = ParkingSystemState::WAITING_FOR_PAYMENT_CONFIRMATION;
            stateStartTime = now;

            buzzer.beepSuccess(); // Bíp báo nhận thẻ và hiện phí

            char uidLine[21];
            snprintf(uidLine, sizeof(uidLine), "UID: %s", exitUid.c_str());
            char feeLine[21];
            snprintf(feeLine, sizeof(feeLine), "FEE: %lu VND", (unsigned long)currentFee);

            lcd.showMessage("EXIT - RFID OK", uidLine, feeLine, "PRESS EXIT BTN");

            temporaryMessageActive = true;
            temporaryMessageStartTime = now;
        }
    }

    // 3. Trạng thái WAITING_FOR_PAYMENT_CONFIRMATION
    else if (state == ParkingSystemState::WAITING_FOR_PAYMENT_CONFIRMATION) {
        // Quá thời gian chờ bấm nút xác nhận thanh toán
        if (now - stateStartTime >= Config::PAYMENT_CONFIRM_TIMEOUT_MS) {
            Serial.println("[FSM] Payment confirmation timeout reached -> Barrier remains CLOSED.");
            buzzer.beepError();
            activeExitSlotIndex = -1;
            activeExitUid = "";
            currentFee = 0;
            state = ParkingSystemState::IDLE;
            return;
        }
    }

    // 4. Trạng thái EXIT_GATE_OPEN -> Chờ xe thực sự đi qua barrier cổng ra
    else if (state == ParkingSystemState::EXIT_GATE_OPEN) {
        // Safety timeout của BarrierManager chỉ được phép đóng cổng.
        // Session chỉ kết thúc khi IR EXIT thực sự chuyển sang CLEAR.
        if (!carAtExit) {
            if (barriers.getExitState() != BarrierState::CLOSED) {
                Serial.println("[FSM] Exit IR CLEAR -> Closing Exit Barrier");
                barriers.closeExit();
            }

            // KẾT THÚC PHIÊN VÀ XÓA ACTIVE SESSION
            if (activeExitSlotIndex >= 0 && activeExitSlotIndex < Config::TOTAL_SLOTS) {
                sessions[activeExitSlotIndex].active = false;
                sessions[activeExitSlotIndex].slot = activeExitSlotIndex + 1;
                sessions[activeExitSlotIndex].cardUid = "";
                sessions[activeExitSlotIndex].parkStartTime = 0;
                sessions[activeExitSlotIndex].entryGateTime = 0;
                sessions[activeExitSlotIndex].calculatedFee = 0;
            }
            pendingEntrySession.active = false;

            state = ParkingSystemState::CHECKOUT_COMPLETE;
            stateStartTime = now;

            Serial.println("[FSM] State -> CHECKOUT_COMPLETE: Session cleared. Slot is now FREE.");
            char freeStr[21];
            snprintf(freeStr, sizeof(freeStr), "FREE:%d/4", sensors.getAvailableSlotsCount());
            lcd.showMessage("CHECKOUT COMPLETE", "THANK YOU!", "SEE YOU AGAIN", freeStr);

            temporaryMessageActive = true;
            temporaryMessageStartTime = now;
        }
    }

    // 5. Trạng thái CHECKOUT_COMPLETE -> Giữ thông báo 2 giây rồi trở về IDLE
    else if (state == ParkingSystemState::CHECKOUT_COMPLETE) {
        if (now - stateStartTime >= 2000) {
            state = ParkingSystemState::IDLE;
            temporaryMessageActive = false;
            Serial.println("[FSM] State -> IDLE: Ready for next vehicle.");
        }
    }
}

// ============================================================================
// XỬ LÝ SỰ KIỆN NÚT BẤM (BUTTON LOGIC)
// ============================================================================

void ParkingFSM::onExitButtonPressed(BarrierManager &barriers, BuzzerManager &buzzer, WiFiNetworkManager &wifi, LCDManager &lcd) {
    unsigned long now = millis();

    // Button EXIT CHỈ CÓ TÁC DỤNG khi FSM đang ở: WAITING_FOR_PAYMENT_CONFIRMATION
    if (state == ParkingSystemState::WAITING_FOR_PAYMENT_CONFIRMATION) {
        Serial.println("[BUTTON] EXIT payment confirmed");
        buzzer.beepSuccess();

        // Mở barrier EXIT
        barriers.openExit();

        // Gửi API checkout non-blocking
        String resp;
        wifi.postCardExit(activeExitUid, resp);

        state = ParkingSystemState::EXIT_GATE_OPEN;
        stateStartTime = now;

        lcd.showMessage("EXIT - PAID OK", "PAYMENT CONFIRMED", "BARRIER OPENING", "THANK YOU");
        temporaryMessageActive = true;
        temporaryMessageStartTime = now;
    }
}

void ParkingFSM::onEntryButtonPressed(BarrierManager &barriers, BuzzerManager &buzzer, const ParkingSensors &sensors) {
    unsigned long now = millis();
    uint8_t freeSlots = sensors.getAvailableSlotsCount();

    // ENTRY BUTTON chỉ là điều khiển thủ công/khẩn cấp.
    // Không tạo parking session và chỉ cho phép bypass RFID khi hệ thống đang ở
    // trạng thái chờ xe tại cổng vào. Không cho phép mở từ PARKING_ACTIVE vì
    // xe đang ở trong bãi và có thể gây nhầm luồng entry thứ hai.
    if (freeSlots == 0) {
        Serial.println("[BUTTON] ENTRY ignored: Parking is full (0 slots available)");
        buzzer.beepError();
        return;
    }

    if (barriers.getEntryState() == BarrierState::OPEN ||
        barriers.getEntryState() == BarrierState::OPENING) {
        Serial.println("[BUTTON] ENTRY ignored: Entry barrier already open");
        return;
    }

    if (state == ParkingSystemState::WAITING_FOR_ENTRY_RFID) {
        Serial.println("[BUTTON] ENTRY allowed -> Opening Entry Barrier (manual override)");
        buzzer.beepSuccess();
        barriers.openEntry();

        state = ParkingSystemState::ENTRY_GATE_OPEN;
        stateStartTime = now;
    } else {
        Serial.println("[BUTTON] ENTRY ignored: RFID authorization is required");
    }
}

// ============================================================================
// HIỂN THỊ MÀN HÌNH LCD2004 REALTIME KHÔNG GIẬT NHÁY
// ============================================================================
void ParkingFSM::updateLCDDisplay(LCDManager &lcd, const ParkingSensors &sensors, float temp, float hum, GasLevel gasLevel) {
    unsigned long now = millis();

    // Nếu đang hiển thị thông báo tạm thời (như RFID OK, PARKING FULL, FEE...)
    if (temporaryMessageActive) {
        if (now - temporaryMessageStartTime >= Config::STATUS_MSG_HOLD_MS) {
            temporaryMessageActive = false;
        } else {
            return; // Giữ nguyên thông báo
        }
    }

    // Hiển thị giao diện giám sát tiêu chuẩn theo trạng thái FSM (chuẩn ASCII không dấu)
    switch (state) {
        case ParkingSystemState::WAITING_FOR_ENTRY_RFID: {
            char freeStr[21];
            snprintf(freeStr, sizeof(freeStr), "FREE:%d/4", sensors.getAvailableSlotsCount());
            lcd.showMessage("ENTRY - CAR DETECT", "SCAN RFID CARD", freeStr, "PLEASE ENTER");
            break;
        }

        case ParkingSystemState::WAITING_FOR_EXIT_RFID:
            lcd.showMessage("EXIT - CAR DETECT", "SCAN RFID CARD", "CHECK PARKING FEE", "SCAN CARD TO EXIT");
            break;

        case ParkingSystemState::WAITING_FOR_PAYMENT_CONFIRMATION: {
            char uidLine[21];
            snprintf(uidLine, sizeof(uidLine), "UID: %s", activeExitUid.c_str());
            char feeLine[21];
            snprintf(feeLine, sizeof(feeLine), "FEE: %lu VND", (unsigned long)currentFee);
            lcd.showMessage("EXIT - RFID OK", uidLine, feeLine, "PRESS EXIT BTN");
            break;
        }

        case ParkingSystemState::IDLE:
        case ParkingSystemState::PARKING_ACTIVE:
        default: {
            // Màn hình tổng quan tiêu chuẩn
            char line0[21];
            snprintf(line0, sizeof(line0), "PARKING: READY");

            char line1[21];
            snprintf(line1, sizeof(line1), "FREE:%d/4 [%c %c %c %c]",
                     sensors.getAvailableSlotsCount(),
                     sensors.isSlotOccupied(1) ? 'X' : '_',
                     sensors.isSlotOccupied(2) ? 'X' : '_',
                     sensors.isSlotOccupied(3) ? 'X' : '_',
                     sensors.isSlotOccupied(4) ? 'X' : '_');

            char line2[21];
            snprintf(line2, sizeof(line2), "IN:%-4s | OUT:%-4s",
                     (state == ParkingSystemState::ENTRY_GATE_OPEN) ? "OPEN" : "CLOS",
                     (state == ParkingSystemState::EXIT_GATE_OPEN) ? "OPEN" : "CLOS");

            char line3[21];
            if (gasLevel == GasLevel::DANGER) {
                snprintf(line3, sizeof(line3), "!GAS DANGER! T:%.0fC", temp);
            } else if (gasLevel == GasLevel::WARNING) {
                snprintf(line3, sizeof(line3), "!GAS WARN!   T:%.0fC", temp);
            } else {
                snprintf(line3, sizeof(line3), "T:%.0fC H:%.0f%% G:OK", temp, hum);
            }

            lcd.showMessage(line0, line1, line2, line3);
            break;
        }
    }
}
