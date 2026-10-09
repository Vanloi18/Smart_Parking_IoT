# Kết quả A/B/C và đề xuất D — 09/10/2026

## A — Đã dọn DB thật

Dry-run đầy đủ từng dòng/giá trị/ảnh: `dashboard/sample_cleanup_plan_20261009_185831_587678.md`.
Backup trước xóa: `dashboard/parking.db.bak_20261009_190010_678008`.
Integrity check: `ok`; SHA-256:
`b90f056dab9125665d1233d6161eff09748df61dd025b4306ed1a8b4a648a1a6`.
Kết quả chi tiết: `dashboard/parking.db.bak_20261009_190010_678008_cleanup_result.json`.
Backup ảnh: thư mục `dashboard/parking.db.bak_20261009_190010_678008_images`.

Đã xóa 36 dòng, 6 JPEG mẫu có fingerprint đã xác minh:

| Bảng | ID đã xóa |
|---|---|
| payments | 1, 6, 7, 8 |
| camera_events | 7, 8, 9, 10, 11, 12 |
| parking_sessions | 9, 10, 11, 12 |
| vehicles | 2 |
| parking_transactions | 15 |
| system_events | 3–8, 57–62, 65–68, 71–74 |

Ảnh: entry `20261007_135918_241`, `140027_885`, `140219_221`;
exit `20261007_135919_623`, `140029_144`, `140221_360`, đều đuôi `.jpg`.
Đối chiếu trước/sau đạt: các bảng bảo vệ, sự kiện camera từ 17:18 hôm nay và SHA-256 ảnh thật giữ nguyên.
Không còn phiên mẫu PARKED; DB integrity `ok`, foreign_key_check không có lỗi.
Lỗi thanh toán mẫu id=1 tham chiếu session không tồn tại cũng hết sau khi xóa đúng dòng mẫu.
Lệnh camera hiện không có bằng chứng UID/plate mẫu, nên không xóa lệnh hoặc camera_status thật.
Các trường RFID cuối trong cache system_state được giữ nguyên, không reset heartbeat/trạng thái.

Chạy lại trước demo:

```powershell
python -B scripts/clean_sample_data.py --dry-run
# Xem báo cáo mới, dừng backend rồi mới áp dụng đúng báo cáo đã duyệt.
python -B scripts/clean_sample_data.py --apply --approved-report "dashboard/<bao-cao-moi>.json"
python -B -u run_dashboard.py
```

## B — Tesseract đã cài; OCR thật chưa đạt

Winget cài Tesseract 5.4.0.20240606 tại `C:\Program Files\Tesseract-OCR\tesseract.exe`.
pytesseract 0.3.13 được cài bằng đúng executable backend:
`C:\Users\levan\AppData\Local\Python\bin\python.exe` (Python 3.14.6).
Không đổi Python của backend, không cập nhật các dependency khác.
Phiên bản cần thiết được pin trong `dashboard/backend/requirements.txt`.
Đã thêm mẫu TESSERACT_CMD/OCR_MIN_CONFIDENCE trong `.env.example`; không sửa/hiển thị `.env`.
Nếu cài lại máy: `python -m pip install -r dashboard/backend/requirements.txt` và cài Tesseract Windows bằng winget.

Thử 4 ảnh thật sau 18:45: `entry_cam_20261009_185151_365.jpg`,
`entry_cam_20261009_185152_580.jpg`, `entry_cam_20261009_185213_654.jpg`,
`exit_cam_20261009_185237_557.jpg`. Bảng benchmark: `scripts/ocr_real_20261009.csv`.
Đã xem ảnh thứ ba và thứ tư: biển hiển thị trên màn hình điện thoại là `99-E1 / 222.68`, ảnh hơi mờ.

| Ảnh | OCR thô toàn ảnh | Điểm engine 0–100 |
|---|---|---|
| entry ...185213_654 | `|`, `99-E]`, `|`, `222.68` | 56, 51, 88, 86 |
| exit ...185237_557 | `Peal`, `22.68` | 5, 76 |

