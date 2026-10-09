/**
 * SMART PARKING IoT — APPLE-LIKE FRONTEND CONTROLLER (JAVASCRIPT)
 * ==============================================================
 * Route Protection • Session Management • Realtime SSE • Full Views
 * Zero Fake Data — Phản ánh chính xác 100% dữ liệu phần cứng.
 */

function getApiBase() {
    const custom = localStorage.getItem("sp_api_base_url");
    if (custom) return custom.trim().replace(/\/+$/, "");
    if (window.AndroidNative && typeof window.AndroidNative.getDefaultBackendUrl === "function") {
        return window.AndroidNative.getDefaultBackendUrl().trim().replace(/\/+$/, "");
    }
    if (window.location.protocol === "file:") {
        return "http://localhost:5000";
    }
    if (window.__API_BASE__) return window.__API_BASE__.trim().replace(/\/+$/, "");
    return "";
}
var API_BASE = getApiBase();
// Đảm bảo API_BASE luôn được làm mới động
setInterval(() => { API_BASE = getApiBase(); }, 1000);
let eventSource = null;
let pollingInterval = null;
let currentActiveView = "dashboard";
let lastSystemData = null;

// ============================================================================
// 1. LIFECYCLE & INITIALIZATION
// ============================================================================

document.addEventListener("DOMContentLoaded", () => {
    initClock();
    checkAuthSession();
    initNavigation();
    detectLocalHostIP();
});

function initClock() {
    function tick() {
        const now = new Date();
        const timeStr = now.toTimeString().split(" ")[0];
        const clockEl = document.getElementById("header-clock");
        if (clockEl) clockEl.innerText = timeStr;
    }
    tick();
    setInterval(tick, 1000);
}

function detectLocalHostIP() {
    const ipSpan = document.getElementById("settings-detected-ip");
    if (ipSpan && window.location.hostname && window.location.hostname !== "localhost") {
        ipSpan.innerText = window.location.hostname;
    }
}

// ============================================================================
// 2. AUTHENTICATION & ROUTE GUARDS
// ============================================================================

function checkAuthSession() {
    const token = localStorage.getItem("sp_token");
    const userStr = localStorage.getItem("sp_user");

    const loginView = document.getElementById("login-view");
    const appView = document.getElementById("app-view");

    if (!token || !userStr) {
        // Chưa đăng nhập -> Hiển thị Login, ẩn App
        loginView.classList.remove("hidden");
        appView.classList.add("hidden");
        if (eventSource) {
            eventSource.close();
            eventSource = null;
        }
        if (pollingInterval) {
            clearInterval(pollingInterval);
            pollingInterval = null;
        }
    } else {
        // Đã đăng nhập -> Hiển thị App
        loginView.classList.add("hidden");
        appView.classList.remove("hidden");

        try {
            const user = JSON.parse(userStr);
            renderUserProfile(user);
        } catch (e) {
            console.error("Failed to parse user profile:", e);
        }

        // Bắt đầu lắng nghe dữ liệu thời gian thực
        fetchFullStatus();
        initRealtimeEvents();
        handleHashRouting();
    }
}

function renderUserProfile(user) {
    const nameEl = document.getElementById("user-display-name");
    const roleEl = document.getElementById("user-display-role");
    const avatarEl = document.getElementById("user-avatar-initials");

    if (nameEl) nameEl.innerText = user.full_name || user.username || "Admin";
    if (roleEl) roleEl.innerText = user.role || "ADMIN";
    if (avatarEl) {
        const initials = (user.username || "AD").slice(0, 2).toUpperCase();
        avatarEl.innerText = initials;
    }
}

async function handleLoginSubmit(event) {
    event.preventDefault();
    const usernameInput = document.getElementById("login-username");
    const passwordInput = document.getElementById("login-password");
    const errorBox = document.getElementById("login-error-alert");
    const errorMsg = document.getElementById("login-error-msg");
    const submitBtn = document.getElementById("btn-login-submit");

    errorBox.classList.add("hidden");
    submitBtn.disabled = true;
    submitBtn.innerHTML = '<span>Đang xác thực...</span> <i class="fa-solid fa-spinner fa-spin"></i>';

    try {
        const resp = await fetch(`${API_BASE}/api/auth/login`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({
                username: usernameInput.value.trim(),
                password: passwordInput.value.trim()
            })
        });

        const data = await resp.json();

        if (resp.ok && data.token) {
            localStorage.setItem("sp_token", data.token);
            localStorage.setItem("sp_user", JSON.stringify(data.user));
            usernameInput.value = "";
            passwordInput.value = "";
            checkAuthSession();
        } else {
            errorMsg.innerText = data.message || "Tên đăng nhập hoặc mật khẩu không chính xác.";
            errorBox.classList.remove("hidden");
        }
    } catch (err) {
        errorMsg.innerText = "Lỗi kết nối tới Backend Server: " + err.message;
        errorBox.classList.remove("hidden");
    } finally {
        submitBtn.disabled = false;
        submitBtn.innerHTML = '<span>Đăng nhập</span> <i class="fa-solid fa-arrow-right"></i>';
    }
}

