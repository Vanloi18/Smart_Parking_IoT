/**
 * SMART PARKING IoT — APPLE-LIKE MOBILE CONTROLLER (JAVASCRIPT)
 * ==============================================================
 * Zero Fake Data — Direct Realtime Sync with Flask Backend API.
 * 100% Shared Backend, Database and Fee Logic with Desktop Dashboard.
 */

// Global Mobile State
const MobileState = {
  currentTab: "home",
  activeSessionFilter: "all",
  lastData: null,
  isOperatingGate: false,
  apiBase: "",
  offline: false
};

// ============================================================================
// 1. INITIALIZATION & LIFECYCLE
// ============================================================================
document.addEventListener("DOMContentLoaded", () => {
  initApiBaseUrl();
  initMobileTabs();
  initPwaServiceWorker();
  initNetworkListeners();
});

function initApiBaseUrl() {
  const saved = localStorage.getItem("sp_api_base_url");
  if (saved) {
    MobileState.apiBase = saved.trim().replace(/\/+$/, "");
  } else if (window.AndroidNative && typeof window.AndroidNative.getDefaultBackendUrl === "function") {
    MobileState.apiBase = window.AndroidNative.getDefaultBackendUrl().trim().replace(/\/+$/, "");
  } else if (window.location.protocol === "file:") {
    MobileState.apiBase = "http://localhost:5000";
  } else if (window.__API_BASE__) {
    MobileState.apiBase = window.__API_BASE__.trim().replace(/\/+$/, "");
  } else {
    // Default: relative URL when hosted together
    MobileState.apiBase = "";
  }
}

function getMobileApiBase() {
  return MobileState.apiBase || (typeof API_BASE !== "undefined" ? API_BASE : "");
}

function initPwaServiceWorker() {
  if ("serviceWorker" in navigator) {
    navigator.serviceWorker.register("/sw.js").then((reg) => {
      console.log("[PWA] Service Worker registered:", reg.scope);
    }).catch((err) => {
      console.warn("[PWA] Service Worker registration failed:", err);
    });
  }
}

function initNetworkListeners() {
  window.addEventListener("online", () => {
    MobileState.offline = false;
    const banner = document.getElementById("m-offline-banner");
    if (banner) banner.classList.add("hidden");
    showToast("Kết nối mạng đã được khôi phục", "success");
    if (typeof fetchFullStatus === "function") fetchFullStatus();
  });

  window.addEventListener("offline", () => {
    MobileState.offline = true;
    const banner = document.getElementById("m-offline-banner");
    if (banner) banner.classList.remove("hidden");
    showToast("Mất kết nối mạng Internet", "error");
  });
}

// ============================================================================
// 2. MOBILE TABS NAVIGATION
// ============================================================================
function initMobileTabs() {
  const tabItems = document.querySelectorAll(".m-tab-item");
  tabItems.forEach((btn) => {
    btn.addEventListener("click", (e) => {
      e.preventDefault();
      const targetTab = btn.getAttribute("data-tab");
      switchMobileTab(targetTab);
    });
  });
}

function switchMobileTab(tabName) {
  MobileState.currentTab = tabName;

  // Update Tab buttons
  document.querySelectorAll(".m-tab-item").forEach((btn) => {
    if (btn.getAttribute("data-tab") === tabName) {
      btn.classList.add("active");
    } else {
      btn.classList.remove("active");
    }
  });

  // Update Tab panels
  document.querySelectorAll(".m-tab-panel").forEach((panel) => {
    if (panel.id === `m-tab-${tabName}`) {
      panel.classList.add("active");
    } else {
      panel.classList.remove("active");
    }
  });

  // Re-render specific view if needed
  if (tabName === "payment") {
    loadMobilePayments();
  } else if (tabName === "session") {
    loadMobileSessions();
  }

  // Scroll to top of content
  const content = document.querySelector(".m-content");
  if (content) content.scrollTop = 0;
}

