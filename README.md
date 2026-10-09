# SMART PARKING IoT — HỆ THỐNG QUẢN LÝ BÃI ĐỖ XE THÔNG MINH

Dự án hoàn chỉnh gồm:
1. **ESP32 DevKit V1**: Bộ điều khiển trung tâm (FSM đa nhiệm non-blocking, 6 IR, 2 RFID, 2 Servo barrier, DHT11, MQ-7, LCD2004, NeoPixel, Buzzer).
2. **2x ESP32-CAM AI-Thinker**: Camera nhận diện biển số ANPR tại Cổng Vào (Entry) và Cổng Ra (Exit).
3. **Backend Server (Python Flask + SQLite + JWT RBAC)**: Quản lý bãi đỗ xe, tính phí, xử lý ANPR và lưu trữ sự kiện.
4. **Web Dashboard (Apple-like Clean Design)**: Giao diện tối giản, hiện đại, hỗ trợ đăng nhập, phân quyền, bản đồ 4 ô đỗ xe thời gian thực (Zero Fake Data).

---

## 1. PHẦN CỨNG (HARDWARE)

Hệ thống sử dụng các linh kiện phần cứng thực tế sau:

| Thiết bị | Số lượng | Chức năng / Kết nối | Chân GPIO (ESP32 DevKit V1) |
| :--- | :---: | :--- | :--- |
| **ESP32 DevKit V1** (30-pin) | 1 | Vi điều khiển trung tâm xử lý FSM | — |
| **ESP32-CAM AI-Thinker** | 2 | Camera chụp ảnh ANPR (Entry & Exit) | Vi điều khiển độc lập riêng |
| **Cảm biến hồng ngoại IR LM393** | 6 | 4 ô đỗ xe P1..P4 + 2 cổng vào/ra | P1: 13, P2: 14, P3: 16, P4: 35<br>Entry: 39, Exit: 34 |
| **Đầu đọc thẻ RFID RC522** | 2 | Quẹt thẻ cổng vào & cổng ra (SPI chung) | SCK: 18, MISO: 19, MOSI: 23<br>SS Vào: 5, SS Ra: 15 |
| **Động cơ Servo SG90** | 2 | Nâng/hạ cần chắn Barrier vào/ra (LEDC PWM) | Entry: 25, Exit: 26 |
| **Cảm biến khí CO MQ-7** | 1 | Đo nồng độ khí độc (Cầu phân áp 10k:10k) | ADC1_CH0 (GPIO 36 / VP) |
| **Cảm biến nhiệt độ & độ ẩm DHT11**| 1 | Giám sát môi trường nhà xe (1-Wire) | GPIO 33 |
| **Màn hình LCD2004 I2C** | 1 | Hiển thị thông báo, phí đỗ xe (I2C 0x27) | SDA: 21, SCL: 22 |
| **Đèn LED RGB WS2812B NeoPixel** | 1 | Báo trạng thái mạng & cảnh báo khí | GPIO 27 |
| **Còi Buzzer báo động** | 1 | Phát âm thanh quẹt thẻ & cảnh báo khí | GPIO 32 (qua NPN Transistor) |
| **Nút bấm thủ công (Buttons)** | 2 | Mở cổng vào / Xác nhận thanh toán ra | Entry: 4, Exit: 17 (INPUT_PULLUP) |

---

## 2. KIẾN TRÚC MẠNG (NETWORK TOPOLOGY)

Tất cả thiết bị giao tiếp với nhau trong cùng một mạng LAN (Local Area Network):

```text
Router Wi-Fi (2.4GHz)
     │
     ├── PC / Laptop chạy Backend Server (Ví dụ: 192.168.0.103)
     │    ├── Flask REST API (Port 5000)
     │    ├── SQLite Database (parking.db)
     │    └── Web Dashboard (Apple-like GUI)
     │
     ├── ESP32 DevKit V1 (Main Controller)
     │    └── Gửi Telemetry Heartbeat 3s & Quẹt thẻ RFID lên Server
     │
     ├── ESP32-CAM ENTRY (Cổng Vào)
     │    └── Chụp ảnh xe vào, POST ảnh tới /api/cameras/entry/capture
     │
     └── ESP32-CAM EXIT (Cổng Ra)
          └── Chụp ảnh xe ra, POST ảnh tới /api/cameras/exit/capture
```

---

## 3. CẤU HÌNH WI-FI & ĐỊA CHỈ SERVER

### Vị trí cấu hình duy nhất trên ESP32 DevKit V1:
File: **`src/config/config.h`**

```cpp
// ========================================================================
// WIFI & SERVER CONFIGURATION - KHU VỰC CẤU HÌNH MẠNG
// ========================================================================
inline const char* WIFI_SSID     = "TÊN_WIFI_CỦA_BẠN";     // << SỬA TÊN WIFI TẠI ĐÂY
inline const char* WIFI_PASSWORD = "MẬT_KHẨU_WIFI";        // << SỬA MẬT KHẨU WIFI TẠI ĐÂY

inline const char* SERVER_HOST   = "192.168.0.103";        // << SỬA IP LAN CỦA MÁY TÍNH
constexpr uint16_t SERVER_PORT   = 5000;                   // Cổng Server (Mặc định 5000)
```

