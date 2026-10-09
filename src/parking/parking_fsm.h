#ifndef PARKING_FSM_H
#define PARKING_FSM_H

#include <Arduino.h>
#include "../config/pins.h"
#include "../config/config.h"
#include "../sensors/parking_sensors.h"
#include "../actuators/barriers.h"
#include "../actuators/buzzer.h"
#include "../rfid/rfid_manager.h"
#include "../display/lcd_manager.h"
#include "../network/wifi_manager.h"
#include "../sensors/mq7.h"

// --- DANH MỤC CÁC TRẠNG THÁI TRONG MÁY TRẠNG THÁI BÃI ĐỖ XE ---
enum class ParkingSystemState {
    IDLE,                               // 0. Chờ xe đến bãi
    WAITING_FOR_ENTRY_RFID,             // 1. Xe đã tới cổng vào, chờ quẹt thẻ
    ENTRY_AUTHORIZED,                   // 2. Thẻ vào hợp lệ & còn chỗ -> Cho phép mở
    ENTRY_GATE_OPEN,                    // 3. Cổng vào đang mở, chờ xe đi qua
    WAITING_FOR_PARKING_SLOT,           // 4. Xe đã qua cổng vào, đang tìm & vào ô đỗ P1-P4
    PARKING_ACTIVE,                     // 5. Xe đã đỗ ổn định trong ô (bắt đầu tính giờ/phí)
    WAITING_FOR_EXIT_RFID,              // 6. Xe đã tới cổng ra, chờ quẹt thẻ
    CALCULATING_FEE,                    // 7. Tìm thấy xe, đang tính thời gian & phí đỗ
    WAITING_FOR_PAYMENT_CONFIRMATION,   // 8. Đã hiện phí, chờ người dùng bấm NÚT EXIT xác nhận
    EXIT_GATE_OPEN,                     // 9. Nút Exit đã bấm -> Mở cổng ra, chờ xe đi qua
    CHECKOUT_COMPLETE,                  // 10. Xe đã ra khỏi cổng -> Đóng cổng, kết thúc phiên
    ERROR_TIMEOUT                       // 11. Hết giờ chờ / Lỗi
};

// --- CẤU TRÚC LƯU TRỮ PHIÊN GỬI XE (PARKING SESSION) ---
struct ParkingSession {
    bool active;                 // true: đang có xe chiếm phiên
    uint8_t slot;                // 1..4 (tương ứng P1..P4), 0 nếu chưa vào slot
    String cardUid;              // Mã UID thẻ RFID thực tế
    unsigned long parkStartTime; // Thời điểm xe thực sự vào ô đỗ (ms) -> DÙNG TÍNH PHÍ
    unsigned long entryGateTime; // Thời điểm xe quẹt thẻ qua cổng vào (ms)
    uint32_t calculatedFee;      // Phí đỗ xe tính toán được (VNĐ)
};

class ParkingFSM {
public:
    ParkingFSM();
    void begin();

    // Vòng lặp cập nhật máy trạng thái chính
    void update(ParkingSensors &sensors,
                BarrierManager &barriers,
                RFIDManager &rfid,
                LCDManager &lcd,
                BuzzerManager &buzzer,
                WiFiNetworkManager &wifi,
                float temp, float hum, GasLevel gasLevel);

    // Xử lý sự kiện nhấn nút điều khiển
    void onExitButtonPressed(BarrierManager &barriers, BuzzerManager &buzzer, WiFiNetworkManager &wifi, LCDManager &lcd);
    void onEntryButtonPressed(BarrierManager &barriers, BuzzerManager &buzzer, const ParkingSensors &sensors);

    // Các hàm truy vấn trạng thái
    ParkingSystemState getState() const;
    const char* getStateStr() const;
    uint32_t getCurrentFee() const;
    String getActiveExitCard() const;
    bool isSessionActiveInSlot(uint8_t slot) const;
    bool hasActiveSessionForUid(const String &uid) const;
    const ParkingSession* getSessions() const;

private:
    ParkingSystemState state;
    unsigned long stateStartTime;

    // Quản lý 4 phiên đỗ ứng với 4 ô P1..P4
    ParkingSession sessions[Config::TOTAL_SLOTS];
    ParkingSession pendingEntrySession; // Xe vừa qua cổng vào, đang di chuyển vào ô đỗ

    // Thông tin thanh toán đang chờ nút Exit xác nhận
    int activeExitSlotIndex;
    String activeExitUid;
    uint32_t currentFee;
    unsigned long currentParkDurationSec;

    // Lưu trạng thái trước của cảm biến slot để phát hiện thời điểm xe vừa lọt vào ô đỗ
    bool prevSlotOccupied[Config::TOTAL_SLOTS];
    bool prevEntryDetected;
    bool prevExitDetected;

    // Quản lý hiển thị màn hình LCD tạm thời
    bool temporaryMessageActive;
    unsigned long temporaryMessageStartTime;

    void handleEntryFlow(ParkingSensors &sensors, BarrierManager &barriers, RFIDManager &rfid, LCDManager &lcd, BuzzerManager &buzzer, WiFiNetworkManager &wifi);
    void handleExitFlow(ParkingSensors &sensors, BarrierManager &barriers, RFIDManager &rfid, LCDManager &lcd, BuzzerManager &buzzer, WiFiNetworkManager &wifi);
    void handleSlotOccupancyTracking(ParkingSensors &sensors, LCDManager &lcd);
    void updateLCDDisplay(LCDManager &lcd, const ParkingSensors &sensors, float temp, float hum, GasLevel gasLevel);
};

#endif // PARKING_FSM_H
