# SMART PARKING IoT — HƯỚNG DẪN WEB MOBILE & TRIỂN KHAI NETLIFY

Tài liệu hướng dẫn toàn diện về giao diện Web Mobile, PWA (Progressive Web App), cấu hình API kết nối thật, và các bước triển khai Frontend lên Netlify.

---

## 1. TỔNG QUAN KIẾN TRÚC & ZERO FAKE DATA

Hệ thống hoạt động theo mô hình một nguồn dữ liệu thật duy nhất (**Single Source of Truth**):

```text
                  ┌────────────────────────────────────────────────────────┐
                  │                 HỆ THỐNG PHẦN CỨNG THẬT                 │
                  │  ESP32 DevKit V1 (6 IR, 2 RFID, 2 Barrier, DHT11, MQ-7) │
                  │  2x ESP32-CAM AI-Thinker (Entry & Exit ANPR)           │
                  └───────────────────────────┬────────────────────────────┘
                                              │ HTTP Telemetry Heartbeat 3s & ANPR Capture
                                              ▼
                  ┌────────────────────────────────────────────────────────┐
                  │                 BACKEND REST API SERVER                │
                  │  Python Flask (Port 5000) • SQLite (parking.db)         │
                  │  Logic Tính Phí: 5.000 VNĐ / 5 Giây (Demo Rule)         │
                  │  Server-Sent Events (SSE) / Polling Realtime           │
                  └───────────────┬────────────────────────┬───────────────┘
                                  │                        │
               Cùng API & CSDL    │                        │   Cùng API & CSDL
                                  ▼                        ▼
     ┌───────────────────────────────────┐    ┌───────────────────────────────────┐
     │       DESKTOP DASHBOARD           │    │       MOBILE WEB APP / PWA        │
     │  - Màn hình rộng (> 768px)        │    │  - Màn hình điện thoại (<= 768px) │
     │  - Đầy đủ Sidebar + KPI + 7 View  │    │  - Apple/iOS Glass Design         │
     │  - Quản trị viên & Chẩn đoán      │    │  - Bottom Tabbar 5 màn hình       │
     │  - Giữ nguyên 100% tính năng cũ   │    │  - Thao tác cảm ứng ngón tay      │
     └───────────────────────────────────┘    └───────────────────────────────────┘
```

---

## 2. CÁCH CHẠY LOCAL (TRÊN MÁY TÍNH)

### Bước 1: Khởi động Backend & Dashboard Server
Tại thư mục gốc của dự án, mở Terminal / PowerShell và chạy:

```bash
python run_dashboard.py
```

Server sẽ tự động:
- Khởi tạo cơ sở dữ liệu `parking.db`.
- Lắng nghe trên mọi giao diện mạng: `0.0.0.0:5000`.
- Tự động mở trình duyệt tại: `http://localhost:5000`.

### Bước 2: Đăng nhập hệ thống
- **Tài khoản mặc định:** `admin`
- **Mật khẩu:** `admin123`

---

## 3. CÁCH TEST GIAO DIỆN MOBILE TRÊN MÁY TÍNH & ĐIỆN THOẠI

### Cách A: Test Mobile trực tiếp trên trình duyệt máy tính (Chrome / Safari / Edge DevTools)
1. Mở `http://localhost:5000` trên trình duyệt.
2. Bấm phím **F12** (hoặc chuột phải chọn **Inspect / Kiểm tra**).
3. Bấm tổ hợp phím **Ctrl + Shift + M** (hoặc icon điện thoại/tablet) để kích hoạt **Device Toolbar**.
4. Chọn thiết bị kiểm thử:
   - **iPhone 12 / 13 / 14 / 15 Pro** (390 x 844 px)
   - **iPhone SE** (375 x 667 px)
   - **iPhone 14 / 15 Pro Max** (430 x 932 px)
   - **Samsung Galaxy S20 / S21** (360 x 800 px)
5. Giao diện tự động chuyển sang **Mobile App Shell**:
   - Header hiển thị logo, badge trạng thái Online/Offline, đồng hồ realtime.
   - Thẻ Hero Sức chứa bãi đỗ xe: 4 Slots, Available, Occupied.
   - Bản đồ 4 ô đỗ P1–P4 với thông tin biển số, thời gian đỗ, phí tạm tính 5.000đ/5s.
   - Điều khiển barrier với hộp thoại xác nhận an toàn (Confirm Dialog).
   - Bottom Tabbar 5 tab: **Home**, **Parking**, **Session**, **Payment**, **System**.

### Cách B: Mở trực tiếp trên điện thoại thật (cùng mạng Wi-Fi LAN)
1. Đảm bảo điện thoại và máy tính kết nối vào **cùng một mạng Wi-Fi** (2.4GHz hoặc 5GHz).
2. Mở PowerShell trên máy tính, gõ:
   ```powershell
   ipconfig
   ```
   Tìm dòng `IPv4 Address`, ví dụ: `192.168.0.103` (hoặc `192.168.1.x`).
3. Mở trình duyệt Safari (trên iPhone) hoặc Chrome (trên Android) và truy cập:
   ```text
   http://192.168.0.103:5000
   ```