Crop đơn giản, ảnh xám, tăng tương phản và phóng 2x không cải thiện thành biển hợp lệ.
Thử cắt hai dòng trên ROI với whitelist: dòng đầu đọc `199-F1I` hoặc `199-F7`, điểm 0;
dòng dưới đọc `222.68`, `1222.68` hoặc `22.68`, điểm 0. Không ép các chuỗi này thành biển đúng.
Do chưa có cải thiện đã chứng minh, backend giữ ảnh màu gốc và thử cả ảnh/cắt hai phần ngang;
không bật contrast/upscale/crop cố định mặc định. Không dùng hint và không gán confidence cứng.
OCR dưới 0.70 hoặc lỗi: biển trống, vé vẫn hoạt động. Điểm OCR không phải xác suất đúng đã hiệu chuẩn.
Cần ảnh rõ, đủ sáng, biển chiếm vùng lớn; thêm ảnh/nhãn thật để benchmark trước khi cải thiện tiếp.

## C — Vé RFID đã tích hợp backend/dashboard

- UID là định danh vé; thẻ mới có thể nhận lượt vào, không cần đăng ký xe trước.
- Vào khi cùng UID đang PARKED: ALREADY_PARKED; ra không có phiên: NO_OPEN_SESSION. Không tạo lệnh chụp cho lần bị từ chối.
- Entry/exit và lệnh CAPTURE cùng transaction SQLite. Một lần ra chỉ chốt một session/payment.
- Camera poll đổi lệnh thành DISPATCHED; mỗi camera tối đa một lệnh đang xử lý. Raw JPEG gắn vào session_id của lệnh vừa giao.
- Ảnh thủ công không tạo/đóng session hoặc thu tiền. Lệnh hết hạn/ảnh trễ không được suy đoán phiên theo plate/UID gần nhất.
- OCR chỉ điền gợi ý ở phiên chưa nhập biển; không ghi đè biển bảo vệ đã xác nhận. Ảnh exit chỉ để so sánh.
- Khai báo mới: plate_source, needs_plate, missing_entry_image, missing_exit_image, ocr_confidence;
  lệnh camera có session_id, dispatched_at, capture_received_at. UID/time/images/fee/status đã có từ schema cũ.
- Migration chỉ thêm cột và khởi tạo cờ ảnh theo dữ liệu cũ; không xóa bảng/đổi ID hoặc giá trị cũ.
- Backup trước migration: `dashboard/parking.db.bak_20261009_191157_339125`, integrity `ok`, SHA-256
  `dfb806a3f5ca60921186fc4d86f548b57aa005747130be63e1e3e35b4c9ee2ed`.
- Đối chiếu toàn bộ cột cũ của sessions/commands/camera_status/users/telemetry: giữ nguyên sau migration.

Phí giữ quy tắc demo hiện có trong `db.calculate_parking_fee`:
`fee = 5000 * max(1, ceil(duration_seconds / 5))`.
duration_seconds là số giây nguyên từ backend nhận RFID vào tới nhận RFID ra.
Ví dụ 0–5s: 5.000đ, 6–10s: 10.000đ, 11–15s: 15.000đ.
Không thu phí lần nữa khi ảnh ra lên. Mobile không còn tự tính phí dự phòng.
Firmware chính còn công thức tính cục bộ/mốc vào ô; cần duyệt D để LCD thống nhất.

API trả allowed, reason, plate, fee, durationMinutes, duration_seconds, session_id, command_id.
PATCH `/api/parking/sessions/<id>/plate` yêu cầu JWT, chỉ sửa phiên PARKED.
Biển trống được giữ; nhập không đúng định dạng báo lỗi rõ. Chuẩn hóa chỉ bao phủ biển phổ thông,
chưa xác minh tỉnh/serial hoặc biển đặc biệt. Chưa có chứng cứ xử lý nguồn điện/servo/LCD thật.

