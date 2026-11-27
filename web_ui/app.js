(function () {
  "use strict";

  const { NOISE_ICONS, SLIDER_ICONS, MENU_ICONS, UI_ICONS, batterySvg } = window.XiaomiIcons;

  const TRANSPARENCY_LABELS = ["Regular", "Enhance voice", "Enhance ambient sound"];
  const IMMERSIVE_LABELS = {
    airplane: "Airplane",
    public_transit: "Public transit",
    train: "Train",
    off: "Off",
  };
  const GESTURE_ACTION_LABELS = {
    none: "None",
    previous_song: "Previous song",
    next_song: "Next song",
    volume_up: "Volume up",
    volume_down: "Volume down",
    play_pause: "Play/Pause",
    voice_assistant: "Voice assistant",
    noise_cancellation: "Noise cancellation",
    adjust_volume: "Adjust volume",
  };
  const TAP_OPTIONS = [
    { value: "none", label: "None" },
    { value: "previous_song", label: "Previous song" },
    { value: "next_song", label: "Next song" },
    { value: "volume_up", label: "Volume up" },
    { value: "volume_down", label: "Volume down" },
    { value: "play_pause", label: "Play/Pause" },
  ];
  const SWIPE_OPTIONS = [
    { value: "adjust_volume", label: "Adjust volume" },
    { value: "none", label: "None" },
  ];
  const IMMERSIVE_OPTIONS = [
    { value: "airplane", label: "Airplane" },
    { value: "public_transit", label: "Public transit" },
    { value: "train", label: "Train" },
    { value: "off", label: "Off" },
  ];
  const SPATIAL_SCENE_LABELS = {
    standard: "Standard",
    music: "Music",
    video: "Video",
    game: "Game",
    audiobooks: "Audiobooks",
  };
  const EQ_PRESET_LABELS = {
    standard: "Standard",
    bass: "Enhance bass",
    treble: "Enhance treble",
    voice: "Enhance voice",
  };
  const WEARING_LABELS = {
    in_ear: "In ear",
    out: "Out of ear",
    in_case: "In case",
    unknown: "Unknown",
  };

  let appState = null;
  let navStack = ["overview"];
  let currentHoldSide = "left";
  let toastTimer = null;
  let audioPlayedByUser = false;
  let lastRingingState = false;
  let activeSliderDrag = false;
  let activeVolumeDrag = false;

  const $ = (sel) => document.querySelector(sel);
  const $$ = (sel) => Array.from(document.querySelectorAll(sel));

  async function apiGet(url) {
    const res = await fetch(url, { cache: "no-store" });
    const data = await res.json().catch(() => ({}));
    if (!res.ok) throw new Error(data.error || `HTTP ${res.status}`);
    return data;
  }

  async function apiPost(url, body) {
    const res = await fetch(url, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body || {}),
    });
    const data = await res.json().catch(() => ({}));
    if (!res.ok) throw new Error(data.error || `HTTP ${res.status}`);
    return data;
  }

  async function runAction(fn) {
    try {
      await fn();
    } catch (err) {
      showToast(err && err.message ? err.message : "Operation failed");
    }
  }

  function showToast(msg) {
    const toast = $("#mi-toast");
    toast.textContent = msg;
    toast.classList.remove("hidden");
    clearTimeout(toastTimer);
    toastTimer = setTimeout(() => toast.classList.add("hidden"), 2800);
  }

  function formatBatteryPct(val) {
    if (val === null || val === undefined || Number.isNaN(Number(val))) return "—";
    return `${val}%`;
  }

  function applyTheme(theme) {
    const root = document.documentElement;
    const t = theme || { mode: "dark", custom_base: "dark", accent: "#2581FF", bg: "#0A0E17", card: "#131A29" };
    const mode = t.mode || "dark";
    const isLight = mode === "light" || (mode === "custom" && t.custom_base === "light");

    root.setAttribute("data-theme-base", isLight ? "light" : "dark");

    if (mode === "custom") {
      root.style.setProperty("--mi-blue", t.accent || "#2581FF");
      root.style.setProperty("--bg-pure", t.bg || (isLight ? "#F5F6F8" : "#0A0E17"));
      root.style.setProperty("--card-bg", t.card || (isLight ? "#FFFFFF" : "#131A29"));
      root.style.setProperty("--popup-bg", t.card || (isLight ? "#FFFFFF" : "#131A29"));
    } else {
      root.style.removeProperty("--mi-blue");
      root.style.removeProperty("--bg-pure");
      root.style.removeProperty("--card-bg");
      root.style.removeProperty("--popup-bg");
    }

    // Update Dolby Audio badge contrast automatically for light/dark themes
    const dolbyImg = $("#dolby-logo-img");
    if (dolbyImg) {
      dolbyImg.src = isLight
        ? "/assets/xiaomi_8_pro/dolby_light.png"
        : "/assets/xiaomi_8_pro/dolby_dark.png";
    }

    // Sync theme controls UI
    $$(".theme-seg-btn").forEach((btn) => {
      btn.classList.toggle("active", btn.dataset.themeMode === mode);
    });
    const isCustom = mode === "custom";
    $("#custom-theme-panel").classList.toggle("hidden", !isCustom);
    $("#btn-theme-reset").classList.toggle("hidden", mode === "dark");

    $$("[data-custom-base]").forEach((btn) => {
      btn.classList.toggle("primary", btn.dataset.customBase === (t.custom_base || "dark"));
    });

    const accentUpper = (t.accent || "#2581FF").toUpperCase();
    $$(".accent-swatch").forEach((sw) => {
      sw.classList.toggle("selected", (sw.dataset.accent || "").toUpperCase() === accentUpper);
    });

    const accentInput = $("#input-theme-accent");
    const bgInput = $("#input-theme-bg");
    const cardInput = $("#input-theme-card");
    if (accentInput && document.activeElement !== accentInput) accentInput.value = t.accent || "#2581FF";
    if (bgInput && document.activeElement !== bgInput) bgInput.value = t.bg || "#0A0E17";
    if (cardInput && document.activeElement !== cardInput) cardInput.value = t.card || "#131A29";

    return isLight;
  }

  function injectStaticIcons() {
    $$(".noise-icon-slot").forEach((el) => {
      el.innerHTML = NOISE_ICONS[el.dataset.icon] || "";
    });
    $$(".hold-mode-icon").forEach((el) => {
      el.innerHTML = NOISE_ICONS[el.dataset.icon] || "";
    });
    $$(".blue-icon-circle").forEach((el) => {
      el.innerHTML = MENU_ICONS[el.dataset.menuIcon] || "";
    });
    $$(".back-btn").forEach((el) => {
      el.innerHTML = UI_ICONS.backArrow;
    });
    $$(".row-chevron").forEach((el) => {
      el.innerHTML = UI_ICONS.chevronRight;
    });
    $$(".updown-chevrons").forEach((el) => {
      el.innerHTML = UI_ICONS.upDownChevrons;
    });
    $("#icon-anc-light").innerHTML = SLIDER_ICONS.ancLight;
    $("#icon-anc-deep").innerHTML = SLIDER_ICONS.ancDeep;
    $("#icon-trans-small").innerHTML = SLIDER_ICONS.transSmall;
    $("#icon-trans-large").innerHTML = SLIDER_ICONS.transLarge;
  }

  function navigateTo(screenName, resetToTab = false) {
    closePopup();
    if (resetToTab) {
      navStack = screenName === "overview" ? ["overview"] : ["overview", screenName];
    } else if (navStack[navStack.length - 1] !== screenName) {
      navStack.push(screenName);
    }
    syncScreenClasses();
  }

  function navigateBack() {
    closePopup();
    if (navStack.length <= 1) return;
    navStack.pop();
    syncScreenClasses();
  }

  function syncScreenClasses() {
    const active = navStack[navStack.length - 1];
    $$(".screen").forEach((sec) => {
      sec.classList.toggle("screen-active", sec.dataset.screen === active);
    });

    const tabName = active === "press-hold" ? "gestures" : active;
    $$(".nav-pill").forEach((pill) => {
      pill.classList.toggle("active", pill.dataset.tab === tabName);
    });
  }

  function openPopup(anchorEl, options, currentValue, onSelect) {
    const backdrop = $("#popup-backdrop");
    const menu = $("#popup-menu");
    const rect = anchorEl.getBoundingClientRect();

    menu.innerHTML = "";
    options.forEach((opt) => {
      const btn = document.createElement("button");
      btn.type = "button";
      btn.className = "popup-item" + (opt.value === currentValue ? " selected" : "");

      const labelSpan = document.createElement("span");
      labelSpan.textContent = opt.label;
      const checkSpan = document.createElement("span");
      checkSpan.className = "popup-check";
      if (opt.value === currentValue) {
        checkSpan.innerHTML = UI_ICONS.checkMark;
      }

      btn.appendChild(labelSpan);
      btn.appendChild(checkSpan);
      btn.addEventListener("click", (ev) => {
        ev.stopPropagation();
        closePopup();
        onSelect(opt.value);
      });
      menu.appendChild(btn);
    });

    backdrop.classList.remove("hidden");

    const menuHeight = menu.offsetHeight || options.length * 46 + 20;
    const vw = window.innerWidth;
    const vh = window.innerHeight;
    let top = rect.top - 4;
    if (top + menuHeight > vh - 16) {
      top = Math.max(16, vh - menuHeight - 16);
    }
    if (top < 16) top = 16;

    const rightOffset = Math.max(16, vw - rect.right - 2);
    menu.style.top = `${Math.round(top)}px`;
    menu.style.right = `${Math.round(rightOffset)}px`;
  }

  function closePopup() {
    $("#popup-backdrop").classList.add("hidden");
  }

  function syncRingAudio(isLive, anyRing) {
    const effectiveRing = isLive && anyRing;
    if (!effectiveRing) {
      if (lastRingingState) {
        lastRingingState = false;
        window.XiaomiAudio.setRinging(false);
      }
    } else if (audioPlayedByUser && !lastRingingState) {
      lastRingingState = true;
      window.XiaomiAudio.setRinging(true);
    }
  }

  function renderState(state) {
    appState = state;
    const {
      device,
      capabilities = {},
      battery,
      noise,
      immersive_commute,
      immersive_commute_volume = 65,
      theme,
      gestures,
      audio_effects,
      additional_settings,
      find_earphones,
      bluetooth,
    } = state;

    const isLight = applyTheme(theme);
    const isLive = device.mode === "live" && Boolean(device.connected);

    // Header & Hero
    const displayTitle = device.name || "MiBuds Linux";
    $("#device-title").textContent = displayTitle;
    document.title = isLive ? `${displayTitle} — MiBuds Linux` : "MiBuds Linux";

    const livePill = $("#live-pill");
    const liveText = $("#live-pill-text");
    livePill.classList.toggle("pill-live", isLive);
    liveText.textContent = isLive
      ? `Connected · ch.${device.rfcomm_channel || "?"}${device.authenticated ? " · SAFER+" : ""}`
      : (bluetooth.scanning ? "Scanning..." : "Disconnected");

    const color = device.color || "black";
    $("#hero-earbuds-img").src = `/assets/xiaomi_8_pro/hero_${color}.png`;
    $("#find-buds-img").src = `/assets/xiaomi_8_pro/hero_${color}.png`;
    $("#fw-hero-img").src = `/assets/xiaomi_8_pro/hero_${color}.png`;
    $("#fit-test-img").src = `/assets/xiaomi_8_pro/fit_${color}.png`;

    const dolbyWrap = $("#dolby-badge-wrap");
    dolbyWrap.classList.toggle("hidden", device.has_dolby_badge === false);
    dolbyWrap.classList.toggle("dolby-off", !isLive || !audio_effects.spatial_audio);

    const wearing = device.wearing || {};
    const anyInEar = wearing.left === "in_ear" || wearing.right === "in_ear";
    if (isLive) {
      const wearSuffix =
        wearing.left === "unknown" && wearing.right === "unknown"
          ? ""
          : (anyInEar ? " · In ear" : " · Out of ear");
      $("#connection-status-text").textContent = `Connected${wearSuffix}`;
    } else {
      $("#connection-status-text").textContent = bluetooth.scanning ? "Scanning BlueZ..." : "Disconnected";
    }

    // Disconnected onboarding banner
    $("#connect-banner").classList.toggle("hidden", isLive);

    // Battery Card
    $("#bat-icon-left").innerHTML = batterySvg(battery.left, battery.left_charging, isLight);
    $("#bat-pct-left").textContent = formatBatteryPct(battery.left);
    $("#bat-label-left").textContent = battery.left_charging ? "L · Charging" : "L";
    $("#bat-icon-right").innerHTML = batterySvg(battery.right, battery.right_charging, isLight);
    $("#bat-pct-right").textContent = formatBatteryPct(battery.right);
    $("#bat-label-right").textContent = battery.right_charging ? "R · Charging" : "R";
    $("#bat-icon-case").innerHTML = batterySvg(battery.case, battery.case_charging, isLight);
    $("#bat-pct-case").textContent = formatBatteryPct(battery.case);
    const caseLabelEl = $("#bat-label-case");
    if (caseLabelEl) {
      if (battery.case_available) caseLabelEl.textContent = battery.case_charging ? "Case · Charging" : "Case";
      else if (battery.case_stale && battery.case !== null) caseLabelEl.textContent = "Case (last)";
      else caseLabelEl.textContent = isLive ? "Open case" : "Case";
    }

    const showCase = Boolean(battery.show_case) || Boolean(battery.case_available);
    $("#battery-case-divider").classList.toggle("hidden", !showCase);
    $("#battery-case-col").classList.toggle("hidden", !showCase);

    // Noise Control Card
    $$(".noise-mode-btn").forEach((btn) => {
      btn.classList.toggle("active", isLive && btn.dataset.mode === noise.mode);
    });
    const showAncSub = isLive && noise.mode === "anc";
    const showTransSub = isLive && noise.mode === "transparency";
    $("#anc-subpanel").classList.toggle("hidden", !showAncSub);
    $("#transparency-subpanel").classList.toggle("hidden", !showTransSub);
    $("#smart-anc-row").classList.toggle("hidden", capabilities.smart_anc === false);

    $("#toggle-smart-anc").setAttribute("aria-checked", String(Boolean(noise.smart_anc)));
    $(".anc-slider-block").classList.toggle("smart-muted", Boolean(noise.smart_anc));
    $("#anc-slider-track").setAttribute("aria-valuenow", String(noise.anc_level));

    $("#transparency-mode-label").textContent = TRANSPARENCY_LABELS[noise.transparency_level] || "Enhance voice";
    $("#trans-slider-track").setAttribute("aria-valuenow", String(noise.transparency_level));

    if (!activeSliderDrag) {
      requestAnimationFrame(() => {
        if (showAncSub) positionThumb("#anc-slider-track", "#anc-slider-thumb", noise.anc_level / 19);
        if (showTransSub) positionThumb("#trans-slider-track", "#trans-slider-thumb", noise.transparency_level / 2);
      });
    }

    // Immersive commute (audio played natively via PipeWire/GStreamer in backend)
    $("#immersive-commute-card").classList.toggle("hidden", isLive && capabilities.immersive_commute === false);
    const activeCommute = isLive && immersive_commute && immersive_commute !== "off";
    $("#immersive-commute-value").textContent = activeCommute ? (IMMERSIVE_LABELS[immersive_commute] || "Off") : "Off";
    $("#immersive-volume-panel").classList.toggle("hidden", !activeCommute);
    if (!activeVolumeDrag) {
      $("#immersive-volume-slider").value = String(immersive_commute_volume);
      $("#immersive-volume-val").textContent = `${immersive_commute_volume}%`;
    }

    // Overview dynamic summaries
    if (isLive) {
      $("#overview-gestures-summary").textContent =
        `Tap L/R: ${GESTURE_ACTION_LABELS[gestures.single.left]} · Swipe: ${GESTURE_ACTION_LABELS[gestures.swipe.left]}`;
      const eqLabel = EQ_PRESET_LABELS[audio_effects.eq_preset] || (audio_effects.eq_preset === "custom" ? "Custom (mobile app)" : "Standard");
      $("#overview-audio-summary").textContent =
        `${audio_effects.spatial_audio ? "Spatial Audio · " : ""}EQ: ${eqLabel}`;
      $("#overview-additional-summary").textContent =
        `In-ear: ${additional_settings.in_ear_detection ? "On" : "Off"} · Dual conn: ${additional_settings.dual_connection ? "On" : "Off"}`;
      $("#home-fw-subtitle").textContent = device.firmware
        ? `Current version: ${device.firmware}`
        : "Firmware version unavailable";
      $("#overview-bt-summary").textContent =
        `RFCOMM ch.${device.rfcomm_channel || "?"}${device.authenticated ? " · SAFER+ verified" : ""}`;
      $("#overview-device-summary").textContent = device.model_id
        ? `Model ${device.model_id} · Theme & finish`
        : "Theme, hardware info & Case toggle";
    } else {
      $("#overview-gestures-summary").textContent = "Customize tap, hold, and swipe actions";
      $("#overview-audio-summary").textContent = "Spatial audio and equalizer presets";
      $("#overview-additional-summary").textContent = "In-ear detection, dual connection, wearing status";
      $("#home-fw-subtitle").textContent = "Connect earbuds to read firmware";
      $("#overview-bt-summary").textContent = "BlueZ RFCOMM session & packet monitor";
      $("#overview-device-summary").textContent = "Theme (Dark / Light / Custom) & hardware info";
    }

    // Firmware info screen
    $("#fw-version-big").textContent = isLive ? (device.firmware || "Unknown") : "—";
    $("#fw-status-text").textContent = isLive
      ? "For safety, OTA firmware flashing is intentionally disabled on Linux. Use the official Xiaomi Earbuds mobile app to install firmware updates."
      : "Connect your earphones to read their installed firmware version. For safety, OTA firmware flashing is intentionally disabled on Linux — use the official Xiaomi Earbuds mobile app to update firmware.";

    // Gestures screen values
    ["single", "double", "triple", "hold", "swipe"].forEach((g) => {
      ["left", "right"].forEach((side) => {
        const el = $(`#val-${g}-${side}`);
        if (el && gestures[g]) {
          el.textContent = isLive ? (GESTURE_ACTION_LABELS[gestures[g][side]] || gestures[g][side]) : "—";
        }
      });
    });

    // Press and hold detail screen
    renderPressHoldScreen(state);

    // Audio effects screen
    const showSpatial = !isLive || capabilities.spatial_audio !== false;
    $("#spatial-card").classList.toggle("hidden", !showSpatial);
    $("#row-head-tracking").classList.toggle("hidden", isLive && capabilities.head_tracking === false);
    $("#btn-spatial-scene").classList.toggle("hidden", isLive && capabilities.spatial_scene === false);
    $("#row-adaptive-sound").classList.toggle("hidden", isLive && capabilities.adaptive_sound === false);

    $("#toggle-spatial-audio").setAttribute("aria-checked", String(Boolean(audio_effects.spatial_audio)));
    $("#toggle-head-tracking").setAttribute("aria-checked", String(Boolean(audio_effects.head_tracking)));
    $("#toggle-adaptive-sound").setAttribute("aria-checked", String(Boolean(audio_effects.adaptive_sound)));
    $("#val-spatial-scene").textContent = SPATIAL_SCENE_LABELS[audio_effects.spatial_scene] || "Standard";
    $("#val-eq-preset").textContent =
      EQ_PRESET_LABELS[audio_effects.eq_preset] ||
      (audio_effects.eq_preset === "custom" ? "Custom (mobile app)" : "Standard");

    // Additional settings screen
    $("#row-in-ear").classList.toggle("hidden", isLive && capabilities.in_ear_detection === false);
    $("#row-dual-conn").classList.toggle("hidden", isLive && capabilities.dual_connection === false);
    $("#row-auto-answer").classList.toggle("hidden", isLive && capabilities.auto_answer === false);
    $("#row-adaptive-vol").classList.toggle("hidden", capabilities.adaptive_volume !== true);

    $("#toggle-in-ear").setAttribute("aria-checked", String(Boolean(additional_settings.in_ear_detection)));
    $("#toggle-dual-conn").setAttribute("aria-checked", String(Boolean(additional_settings.dual_connection)));
    $("#toggle-auto-answer").setAttribute("aria-checked", String(Boolean(additional_settings.auto_answer)));
    $("#toggle-adaptive-vol").setAttribute("aria-checked", String(Boolean(additional_settings.adaptive_volume)));

    const leftWear = isLive ? (wearing.left || "unknown") : "unknown";
    const rightWear = isLive ? (wearing.right || "unknown") : "unknown";
    const leftBadge = $("#wearing-badge-left");
    const rightBadge = $("#wearing-badge-right");
    leftBadge.textContent = `L: ${WEARING_LABELS[leftWear] || "Unknown"}`;
    rightBadge.textContent = `R: ${WEARING_LABELS[rightWear] || "Unknown"}`;
    leftBadge.classList.toggle("fit-neutral", leftWear !== "in_ear");
    rightBadge.classList.toggle("fit-neutral", rightWear !== "in_ear");

    // Find earphones
    $("#btn-ring-left").classList.toggle("ringing", isLive && Boolean(find_earphones.ringing_left));
    $("#btn-ring-right").classList.toggle("ringing", isLive && Boolean(find_earphones.ringing_right));
    const anyRing = isLive && Boolean(find_earphones.ringing_left || find_earphones.ringing_right);
    const ringBothBtn = $("#btn-ring-both");
    ringBothBtn.classList.toggle("active-ring", anyRing);
    ringBothBtn.textContent = anyRing ? "Stop Ringing" : "Ring Both Earphones";
    syncRingAudio(isLive, anyRing);

    // About device
    $("#about-name").textContent = isLive ? (device.name || "—") : "—";
    $("#about-model").textContent = device.model_id || "—";
    $("#about-sale-model").textContent = device.sale_model || "—";
    $("#about-fw").textContent = device.firmware || "—";
    $("#about-vidpid").textContent = device.vid && device.pid ? `${device.vid} / ${device.pid}` : "—";
    $("#about-serial").textContent = device.serial || "—";
    $("#about-uuid").textContent = device.service_uuid || "—";
    $$(".color-dot").forEach((dot) => dot.classList.toggle("selected", dot.dataset.color === color));
    $("#toggle-show-case").setAttribute("aria-checked", String(Boolean(battery.show_case)));

    // Manage / BlueZ diagnostics
    $("#bt-mode-badge").textContent = isLive ? "BlueZ RFCOMM Live" : "Disconnected";
    $("#bt-mac-val").textContent = device.mac_address || "—";
    $("#bt-chan-val").textContent = device.rfcomm_channel ? `Channel ${device.rfcomm_channel}` : "—";
    $("#bt-auth-val").textContent = isLive
      ? (device.authenticated ? "SAFER+ Verified" : "Unauthenticated")
      : "Standby";
    $("#btn-bt-disconnect").classList.toggle("hidden", !isLive);
    $("#btn-bt-connect").textContent = isLive ? "Reconnect" : "Connect";

    const errBanner = $("#bt-error-banner");
    const homeErrBanner = $("#banner-error-note");
    if (bluetooth.last_error) {
      errBanner.textContent = bluetooth.last_error;
      errBanner.classList.remove("hidden");
      if (homeErrBanner) {
        homeErrBanner.textContent = bluetooth.last_error;
        homeErrBanner.classList.remove("hidden");
      }
    } else {
      errBanner.textContent = "";
      errBanner.classList.add("hidden");
      if (homeErrBanner) {
        homeErrBanner.textContent = "";
        homeErrBanner.classList.add("hidden");
      }
    }

    renderBluetoothDevices(bluetooth.paired_devices || [], device.mac_address, isLive);
    renderTxLog(bluetooth.tx_log || []);
  }

  function renderPressHoldScreen(state) {
    const titleEl = $("#press-hold-title");
    titleEl.textContent = `Press and hold ${currentHoldSide} earphone`;

    const action = state.gestures.hold[currentHoldSide];
    $$(".hold-action-option").forEach((btn) => {
      const selected = btn.dataset.holdAction === action;
      btn.classList.toggle("selected", selected);
      btn.querySelector(".hold-check-slot").innerHTML = selected ? UI_ICONS.checkMark : "";
    });

    const modesList = $("#hold-cycle-modes-list");
    modesList.classList.toggle("disabled", action !== "noise_cancellation");

    const selectedModes = new Set(state.gestures.hold_modes[currentHoldSide] || ["transparency", "off"]);
    $$(".hold-cycle-row").forEach((row) => {
      const checked = selectedModes.has(row.dataset.cycleMode);
      row.classList.toggle("checked", checked);
      row.querySelector(".mi-radio-check").innerHTML = checked ? UI_ICONS.checkMark : "";
    });
  }

  function renderBluetoothDevices(devices, activeMac, isLive) {
    const list = $("#bt-devices-list");
    list.innerHTML = "";
    if (!devices.length) {
      const empty = document.createElement("div");
      empty.className = "tx-log-item";
      empty.textContent = "No paired Bluetooth devices found in BlueZ. Pair and connect your earbuds in Linux Bluetooth settings, then click Scan BlueZ.";
      list.appendChild(empty);
      return;
    }

    devices.forEach((d) => {
      const item = document.createElement("div");
      item.className = "bt-device-item";

      const infoWrap = document.createElement("div");
      const nameDiv = document.createElement("div");
      nameDiv.className = "bt-device-name";
      nameDiv.textContent = d.name || d.address;

      const metaDiv = document.createElement("div");
      metaDiv.className = "bt-device-meta";
      const statusLabel = d.connected ? "Connected in BlueZ" : "Paired";
      const supportTag = d.supported ? " · Xiaomi/Redmi" : "";
      metaDiv.textContent = `${d.address} · ${statusLabel}${supportTag}`;

      infoWrap.appendChild(nameDiv);
      infoWrap.appendChild(metaDiv);

      const isThisActive = isLive && activeMac && d.address.toUpperCase() === activeMac.toUpperCase();
      const btn = document.createElement("button");
      btn.type = "button";
      btn.className = `mi-pill-btn ${isThisActive ? "" : (d.supported ? "primary" : "")}`;
      btn.textContent = isThisActive ? "Connected" : "Connect";
      btn.addEventListener("click", () => runAction(async () => {
        showToast(`Connecting to ${d.name}...`);
        const st = await apiPost("/api/bluetooth/connect", { address: d.address, name: d.name });
        renderState(st);
        if (st.bluetooth.last_error) showToast(st.bluetooth.last_error);
        else showToast(`Connected to ${st.device.name}`);
      }));

      item.appendChild(infoWrap);
      item.appendChild(btn);
      list.appendChild(item);
    });
  }

  function renderTxLog(entries) {
    const list = $("#tx-log-list");
    list.innerHTML = "";
    if (!entries.length) {
      const empty = document.createElement("div");
      empty.className = "tx-log-item";
      empty.textContent = "No RCSP packets logged yet. Connect your earbuds and toggle a setting to inspect live TX/RX frames.";
      list.appendChild(empty);
      return;
    }

    entries.forEach((e) => {
      const item = document.createElement("div");
      item.className = "tx-log-item";

      const meta = document.createElement("div");
      meta.className = "tx-log-meta";
      const labelSpan = document.createElement("span");
      labelSpan.textContent = e.label || "";
      const timeSpan = document.createElement("span");
      timeSpan.textContent = `${e.ts || ""} · ${e.transport || ""}`;
      meta.appendChild(labelSpan);
      meta.appendChild(timeSpan);

      const hexDiv = document.createElement("div");
      hexDiv.className = "tx-log-hex";
      hexDiv.textContent = e.hex || "";

      item.appendChild(meta);
      item.appendChild(hexDiv);
      list.appendChild(item);
    });
  }

  function positionThumb(trackSel, thumbSel, ratio) {
    const track = $(trackSel);
    const thumb = $(thumbSel);
    if (!track || !thumb) return;
    const clamped = Math.max(0, Math.min(1, Number(ratio) || 0));
    const width = track.clientWidth;
    if (!width) return;
    const minX = 12;
    const maxX = Math.max(minX, width - 12);
    const x = minX + clamped * (maxX - minX);
    thumb.style.left = `${x.toFixed(1)}px`;
  }

  function setupSliderDrag(trackSel, thumbSel, steps, getCurrent, onChangeImmediate, onCommit) {
    const track = $(trackSel);
    let dragging = false;

    const ratioFromEvent = (ev) => {
      const rect = track.getBoundingClientRect();
      const pad = 12;
      const usable = Math.max(1, rect.width - pad * 2);
      return Math.max(0, Math.min(1, (ev.clientX - rect.left - pad) / usable));
    };

    const valueFromRatio = (r) => Math.round(r * (steps - 1));

    const handleMove = (ev) => {
      if (!dragging) return;
      const r = ratioFromEvent(ev);
      const val = valueFromRatio(r);
      const displayRatio = steps <= 5 ? val / (steps - 1) : r;
      positionThumb(trackSel, thumbSel, displayRatio);
      onChangeImmediate(val);
    };

    track.addEventListener("pointerdown", (ev) => {
      dragging = true;
      activeSliderDrag = true;
      track.setPointerCapture(ev.pointerId);
      handleMove(ev);
    });

    track.addEventListener("pointermove", handleMove);

    const endDrag = (ev) => {
      if (!dragging) return;
      dragging = false;
      activeSliderDrag = false;
      const val = valueFromRatio(ratioFromEvent(ev));
      positionThumb(trackSel, thumbSel, val / (steps - 1));
      onCommit(val);
    };

    track.addEventListener("pointerup", endDrag);
    track.addEventListener("pointercancel", endDrag);

    track.addEventListener("keydown", (ev) => {
      const cur = Number(getCurrent()) || 0;
      let next = cur;
      if (ev.key === "ArrowLeft" || ev.key === "ArrowDown") next = Math.max(0, cur - 1);
      else if (ev.key === "ArrowRight" || ev.key === "ArrowUp") next = Math.min(steps - 1, cur + 1);
      else if (ev.key === "Home") next = 0;
      else if (ev.key === "End") next = steps - 1;
      else return;
      ev.preventDefault();
      if (next !== cur) {
        positionThumb(trackSel, thumbSel, next / (steps - 1));
        onChangeImmediate(next);
        onCommit(next);
      }
    });
  }

  function bindEvents() {
    // Topbar navigation pills
    $$(".nav-pill[data-tab]").forEach((pill) => {
      pill.addEventListener("click", () => navigateTo(pill.dataset.tab, true));
    });

    // Header navigation & quick actions
    $("#btn-manage-earphones").addEventListener("click", () => navigateTo("manage", true));
    $("#btn-theme-shortcut").addEventListener("click", () => navigateTo("about-device", true));
    $("#btn-add-device").addEventListener("click", () => navigateTo("manage", true));
    $("#live-pill").addEventListener("click", () => navigateTo("manage", true));
    $("#btn-quick-refresh").addEventListener("click", () => runAction(async () => {
      renderState(await apiPost("/api/battery/refresh", {}));
      showToast("Requested battery & status from earbuds");
    }));

    // Onboarding banner buttons
    $("#btn-banner-connect").addEventListener("click", () => runAction(async () => {
      showToast("Scanning BlueZ & connecting...");
      const st = await apiPost("/api/bluetooth/connect", {});
      renderState(st);
      if (st.bluetooth.last_error) showToast(st.bluetooth.last_error);
      else showToast(`Connected to ${st.device.name}`);
    }));
    $("#btn-banner-manage").addEventListener("click", () => navigateTo("manage", true));

    // Overview menu navigation
    $$(".menu-row[data-nav]").forEach((btn) => {
      btn.addEventListener("click", () => navigateTo(btn.dataset.nav));
    });

    // Back buttons
    $$(".back-btn[data-back]").forEach((btn) => {
      btn.addEventListener("click", navigateBack);
    });

    // Noise control 3 mode buttons
    $$(".noise-mode-btn").forEach((btn) => {
      btn.addEventListener("click", () => runAction(async () => {
        audioPlayedByUser = true;
        const mode = btn.dataset.mode;
        const st = await apiPost("/api/noise", { mode });
        renderState(st);
        if (st.bluetooth && st.bluetooth.warning) showToast(st.bluetooth.warning);
      }));
    });

    // Smart noise cancellation switch
    $("#toggle-smart-anc").addEventListener("click", () => runAction(async () => {
      const next = !appState.noise.smart_anc;
      const st = await apiPost("/api/noise", { smart_anc: next });
      renderState(st);
      if (st.bluetooth && st.bluetooth.warning) showToast(st.bluetooth.warning);
    }));

    // ANC Continuous Slider (0..19)
    setupSliderDrag(
      "#anc-slider-track",
      "#anc-slider-thumb",
      20,
      () => (appState ? appState.noise.anc_level : 18),
      (val) => {
        if (appState) appState.noise.anc_level = val;
      },
      (val) => runAction(async () => {
        const st = await apiPost("/api/noise", { anc_level: val, smart_anc: false });
        renderState(st);
        if (st.bluetooth && st.bluetooth.warning) showToast(st.bluetooth.warning);
      })
    );

    // Transparency 3-step Snapped Slider (0..2)
    setupSliderDrag(
      "#trans-slider-track",
      "#trans-slider-thumb",
      3,
      () => (appState ? appState.noise.transparency_level : 1),
      (val) => {
        $("#transparency-mode-label").textContent = TRANSPARENCY_LABELS[val];
      },
      (val) => runAction(async () => {
        const st = await apiPost("/api/noise", { transparency_level: val });
        renderState(st);
        if (st.bluetooth && st.bluetooth.warning) showToast(st.bluetooth.warning);
      })
    );

    // Immersive commute floating popup + ambient volume slider
    $("#immersive-commute-trigger").addEventListener("click", () => {
      const anchor = $("#immersive-commute-trigger .row-right-selector");
      openPopup(anchor, IMMERSIVE_OPTIONS, appState.immersive_commute, (mode) => runAction(async () => {
        const next = await apiPost("/api/immersive-commute", { mode });
        renderState(next);
        if (next.bluetooth && next.bluetooth.warning) showToast(next.bluetooth.warning);
        else if (mode !== "off") showToast(`Immersive commute: ${IMMERSIVE_LABELS[mode]}`);
        else showToast("Immersive commute turned off");
      }));
    });

    const volSlider = $("#immersive-volume-slider");
    volSlider.addEventListener("pointerdown", () => { activeVolumeDrag = true; });
    volSlider.addEventListener("pointerup", () => { activeVolumeDrag = false; });
    volSlider.addEventListener("pointercancel", () => { activeVolumeDrag = false; });
    volSlider.addEventListener("input", () => {
      $("#immersive-volume-val").textContent = `${volSlider.value}%`;
    });
    volSlider.addEventListener("change", () => runAction(async () => {
      activeVolumeDrag = false;
      renderState(await apiPost("/api/immersive-commute/volume", { volume: Number(volSlider.value) }));
    }));

    // Theme controls (Dark / Light / Custom)
    $$(".theme-seg-btn").forEach((btn) => {
      btn.addEventListener("click", () => runAction(async () => {
        renderState(await apiPost("/api/theme", { mode: btn.dataset.themeMode }));
      }));
    });
    $$("[data-custom-base]").forEach((btn) => {
      btn.addEventListener("click", () => runAction(async () => {
        const base = btn.dataset.customBase;
        const defaults = base === "light"
          ? { bg: "#F4F6FB", card: "#FFFFFF" }
          : { bg: "#0A0E17", card: "#131A29" };
        renderState(await apiPost("/api/theme", { mode: "custom", custom_base: base, ...defaults }));
      }));
    });
    $$(".accent-swatch").forEach((sw) => {
      sw.addEventListener("click", () => runAction(async () => {
        renderState(await apiPost("/api/theme", { mode: "custom", accent: sw.dataset.accent }));
      }));
    });
    $("#input-theme-accent").addEventListener("input", (ev) => {
      document.documentElement.style.setProperty("--mi-blue", ev.target.value);
    });
    $("#input-theme-accent").addEventListener("change", (ev) => runAction(async () => {
      renderState(await apiPost("/api/theme", { mode: "custom", accent: ev.target.value }));
    }));
    $("#input-theme-bg").addEventListener("input", (ev) => {
      document.documentElement.style.setProperty("--bg-pure", ev.target.value);
    });
    $("#input-theme-bg").addEventListener("change", (ev) => runAction(async () => {
      renderState(await apiPost("/api/theme", { mode: "custom", bg: ev.target.value }));
    }));
    $("#input-theme-card").addEventListener("input", (ev) => {
      document.documentElement.style.setProperty("--card-bg", ev.target.value);
      document.documentElement.style.setProperty("--popup-bg", ev.target.value);
    });
    $("#input-theme-card").addEventListener("change", (ev) => runAction(async () => {
      renderState(await apiPost("/api/theme", { mode: "custom", card: ev.target.value }));
    }));
    $("#btn-theme-reset").addEventListener("click", () => runAction(async () => {
      renderState(await apiPost("/api/theme", { reset: true }));
      showToast("Restored default OLED Dark theme");
    }));

    // Gestures popup rows (Tap & Swipe)
    $$(".flat-row[data-gesture-popup]").forEach((row) => {
      row.addEventListener("click", () => {
        const [gesture, side] = row.dataset.gesturePopup.split(":");
        const options = gesture === "swipe" ? SWIPE_OPTIONS : TAP_OPTIONS;
        const current = appState.gestures[gesture][side];
        const anchor = row.querySelector(".row-right-selector");
        openPopup(anchor, options, current, (action) => runAction(async () => {
          renderState(await apiPost("/api/gestures", { gesture, side, action }));
        }));
      });
    });

    // Press and hold rows -> dedicated sub-screen
    $$(".flat-row[data-hold-side]").forEach((row) => {
      row.addEventListener("click", () => {
        currentHoldSide = row.dataset.holdSide;
        renderPressHoldScreen(appState);
        navigateTo("press-hold");
      });
    });

    // Press and hold action choices
    $$(".hold-action-option").forEach((btn) => {
      btn.addEventListener("click", () => runAction(async () => {
        renderState(
          await apiPost("/api/gestures", {
            gesture: "hold",
            side: currentHoldSide,
            action: btn.dataset.holdAction,
          })
        );
      }));
    });

    // Press and hold NC cycle modes (minimum 2 selected)
    $$(".hold-cycle-row").forEach((row) => {
      row.addEventListener("click", () => runAction(async () => {
        const mode = row.dataset.cycleMode;
        const current = [...(appState.gestures.hold_modes[currentHoldSide] || [])];
        const idx = current.indexOf(mode);
        if (idx >= 0) {
          if (current.length <= 2) {
            showToast("Select at least two options");
            return;
          }
          current.splice(idx, 1);
        } else {
          current.push(mode);
        }
        renderState(await apiPost("/api/press-hold-modes", { side: currentHoldSide, modes: current }));
      }));
    });

    // Audio effects controls
    $("#toggle-spatial-audio").addEventListener("click", () => runAction(async () => {
      renderState(await apiPost("/api/audio-effects", { spatial_audio: !appState.audio_effects.spatial_audio }));
    }));
    $("#toggle-head-tracking").addEventListener("click", () => runAction(async () => {
      renderState(
        await apiPost("/api/audio-effects", {
          spatial_audio: true,
          head_tracking: !appState.audio_effects.head_tracking,
        })
      );
    }));
    $("#toggle-adaptive-sound").addEventListener("click", () => runAction(async () => {
      renderState(await apiPost("/api/audio-effects", { adaptive_sound: !appState.audio_effects.adaptive_sound }));
    }));
    $("#btn-spatial-scene").addEventListener("click", () => {
      const opts = Object.entries(SPATIAL_SCENE_LABELS).map(([value, label]) => ({ value, label }));
      openPopup($("#btn-spatial-scene .row-right-selector"), opts, appState.audio_effects.spatial_scene, (spatial_scene) =>
        runAction(async () => {
          renderState(await apiPost("/api/audio-effects", { spatial_scene }));
        })
      );
    });
    $("#btn-eq-preset").addEventListener("click", () => {
      const opts = Object.entries(EQ_PRESET_LABELS).map(([value, label]) => ({ value, label }));
      openPopup($("#btn-eq-preset .row-right-selector"), opts, appState.audio_effects.eq_preset, (eq_preset) =>
        runAction(async () => {
          renderState(await apiPost("/api/audio-effects", { eq_preset }));
        })
      );
    });

    // Additional settings
    $("#toggle-in-ear").addEventListener("click", () => runAction(async () => {
      renderState(await apiPost("/api/additional-settings", { in_ear_detection: !appState.additional_settings.in_ear_detection }));
    }));
    $("#toggle-dual-conn").addEventListener("click", () => runAction(async () => {
      renderState(await apiPost("/api/additional-settings", { dual_connection: !appState.additional_settings.dual_connection }));
    }));
    $("#toggle-auto-answer").addEventListener("click", () => runAction(async () => {
      renderState(await apiPost("/api/additional-settings", { auto_answer: !appState.additional_settings.auto_answer }));
    }));
    $("#toggle-adaptive-vol").addEventListener("click", () => runAction(async () => {
      renderState(await apiPost("/api/additional-settings", { adaptive_volume: !appState.additional_settings.adaptive_volume }));
    }));
    $("#btn-refresh-wearing").addEventListener("click", () => runAction(async () => {
      renderState(await apiPost("/api/wearing/refresh", {}));
      showToast("Requested wearing sensor status");
    }));

    // Find earphones
    $("#btn-ring-left").addEventListener("click", () => runAction(async () => {
      audioPlayedByUser = true;
      renderState(await apiPost("/api/find-earphones", { target: "left", active: !appState.find_earphones.ringing_left }));
    }));
    $("#btn-ring-right").addEventListener("click", () => runAction(async () => {
      audioPlayedByUser = true;
      renderState(await apiPost("/api/find-earphones", { target: "right", active: !appState.find_earphones.ringing_right }));
    }));
    $("#btn-ring-both").addEventListener("click", () => runAction(async () => {
      audioPlayedByUser = true;
      const any = appState.find_earphones.ringing_left || appState.find_earphones.ringing_right;
      renderState(await apiPost("/api/find-earphones", { target: "both", active: !any }));
    }));

    // Firmware info refresh
    $("#btn-check-fw").addEventListener("click", () => runAction(async () => {
      renderState(await apiPost("/api/battery/refresh", {}));
      showToast("Requested firmware & device info from earbuds");
    }));

    // About device UI customization (works offline too)
    $$(".color-dot").forEach((dot) => {
      dot.addEventListener("click", () => runAction(async () => {
        renderState(await apiPost("/api/additional-settings", { color: dot.dataset.color }));
      }));
    });
    $("#toggle-show-case").addEventListener("click", () => runAction(async () => {
      renderState(await apiPost("/api/additional-settings", { show_case: !appState.battery.show_case }));
    }));

    // Manage / BlueZ controls
    $("#btn-bt-scan").addEventListener("click", () => runAction(async () => {
      const res = await apiGet("/api/bluetooth/scan");
      renderState(res.state);
      showToast(`BlueZ scan complete (${res.devices.length} device(s))`);
    }));
    $("#btn-bt-connect").addEventListener("click", () => runAction(async () => {
      showToast("Connecting via BlueZ RFCOMM + SAFER+...");
      const st = await apiPost("/api/bluetooth/connect", {});
      renderState(st);
      if (st.bluetooth.last_error) showToast(st.bluetooth.last_error);
      else showToast(`Connected to ${st.device.name}`);
    }));
    $("#btn-bt-disconnect").addEventListener("click", () => runAction(async () => {
      renderState(await apiPost("/api/bluetooth/disconnect", {}));
      showToast("Disconnected RFCOMM session");
    }));
    $("#btn-bt-battery").addEventListener("click", () => runAction(async () => {
      renderState(await apiPost("/api/battery/refresh", {}));
      showToast("Sent DeviceInfo / Battery RCSP query");
    }));
    $("#btn-clear-log").addEventListener("click", () => runAction(async () => {
      renderState(await apiPost("/api/logs/clear", {}));
      showToast("Cleared RCSP packet log");
    }));

    // Close popup when clicking backdrop or pressing Escape
    $("#popup-backdrop").addEventListener("click", closePopup);
    window.addEventListener("keydown", (ev) => {
      if (ev.key === "Escape") {
        if (!$("#popup-backdrop").classList.contains("hidden")) closePopup();
        else navigateBack();
      }
    });

    window.addEventListener("resize", () => {
      if (appState) renderState(appState);
    });
  }

  async function init() {
    injectStaticIcons();
    bindEvents();
    try {
      const initial = await apiGet("/api/state");
      renderState(initial);
    } catch (_) {
      showToast("Backend connection error");
    }

    // Periodic sync for live Bluetooth notifications and auto-connect updates
    setInterval(async () => {
      if (activeSliderDrag || activeVolumeDrag) return;
      try {
        const latest = await apiGet("/api/state");
        renderState(latest);
      } catch (_) {}
    }, 2000);
  }

  document.addEventListener("DOMContentLoaded", init);
})();