function handleLogout() {
    localStorage.removeItem("sp_token");
    localStorage.removeItem("sp_user");
    checkAuthSession();
}

function getAuthHeader() {
    const token = localStorage.getItem("sp_token");
    return token ? { "Authorization": `Bearer ${token}` } : {};
}

// ============================================================================
// 3. NAVIGATION & VIEW SWITCHING
// ============================================================================

function initNavigation() {
    window.addEventListener("hashchange", handleHashRouting);

    const navLinks = document.querySelectorAll(".nav-item");
    navLinks.forEach(link => {
        link.addEventListener("click", (e) => {
            const targetView = link.getAttribute("data-view");
            if (targetView) {
                switchView(targetView);
            }
        });
    });
}

function handleHashRouting() {
    const hash = window.location.hash.replace("#", "").trim();
    const validViews = ["dashboard", "parking", "vehicles", "payments", "history", "sensors", "settings"];
    if (validViews.includes(hash)) {
        switchView(hash);
    } else {
        switchView("dashboard");
    }
}

function switchView(viewName) {
    currentActiveView = viewName;

    // Cập nhật active link
    document.querySelectorAll(".nav-item").forEach(el => {
        el.classList.toggle("active", el.getAttribute("data-view") === viewName);
    });

    // Cập nhật pane
    document.querySelectorAll(".view-pane").forEach(pane => {
        pane.classList.remove("active");
    });
    const activePane = document.getElementById(`view-${viewName}`);
    if (activePane) activePane.classList.add("active");

    // Cập nhật tiêu đề Header
    const titles = {
        "dashboard": { title: "Dashboard", sub: "Tổng quan bãi đỗ xe thời gian thực" },
        "parking":   { title: "Parking Lots", sub: "Trạng thái chi tiết 4 vị trí ô đỗ P1 - P4" },
        "vehicles":  { title: "Vehicles", sub: "Quản lý danh sách phương tiện ra vào" },
        "payments":  { title: "Payments", sub: "Lịch sử thu phí đỗ xe theo phiên" },
        "history":   { title: "System History", sub: "Nhật ký kiểm toán sự kiện toàn hệ thống" },
        "sensors":   { title: "Hardware Sensors", sub: "Chẩn đoán chi tiết 6 IR, 2 RFID, DHT11 & MQ-7" },
        "settings":  { title: "Settings & Guide", sub: "Cấu hình Wi-Fi LAN và công cụ kiểm thử" }
    };

    const info = titles[viewName] || titles["dashboard"];
    document.getElementById("page-title").innerText = info.title;
    document.getElementById("page-subtitle").innerText = info.sub;

    // Load view data
    if (viewName === "parking") loadParkingView();
    else if (viewName === "vehicles") loadVehiclesView();
    else if (viewName === "payments") loadPaymentsView();
    else if (viewName === "history") loadHistoryView();
    else if (viewName === "sensors") loadSensorsView();
}

// ============================================================================
// 4. REALTIME DATA HANDLING (SSE & POLLING)
// ============================================================================

function initRealtimeEvents() {
    if (eventSource) eventSource.close();

    try {
        eventSource = new EventSource(`${API_BASE}/api/events`);

        eventSource.onopen = () => {
            console.log("[SSE] Realtime connection established.");
            if (pollingInterval) {
                clearInterval(pollingInterval);
                pollingInterval = null;
            }
        };

        eventSource.onmessage = (event) => {
            try {
                const message = JSON.parse(event.data);
                handleIncomingMessage(message);
            } catch (e) {
                console.warn("[SSE] Parse error:", e);
            }
        };

        eventSource.onerror = () => {
            console.warn("[SSE] Error. Falling back to HTTP polling...");
            eventSource.close();
            if (!pollingInterval) {
                pollingInterval = setInterval(fetchFullStatus, 2500);
            }
            setTimeout(initRealtimeEvents, 5000);
        };
    } catch (err) {
        if (!pollingInterval) {
            pollingInterval = setInterval(fetchFullStatus, 2500);
        }
    }
}

function handleIncomingMessage(msg) {
    const type = msg.type;
    const data = msg.data;

    if (type === "telemetry" || type === "init" || type === "barrier_override") {
        updateAllDashboardComponents(data);
    } else if (type === "camera_capture" || type === "camera_event") {
        fetchFullStatus();
        if (currentActiveView === "history") loadHistoryView();
    } else if (type === "entry_granted" || type === "exit_granted") {
        fetchFullStatus();
    }
}

async function fetchFullStatus() {
    try {
        const resp = await fetch(`${API_BASE}/api/parking/status`, {
            headers: { ...getAuthHeader() }
        });
        if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
        const data = await resp.json();
        updateAllDashboardComponents(data);
    } catch (e) {
        console.error("fetchFullStatus failed:", e);
    }
}