Web: chọn vé ở mục VÉ GỬI XE, mở hai ảnh cạnh nhau, nhập/xác nhận biển; nút Cập nhật ảnh để tải lại.
Mobile nguồn: nút Ảnh / biển số trong thẻ session. Không đổi ID/class cũ.
APK cũ chưa có các thay đổi nguồn này vì không build/sửa android hoặc dist.

Kiểm thử: 9 bài luồng vé + 3 TTL + 4 cleanup + 7 benchmark mock đạt; JS syntax và mock chi tiết vé đạt.
HTTP thực trên cổng 5001, snapshot DB/ảnh: thẻ lạ ra bị từ chối; vào được, vào trùng bị từ chối;
upload ảnh thật gắn session dù OCR trống; ra được phí tối thiểu 5.000đ; ra trùng bị từ chối.
Server snapshot đã dừng sau kiểm thử. Không POST thử trên backend DB thật, không chạy test_telemetry.py.
Backend thật đã khởi động lại trên 0.0.0.0:5000; localhost và 192.168.0.103 trả HTTP 200.

Tự thử an toàn khi chưa có ESP32 chính (terminal riêng):

```powershell
python -B scripts/run_demo_copy.py
```

Terminal thứ hai (chỉ gọi cổng 5001):

```powershell
Invoke-RestMethod http://127.0.0.1:5001/api/parking/entry -Method Post -ContentType application/json -Body '{"cardUid":"DEMO_TICKET_01","gate":"ENTRY"}'
# Chạy entry lần nữa để thấy ALREADY_PARKED.
Invoke-RestMethod http://127.0.0.1:5001/api/parking/exit -Method Post -ContentType application/json -Body '{"cardUid":"DEMO_TICKET_01","gate":"EXIT"}'
# Chạy exit lần nữa để thấy NO_OPEN_SESSION.
```

Mở `http://127.0.0.1:5001`, đăng nhập bằng tài khoản của bản sao, xem vé/nhập biển khi đang PARKED.
Để thử ảnh bằng tay: GET `/api/cameras/commands?camera_id=ENTRY_CAM` rồi POST raw JPEG tới
`/api/cameras/entry/capture`; tương tự EXIT_CAM. Chỉ poll/gửi JPEG trên cổng 5001.
Ảnh và DB thử nằm trong thư mục Temp được script in ra; Ctrl+C dừng server thử.

## D — Chỉ đề xuất, chưa sửa firmware chính

| Vị trí hiện tại | Lỗi / thay đổi đề nghị |
|---|---|
| src/network/wifi_manager.cpp:206,244; wifi_manager.h:39,42 | Trả kết quả có allowed/reason/plate/fee/duration từ JSON. Bỏ true fallback khi offline/HTTP lỗi; timeout tối đa 3s. HTTP 200 không đồng nghĩa allowed=true. |
| src/parking/parking_fsm.cpp:273,277 | Cổng vào hiện mở trước khi hỏi backend: đổi thành chờ phản hồi, chỉ mở khi allowed=true; bị từ chối thì LCD/buzzer, giữ đóng. |
| src/parking/parking_fsm.cpp:395,421–448 | UID đang chỉ tìm ở RAM và tính phí cục bộ: hỏi backend tại lúc quẹt thẻ ra; lấy plate/fee/duration từ JSON. Không có phản hồi/deny: LCD lỗi, buzzer và không mở barie. Không dùng thiếu biển số làm điều kiện từ chối. |
| src/parking/parking_fsm.cpp:520–530 | Nút exit đang mở barie trước POST exit: chỉ dùng kết quả allowed đã nhận; không POST exit lần hai, không tính phí lần hai. Giữ nút xác nhận hiện có nếu cần demo. |
| src/actuators/barriers.cpp:83,87,102–104,118–120 | Không auto-close khi IR còn vật cản. Kiểm tra trước bước servo khi đang CLOSING; nếu vật cản quay lại thì mở lại. Giữ mở/thử lại khi cảm biến an toàn; sau giới hạn đề xuất 30s báo lỗi và giữ mở, không ép đóng để hết timeout. |
| src/config/config.h:37,40–41; barriers.h | Thêm giới hạn giữ mở/cờ lỗi và cách FSM/LCD/buzzer nhận lỗi; ngừng dùng đơn giá cục bộ. Hằng số cũ có thể giữ để tương thích nhưng không dùng tính phí. |

