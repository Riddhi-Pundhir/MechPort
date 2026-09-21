/**
 * ==============================================================================
 * MechPort - Tactical Tech-Punk Web Dashboard Controller (Phase 4 Redesign)
 * ==============================================================================
 * Preserves 100% of existing API, driving, heartbeat, and safety contracts:
 *   - Configurable endpoints with localStorage persistence
 *   - Real-time telemetry polling via GET /api/status
 *   - Tactile D-Pad & Keyboard driving (W, A, S, D, SPACE)
 *   - 700ms heartbeat generator during key hold
 *   - Key-release auto-stop & prominent emergency STOP
 *   - ESP32-CAM stream integration with error HUD
 *   - Live system clock & session uptime counter
 *   - Single-page section tab navigation with scroll-spy
 *   - Client-side quick jump search with section highlight glow
 * ==============================================================================
 */

(function () {
  "use strict";

  // Default configuration fallback
  const DEFAULT_CONFIG = {
    rpiBaseUrl: "http://127.0.0.1:5000",
    camStreamUrl: "http://192.168.1.50:81/stream",
    pollIntervalMs: 1000,
    heartbeatIntervalMs: 700, // Feeds 1.5s watchdog before expiry
  };

  // Application State
  let config = loadConfig();
  let currentActiveCommand = null;
  let heartbeatTimer = null;
  let pollTimer = null;
  let clockTimer = null;
  let sessionStartTime = Date.now();
  let isRpiConnected = false;
  let isCamOnline = false;
  let isRequestPending = false;

  // Keyboard Mapping: Key Code -> Command Name & Button Element ID
  const KEY_MAP = {
    KeyW: { command: "FORWARD", btnId: "btn-forward" },
    ArrowUp: { command: "FORWARD", btnId: "btn-forward" },
    KeyS: { command: "BACKWARD", btnId: "btn-backward" },
    ArrowDown: { command: "BACKWARD", btnId: "btn-backward" },
    KeyA: { command: "LEFT", btnId: "btn-left" },
    ArrowLeft: { command: "LEFT", btnId: "btn-left" },
    KeyD: { command: "RIGHT", btnId: "btn-right" },
    ArrowRight: { command: "RIGHT", btnId: "btn-right" },
    Space: { command: "STOP", btnId: "btn-stop" },
    Escape: { command: "STOP", btnId: "btn-stop" },
  };

  // Search Index Dictionary
  const SEARCH_INDEX = [
    { title: "Live Camera Stream", section: "section-camera", keywords: ["camera", "stream", "video", "feed", "mjpeg", "cam", "lens"] },
    { title: "Vehicle Controls (D-Pad)", section: "section-controls", keywords: ["controls", "drive", "move", "forward", "backward", "left", "right", "steering", "pad"] },
    { title: "Emergency STOP", section: "section-controls", keywords: ["stop", "brake", "halt", "emergency", "space"] },
    { title: "Motor Speed / Throttle", section: "section-controls", keywords: ["speed", "throttle", "pwm", "slider", "power"] },
    { title: "System Status & Telemetry", section: "section-status", keywords: ["status", "telemetry", "hardware", "mode", "metrics", "engine", "cors"] },
    { title: "Quick Configuration (IPs)", section: "section-settings", keywords: ["settings", "config", "url", "ip", "rpi", "address", "connection"] },
    { title: "Dashboard Overview", section: "section-dashboard", keywords: ["dashboard", "overview", "top", "home", "metrics"] },
    { title: "Help & Shortcuts Guide", section: "section-help", keywords: ["help", "shortcuts", "keyboard", "guide", "keys", "manual"] },
  ];

  // DOM Elements Cache
  const elements = {
    // Header telemetry badges
    dotRpi: document.getElementById("dot-rpi"),
    valRpiStatus: document.getElementById("val-rpi-status"),
    valRpiMode: document.getElementById("val-rpi-mode"),
    dotCam: document.getElementById("dot-cam"),
    valCamStatus: document.getElementById("val-cam-status"),
    dotWatchdog: document.getElementById("dot-watchdog"),
    valWatchdog: document.getElementById("val-watchdog"),
    clockTime: document.getElementById("clock-time"),
    hudTimestamp: document.getElementById("hud-timestamp"),
    sessionUptime: document.getElementById("session-uptime"),

    // Nav & Search
    navTabs: document.querySelectorAll(".nav-tab"),
    searchInput: document.getElementById("search-input"),
    searchDropdown: document.getElementById("search-dropdown"),

    // Toast
    toastBanner: document.getElementById("toast-banner"),
    toastMessage: document.getElementById("toast-message"),
    btnDismissToast: document.getElementById("btn-dismiss-toast"),

    // Video feed
    videoViewport: document.getElementById("video-viewport"),
    camStreamImg: document.getElementById("cam-stream-img"),
    camPlaceholder: document.getElementById("cam-placeholder"),
    camPlaceholderText: document.getElementById("cam-placeholder-text"),
    displayCamUrl: document.getElementById("display-cam-url"),
    camFooterUrl: document.getElementById("cam-footer-url"),
    btnConnectCam: document.getElementById("btn-connect-cam"),
    btnRefreshStream: document.getElementById("btn-refresh-stream"),

    // Vehicle controls
    stateBanner: document.getElementById("state-banner"),
    stateReadout: document.getElementById("state-readout"),
    speedSlider: document.getElementById("speed-slider"),
    speedDisplay: document.getElementById("speed-display"),
    btnForward: document.getElementById("btn-forward"),
    btnBackward: document.getElementById("btn-backward"),
    btnLeft: document.getElementById("btn-left"),
    btnRight: document.getElementById("btn-right"),
    btnStop: document.getElementById("btn-stop"),

    // Telemetry displays
    telemApiUrl: document.getElementById("telem-api-url"),
    telemHwMode: document.getElementById("telem-hw-mode"),
    telemWatchdogTime: document.getElementById("telem-watchdog-time"),
    telemSummaryUrl: document.getElementById("telem-summary-url"),
    telemSummaryState: document.getElementById("telem-summary-state"),
    telemSummarySpeed: document.getElementById("telem-summary-speed"),
    telemSummaryWatchdog: document.getElementById("telem-summary-watchdog"),
    telemSummaryHw: document.getElementById("telem-summary-hw"),

    // Configuration Inputs
    inputRpiUrl: document.getElementById("input-rpi-url"),
    inputCamUrl: document.getElementById("input-cam-url"),
    btnSaveConfig: document.getElementById("btn-save-config"),
    btnResetConfig: document.getElementById("btn-reset-config"),
  };

  // ============================================================================
  // Configuration Storage (localStorage)
  // ============================================================================
  function loadConfig() {
    try {
      const saved = localStorage.getItem("mechport_config");
      if (saved) {
        return { ...DEFAULT_CONFIG, ...JSON.parse(saved) };
      }
    } catch (e) {
      console.warn("Could not load stored config, using defaults", e);
    }
    return { ...DEFAULT_CONFIG };
  }

  function saveConfig(newConfig) {
    config = { ...config, ...newConfig };
    try {
      localStorage.setItem("mechport_config", JSON.stringify(config));
    } catch (e) {
      console.error("Failed to save config to localStorage", e);
    }
    updateConfigInputs();
    reconnectAll();
  }

  function updateConfigInputs() {
    if (elements.inputRpiUrl) elements.inputRpiUrl.value = config.rpiBaseUrl;
    if (elements.inputCamUrl) elements.inputCamUrl.value = config.camStreamUrl;
    if (elements.displayCamUrl) elements.displayCamUrl.textContent = config.camStreamUrl;
    if (elements.camFooterUrl) elements.camFooterUrl.textContent = config.camStreamUrl;
    if (elements.telemApiUrl) elements.telemApiUrl.textContent = config.rpiBaseUrl;
    if (elements.telemSummaryUrl) elements.telemSummaryUrl.textContent = config.rpiBaseUrl;
  }

  // ============================================================================
  // Notification / Toast
  // ============================================================================
  function showToast(msg, isError = true) {
    if (!elements.toastBanner) return;
    elements.toastMessage.textContent = msg;
    elements.toastBanner.style.borderColor = isError ? "var(--neon-stop)" : "var(--neon-green)";
    elements.toastBanner.classList.remove("hidden");
  }

  function hideToast() {
    if (elements.toastBanner) {
      elements.toastBanner.classList.add("hidden");
    }
  }

  // ============================================================================
  // Telemetry Polling (GET /api/status)
  // ============================================================================
  async function pollStatus() {
    const url = `${config.rpiBaseUrl.replace(/\/+$/, "")}/api/status`;
    const controller = new AbortController();
    const timeoutId = setTimeout(() => controller.abort(), 2500);

    try {
      const response = await fetch(url, {
        method: "GET",
        headers: { "Accept": "application/json" },
        signal: controller.signal,
      });
      clearTimeout(timeoutId);

      if (!response.ok) {
        throw new Error(`HTTP ${response.status}`);
      }

      const data = await response.json();
      handleStatusSuccess(data);
    } catch (err) {
      clearTimeout(timeoutId);
      handleStatusError(err);
    }
  }

  function handleStatusSuccess(data) {
    if (!isRpiConnected) {
      isRpiConnected = true;
      hideToast();
    }

    // Header Status Card
    if (elements.dotRpi) elements.dotRpi.className = "status-dot online";
    if (elements.valRpiStatus) elements.valRpiStatus.textContent = "Connected";
    const modeStr = data.hardware?.mode || "MOCK";
    if (elements.valRpiMode) {
      elements.valRpiMode.textContent = modeStr;
      elements.valRpiMode.className = `mode-pill ${modeStr === 'MOCK' ? 'pill-purple' : 'pill-safe'}`;
    }

    // Motor State
    const motorState = data.motor?.state || "STOP";
    updateStateDisplay(motorState);

    // Watchdog Telemetry
    const remaining = data.watchdog?.time_remaining_seconds ?? 1.5;
    const timeout = data.watchdog?.timeout_seconds ?? 1.5;
    const expired = data.watchdog?.expired ?? false;
    if (elements.valWatchdog) elements.valWatchdog.textContent = `${timeout}s`;
    if (elements.telemWatchdogTime) {
      elements.telemWatchdogTime.textContent = expired 
        ? "Auto-Stopped (Silent)" 
        : `${remaining}s remaining`;
    }

    // Telemetry Summary Panel
    if (elements.telemHwMode) elements.telemHwMode.textContent = `${modeStr} MODE`;
    if (elements.telemSummaryHw) elements.telemSummaryHw.textContent = `${modeStr} MODE`;
    if (elements.telemSummaryState) elements.telemSummaryState.textContent = motorState;
    if (elements.telemSummarySpeed) elements.telemSummarySpeed.textContent = `${data.motor?.speed ?? 80}%`;
    if (elements.telemSummaryWatchdog) {
      elements.telemSummaryWatchdog.textContent = expired ? "Auto-Stopped" : `${remaining}s (Active)`;
    }
  }

  function handleStatusError(err) {
    if (isRpiConnected) {
      isRpiConnected = false;
      showToast(`Raspberry Pi disconnected (${err.message}). Retrying...`);
    }

    if (elements.dotRpi) elements.dotRpi.className = "status-dot offline";
    if (elements.valRpiStatus) elements.valRpiStatus.textContent = "Disconnected";
    if (elements.valRpiMode) {
      elements.valRpiMode.textContent = "OFFLINE";
      elements.valRpiMode.className = "mode-pill";
    }
    if (elements.telemWatchdogTime) elements.telemWatchdogTime.textContent = "Offline";
    if (elements.telemSummaryState) elements.telemSummaryState.textContent = "DISCONNECTED";

    updateStateDisplay("DISCONNECTED");
  }

  function updateStateDisplay(state) {
    if (!elements.stateBanner || !elements.stateReadout) return;

    elements.stateReadout.textContent = state;
    elements.stateBanner.className = "state-banner";

    switch (state.toUpperCase()) {
      case "FORWARD":
        elements.stateBanner.classList.add("state-forward");
        break;
      case "BACKWARD":
        elements.stateBanner.classList.add("state-backward");
        break;
      case "LEFT":
        elements.stateBanner.classList.add("state-left");
        break;
      case "RIGHT":
        elements.stateBanner.classList.add("state-right");
        break;
      default:
        elements.stateBanner.classList.add("state-stop");
        break;
    }
  }

  // ============================================================================
  // Motor Movement API Dispatch (POST /api/move)
  // ============================================================================
  async function sendMoveCommand(command) {
    if (isRequestPending && command === currentActiveCommand) {
      return; // Deduplicate in-flight command
    }

    const speed = parseInt(elements.speedSlider?.value, 10) || 80;
    const url = `${config.rpiBaseUrl.replace(/\/+$/, "")}/api/move`;

    isRequestPending = true;
    try {
      const response = await fetch(url, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          "Accept": "application/json",
        },
        body: JSON.stringify({
          command: command,
          speed: speed,
        }),
      });

      const data = await response.json();

      if (!response.ok) {
        showToast(data.message || `Command failed: HTTP ${response.status}`);
      } else {
        if (data.current_state) {
          updateStateDisplay(data.current_state);
        }
      }
    } catch (err) {
      console.error("Network error sending move command:", err);
      showToast(`Failed to send command to ${url}: ${err.message}`);
    } finally {
      isRequestPending = false;
    }
  }

  // ============================================================================
  // Driving & Watchdog Heartbeat Engine
  // ============================================================================
  function startDriving(command, triggerBtnId = null) {
    if (currentActiveCommand === command) return;

    currentActiveCommand = command;
    highlightButton(triggerBtnId, true);

    // Send immediate command
    sendMoveCommand(command);

    // Reset heartbeat timer
    if (heartbeatTimer) clearInterval(heartbeatTimer);

    // If movement command, refresh watchdog periodically while held
    if (command !== "STOP") {
      heartbeatTimer = setInterval(() => {
        if (currentActiveCommand === command) {
          sendMoveCommand(command);
        }
      }, config.heartbeatIntervalMs);
    }
  }

  function stopDriving(triggerBtnId = null) {
    if (heartbeatTimer) {
      clearInterval(heartbeatTimer);
      heartbeatTimer = null;
    }

    highlightButton(triggerBtnId, false);
    currentActiveCommand = "STOP";
    sendMoveCommand("STOP");
  }

  function highlightButton(btnId, active) {
    if (!btnId) return;
    const btn = document.getElementById(btnId);
    if (btn) {
      if (active) {
        btn.classList.add("is-active");
      } else {
        btn.classList.remove("is-active");
      }
    }
  }

  function clearAllButtonHighlights() {
    ["btn-forward", "btn-backward", "btn-left", "btn-right", "btn-stop"].forEach(id => {
      const el = document.getElementById(id);
      if (el) el.classList.remove("is-active");
    });
  }

  // ============================================================================
  // ESP32-CAM Stream Handling
  // ============================================================================
  function connectCameraStream() {
    const img = elements.camStreamImg;
    const placeholder = elements.camPlaceholder;
    if (!img || !placeholder) return;

    if (elements.valCamStatus) elements.valCamStatus.textContent = "Connecting...";
    if (elements.dotCam) elements.dotCam.className = "status-dot active";
    placeholder.classList.remove("hidden");
    if (elements.camPlaceholderText) {
      elements.camPlaceholderText.textContent = "Attempting video stream connection...";
    }

    // Bypass browser cache with timestamp query
    const streamUrl = `${config.camStreamUrl}?ts=${Date.now()}`;
    img.src = streamUrl;

    img.onload = () => {
      isCamOnline = true;
      if (elements.valCamStatus) elements.valCamStatus.textContent = "Online";
      if (elements.dotCam) elements.dotCam.className = "status-dot online";
      placeholder.classList.add("hidden");
      img.classList.remove("hidden");
    };

    img.onerror = () => {
      isCamOnline = false;
      if (elements.valCamStatus) elements.valCamStatus.textContent = "Offline";
      if (elements.dotCam) elements.dotCam.className = "status-dot offline";
      img.classList.add("hidden");
      placeholder.classList.remove("hidden");
      if (elements.camPlaceholderText) {
        elements.camPlaceholderText.textContent = 
          "Stream offline. Ensure ESP32-CAM is powered & Wi-Fi IP matches configuration.";
      }
    };
  }

  // ============================================================================
  // Navigation & Smooth Scroll-Spy
  // ============================================================================
  function setupNavigation() {
    elements.navTabs.forEach(tab => {
      tab.addEventListener("click", (e) => {
        e.preventDefault();
        const targetId = tab.getAttribute("data-target");
        jumpToSection(targetId);
      });
    });

    // Scroll spy with IntersectionObserver
    const sections = document.querySelectorAll("section[id]");
    const observer = new IntersectionObserver((entries) => {
      entries.forEach(entry => {
        if (entry.isIntersecting) {
          const id = entry.target.id;
          elements.navTabs.forEach(tab => {
            if (tab.getAttribute("data-target") === id) {
              tab.classList.add("active");
            } else {
              tab.classList.remove("active");
            }
          });
        }
      });
    }, { threshold: 0.25 });

    sections.forEach(sec => observer.observe(sec));
  }

  function jumpToSection(sectionId) {
    const sec = document.getElementById(sectionId);
    if (!sec) return;

    sec.scrollIntoView({ behavior: "smooth", block: "start" });

    // Section jump glow animation
    sec.classList.remove("section-highlight");
    void sec.offsetWidth; // Trigger reflow
    sec.classList.add("section-highlight");
    setTimeout(() => sec.classList.remove("section-highlight"), 2200);

    // Update active tab visually
    elements.navTabs.forEach(tab => {
      if (tab.getAttribute("data-target") === sectionId) {
        tab.classList.add("active");
      } else {
        tab.classList.remove("active");
      }
    });
  }

  // ============================================================================
  // Client-Side Search Engine
  // ============================================================================
  function setupSearch() {
    const input = elements.searchInput;
    const dropdown = elements.searchDropdown;
    if (!input || !dropdown) return;

    input.addEventListener("input", () => {
      const q = input.value.trim().toLowerCase();
      if (!q) {
        dropdown.classList.add("hidden");
        dropdown.innerHTML = "";
        return;
      }

      // Filter matches
      const matches = SEARCH_INDEX.filter(item => {
        return item.title.toLowerCase().includes(q) ||
               item.keywords.some(k => k.toLowerCase().includes(q));
      });

      if (matches.length === 0) {
        dropdown.innerHTML = `<div class="search-result-item" style="color: var(--text-dim);">No matches found for "${q}"</div>`;
        dropdown.classList.remove("hidden");
        return;
      }

      dropdown.innerHTML = matches.map((m, idx) => `
        <div class="search-result-item ${idx === 0 ? 'selected' : ''}" data-target="${m.section}">
          <span>${m.title}</span>
          <span class="search-result-section">#${m.section.replace('section-', '')}</span>
        </div>
      `).join("");

      dropdown.classList.remove("hidden");

      // Attach click listeners to results
      dropdown.querySelectorAll(".search-result-item").forEach(item => {
        item.addEventListener("click", () => {
          const target = item.getAttribute("data-target");
          if (target) {
            jumpToSection(target);
            input.value = "";
            dropdown.classList.add("hidden");
          }
        });
      });
    });

    // Enter key triggers top search result
    input.addEventListener("keydown", (e) => {
      if (e.key === "Enter") {
        const topItem = dropdown.querySelector(".search-result-item");
        if (topItem) {
          const target = topItem.getAttribute("data-target");
          if (target) {
            jumpToSection(target);
            input.value = "";
            dropdown.classList.add("hidden");
            input.blur();
          }
        }
      } else if (e.key === "Escape") {
        input.value = "";
        dropdown.classList.add("hidden");
        input.blur();
      }
    });

    // Close dropdown on outside click
    document.addEventListener("click", (e) => {
      if (!e.target.closest(".nav-search-container")) {
        dropdown.classList.add("hidden");
      }
    });
  }

  // ============================================================================
  // Live Clock & Session Uptime
  // ============================================================================
  function startClock() {
    function tick() {
      const now = new Date();
      const timeStr = now.toTimeString().split(" ")[0];
      if (elements.clockTime) elements.clockTime.textContent = timeStr;
      if (elements.hudTimestamp) elements.hudTimestamp.textContent = timeStr;

      // Session Uptime
      const elapsedSec = Math.floor((Date.now() - sessionStartTime) / 1000);
      const hrs = String(Math.floor(elapsedSec / 3600)).padStart(2, "0");
      const mins = String(Math.floor((elapsedSec % 3600) / 60)).padStart(2, "0");
      const secs = String(elapsedSec % 60).padStart(2, "0");
      if (elements.sessionUptime) elements.sessionUptime.textContent = `${hrs}:${mins}:${secs}`;
    }
    tick();
    clockTimer = setInterval(tick, 1000);
  }

  // ============================================================================
  // Setup Event Listeners
  // ============================================================================
  function setupEventListeners() {
    // 1. Keyboard Driving
    window.addEventListener("keydown", (e) => {
      // Ignore keystrokes when typing in inputs
      if (e.target.tagName === "INPUT" || e.target.tagName === "TEXTAREA") {
        return;
      }

      // Space or Escape triggers immediate STOP
      if (e.code === "Space" || e.code === "Escape") {
        e.preventDefault();
        stopDriving("btn-stop");
        return;
      }

      const mapping = KEY_MAP[e.code];
      if (mapping && !e.repeat) {
        e.preventDefault();
        startDriving(mapping.command, mapping.btnId);
      }
    });

    window.addEventListener("keyup", (e) => {
      if (e.target.tagName === "INPUT" || e.target.tagName === "TEXTAREA") {
        return;
      }

      const mapping = KEY_MAP[e.code];
      if (mapping && mapping.command !== "STOP") {
        e.preventDefault();
        stopDriving(mapping.btnId);
      }
    });

    // 2. Mouse / Touch Controls on DPad Buttons
    const setupControlBtn = (btn, command) => {
      if (!btn) return;

      const handlePressStart = (e) => {
        e.preventDefault();
        if (command === "STOP") {
          stopDriving(btn.id);
        } else {
          startDriving(command, btn.id);
        }
      };

      const handlePressEnd = (e) => {
        e.preventDefault();
        if (command !== "STOP") {
          stopDriving(btn.id);
        }
      };

      btn.addEventListener("mousedown", handlePressStart);
      btn.addEventListener("mouseup", handlePressEnd);
      btn.addEventListener("mouseleave", handlePressEnd);

      // Touch events
      btn.addEventListener("touchstart", handlePressStart, { passive: false });
      btn.addEventListener("touchend", handlePressEnd, { passive: false });
    };

    setupControlBtn(elements.btnForward, "FORWARD");
    setupControlBtn(elements.btnBackward, "BACKWARD");
    setupControlBtn(elements.btnLeft, "LEFT");
    setupControlBtn(elements.btnRight, "RIGHT");
    setupControlBtn(elements.btnStop, "STOP");

    // 3. Speed Slider
    if (elements.speedSlider && elements.speedDisplay) {
      elements.speedSlider.addEventListener("input", (e) => {
        const val = `${e.target.value}%`;
        elements.speedDisplay.textContent = val;
        if (elements.telemSummarySpeed) elements.telemSummarySpeed.textContent = val;
      });
    }

    // 4. Configuration Form Buttons
    if (elements.btnSaveConfig) {
      elements.btnSaveConfig.addEventListener("click", () => {
        const rpiUrl = elements.inputRpiUrl?.value.trim();
        const camUrl = elements.inputCamUrl?.value.trim();
        saveConfig({
          rpiBaseUrl: rpiUrl || DEFAULT_CONFIG.rpiBaseUrl,
          camStreamUrl: camUrl || DEFAULT_CONFIG.camStreamUrl,
        });
        showToast("Configuration saved and reconnected!", false);
      });
    }

    if (elements.btnResetConfig) {
      elements.btnResetConfig.addEventListener("click", () => {
        saveConfig(DEFAULT_CONFIG);
        showToast("Configuration reset to factory defaults.", false);
      });
    }

    // 5. Stream Reconnect / Refresh
    if (elements.btnConnectCam) {
      elements.btnConnectCam.addEventListener("click", connectCameraStream);
    }
    if (elements.btnRefreshStream) {
      elements.btnRefreshStream.addEventListener("click", connectCameraStream);
    }

    // 6. Toast Dismiss
    if (elements.btnDismissToast) {
      elements.btnDismissToast.addEventListener("click", hideToast);
    }
  }

  // ============================================================================
  // Initialization & Lifecycle
  // ============================================================================
  function reconnectAll() {
    clearAllButtonHighlights();
    pollStatus();
    connectCameraStream();
  }

  function init() {
    updateConfigInputs();
    setupEventListeners();
    setupNavigation();
    setupSearch();
    startClock();

    // Start background telemetry polling
    pollStatus();
    pollTimer = setInterval(pollStatus, config.pollIntervalMs);

    // Initial stream connection
    connectCameraStream();

    console.log("MechPort Tech-Punk Dashboard initialized successfully.");
  }

  // Run on DOM Ready
  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", init);
  } else {
    init();
  }
})();