// ============================================================================
// 3. REALTIME DATA SYNC (DISPATCHED FROM MAIN SYSTEM DATA)
// ============================================================================
function updateMobileDashboard(data) {
  if (!data) return;
  MobileState.lastData = data;

  updateMobileHeader(data);
  updateMobileHeroCapacity(data);
  updateMobileSlots(data);
  updateMobileGates(data);
  updateMobileSensors(data);
  updateMobileRfid(data);
  updateMobileCameras(data);
  updateMobileSystemMatrix(data);

  // If in session or payment tab, keep refreshed
  if (MobileState.currentTab === "session") renderMobileSessionsList(data);
}

// HEADER
function updateMobileHeader(data) {
  const statusPill = document.getElementById("m-header-status-pill");
  const statusText = document.getElementById("m-header-status-text");
  const timeText = document.getElementById("m-header-time-text");

  const isOnline = data.system && (data.system.wifi_connected || data.system.esp32_status === "CONNECTED");

  if (statusPill && statusText) {
    if (isOnline) {
      statusPill.className = "m-status-pill online";
      statusText.innerText = "ONLINE";
    } else {
      statusPill.className = "m-status-pill offline";
      statusText.innerText = "OFFLINE";
    }
  }

  if (timeText) {
    const now = new Date();
    timeText.innerText = now.toTimeString().split(" ")[0];
  }
}

// HERO CAPACITY
function updateMobileHeroCapacity(data) {
  const total = data.total_slots || 4;
  const occupied = data.occupied_slots !== undefined ? data.occupied_slots : 0;
  const free = data.free_slots !== undefined ? data.free_slots : (total - occupied);
  const percent = total > 0 ? Math.round((occupied / total) * 100) : 0;

  const totalEl = document.getElementById("m-hero-total");
  const freeEl = document.getElementById("m-hero-free");
  const occEl = document.getElementById("m-hero-occ");
  const fillEl = document.getElementById("m-hero-progress-fill");
  const percentEl = document.getElementById("m-hero-progress-pct");

  if (totalEl) totalEl.innerText = total;
  if (freeEl) freeEl.innerText = free;
  if (occEl) occEl.innerText = occupied;
  if (fillEl) fillEl.style.width = `${percent}%`;
  if (percentEl) percentEl.innerText = `${percent}% Đang đỗ`;
}