Đề nghị tối thiểu sửa wifi_manager.cpp/.h, parking_fsm.cpp/.h (nếu thêm trường phản hồi),
barriers.cpp/.h, config.h. Nếu LCD không đủ API thì bổ sung lcd_manager.cpp/.h;
Smart_Parking_IoT.ino chỉ cần đổi khi nối báo lỗi barie. Chưa sửa file nào trong nhóm này.
HTTP đồng bộ vẫn có nguy cơ chặn loop; khi thực hiện D cần bảo đảm chờ mạng không bỏ cập nhật IR/servo,
ưu tiên task/hàng đợi nhỏ cho phản hồi RFID thay vì gọi HTTP giữa chuyển động servo.

Sau khi duyệt: compile main bằng arduino-cli với FQBN đúng board ESP32 chính
(ESP32 Dev Module thường là `esp32:esp32:esp32`), kiểm tra ArduinoJson/servo/RFID/LCD dependencies.
Chỉ compile trước, chưa nạp khi chưa cho phép. Các lần sửa A/B/C không yêu cầu nạp lại board.
Khi mô hình dùng được: thử vào/ra thường, thẻ sai/trùng, rút backend, thiếu ảnh/biển;
LCD phải khớp phí backend. Giữ vật cản quá 5s rồi 30s, barie không đóng; thử vật cản xuất hiện khi đang đóng.
Các bài phần cứng này chưa được kiểm chứng.

## File thay đổi trong lượt MASTER PROMPT

| File | Nội dung |
|---|---|
| scripts/clean_sample_data.py | In từng dòng/ảnh trước apply; chạy xóa thật đúng danh sách đã duyệt |
| dashboard/backend/app.py | API vé/chi tiết/sửa biển; capture chỉ bổ sung ảnh cho lệnh/phiên |
| dashboard/backend/db.py | Migration an toàn; dispatch camera, TTL và adapter record_entry/exit; trả cột phiên mới |
| dashboard/backend/tickets.py | Transaction UID, chốt phí/payment một lần, nối ảnh và xác nhận biển |
| dashboard/backend/anpr_engine.py | Tesseract thật, confidence thật, bỏ hint, lỗi/điểm thấp để trống |
| dashboard/backend/plate_ocr.py | Chuẩn hóa biển phổ thông |
| dashboard/backend/requirements.txt | Pin dependency theo Python backend thực tế |
| .env.example | Mẫu TESSERACT_CMD/OCR_MIN_CONFIDENCE; .env thật không sửa |
| dashboard/frontend/index.html | Panel chọn vé; giữ ID/class cũ |
| dashboard/frontend/js/app.js | Chi tiết hai ảnh, nguồn biển, nhập/xác nhận và lỗi API |
| dashboard/frontend/js/mobile.js | Mở chi tiết vé; bỏ tự tính phí |
| test/test_camera_commands.py | Migration/dispatch trên bản sao để giữ kiểm thử TTL |
| test/test_ticket_flow.py | Kiểm thử vé/OCR/ảnh/migration, không ghi DB thật |
| test/test_ticket_ui.js | Mock DOM/fetch cho hai ảnh và lưu biển |
| scripts/run_demo_copy.py | Backend thử trên DB/ảnh Temp, chỉ localhost:5001 |
| scripts/ocr_real_20261009.csv | Bảng thử 4 ảnh mới bằng Tesseract |
| scripts/MASTER_REPORT_20261009.md | Báo cáo, hướng dẫn thử và đề xuất D |

Mail alerts chưa có implementation trong nguồn; không thêm ngoài phạm vi MASTER PROMPT.
Không sửa dist/android/firmware, không build APK, không nạp firmware.
Chưa sửa DATABASE_PATH từ .env (ngoài phạm vi lần này); server thử dùng override DB_PATH riêng.