// ============================================================================
// 5. UPDATE DASHBOARD UI WITH REAL DATA (ZERO FAKE DATA)
// ============================================================================

function updateAllDashboardComponents(data) {
    if (!data) return;
    lastSystemData = data;

    // 1. KPI Cards
    const total = data.total_slots || 4;
    const occupied = data.occupied_slots !== undefined ? data.occupied_slots : 0;
    const free = data.free_slots !== undefined ? data.free_slots : (total - occupied);

    document.getElementById("kpi-total-slots").innerText = total;
    document.getElementById("kpi-available-slots").innerText = free;
    document.getElementById("kpi-occupied-slots").innerText = occupied;

    const rate = Math.round((occupied / total) * 100);
    const rateSub = document.getElementById("kpi-rate-sub");
    if (rateSub) rateSub.innerText = `Tỉ lệ chiếm dụng: ${rate}%`;

    const availChip = document.getElementById("kpi-avail-chip");
    if (availChip) {
        if (free === 0) {
            availChip.innerText = "BÃI ĐẦY";
            availChip.className = "kpi-sub status-chip chip-red";
        } else {
            availChip.innerText = "SẴN SÀNG";
            availChip.className = "kpi-sub status-chip chip-green";
        }
    }

    // 2. Cảm biến khí MQ-7
    const env = data.environment || {};
    const gasLvl = (env.gas_level || "NORMAL").toUpperCase();
    const gasRaw = env.gas_raw || 0;
    const gasLevelEl = document.getElementById("kpi-gas-level");
    const gasAdcEl = document.getElementById("kpi-gas-adc");
    const gasSubEl = document.getElementById("kpi-gas-sub");
    const gasCardEl = document.getElementById("card-kpi-gas");

    if (gasLevelEl) {
        gasLevelEl.innerText = gasLvl;
        gasAdcEl.innerText = `(ADC: ${gasRaw})`;

        if (gasLvl === "DANGER") {
            gasLevelEl.className = "kpi-value val-red";
            gasSubEl.innerText = "CẢNH BÁO NGUY HIỂM!";
            if (gasCardEl) gasCardEl.style.borderColor = "var(--apple-red)";
        } else if (gasLvl === "WARNING") {
            gasLevelEl.className = "kpi-value val-orange";
            gasSubEl.innerText = "Khí gas vượt ngưỡng";
            if (gasCardEl) gasCardEl.style.borderColor = "var(--apple-orange)";
        } else {
            gasLevelEl.className = "kpi-value val-green";
            gasSubEl.innerText = "Không khí an toàn";
            if (gasCardEl) gasCardEl.style.borderColor = "var(--border-color)";
        }
    }

    // 3. Cập nhật 4 Ô Đỗ (P1..P4) Map
    const slots = data.slots || {};
    ["P1", "P2", "P3", "P4"].forEach(sId => {
        const isOcc = slots[sId] === 1 || slots[sId] === true;
        updateSlotBoxUI(sId, isOcc);
    });

    // 4. Barriers & RFIDs
    const barriers = data.barriers || {};
    const rfid = data.rfid || {};

    const entryTag = document.getElementById("dash-barrier-entry-tag");
    const exitTag = document.getElementById("dash-barrier-exit-tag");
    if (entryTag) {
        entryTag.innerText = barriers.entry || "CLOSED";
        entryTag.className = `status-chip ${barriers.entry === "OPEN" ? "chip-open" : "chip-closed"}`;
    }
    if (exitTag) {
        exitTag.innerText = barriers.exit || "CLOSED";
        exitTag.className = `status-chip ${barriers.exit === "OPEN" ? "chip-open" : "chip-closed"}`;
    }

    const rfidEntryUid = document.getElementById("dash-rfid-entry-uid");
    const rfidExitUid = document.getElementById("dash-rfid-exit-uid");
    if (rfidEntryUid) rfidEntryUid.innerText = rfid.last_entry_card || "Chưa có thẻ";
    if (rfidExitUid) rfidExitUid.innerText = rfid.last_exit_card || "Chưa có thẻ";

    // 5. Trạng thái Thiết bị (Main ESP32, Cameras)
    updateDeviceStatusIndicators(data);

    // 6. Camera Monitor Cards
    updateCameraWidgets(data);

    // 7. Lần đồng bộ
    const sys = data.system || {};
    if (sys.last_heartbeat) {
        const syncEl = document.getElementById("header-sync-time");
        if (syncEl) syncEl.innerText = formatTimeStr(sys.last_heartbeat);
    }

    // 8. Recent Activity Table
    const recentTxns = data.recent_transactions || [];
    const recentSessions = data.recent_sessions || [];
    renderRecentActivityTable(recentSessions, recentTxns);

    // 9. Đồng bộ tức thời tới Giao diện Web Mobile
    if (typeof window.updateMobileDashboard === "function") {
        window.updateMobileDashboard(data);
    }
}