4. Đăng nhập với tài khoản `admin` / `admin123`.

---

## 4. CÀI ĐẶT PWA — "ADD TO HOME SCREEN" NHƯ ỨNG DỤNG ĐIỆN THOẠI

Hệ thống đã tích hợp sẵn **Progressive Web App (PWA)**:

- **Trên iPhone (Safari):**
  1. Mở trang web Smart Parking.
  2. Bấm vào nút **Share** (icon hình vuông có mũi tên trỏ lên ở thanh dưới Safari).
  3. Cuộn xuống và chọn **"Add to Home Screen"** (Thêm vào Màn hình chính).
  4. Bấm **Add**. Ứng dụng sẽ xuất hiện trên màn hình chính với icon quả táo Apple Smart Parking và mở không viền trình duyệt.

- **Trên Android (Chrome):**
  1. Mở trang web Smart Parking.
  2. Bấm vào nút menu 3 chấm ở góc trên bên phải.
  3. Chọn **"Add to Home screen"** hoặc **"Install app"** (Cài đặt ứng dụng).

> **Lưu ý về Dữ liệu Realtime trong PWA:**
> Service Worker (`sw.js`) chỉ cache tài nguyên tĩnh (HTML/CSS/JS/Icons/Fonts) để app mở tức thì; toàn bộ API `/api/*`, sự kiện SSE `/api/events`, và ảnh camera `/uploads/*` đều là **Network Only**, cam kết không bao giờ hiển thị dữ liệu cũ.

---

## 5. ĐỒNG BỘ LOGIC TÍNH PHÍ (DEMO BILLING RATE)

Quy tắc tính phí đồng bộ 100% giữa **Firmware ESP32**, **Backend Python Flask**, và **Giao diện Desktop + Mobile**:

- **Đơn giá:** `5.000 VNĐ / 5 giây` (1 block = 5.000 VNĐ mỗi 5 giây).
- **Công thức:**
  $$\text{Số block} = \left\lceil \frac{\text{Thời gian (giây)}}{5} \right\rceil = \frac{\text{duration} + 4}{5}$$
  $$\text{Phí} = \text{Số block} \times 5.000 \text{ VNĐ}$$
  - Xe đỗ 1–5 giây: 5.000 VNĐ
  - Xe đỗ 6–10 giây: 10.000 VNĐ
  - Xe đỗ 11–15 giây: 15.000 VNĐ
- **API tính phí trực tiếp:** `GET /api/parking/fee?duration=<seconds>`

---

## 6. DANH SÁCH API ENDPOINTS SỬ DỤNG

| Endpoint | Method | Chức năng | Dữ liệu trả về |
| :--- | :---: | :--- | :--- |
| `/api/auth/login` | POST | Đăng nhập tài khoản | JWT Token & User Profile |
| `/api/status` | GET | Toàn bộ trạng thái hệ thống | 4 Slots, Môi trường, Barrier, RFID, Cameras, Sessions |
| `/api/parking/slots` | GET | Chi tiết 4 ô đỗ P1–P4 | Trạng thái, biển số, mã RFID, thời gian đỗ, phí tạm tính |
| `/api/parking/fee` | GET | Tính phí đỗ xe theo thời gian thực | Phí (VND) theo rule 5.000đ/5s |
| `/api/barrier/control` | POST | Điều khiển Barrier Cổng Vào / Cổng Ra | ID lệnh PENDING cho ESP32 |
| `/api/cameras/status` | GET | Trạng thái thực tế 2 camera | Online/Offline, snapshot JPEG, biển số ANPR |
| `/api/payments` | GET | Lịch sử các giao dịch thu phí | Danh sách phiên, số tiền, trạng thái PAID |
| `/api/history` | GET | Nhật ký kiểm toán toàn hệ thống | Lịch sử sự kiện cảm biến, quẹt thẻ, camera |
| `/api/sensors` | GET | Chẩn đoán phần cứng chuyên sâu | Nhiệt độ, độ ẩm, MQ-7 ADC & điện áp V_ADC, V_AO |
| `/api/events` | GET | Server-Sent Events (SSE) | Luồng đẩy dữ liệu realtime về client |

---

## 7. CẤU HÌNH & TRIỂN KHAI FRONTEND LÊN NETLIFY

### 7.1. Cấu hình Build & Publish
Dự án đã được cấu hình sẵn cho Netlify qua file `netlify.toml` và `package.json`:

- **Framework:** Vanilla Web (HTML5/CSS3/JavaScript ES6)
- **Build command:** `npm run build`
- **Publish directory:** `dist`
- **Redirects:** `/*  /index.html  200` (đã có trong `dist/_redirects` và `netlify.toml`)

### 7.2. Các bước triển khai lên tài khoản Netlify (`vanloi18`)

Bạn có 2 cách cực kỳ nhanh để deploy lên team của bạn tại `https://app.netlify.com/teams/vanloi18/projects`:

#### CÁCH 1: Kéo thả thư mục (Netlify Drop — Nhanh nhất, mất 30 giây)
1. Trên máy tính, chạy lệnh build để sinh thư mục `dist`:
   ```bash
   npm run build
   ```
2. Mở trình duyệt, truy cập: [https://app.netlify.com/teams/vanloi18/projects](https://app.netlify.com/teams/vanloi18/projects)
3. Kéo toàn bộ thư mục **`F:\Desktop\Smart_Parking_IoT\dist`** và thả vào vùng **"Want to deploy a new site without connecting to Git? Drag and drop your site output folder here"**.
4. Netlify sẽ tự động cấp một URL public HTTPS (ví dụ: `https://smart-parking-iot-xyz.netlify.app`).

#### CÁCH 2: Kết nối qua Git Repository (Khuyến nghị để Auto Deploy)
1. Push mã nguồn lên GitHub / GitLab cá nhân.
2. Tại dashboard Netlify, bấm **"Add new site"** -> **"Import an existing project"**.
3. Chọn repo `Smart_Parking_IoT`.
4. Nhập các thông số sau:
   - **Base directory:** (để trống)
   - **Build command:** `npm run build`
   - **Publish directory:** `dist`
5. Bấm **Deploy Site**.

---

## 8. KẾT NỐI FRONTEND NETLIFY VỚI BACKEND (QUAN TRỌNG)

### Vấn đề kỹ thuật:
- Netlify là dịch vụ lưu trữ tĩnh (Static Hosting), **chỉ chứa giao diện Frontend (HTML, CSS, JS)**.
- Backend Python Flask (`run_dashboard.py`) và SQLite đang chạy trên **máy tính của bạn**.
- Nếu Frontend trên Netlify gọi tới `http://localhost:5000`, chỉ có máy tính của bạn truy cập được; **điện thoại khi mở link Netlify sẽ KHÔNG THỂ kết nối tới máy tính nếu máy tính chưa được mở ra Internet**.

### Giải pháp mở Backend ra Internet để Điện thoại ngoài LAN truy cập:
Bạn chỉ cần chọn **1 trong 2 công cụ miễn phí sau** để tạo URL HTTPS an toàn cho Backend:

#### Lựa chọn A: Sử dụng Cloudflare Tunnel (Miễn phí 100%, không cần tài khoản)
Tải `cloudflared.exe` và chạy lệnh:
```bash
cloudflared tunnel --url http://localhost:5000
```
Cloudflare sẽ cung cấp một đường dẫn HTTPS công khai, ví dụ: `https://my-parking-api.trycloudflare.com`.

#### Lựa chọn B: Sử dụng ngrok
Chạy lệnh:
```bash
ngrok http 5000
```
ngrok sẽ cung cấp một đường dẫn HTTPS, ví dụ: `https://abc-123.ngrok-free.app`.

### Cấu hình URL Backend trên giao diện Mobile:
1. Mở trang web Smart Parking trên điện thoại (qua link Netlify).
2. Tại thanh Header, bấm vào biểu tượng **Mạng / Cài đặt** (icon cáp mạng bên cạnh nút làm mới).
3. Nhập đường dẫn Backend URL của bạn (ví dụ: `https://my-parking-api.trycloudflare.com` hoặc `http://192.168.0.103:5000` nếu trong LAN).
4. Bấm **"Kiểm tra kết nối (Ping)"** để xác nhận phản hồi từ server.
5. Bấm **"Lưu cấu hình"**. 
Toàn bộ dữ liệu thật, trạng thái 4 slot, camera, và lệnh barrier sẽ kết nối trực tiếp với bãi đỗ xe của bạn!

---

## 9. KHẮC PHỤC SỰ CỐ (TROUBLESHOOTING)

1. **Điện thoại báo "Mất kết nối Backend Server":**
   - Kiểm tra `run_dashboard.py` đã chạy trên máy tính chưa.
   - Kiểm tra Windows Defender Firewall: Cho phép cổng 5000 (Inbound Rule).
   - Kiểm tra điện thoại và máy tính có cùng kết nối chung mạng Wi-Fi không (nếu dùng IP LAN).
2. **Cổng Barrier bấm không phản hồi:**
   - Kiểm tra ESP32 DevKit V1 đã kết nối Wi-Fi chưa (đèn Neopixel / Serial Monitor).
   - Kiểm tra trạng thái ESP32 trên mục System Matrix có báo **ONLINE** không.
3. **Camera báo "Chưa có ảnh":**
   - Đây là trạng thái trung thực (Zero Fake Data). Khi xe quẹt thẻ hoặc ESP32-CAM gửi capture lên server, ảnh sẽ xuất hiện tức thì trên màn hình.

---

## 10. KIỂM THỬ TỰ ĐỘNG

Chạy lệnh kiểm thử tự động toàn diện:
```bash
python dashboard/test_telemetry.py
```
Kết quả mong muốn: **10/10 bài test PASS (100% Successful)** bao gồm đăng nhập JWT, đồng bộ 4 ô đỗ, nhịp tim camera, upload ảnh ANPR, quẹt thẻ RFID và tính phí demo 5.000đ/5s.