// 4 PARKING SLOTS (P1 - P4)
function updateMobileSlots(data) {
  const slots = data.slots || {};
  const isEspOnline = data.system && (data.system.wifi_connected || data.system.esp32_status === "CONNECTED");

  // Also try to find session information from recent_sessions
  const recentSessions = data.recent_sessions || [];

  ["P1", "P2", "P3", "P4"].forEach((slotId) => {
    const isOccupied = slots[slotId] === 1;
    const cardEl = document.getElementById(`m-slot-${slotId.toLowerCase()}`);
    if (!cardEl) return;

    // Remove previous state classes
    cardEl.classList.remove("available", "occupied", "unknown");

    const badgeEl = cardEl.querySelector(".m-slot-badge");
    const descTitle = cardEl.querySelector(".m-slot-title");
    const descSub = cardEl.querySelector(".m-slot-sub");
    const detailsBox = cardEl.querySelector(".m-slot-details");

    if (!isEspOnline && !data.system?.backend_online) {
      cardEl.classList.add("unknown");
      if (badgeEl) { badgeEl.className = "m-slot-badge unknown"; badgeEl.innerText = "UNKNOWN"; }
      if (descTitle) descTitle.innerText = "Mất kết nối";
      if (descSub) descSub.innerText = "Không nhận diện được tín hiệu IR";
      if (detailsBox) detailsBox.style.display = "none";
      return;
    }

    if (isOccupied) {
      cardEl.classList.add("occupied");
      if (badgeEl) { badgeEl.className = "m-slot-badge occupied"; badgeEl.innerText = "OCCUPIED"; }
      if (descTitle) descTitle.innerText = "Đang có xe đỗ";
      if (descSub) descSub.innerText = "Cảm biến IR phát hiện vật cản";

      // Find matching session if available
      const sess = recentSessions.find(s => (s.slot_id === slotId || !s.slot_id) && s.status === "PARKED");
      if (detailsBox) {
        detailsBox.style.display = "flex";
        const plateEl = cardEl.querySelector(".m-slot-plate-val");
        const rfidEl = cardEl.querySelector(".m-slot-rfid-val");
        const durEl = cardEl.querySelector(".m-slot-dur-val");
        const feeEl = cardEl.querySelector(".m-slot-fee-val");

        if (plateEl) plateEl.innerText = (sess && sess.plate_number) ? sess.plate_number : "Xe vãng lai";
        if (rfidEl) rfidEl.innerText = (sess && sess.rfid_uid) ? sess.rfid_uid : "--";
        
        let durSec = sess ? (sess.duration_seconds || 0) : 0;
        let durDisplay = durSec > 60 ? `${Math.floor(durSec / 60)}p ${durSec % 60}s` : `${durSec}s`;
        if (durEl) durEl.innerText = durDisplay;

        // Phí lấy trực tiếp từ backend hoặc calculate_parking_fee logic: 5000đ / 5s
        let currentFee = sess && sess.fee ? sess.fee : (Math.max(1, Math.ceil((durSec || 1) / 5)) * 5000);
        if (feeEl) feeEl.innerText = `${currentFee.toLocaleString()} đ`;
      }
    } else {
      cardEl.classList.add("available");
      if (badgeEl) { badgeEl.className = "m-slot-badge available"; badgeEl.innerText = "AVAILABLE"; }
      if (descTitle) descTitle.innerText = "Chỗ trống";
      if (descSub) descSub.innerText = "Sẵn sàng đón phương tiện mới";
      if (detailsBox) detailsBox.style.display = "none";
    }
  });
}

// GATE CONTROLS
function updateMobileGates(data) {
  const barriers = data.barriers || {};
  const isEspOnline = data.system && (data.system.wifi_connected || data.system.esp32_status === "CONNECTED");

  const entryStatusEl = document.getElementById("m-gate-entry-status");
  const exitStatusEl = document.getElementById("m-gate-exit-status");
  const btnEntry = document.getElementById("m-btn-open-entry");
  const btnExit = document.getElementById("m-btn-open-exit");

  const isEntryOpen = barriers.entry === "OPEN";
  const isExitOpen = barriers.exit === "OPEN";

  if (entryStatusEl) {
    entryStatusEl.className = `m-gate-status ${isEntryOpen ? "open" : "closed"}`;
    entryStatusEl.innerHTML = `<i class="fa-solid fa-${isEntryOpen ? 'lock-open' : 'lock'}"></i> ${isEntryOpen ? "ĐANG MỞ" : "ĐANG ĐÓNG"}`;
  }

  if (exitStatusEl) {
    exitStatusEl.className = `m-gate-status ${isExitOpen ? "open" : "closed"}`;
    exitStatusEl.innerHTML = `<i class="fa-solid fa-${isExitOpen ? 'lock-open' : 'lock'}"></i> ${isExitOpen ? "ĐANG MỞ" : "ĐANG ĐÓNG"}`;
  }

  // Update button texts
  if (btnEntry && !MobileState.isOperatingGate) {
    btnEntry.innerHTML = isEntryOpen ? '<i class="fa-solid fa-lock"></i> Đóng Cổng' : '<i class="fa-solid fa-arrow-up-from-bracket"></i> Mở Cổng Vào';
    btnEntry.className = isEntryOpen ? "m-btn-gate m-btn-gate-secondary" : "m-btn-gate m-btn-gate-primary";
  }

  if (btnExit && !MobileState.isOperatingGate) {
    btnExit.innerHTML = isExitOpen ? '<i class="fa-solid fa-lock"></i> Đóng Cổng' : '<i class="fa-solid fa-arrow-up-from-bracket"></i> Mở Cổng Ra';
    btnExit.className = isExitOpen ? "m-btn-gate m-btn-gate-secondary" : "m-btn-gate m-btn-gate-primary";
  }
}