function updateSlotBoxUI(slotId, isOccupied) {
    const cardEl = document.getElementById(`slot-card-${slotId}`);
    const pillEl = document.getElementById(`slot-pill-${slotId}`);
    const carVisual = document.getElementById(`car-visual-${slotId}`);
    const emptyVisual = document.getElementById(`empty-visual-${slotId}`);

    if (!cardEl || !pillEl) return;

    if (isOccupied) {
        cardEl.className = "slot-box is-occupied";
        pillEl.innerText = "OCCUPIED";
        pillEl.className = "slot-status-pill pill-occ";
        if (carVisual) carVisual.classList.remove("hidden");
        if (emptyVisual) emptyVisual.classList.add("hidden");
    } else {
        cardEl.className = "slot-box is-available";
        pillEl.innerText = "AVAILABLE";
        pillEl.className = "slot-status-pill pill-avail";
        if (carVisual) carVisual.classList.add("hidden");
        if (emptyVisual) emptyVisual.classList.remove("hidden");
    }
}

function updateDeviceStatusIndicators(data) {
    const sys = data.system || {};
    const cams = data.cameras || {};

    // Main ESP32
    const mainDot = document.getElementById("dot-main-esp");
    const mainText = document.getElementById("text-main-esp");
    const isMainOnline = sys.esp32_status === "CONNECTED";

    if (mainDot) mainDot.className = `dot-indicator ${isMainOnline ? "is-online" : "is-offline"}`;
    if (mainText) {
        mainText.innerText = isMainOnline ? "ONLINE" : "OFFLINE";
        mainText.style.color = isMainOnline ? "var(--apple-green)" : "var(--apple-red)";
    }

    // Cameras
    const entryCam = cams.entry || {};
    const exitCam = cams.exit || {};

    const entryDot = document.getElementById("dot-entry-cam");
    const entryText = document.getElementById("text-entry-cam");
    if (entryDot) entryDot.className = `dot-indicator ${entryCam.online ? "is-online" : "is-offline"}`;
    if (entryText) {
        entryText.innerText = entryCam.online ? "ONLINE" : "OFFLINE";
        entryText.style.color = entryCam.online ? "var(--apple-green)" : "var(--apple-red)";
    }

    const exitDot = document.getElementById("dot-exit-cam");
    const exitText = document.getElementById("text-exit-cam");
    if (exitDot) exitDot.className = `dot-indicator ${exitCam.online ? "is-online" : "is-offline"}`;
    if (exitText) {
        exitText.innerText = exitCam.online ? "ONLINE" : "OFFLINE";
        exitText.style.color = exitCam.online ? "var(--apple-green)" : "var(--apple-red)";
    }
}

function updateCameraWidgets(data) {
    const cams = data.cameras || {};
    const entry = cams.entry || {};
    const exit = cams.exit || {};

    // Chips
    const chipEntry = document.getElementById("chip-cam-entry");
    const chipExit = document.getElementById("chip-cam-exit");
    if (chipEntry) {
        chipEntry.innerText = `ENTRY: ${entry.online ? "ONLINE" : "OFFLINE"}`;
        chipEntry.className = `status-chip ${entry.online ? "chip-online" : "chip-offline"}`;
    }
    if (chipExit) {
        chipExit.innerText = `EXIT: ${exit.online ? "ONLINE" : "OFFLINE"}`;
        chipExit.className = `status-chip ${exit.online ? "chip-online" : "chip-offline"}`;
    }

    // Details Entry
    const stEntry = document.getElementById("cam-entry-status-text");
    if (stEntry) {
        stEntry.innerText = entry.online ? "ONLINE" : "OFFLINE";
        stEntry.style.color = entry.online ? "var(--apple-green)" : "var(--apple-red)";
    }
    const ipEntry = document.getElementById("dash-cam-entry-ip");
    if (ipEntry) ipEntry.innerText = entry.ip || "N/A";
    const timeEntry = document.getElementById("dash-cam-entry-time");
    if (timeEntry) timeEntry.innerText = entry.frame_time ? formatTimeStr(entry.frame_time) : (entry.last_seen ? formatTimeStr(entry.last_seen) : "--:--:--");
    const plateEntry = document.getElementById("dash-cam-entry-plate");
    if (plateEntry) plateEntry.innerText = entry.plate_number || "--";
    const frameEntry = document.getElementById("feed-frame-entry");
    if (frameEntry) {
        if (entry.image_url) {
            frameEntry.innerHTML = `<img src="${entry.image_url}" alt="Entry Cam Feed" style="width:100%; height:100%; object-fit:cover; border-radius:8px;">`;
        } else {
            frameEntry.innerHTML = `
                <div class="feed-placeholder">
                    <i class="fa-solid fa-camera"></i>
                    <span>Chưa có ảnh</span>
                </div>`;
        }
    }

    // Details Exit
    const stExit = document.getElementById("cam-exit-status-text");
    if (stExit) {
        stExit.innerText = exit.online ? "ONLINE" : "OFFLINE";
        stExit.style.color = exit.online ? "var(--apple-green)" : "var(--apple-red)";
    }
    const ipExit = document.getElementById("dash-cam-exit-ip");
    if (ipExit) ipExit.innerText = exit.ip || "N/A";
    const timeExit = document.getElementById("dash-cam-exit-time");
    if (timeExit) timeExit.innerText = exit.frame_time ? formatTimeStr(exit.frame_time) : (exit.last_seen ? formatTimeStr(exit.last_seen) : "--:--:--");
    const plateExit = document.getElementById("dash-cam-exit-plate");
    if (plateExit) plateExit.innerText = exit.plate_number || "--";
    const frameExit = document.getElementById("feed-frame-exit");
    if (frameExit) {
        if (exit.image_url) {
            frameExit.innerHTML = `<img src="${exit.image_url}" alt="Exit Cam Feed" style="width:100%; height:100%; object-fit:cover; border-radius:8px;">`;
        } else {
            frameExit.innerHTML = `
                <div class="feed-placeholder">
                    <i class="fa-solid fa-camera"></i>
                    <span>Chưa có ảnh</span>
                </div>`;
        }
    }
}