> **LƯU Ý:**
> - Máy tính và ESP32 bắt buộc phải cùng kết nối vào một mạng Wi-Fi (2.4GHz).
> - Mở PowerShell/CMD trên Windows và gõ `ipconfig` để lấy địa chỉ IPv4 của máy tính (ví dụ: `192.168.0.103` hoặc `192.168.1.100`).
> - **KHÔNG** sử dụng `localhost` hoặc `127.0.0.1` trên ESP32 vì ESP32 không thể kết nối tới localhost của chính nó.
> - Nếu ESP32 báo lỗi không kết nối được tới server, kiểm tra **Windows Defender Firewall** và cho phép cổng **5000**.

### Vị trí cấu hình trên 2x ESP32-CAM:
1. **Camera Cổng Vào:** `esp32cam_entry/esp32cam_entry.ino` (sửa `WIFI_SSID`, `WIFI_PASSWORD`, `SERVER_HOST`).
2. **Camera Cổng Ra:** `esp32cam_exit/esp32cam_exit.ino` (sửa `WIFI_SSID`, `WIFI_PASSWORD`, `SERVER_HOST`).

---

## 4. HƯỚNG DẪN KHỞI CHẠY BACKEND & DASHBOARD

### Bước 1: Khởi động Server
Chạy lệnh sau tại thư mục gốc của project:

```bash
python run_dashboard.py
```

Server sẽ tự động:
- Khởi tạo cơ sở dữ liệu SQLite (`dashboard/parking.db`).
- Khởi tạo tài khoản quản trị mặc định: `admin` / `admin123`.
- Mở trình duyệt web tại: `http://localhost:5000`.

### Bước 2: Đăng nhập Web Dashboard
- **URL:** `http://localhost:5000` (hoặc `http://<LAN_IP>:5000` từ điện thoại/máy tính khác trong mạng LAN).
- **Tài khoản:** `admin`
- **Mật khẩu:** `admin123`

---

## 5. CÁC TRANG CHỨC NĂNG TRÊN DASHBOARD

Giao diện Dashboard thiết kế chuẩn Apple-like (sạch sẽ, tối giản, bo tròn tinh tế, light theme):

1. **Dashboard**:
   - Thẻ thống kê: Tổng chỗ đỗ (4), Chỗ trống (Available), Chỗ có xe (Occupied), Chất lượng không khí (MQ-7).
   - Bản đồ 4 ô đỗ xe thời gian thực: P1, P2, P3, P4 hiển thị màu xanh (Available) hoặc màu cam (Occupied) hoàn toàn từ cảm biến IR thực tế.
   - Bảng điều khiển Barrier Cổng Vào & Cổng Ra (kèm nút mở/đóng từ xa).
   - Khung giám sát 2 Camera (Entry CAM & Exit CAM) hiển thị ảnh snapshot và biển số nhận diện ANPR.
   - Bảng hoạt động ra/vào gần đây.
2. **Parking**: Mặt bằng chi tiết 4 vị trí ô đỗ, thời gian đỗ xe, mã thẻ và biển số.
3. **Vehicles**: Quản lý danh sách phương tiện, có công cụ tìm kiếm theo biển số / RFID UID.
4. **Payments**: Bảng kê chi tiết thu phí đỗ xe theo phiên, phương thức thanh toán, xác nhận tiền mặt.
5. **History**: Nhật ký kiểm toán (Audit log) ghi lại toàn bộ sự kiện ra vào, quẹt thẻ, nhận diện camera, cảnh báo cảm biến.
6. **Sensors**: Trang chẩn đoán phần cứng chuyên sâu:
   - Gauge nhiệt độ & độ ẩm DHT11.
   - Cảm biến khí CO MQ-7 (ADC, điện áp V_ADC và V_AO).
   - Trạng thái 6 cảm biến hồng ngoại IR LM393 & 2 module RC522.
7. **Settings**: Hướng dẫn cấu hình mạng LAN, kiểm tra kết nối thiết bị và công cụ test kiểm thử dữ liệu End-to-End.

---

## 6. KIỂM THỬ TỰ ĐỘNG (TESTING & VERIFICATION)

Dự án tích hợp sẵn 2 bộ kiểm thử chuyên nghiệp:

### Kiểm tra an toàn tĩnh chân GPIO (Hardware Safety Check):
```bash
python test/test_gpio_static.py
```
*Kết quả: Kiểm tra 21 chân GPIO, đảm bảo không trùng lặp, không gắn sai chân boot strapping, tách biệt ADC1 chống xung đột Wi-Fi.*

### Kiểm tra luồng dữ liệu toàn diện (Full E2E Verification):
```bash
python dashboard/test_telemetry.py
```
*Kết quả: 10 bài test End-to-End tự động kiểm tra đăng nhập JWT, gửi telemetry ESP32, đồng bộ trạng thái 4 slot, nhịp tim camera, upload ảnh ANPR, quẹt thẻ RFID và tính phí đỗ xe.*

---

## 7. QUY TẮC TOÀN VẸN DỮ LIỆU (ZERO FAKE DATA)

Hệ thống hoạt động trên nguyên tắc kỹ thuật trung thực:
- Trạng thái kết nối của ESP32 và Camera hiển thị **ONLINE** khi nhận được nhịp tim thật trong 10-15 giây gần nhất; hiển thị **OFFLINE** khi mất tín hiệu.
- Dữ liệu 4 ô đỗ xe phản ánh trực tiếp từ cảm biến quang học hồng ngoại IR.
- Nếu camera chưa gửi ảnh hoặc không nhận diện được biển số, hệ thống trả về thông báo rõ ràng (`ANPR_UNAVAILABLE` hoặc `PLATE_NOT_DETECTED`), tuyệt đối **không fake biển số**.