// SENSORS
function updateMobileSensors(data) {
  const env = data.environment || {};
  const tempEl = document.getElementById("m-sensor-temp-val");
  const humEl = document.getElementById("m-sensor-hum-val");
  const gasEl = document.getElementById("m-sensor-gas-val");
  const gasBadge = document.getElementById("m-sensor-gas-badge");

  if (tempEl) tempEl.innerText = env.temperature !== undefined ? `${env.temperature.toFixed(1)}°C` : "--";
  if (humEl) humEl.innerText = env.humidity !== undefined ? `${env.humidity.toFixed(0)}%` : "--";

  if (gasEl) {
    gasEl.innerText = env.gas_raw !== undefined ? `${env.gas_raw} ADC` : "--";
  }

  if (gasBadge) {
    const level = (env.gas_level || "NORMAL").toUpperCase();
    gasBadge.className = `m-sensor-badge ${level.toLowerCase()}`;
    gasBadge.innerText = level;
  }
}

// RFID
function updateMobileRfid(data) {
  const rfid = data.rfid || {};
  const entryCardEl = document.getElementById("m-rfid-entry-val");
  const exitCardEl = document.getElementById("m-rfid-exit-val");

  if (entryCardEl) entryCardEl.innerText = rfid.last_entry_card || "--";
  if (exitCardEl) exitCardEl.innerText = rfid.last_exit_card || "--";
}

// CAMERAS
function updateMobileCameras(data) {
  const cams = data.cameras || {};
  const entryCam = cams.entry || {};
  const exitCam = cams.exit || {};

  renderMobileCamFeed("m-cam-entry-frame", entryCam, "Cổng Vào");
  renderMobileCamFeed("m-cam-exit-frame", exitCam, "Cổng Ra");

  const entryStatEl = document.getElementById("m-cam-entry-status");
  const exitStatEl = document.getElementById("m-cam-exit-status");

  if (entryStatEl) {
    entryStatEl.innerText = entryCam.online ? "ONLINE" : "OFFLINE";
    entryStatEl.style.color = entryCam.online ? "#34c759" : "#8e8e93";
  }

  if (exitStatEl) {
    exitStatEl.innerText = exitCam.online ? "ONLINE" : "OFFLINE";
    exitStatEl.style.color = exitCam.online ? "#34c759" : "#8e8e93";
  }
}

function renderMobileCamFeed(elementId, camObj, label) {
  const el = document.getElementById(elementId);
  if (!el) return;

  const base = getMobileApiBase();

  if (camObj.image_url) {
    const fullImgUrl = camObj.image_url.startsWith("http") ? camObj.image_url : `${base}${camObj.image_url}`;
    el.innerHTML = `
      <img src="${fullImgUrl}" alt="${label} Feed" onerror="this.onerror=null; this.parentElement.innerHTML='<div class=\\'m-cam-offline-box\\'><i class=\\'fa-solid fa-video-slash\\'></i><span>Không tải được ảnh snapshot</span></div>';">
      <div style="position:absolute; bottom:6px; left:8px; background:rgba(0,0,0,0.6); color:#fff; padding:2px 8px; border-radius:6px; font-size:10px;">
        ${camObj.plate_number ? `Biển số: <b>${camObj.plate_number}</b>` : label}
      </div>
    `;
  } else {
    el.innerHTML = `
      <div class="m-cam-offline-box">
        <i class="fa-solid fa-video-slash" style="font-size:22px;"></i>
        <span>Camera ${camObj.online ? "chưa có ảnh chụp" : "Offline"}</span>
      </div>
    `;
  }
}