function renderRecentActivityTable(sessions, transactions) {
    const tbody = document.getElementById("dash-recent-table-body");
    if (!tbody) return;

    if ((!sessions || sessions.length === 0) && (!transactions || transactions.length === 0)) {
        tbody.innerHTML = `<tr><td colspan="8" class="text-center text-muted">Chưa có giao dịch hoặc phiên đỗ nào ghi nhận.</td></tr>`;
        return;
    }

    // Ưu tiên hiển thị dữ liệu từ sessions nếu có, kết hợp transactions
    let rowsHtml = "";
    if (sessions && sessions.length > 0) {
        sessions.slice(0, 10).forEach(s => {
            const statusBadge = s.status === "PARKED" 
                ? `<span class="status-chip chip-orange">ĐANG ĐỖ</span>` 
                : `<span class="status-chip chip-green">ĐÃ RA</span>`;

            rowsHtml += `
                <tr>
                    <td><b>#${s.id}</b></td>
                    <td><code>${s.rfid_uid || "N/A"}</code></td>
                    <td><strong>${s.plate_number || "--"}</strong></td>
                    <td>${formatTimeStr(s.entry_time)}</td>
                    <td>${s.exit_time ? formatTimeStr(s.exit_time) : "--:--:--"}</td>
                    <td>${s.duration_seconds ? Math.round(s.duration_seconds / 60) + " phút" : "Đang đỗ"}</td>
                    <td>${s.fee ? s.fee.toLocaleString() + " đ" : "0 đ"}</td>
                    <td>${statusBadge}</td>
                </tr>
            `;
        });
    } else {
        transactions.slice(0, 10).forEach(t => {
            const statusBadge = t.status === "PARKED" 
                ? `<span class="status-chip chip-orange">ĐANG ĐỖ</span>` 
                : `<span class="status-chip chip-green">HOÀN TẤT</span>`;

            rowsHtml += `
                <tr>
                    <td><b>#${t.id}</b></td>
                    <td><code>${t.card_uid}</code></td>
                    <td>--</td>
                    <td>${formatTimeStr(t.entry_time)}</td>
                    <td>${t.exit_time ? formatTimeStr(t.exit_time) : "--:--:--"}</td>
                    <td>${t.duration_seconds ? Math.round(t.duration_seconds / 60) + " phút" : "Đang đỗ"}</td>
                    <td>${t.fee ? t.fee.toLocaleString() + " đ" : "0 đ"}</td>
                    <td>${statusBadge}</td>
                </tr>
            `;
        });
    }

    tbody.innerHTML = rowsHtml;
}

// ============================================================================
// 6. SPECIFIC VIEW LOADERS
// ============================================================================

async function loadParkingView() {
    try {
        const resp = await fetch(`${API_BASE}/api/parking/slots`, { headers: { ...getAuthHeader() } });
        const data = await resp.json();
        const container = document.getElementById("parking-detail-container");
        if (!container) return;

        const slots = data.slots || [];
        container.innerHTML = slots.map(s => {
            const isOcc = s.is_occupied;
            const veh = s.vehicle;
            return `
                <div class="apple-card" style="border-left: 4px solid ${isOcc ? 'var(--apple-orange)' : 'var(--apple-green)'}">
                    <div class="card-head">
                        <h3>Vị Trí ${s.slot_id}</h3>
                        <span class="status-chip ${isOcc ? 'chip-orange' : 'chip-green'}">${s.status}</span>
                    </div>
                    <p class="text-secondary" style="margin-bottom: 8px;">Cập nhật lúc: ${formatTimeStr(s.updated_at)}</p>
                    ${isOcc && veh ? `
                        <div style="background: var(--bg-card-subtle); padding: 12px; border-radius: var(--radius-sm); font-size: 13px;">
                            <div>Biển số: <b>${veh.plate_number}</b></div>
                            <div>Thẻ RFID: <code>${veh.rfid_uid}</code></div>
                            <div>Thời gian đỗ: <b>${Math.round(veh.duration_seconds / 60)} phút</b></div>
                        </div>
                    ` : `<p class="text-muted" style="font-size: 13px;">Ô đỗ đang sẵn sàng đón phương tiện.</p>`}
                </div>
            `;
        }).join("");
    } catch (e) {
        console.error("loadParkingView error:", e);
    }
}