// SYSTEM STATUS MATRIX
function updateMobileSystemMatrix(data) {
  const sys = data.system || {};
  const cams = data.cameras || {};
  const env = data.environment || {};

  const espOnline = sys.wifi_connected || sys.esp32_status === "CONNECTED";
  setSystemRowStatus("m-sys-esp32", espOnline ? "ONLINE" : "OFFLINE", espOnline, sys.last_heartbeat ? `Heartbeat: ${formatShortTime(sys.last_heartbeat)}` : "Chưa có tín hiệu");
  setSystemRowStatus("m-sys-backend", "ONLINE", true, `Flask REST API Port 5000`);
  setSystemRowStatus("m-sys-database", "ONLINE", true, `SQLite parking.db`);
  setSystemRowStatus("m-sys-cam-entry", cams.entry?.online ? "ONLINE" : "OFFLINE", cams.entry?.online, cams.entry?.ip || "192.168.0.101");
  setSystemRowStatus("m-sys-cam-exit", cams.exit?.online ? "ONLINE" : "OFFLINE", cams.exit?.online, cams.exit?.ip || "192.168.0.106");
  setSystemRowStatus("m-sys-mq7", espOnline ? (env.gas_level || "ONLINE") : "OFFLINE", espOnline, `${env.gas_raw || 0} ADC`);
  setSystemRowStatus("m-sys-rfid", espOnline ? "ONLINE" : "OFFLINE", espOnline, "2x RC522 Reader");
}

function setSystemRowStatus(elementId, statusText, isOnline, subText) {
  const row = document.getElementById(elementId);
  if (!row) return;

  const badge = row.querySelector(".m-slot-badge");
  const sub = row.querySelector(".m-sys-sub");

  if (badge) {
    badge.className = `m-slot-badge ${isOnline ? "available" : "unknown"}`;
    badge.innerText = statusText;
  }
  if (sub && subText) {
    sub.innerText = subText;
  }
}

// ============================================================================
// 4. GATE REMOTE CONTROL ACTIONS (WITH CONFIRM MODAL & ZERO FAKE)
// ============================================================================
function handleMobileGateAction(gateName) {
  const barriers = MobileState.lastData?.barriers || {};
  const isCurrentlyOpen = (gateName === "ENTRY" ? barriers.entry : barriers.exit) === "OPEN";
  const targetAction = isCurrentlyOpen ? "CLOSE" : "OPEN";
  const gateTitle = gateName === "ENTRY" ? "Cổng Vào" : "Cổng Ra";
  const actionTitle = targetAction === "OPEN" ? "Mở Cổng" : "Đóng Cổng";

  showConfirmDialog(
    `Xác nhận ${actionTitle} ${gateTitle}?`,
    `Lệnh sẽ được gửi tới Backend và ESP32 để điều khiển động cơ servo chắn barrier.`,
    async () => {
      await executeGateCommand(gateName, targetAction);
    }
  );
}

async function executeGateCommand(gate, action) {
  MobileState.isOperatingGate = true;
  const base = getMobileApiBase();
  const token = localStorage.getItem("sp_token");

  showToast(`Đang gửi lệnh ${action} ${gate}...`, "info");

  try {
    const resp = await fetch(`${base}/api/barrier/control`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        ...(token ? { "Authorization": `Bearer ${token}` } : {})
      },
      body: JSON.stringify({ barrier: gate, action: action })
    });

    const res = await resp.json();
    if (resp.ok && res.status === "success") {
      showToast(`Đã gửi lệnh thành công! #${res.command_id || ""}`, "success");
      if (typeof fetchFullStatus === "function") fetchFullStatus();
    } else {
      showToast(`Lỗi điều khiển: ${res.message || "Không xác định"}`, "error");
    }
  } catch (err) {
    showToast(`Không kết nối được Server: ${err.message}`, "error");
  } finally {
    MobileState.isOperatingGate = false;
  }
}

// ============================================================================
// 5. SESSIONS & VEHICLES LOAD & RENDER
// ============================================================================
async function loadMobileSessions() {
  const container = document.getElementById("m-sessions-list");
  if (!container) return;

  container.innerHTML = `
    <div style="padding: 24px; text-align: center; color: #8e8e93;">
      <i class="fa-solid fa-spinner fa-spin" style="font-size:24px; margin-bottom: 8px;"></i>
      <div>Đang đồng bộ dữ liệu phiên xe...</div>
    </div>
  `;

  const base = getMobileApiBase();
  const token = localStorage.getItem("sp_token");

  try {
    const resp = await fetch(`${base}/api/parking/status`, {
      headers: { ...(token ? { "Authorization": `Bearer ${token}` } : {}) }
    });
    if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
    const data = await resp.json();
    renderMobileSessionsList(data);
  } catch (err) {
    container.innerHTML = `
      <div style="padding: 20px; text-align: center; color: #ff3b30;">
        <i class="fa-solid fa-circle-exclamation" style="font-size:24px; margin-bottom: 8px;"></i>
        <div>Lỗi tải danh sách: ${err.message}</div>
      </div>
    `;
  }
}

function filterMobileSessions(filterType) {
  MobileState.activeSessionFilter = filterType;
  document.querySelectorAll(".m-pill-btn").forEach(btn => {
    if (btn.getAttribute("data-filter") === filterType) {
      btn.classList.add("active");
    } else {
      btn.classList.remove("active");
    }
  });
  if (MobileState.lastData) {
    renderMobileSessionsList(MobileState.lastData);
  } else {
    loadMobileSessions();
  }
}

function renderMobileSessionsList(data) {
  const container = document.getElementById("m-sessions-list");
  if (!container) return;

  let sessions = data.recent_sessions || [];

  if (MobileState.activeSessionFilter === "parked") {
    sessions = sessions.filter(s => s.status === "PARKED");
  } else if (MobileState.activeSessionFilter === "checkout") {
    sessions = sessions.filter(s => s.status !== "PARKED");
  }

  if (sessions.length === 0) {
    container.innerHTML = `
      <div style="padding: 36px 16px; text-align: center; color: #8e8e93;">
        <i class="fa-solid fa-car-side" style="font-size:32px; opacity: 0.3; margin-bottom: 8px;"></i>
        <div>Không có phiên đỗ xe nào phù hợp.</div>
      </div>
    `;
    return;
  }

  container.innerHTML = sessions.map(s => {
    const isParked = s.status === "PARKED";
    const statusChip = isParked
      ? `<span class="m-slot-badge occupied">Đang đỗ</span>`
      : `<span class="m-slot-badge available">Đã rời</span>`;
    
    const payChip = s.payment_status === "PAID"
      ? `<span style="color:#34c759; font-weight:600;"><i class="fa-solid fa-check-circle"></i> Đã thanh toán</span>`
      : `<span style="color:#ff9500; font-weight:600;"><i class="fa-solid fa-clock"></i> Chưa thanh toán</span>`;

    const durSec = s.duration_seconds || 0;
    const durDisplay = durSec > 60 ? `${Math.floor(durSec / 60)} phút ${durSec % 60}s` : `${durSec} giây`;

    // Phí: 5.000 VNĐ / 5 giây đồng bộ
    const feeDisplay = s.fee ? `${s.fee.toLocaleString()} đ` : (isParked ? `${(Math.max(1, Math.ceil((durSec || 1) / 5)) * 5000).toLocaleString()} đ` : "0 đ");

    return `
      <div class="m-session-item">
        <div class="m-session-head">
          <div class="m-session-plate">
            <i class="fa-solid fa-car"></i>
            <span>${s.plate_number || "Chưa có biển số"}</span>
          </div>
          ${statusChip}
        </div>
        <div class="m-session-meta">
          <div class="m-session-meta-item">Thẻ: <span>${s.rfid_uid || "--"}</span></div>
          <div class="m-session-meta-item">Vị trí: <span>${s.slot_id || "Chung"}</span></div>
          <div class="m-session-meta-item">Vào lúc: <span>${formatShortTime(s.entry_time)}</span></div>
          <div class="m-session-meta-item">Thời gian: <span>${durDisplay}</span></div>
        </div>
        <div class="m-session-foot">
          <div>${payChip}</div>
          <div class="m-session-fee">${feeDisplay}</div>
        </div>
      </div>
    `;
  }).join("");
}