async function loadVehiclesView(searchQuery = "") {
    try {
        const url = searchQuery ? `${API_BASE}/api/vehicles?q=${encodeURIComponent(searchQuery)}` : `${API_BASE}/api/vehicles`;
        const resp = await fetch(url, { headers: { ...getAuthHeader() } });
        const data = await resp.json();
        const tbody = document.getElementById("vehicles-table-body");
        if (!tbody) return;

        const vehicles = data.vehicles || [];
        if (vehicles.length === 0) {
            tbody.innerHTML = `<tr><td colspan="6" class="text-center text-muted" style="padding: 32px;"><i class="fa-solid fa-car-side" style="font-size: 24px; margin-bottom: 8px; display: block; opacity: 0.4;"></i>Chưa có phương tiện trong bãi</td></tr>`;
            return;
        }

        tbody.innerHTML = vehicles.map(v => `
            <tr>
                <td>#${v.id}</td>
                <td><strong>${v.plate_number}</strong></td>
                <td><code>${v.rfid_uid || "N/A"}</code></td>
                <td>${v.current_slot ? `<span class="status-chip chip-orange">${v.current_slot}</span>` : `<span class="status-chip chip-neutral">Ngoài bãi</span>`}</td>
                <td>${v.current_status === 'PARKED' ? '<span class="status-chip chip-orange">ĐANG ĐỖ</span>' : '<span class="status-chip chip-green">ĐÃ RA</span>'}</td>
                <td>${formatTimeStr(v.registered_at)}</td>
            </tr>
        `).join("");
    } catch (e) {
        console.error("loadVehiclesView error:", e);
    }
}

async function loadPaymentsView() {
    try {
        const resp = await fetch(`${API_BASE}/api/payments`, { headers: { ...getAuthHeader() } });
        const data = await resp.json();
        const tbody = document.getElementById("payments-table-body");
        if (!tbody) return;

        const payments = data.payments || [];
        if (payments.length === 0) {
            tbody.innerHTML = `<tr><td colspan="7" class="text-center text-muted">Chưa có bản ghi thanh toán nào.</td></tr>`;
            return;
        }

        tbody.innerHTML = payments.map(p => `
            <tr>
                <td>#${p.id}</td>
                <td><strong>${p.plate_number || "Vãng lai"}</strong></td>
                <td>${p.duration_seconds ? Math.round(p.duration_seconds / 60) + " phút" : "N/A"}</td>
                <td><b style="color: var(--apple-blue);">${p.amount.toLocaleString()} đ</b></td>
                <td><span class="status-chip chip-neutral">${p.payment_method || "CASH"}</span></td>
                <td><span class="status-chip chip-green">${p.payment_status}</span></td>
                <td>${formatTimeStr(p.paid_at)}</td>
            </tr>
        `).join("");
    } catch (e) {
        console.error("loadPaymentsView error:", e);
    }
}

async function loadHistoryView() {
    try {
        const resp = await fetch(`${API_BASE}/api/history`, { headers: { ...getAuthHeader() } });
        const data = await resp.json();
        const container = document.getElementById("history-timeline-container");
        if (!container) return;

        const history = data.history || [];
        if (history.length === 0) {
            container.innerHTML = `<div class="text-center text-muted">Chưa có sự kiện hệ thống nào được ghi nhận.</div>`;
            return;
        }

        container.innerHTML = history.map(h => {
            let icon = "fa-bell";
            if (h.event_type.includes("VEHICLE_ENTERED")) icon = "fa-arrow-right-to-bracket";
            else if (h.event_type.includes("VEHICLE_EXITED")) icon = "fa-arrow-right-from-bracket";
            else if (h.event_type.includes("CAMERA")) icon = "fa-camera";
            else if (h.event_type.includes("SENSOR_ALERT")) icon = "fa-triangle-exclamation";
            else if (h.event_type.includes("PAYMENT")) icon = "fa-receipt";

            return `
                <div class="timeline-item">
                    <div class="timeline-icon"><i class="fa-solid ${icon}"></i></div>
                    <div class="timeline-content">
                        <div class="timeline-title">${h.description}</div>
                        <div class="timeline-meta">${h.details || ''} • ${formatTimeStr(h.timestamp)}</div>
                    </div>
                </div>
            `;
        }).join("");
    } catch (e) {
        console.error("loadHistoryView error:", e);
    }
}