// ============================================================================
// 6. PAYMENTS LOAD & MANUAL CASH CONFIRM
// ============================================================================
async function loadMobilePayments() {
  const container = document.getElementById("m-payments-list");
  const totalRevEl = document.getElementById("m-pay-total-rev");
  const totalCountEl = document.getElementById("m-pay-total-count");

  if (!container) return;

  container.innerHTML = `
    <div style="padding: 24px; text-align: center; color: #8e8e93;">
      <i class="fa-solid fa-spinner fa-spin" style="font-size:24px; margin-bottom: 8px;"></i>
      <div>Đang tải lịch sử thu phí...</div>
    </div>
  `;

  const base = getMobileApiBase();
  const token = localStorage.getItem("sp_token");

  try {
    const resp = await fetch(`${base}/api/payments`, {
      headers: { ...(token ? { "Authorization": `Bearer ${token}` } : {}) }
    });
    if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
    const data = await resp.json();
    const payments = data.payments || [];

    const totalRev = payments.reduce((acc, p) => acc + (p.amount || 0), 0);
    if (totalRevEl) totalRevEl.innerText = `${totalRev.toLocaleString()} đ`;
    if (totalCountEl) totalCountEl.innerText = `${payments.length} lượt`;

    if (payments.length === 0) {
      container.innerHTML = `
        <div style="padding: 32px 16px; text-align: center; color: #8e8e93;">
          <i class="fa-solid fa-receipt" style="font-size:32px; opacity: 0.3; margin-bottom: 8px;"></i>
          <div>Chưa có giao dịch thu phí nào.</div>
        </div>
      `;
      return;
    }

    container.innerHTML = payments.map(p => `
      <div class="m-session-item">
        <div class="m-session-head">
          <div class="m-session-plate">
            <i class="fa-solid fa-receipt" style="color:#0071e3;"></i>
            <span>${p.plate_number || "Giao dịch #" + p.id}</span>
          </div>
          <span class="m-slot-badge available">ĐÃ THU</span>
        </div>
        <div class="m-session-meta">
          <div class="m-session-meta-item">Phương thức: <span>${p.payment_method || "CASH"}</span></div>
          <div class="m-session-meta-item">Thời gian: <span>${formatShortTime(p.paid_at)}</span></div>
        </div>
        <div class="m-session-foot">
          <span style="font-size:11px; color:#8e8e93;">Biên lai điện tử</span>
          <div class="m-session-fee">${(p.amount || 0).toLocaleString()} đ</div>
        </div>
      </div>
    `).join("");

  } catch (err) {
    container.innerHTML = `
      <div style="padding: 20px; text-align: center; color: #ff3b30;">
        <i class="fa-solid fa-circle-exclamation" style="font-size:24px; margin-bottom: 8px;"></i>
        <div>Lỗi tải thanh toán: ${err.message}</div>
      </div>
    `;
  }
}

// ============================================================================
// 7. TOAST & MODAL UTILITIES
// ============================================================================
function showToast(message, type = "info") {
  if (window.AndroidNative && typeof window.AndroidNative.vibrate === "function") {
    window.AndroidNative.vibrate();
  }
  const container = document.getElementById("m-toast-container");
  if (!container) return;

  const toast = document.createElement("div");
  toast.className = `m-toast ${type}`;
  let icon = "fa-circle-info";
  if (type === "success") icon = "fa-circle-check";
  else if (type === "error") icon = "fa-triangle-exclamation";

  toast.innerHTML = `<i class="fa-solid ${icon}"></i> <span>${message}</span>`;
  container.appendChild(toast);

  setTimeout(() => {
    toast.style.opacity = "0";
    toast.style.transform = "translateY(-10px)";
    toast.style.transition = "all 0.25s ease";
    setTimeout(() => toast.remove(), 250);
  }, 2800);
}

let activeConfirmCallback = null;