async function loadSensorsView() {
    try {
        const resp = await fetch(`${API_BASE}/api/sensors`, { headers: { ...getAuthHeader() } });
        const data = await resp.json();
        const s = data.sensors || {};
        const env = s.environment || {};

        // Cập nhật DHT11
        const temp = env.temperature_c || 0.0;
        const hum = env.humidity_percent || 0.0;
        document.getElementById("sensor-val-temp").innerText = temp.toFixed(1);
        document.getElementById("sensor-val-hum").innerText = hum.toFixed(1);
        document.getElementById("sensor-bar-temp").style.width = `${Math.min(100, (temp / 50) * 100)}%`;
        document.getElementById("sensor-bar-hum").style.width = `${Math.min(100, hum)}%`;

        // Cập nhật MQ-7
        const gasLvl = env.gas_level || "NORMAL";
        document.getElementById("sensor-gas-status").innerText = gasLvl;
        document.getElementById("sensor-gas-adc").innerText = env.gas_raw_adc || 0;
        document.getElementById("sensor-gas-volt").innerText = `V_ADC: ~${env.gas_v_adc}V | V_AO: ~${env.gas_v_ao}V`;

        // Cập nhật 6 IR + Gates
        const grid = document.getElementById("sensors-hardware-grid");
        if (grid) {
            const slotsIr = s.slots_ir || {};
            const gates = s.gates || {};

            let cardsHtml = "";
            // 4 Slots
            ["P1", "P2", "P3", "P4"].forEach((sl, idx) => {
                const pins = [13, 14, 16, 35];
                const item = slotsIr[sl] || {};
                const isOcc = item.occupied;
                cardsHtml += `
                    <div class="hardware-pin-card">
                        <div class="pin-name"><span>Cảm biến Ô ${sl}</span> <span class="status-chip ${isOcc ? 'chip-orange' : 'chip-green'}">${isOcc ? 'CÓ XE' : 'TRỐNG'}</span></div>
                        <div class="pin-gpio">GPIO ${pins[idx]} (IR LM393)</div>
                        <div style="font-size: 11px; color: var(--text-tertiary);">${item.updated_at ? formatTimeStr(item.updated_at) : 'N/A'}</div>
                    </div>
                `;
            });

            // Entry Gate IR & Barrier
            cardsHtml += `
                <div class="hardware-pin-card">
                    <div class="pin-name"><span>Cổng Vào (Entry)</span> <span class="status-chip ${gates.barrier_entry === 'OPEN' ? 'chip-green' : 'chip-closed'}">${gates.barrier_entry}</span></div>
                    <div class="pin-gpio">Servo GPIO 25 | IR GPIO 39</div>
                    <div style="font-size: 11px; color: var(--text-tertiary);">RFID: ${gates.rfid_entry_last || 'N/A'}</div>
                </div>
            `;

            // Exit Gate IR & Barrier
            cardsHtml += `
                <div class="hardware-pin-card">
                    <div class="pin-name"><span>Cổng Ra (Exit)</span> <span class="status-chip ${gates.barrier_exit === 'OPEN' ? 'chip-green' : 'chip-closed'}">${gates.barrier_exit}</span></div>
                    <div class="pin-gpio">Servo GPIO 26 | IR GPIO 34</div>
                    <div style="font-size: 11px; color: var(--text-tertiary);">RFID: ${gates.rfid_exit_last || 'N/A'}</div>
                </div>
            `;

            // 2 RFID Modules
            cardsHtml += `
                <div class="hardware-pin-card">
                    <div class="pin-name"><span>RFID RC522 Vào</span> <span class="status-chip chip-neutral">SPI BUS</span></div>
                    <div class="pin-gpio">SS GPIO 5 | SCK 18, MISO 19, MOSI 23</div>
                    <div style="font-size: 11px; color: var(--text-tertiary);">Thẻ cuối: ${gates.rfid_entry_last || 'N/A'}</div>
                </div>
            `;

            cardsHtml += `
                <div class="hardware-pin-card">
                    <div class="pin-name"><span>RFID RC522 Ra</span> <span class="status-chip chip-neutral">SPI BUS</span></div>
                    <div class="pin-gpio">SS GPIO 15 | SCK 18, MISO 19, MOSI 23</div>
                    <div style="font-size: 11px; color: var(--text-tertiary);">Thẻ cuối: ${gates.rfid_exit_last || 'N/A'}</div>
                </div>
            `;

            grid.innerHTML = cardsHtml;
        }
    } catch (e) {
        console.error("loadSensorsView error:", e);
    }
}

// ============================================================================
// 7. REMOTE BARRIER CONTROL & CAMERA TRIGGER TOOLKIT
// ============================================================================

async function controlBarrierRemote(gate, command) {
    try {
        const resp = await fetch(`${API_BASE}/api/barrier/control`, {
            method: "POST",
            headers: { "Content-Type": "application/json", ...getAuthHeader() },
            body: JSON.stringify({ barrier: gate, action: command, gate: gate, command: command })
        });
        const res = await resp.json();
        console.log("Barrier control result:", res);
        fetchFullStatus();
    } catch (err) {
        alert("Lỗi điều khiển Barrier: " + err.message);
    }
}

async function triggerCameraCapture(role) {
    const isEntry = role.toUpperCase() === 'ENTRY';
    const btn = document.getElementById(isEntry ? 'btn-trigger-cam-entry' : 'btn-trigger-cam-exit');
    const originalText = btn ? btn.innerHTML : '';
    if (btn) {
        btn.disabled = true;
        btn.innerHTML = `<i class="fa-solid fa-spinner fa-spin"></i> Đang chụp ảnh...`;
    }

    try {
        const resp = await fetch(`${API_BASE}/api/cameras/${role.toLowerCase()}/command`, {
            method: "POST",
            headers: { "Content-Type": "application/json", ...getAuthHeader() },
            body: JSON.stringify({ command: "CAPTURE", camera: role })
        });
        const res = await resp.json();
        console.log(`Trigger capture ${role} response:`, res);
        if (btn) {
            btn.innerHTML = `<i class="fa-solid fa-check"></i> Đã gửi lệnh!`;
        }
        setTimeout(() => {
            fetchFullStatus();
            if (btn) {
                btn.disabled = false;
                btn.innerHTML = originalText;
            }
        }, 3000);
    } catch (err) {
        console.error("triggerCameraCapture error:", err);
        if (btn) {
            btn.innerHTML = `<i class="fa-solid fa-triangle-exclamation"></i> Lỗi!`;
            setTimeout(() => {
                btn.disabled = false;
                btn.innerHTML = originalText;
            }, 3000);
        }
    }
}

async function sendSimulatedHeartbeat() {
    const p1 = document.getElementById("sim-cb-p1").checked ? 1 : 0;
    const p2 = document.getElementById("sim-cb-p2").checked ? 1 : 0;
    const p3 = document.getElementById("sim-cb-p3").checked ? 1 : 0;
    const p4 = document.getElementById("sim-cb-p4").checked ? 1 : 0;

    const gasVal = document.getElementById("sim-select-gas").value.split("|");
    const gasRaw = parseInt(gasVal[0]);
    const gasLevel = gasVal[1];

    const logEl = document.getElementById("sim-action-log");
    logEl.innerText = "Đang gửi heartbeat telemetry...";

    try {
        const resp = await fetch(`${API_BASE}/api/telemetry/heartbeat`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({
                slots: { P1: p1, P2: p2, P3: p3, P4: p4 },
                temp: 29.0,
                hum: 70.0,
                gas: gasRaw,
                gasLevel: gasLevel,
                barrierEntry: "CLOSED",
                barrierExit: "CLOSED",
                freeSlots: 4 - (p1 + p2 + p3 + p4)
            })
        });
        const res = await resp.json();
        logEl.innerText = `[THÀNH CÔNG] Heartbeat gửi lúc ${formatTimeStr(new Date())}: Free slots = ${res.freeSlots}`;
    } catch (e) {
        logEl.innerText = `[LỖI] ${e.message}`;
    }
}

async function simulateCardScanAction(gate) {
    const logEl = document.getElementById("sim-action-log");
    const testCard = "TEST_" + Math.floor(1000 + Math.random() * 9000);
    logEl.innerText = `Đang quét thẻ ${testCard} tại cổng ${gate}...`;

    try {
        const endpoint = gate === "ENTRY" ? `${API_BASE}/api/parking/entry` : `${API_BASE}/api/parking/exit`;
        const resp = await fetch(endpoint, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ cardUid: testCard, gate: gate })
        });
        const res = await resp.json();
        logEl.innerText = `[${gate} SCAN] Thẻ ${testCard}: ${res.action || res.status} - ${res.message}`;
        fetchFullStatus();
    } catch (e) {
        logEl.innerText = `[LỖI] ${e.message}`;
    }
}

function handleGlobalSearch(query) {
    if (!query) return;
    const q = query.trim().toUpperCase();
    if (currentActiveView !== "vehicles") {
        switchView("vehicles");
    }
    const filterInput = document.getElementById("vehicle-filter-input");
    if (filterInput) filterInput.value = query;
    loadVehiclesView(q);
}

function formatTimeStr(val) {
    if (!val) return "--:--:--";
    const s = String(val);
    if (s.includes("T")) return s.split("T")[1].slice(0, 8);
    if (s.includes(" ")) return s.split(" ")[1].slice(0, 8);
    if (val instanceof Date) return val.toTimeString().split(" ")[0];
    return s.slice(0, 8);
}