function showConfirmDialog(title, description, onConfirm) {
  const backdrop = document.getElementById("m-confirm-modal");
  const titleEl = document.getElementById("m-confirm-title");
  const descEl = document.getElementById("m-confirm-desc");

  if (!backdrop) return;
  if (titleEl) titleEl.innerText = title;
  if (descEl) descEl.innerText = description;

  activeConfirmCallback = onConfirm;
  backdrop.classList.add("active");
}

function closeConfirmDialog() {
  const backdrop = document.getElementById("m-confirm-modal");
  if (backdrop) backdrop.classList.remove("active");
  activeConfirmCallback = null;
}

function handleConfirmSubmit() {
  if (typeof activeConfirmCallback === "function") {
    activeConfirmCallback();
  }
  closeConfirmDialog();
}

// API CONFIG MODAL (FOR NETLIFY PUBLIC DEPLOYMENT)
function openApiConfigModal() {
  const modal = document.getElementById("m-api-config-modal");
  const input = document.getElementById("m-api-url-input");
  if (input) {
    input.value = localStorage.getItem("sp_api_base_url") || "";
  }
  if (modal) modal.classList.add("active");
}

function closeApiConfigModal() {
  const modal = document.getElementById("m-api-config-modal");
  if (modal) modal.classList.remove("active");
}

async function saveApiConfig() {
  const input = document.getElementById("m-api-url-input");
  const val = input ? input.value.trim().replace(/\/+$/, "") : "";

  if (val) {
    localStorage.setItem("sp_api_base_url", val);
    MobileState.apiBase = val;
    showToast("Đã lưu URL Backend API!", "success");
  } else {
    localStorage.removeItem("sp_api_base_url");
    MobileState.apiBase = "";
    showToast("Đã chuyển về URL mặc định (cùng host)", "info");
  }

  closeApiConfigModal();
  if (typeof fetchFullStatus === "function") fetchFullStatus();
}

async function testApiConnection() {
  const input = document.getElementById("m-api-url-input");
  const url = input ? input.value.trim().replace(/\/+$/, "") : "";
  const statusBox = document.getElementById("m-api-test-result");

  if (!statusBox) return;
  statusBox.innerHTML = '<i class="fa-solid fa-spinner fa-spin"></i> Đang kiểm tra kết nối...';
  statusBox.style.color = "#0071e3";

  try {
    const start = performance.now();
    const resp = await fetch(`${url}/api/status`, { method: "GET" });
    const elapsed = Math.round(performance.now() - start);

    if (resp.ok) {
      statusBox.innerHTML = `<i class="fa-solid fa-circle-check"></i> Kết nối thành công! Ping: ${elapsed}ms`;
      statusBox.style.color = "#34c759";
    } else {
      statusBox.innerHTML = `<i class="fa-solid fa-circle-exclamation"></i> Server trả về mã lỗi HTTP ${resp.status}`;
      statusBox.style.color = "#ff9500";
    }
  } catch (e) {
    statusBox.innerHTML = `<i class="fa-solid fa-circle-xmark"></i> Không kết nối được: ${e.message}`;
    statusBox.style.color = "#ff3b30";
  }
}

// HELPERS
function formatShortTime(isoStr) {
  if (!isoStr) return "--";
  try {
    const dt = new Date(isoStr);
    return dt.toLocaleTimeString("vi-VN", { hour: "2-digit", minute: "2-digit", second: "2-digit" });
  } catch (e) {
    return isoStr.slice(11, 19);
  }
}

// Expose to window
window.updateMobileDashboard = updateMobileDashboard;
window.switchMobileTab = switchMobileTab;
window.handleMobileGateAction = handleMobileGateAction;
window.filterMobileSessions = filterMobileSessions;
window.showToast = showToast;
window.showConfirmDialog = showConfirmDialog;
window.closeConfirmDialog = closeConfirmDialog;
window.handleConfirmSubmit = handleConfirmSubmit;
window.openApiConfigModal = openApiConfigModal;
window.closeApiConfigModal = closeApiConfigModal;
window.saveApiConfig = saveApiConfig;
window.testApiConnection = testApiConnection;
