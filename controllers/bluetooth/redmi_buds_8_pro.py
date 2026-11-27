"""Xiaomi/Redmi earbuds RCSP protocol codec and Linux BlueZ RFCOMM service."""

from __future__ import annotations

from copy import deepcopy
import json
import os
from pathlib import Path
import re
import socket
import subprocess
import threading
import time
from typing import Any, Callable, Optional

from controllers.audio import CommuteAudioPlayer
from .auth_session import AuthPolicy
from .capabilities import resolve_capabilities
from .config_transport import parse_config_records
from .connection import BluetoothConnection
from .device_catalog import get_device_models, get_device_models_by_name
from .discovery import BluetoothDiscovery
from .equalizer import build_profile
from .gestures import build_gesture_assignment
from .noise import build_noise_level, build_noise_mode
from .rcsp import RcspPacket, RcspStreamParser, build_identity_request, decode_version


# ─────────────────────────────────────────────────────────────────────────────
# Protocol Constants (Xiaomi MMA / RCSP over MIUI SPP)
# ─────────────────────────────────────────────────────────────────────────────
APP_DEFAULT_NAME = "MiBuds Linux"

UUID_MIUI_SPP = "0000fd2d-0000-1000-8000-00805f9b34fb"
UUID_XIAOAI_SPP = "00001101-0000-1000-8000-008584d01810"
UUID_STANDARD_SPP = "00001101-0000-1000-8000-00805f9b34fb"

OPCODE_GET_DEVICE_INFO = 0x02
OPCODE_SET_DEVICE_INFO = 0x08
OPCODE_GET_DEVICE_RUN_INFO = 0x09
OPCODE_REPORT_STATUS = 0x0E
OPCODE_SET_CONFIG = 0xF2
OPCODE_GET_CONFIG = 0xF3
OPCODE_NOTIFY_CONFIG = 0xF4

CONFIG_GESTURES = 0x0002
CONFIG_AUTO_ANSWER = 0x0003
CONFIG_DUAL_CONNECTION = 0x0004
CONFIG_EQ_PRESET = 0x0007
CONFIG_FIND_EARBUDS = 0x0009
CONFIG_NOISE_LIST = 0x000A
CONFIG_ANC = 0x000B
CONFIG_IN_EAR_STATE = 0x000C
CONFIG_SPATIAL_STATE_SET = 0x001D
CONFIG_SPATIAL_STATE_GET = 0x001E
CONFIG_ADAPTIVE_ANC = 0x0025
CONFIG_SERIAL_NUMBER = 0x0027
CONFIG_ADAPTIVE_SOUND = 0x0029
CONFIG_SPATIAL_SCENE = 0x0036
CONFIG_ADAPTIVE_VOLUME = 0x0048
CONFIG_IMMERSIVE_COMMUTE = 0x004A  # func_id 1009 (FUNC_NOISE_IMMERSE)

NOISE_MODES = {
    "off": 0x00,
    "anc": 0x01,
    "transparency": 0x02,
}
NOISE_MODE_BY_CODE = {v: k for k, v in NOISE_MODES.items()}

TRANSPARENCY_MODES = {
    0: "Regular",
    1: "Enhance voice",
    2: "Enhance ambient sound",
}

IMMERSIVE_COMMUTE_MODES = {
    "off": 0x00,
    "airplane": 0x01,
    "public_transit": 0x02,
    "train": 0x03,
}
IMMERSIVE_COMMUTE_BY_CODE = {v: k for k, v in IMMERSIVE_COMMUTE_MODES.items()}

GESTURE_TYPES = {
    "single": 0x04,
    "double": 0x01,
    "triple": 0x02,
    "hold": 0x03,
    "swipe": 0x05,
}
GESTURE_TYPE_BY_CODE = {v: k for k, v in GESTURE_TYPES.items()}

GESTURE_ACTIONS = {
    "voice_assistant": 0x00,
    "play_pause": 0x01,
    "previous_song": 0x02,
    "next_song": 0x03,
    "volume_up": 0x04,
    "volume_down": 0x05,
    "noise_cancellation": 0x06,
    "none": 0x08,
    "adjust_volume": 0x0B,
}
GESTURE_ACTION_BY_CODE = {v: k for k, v in GESTURE_ACTIONS.items()}

# Custom EQ (profile 0x0A) is intentionally hidden and disabled for write operations.
EQ_PRESETS = {
    "standard": 0x00,
    "voice": 0x01,
    "bass": 0x05,
    "treble": 0x06,
}
EQ_PRESET_BY_CODE = {v: k for k, v in EQ_PRESETS.items()}
EQ_PRESET_BY_CODE[0x0A] = "custom"

SPATIAL_SCENES = {
    "standard": 0x01,
    "music": 0x02,
    "video": 0x03,
    "game": 0x04,
    "audiobooks": 0x05,
}
SPATIAL_SCENE_BY_CODE = {v: k for k, v in SPATIAL_SCENES.items()}

ANC_LEVELS = tuple(range(20))
TRANSPARENCY_LEVELS = (0, 1, 2)
VALID_COLORS = ("black", "white", "blue")
VALID_THEME_MODES = ("dark", "light", "custom")
VALID_THEME_BASES = ("dark", "light")
HEX_COLOR_RE = re.compile(r"^#[0-9A-Fa-f]{6}$")

DEFAULT_THEME = {
    "mode": "dark",
    "custom_base": "dark",
    "accent": "#2581FF",
    "bg": "#0A0E17",
    "card": "#131A29",
}

ANC_WEAR_WARNING = (
    "Wear your earbuds to enable Noise cancellation or Transparency "
    "(Xiaomi firmware wearing protection)."
)


# ─────────────────────────────────────────────────────────────────────────────
# Low-level RCSP Packet Builders (Xiaomi MMA Protocol)
# ─────────────────────────────────────────────────────────────────────────────
def format_hex(frame: bytes) -> str:
    """Format raw RCSP frame bytes as uppercase space-separated hex."""
    return frame.hex(" ").upper()


def _check_counter(counter: int) -> int:
    if type(counter) is not int or not 0 <= counter <= 0xFF:
        raise ValueError("RCSP counter must be an integer between 0 and 255")
    return counter


def build_rcsp_frame(opcode: int, counter: int, payload: bytes, flags: int = 0xC4) -> bytes:
    """Build a length-framed Xiaomi MMA RCSP packet."""
    _check_counter(counter)
    body = bytes([counter]) + payload
    return (
        bytes.fromhex("fe dc ba")
        + bytes([flags & 0xFF, opcode & 0xFF])
        + len(body).to_bytes(2, "big")
        + body
        + bytes.fromhex("ef")
    )


def build_rcsp_ack(opcode: int, seq: int) -> bytes:
    """Build a status=0x00 RCSP response ACK frame for device notifications."""
    return (
        bytes.fromhex("fe dc ba 04")
        + bytes([opcode & 0xFF, 0x00, 0x02, 0x00, seq & 0xFF, 0xEF])
    )


def build_get_config_frame(counter: int, config_id: int) -> bytes:
    """Build an Opcode 0xF3 GET_CONFIG packet for a 16-bit config ID."""
    return build_rcsp_frame(OPCODE_GET_CONFIG, counter, config_id.to_bytes(2, "big"))


def build_run_info_request(counter: int) -> bytes:
    """Build an Opcode 0x09 GET_DEVICE_RUN_INFO packet."""
    return build_rcsp_frame(OPCODE_GET_DEVICE_RUN_INFO, counter, bytes.fromhex("ff ff ff ff"))


def build_set_config_frame(counter: int, config_id: int, value: bytes) -> bytes:
    """Build an Opcode 0xF2 SET_CONFIG packet for a 16-bit config ID."""
    length = 2 + len(value)
    if length >= 0xFF:
        raise ValueError("Config payload exceeds standard RCSP record length")
    return build_rcsp_frame(
        OPCODE_SET_CONFIG,
        counter,
        bytes([length]) + config_id.to_bytes(2, "big") + value,
    )


def build_smart_anc_frame(counter: int, enabled: bool) -> bytes:
    """Build Smart Noise Cancellation toggle (ConfigType 0x0025)."""
    return build_set_config_frame(counter, CONFIG_ADAPTIVE_ANC, bytes([0x01 if enabled else 0x00]))


def build_immersive_commute_frame(counter: int, mode: str) -> bytes:
    """Build Immersive Commute mode command (func_id 1009 / ConfigType 0x004A)."""
    if mode not in IMMERSIVE_COMMUTE_MODES:
        raise ValueError(f"Unsupported immersive commute mode: {mode}")
    return build_set_config_frame(counter, CONFIG_IMMERSIVE_COMMUTE, bytes([IMMERSIVE_COMMUTE_MODES[mode]]))


def encode_noise_cycle_mask(modes: list[str] | tuple[str, ...]) -> int:
    """Encode NoiseCancellationList bitmask (bit0=off, bit1=anc, bit2=transparency)."""
    unique_modes = []
    for item in modes:
        if item not in NOISE_MODES:
            raise ValueError(f"Unknown noise cycle mode: {item}")
        if item not in unique_modes:
            unique_modes.append(item)
    if len(unique_modes) < 2:
        raise ValueError("Select at least two noise cancellation options")
    mask = 0
    for item in unique_modes:
        mask |= 1 << NOISE_MODES[item]
    return mask


def decode_noise_cycle_mask(mask: int) -> list[str]:
    """Decode NoiseCancellationList bitmask into ordered mode names."""
    ordered = []
    for key in ("anc", "transparency", "off"):
        if mask & (1 << NOISE_MODES[key]):
            ordered.append(key)
    return ordered


def build_press_hold_cycle_frame(
    counter: int,
    side: str,
    modes: list[str] | tuple[str, ...],
) -> bytes:
    """Build ConfigType 0x000A (NoiseCancellationList) command using 0xFF for unchanged side."""
    if side not in ("left", "right"):
        raise ValueError("Side must be 'left' or 'right'")
    mask = encode_noise_cycle_mask(modes)
    left_byte, right_byte = (mask, 0xFF) if side == "left" else (0xFF, mask)
    return build_set_config_frame(counter, CONFIG_NOISE_LIST, bytes([left_byte, right_byte]))


def build_spatial_audio_frame(counter: int, enabled: bool, head_tracking: bool = False) -> bytes:
    """Build Spatial Audio state frame (ConfigType 0x001D)."""
    val = 0x02  # offload flag preserved, spatial disabled
    if enabled:
        val = 0x0B if head_tracking else 0x03
    return build_set_config_frame(counter, CONFIG_SPATIAL_STATE_SET, bytes([val]))


def build_spatial_scene_frame(counter: int, scene: str) -> bytes:
    """Build Spatial Audio scene frame (ConfigType 0x0036)."""
    if scene not in SPATIAL_SCENES:
        raise ValueError(f"Unsupported spatial scene: {scene}")
    return build_set_config_frame(counter, CONFIG_SPATIAL_SCENE, bytes([0x01, SPATIAL_SCENES[scene]]))


def build_adaptive_sound_frame(counter: int, enabled: bool) -> bytes:
    """Build Adaptive Sound toggle frame (ConfigType 0x0029)."""
    return build_set_config_frame(counter, CONFIG_ADAPTIVE_SOUND, bytes([0x01 if enabled else 0x00]))


def build_in_ear_detection_frame(counter: int, enabled: bool) -> bytes:
    """Build In-ear detection frame via SET_DEVICE_INFO tag 0x06 (0x00=on, 0x01=off)."""
    return build_rcsp_frame(
        OPCODE_SET_DEVICE_INFO,
        counter,
        bytes([0x02, 0x06, 0x00 if enabled else 0x01]),
    )


def build_dual_connection_frame(counter: int, enabled: bool) -> bytes:
    """Build Dual device connection toggle (ConfigType 0x0004)."""
    return build_set_config_frame(counter, CONFIG_DUAL_CONNECTION, bytes([0x01 if enabled else 0x00]))


def build_auto_answer_frame(counter: int, enabled: bool) -> bytes:
    """Build Auto-answer incoming calls toggle (ConfigType 0x0003)."""
    return build_set_config_frame(counter, CONFIG_AUTO_ANSWER, bytes([0x01 if enabled else 0x00]))


def build_adaptive_volume_frame(counter: int, enabled: bool) -> bytes:
    """Build Adaptive volume toggle (ConfigType 0x0048)."""
    return build_set_config_frame(counter, CONFIG_ADAPTIVE_VOLUME, bytes([0x01 if enabled else 0x00]))


def build_find_earbuds_frame(counter: int, enabled: bool, target: str = "both") -> bytes:
    """Build Find your earphones ring command (ConfigType 0x0009)."""
    mask_map = {"left": 0x01, "right": 0x02, "both": 0x03}
    if target not in mask_map:
        raise ValueError(f"Invalid target '{target}'")
    return build_set_config_frame(
        counter,
        CONFIG_FIND_EARBUDS,
        bytes([0x01 if enabled else 0x00, mask_map[target]]),
    )


# ─────────────────────────────────────────────────────────────────────────────
# Clean Disconnected Initial State (Zero Fake Hardware Placeholders)
# ─────────────────────────────────────────────────────────────────────────────
def default_capabilities() -> dict[str, bool]:
    """Return default capability visibility flags."""
    return {
        "anc": True,
        "transparency": True,
        "smart_anc": True,
        "immersive_commute": True,
        "spatial_audio": True,
        "head_tracking": True,
        "spatial_scene": True,
        "adaptive_sound": True,
        "eq": True,
        "in_ear_detection": True,
        "dual_connection": True,
        "auto_answer": True,
        "adaptive_volume": False,
        "find_earphones": True,
        "gestures": True,
    }


def default_device_state() -> dict[str, Any]:
    """Return clean disconnected state without placeholder serials, firmware, or battery."""
    return {
        "device": {
            "name": APP_DEFAULT_NAME,
            "model_id": "",
            "sale_model": "",
            "vid": "",
            "pid": "",
            "firmware": "",
            "serial": "",
            "color": "black",
            "connected": False,
            "mode": "disconnected",  # "live" when RFCOMM connected, "disconnected" otherwise
            "mac_address": "",
            "service_uuid": "",
            "rfcomm_channel": None,
            "authenticated": False,
            "has_dolby_badge": True,
            "wearing": {"left": "unknown", "right": "unknown"},
        },
        "capabilities": default_capabilities(),
        "battery": {
            "left": None,
            "left_charging": False,
            "right": None,
            "right_charging": False,
            "case": None,
            "case_charging": False,
            "show_case": False,
            "case_available": False,
            "case_stale": False,
        },
        "noise": {
            "mode": "off",  # "transparency" | "anc" | "off"
            "smart_anc": False,
            "anc_level": 18,  # 0..19 (Light -> Deep)
            "transparency_level": 1,  # 0=Regular, 1=Enhance voice, 2=Enhance ambient sound
        },
        "immersive_commute": "off",  # "off" | "airplane" | "public_transit" | "train"
        "immersive_commute_volume": 65,  # 0..100 desktop ambient sound volume
        "theme": deepcopy(DEFAULT_THEME),
        "gestures": {
            "single": {"left": "play_pause", "right": "play_pause"},
            "double": {"left": "previous_song", "right": "next_song"},
            "triple": {"left": "volume_down", "right": "volume_up"},
            "hold": {"left": "noise_cancellation", "right": "noise_cancellation"},
            "swipe": {"left": "adjust_volume", "right": "adjust_volume"},
            "hold_modes": {
                "left": ["transparency", "off"],
                "right": ["transparency", "off"],
            },
        },
        "audio_effects": {
            "spatial_audio": False,
            "head_tracking": False,
            "spatial_scene": "standard",
            "eq_preset": "standard",
            "adaptive_sound": False,
        },
        "additional_settings": {
            "in_ear_detection": True,
            "dual_connection": False,
            "auto_answer": False,
            "adaptive_volume": False,
        },
        "find_earphones": {
            "ringing_left": False,
            "ringing_right": False,
        },
        "bluetooth": {
            "paired_devices": [],
            "scanning": False,
            "last_tx_hex": "",
            "last_tx_label": "",
            "tx_log": [],
            "last_error": "",
            "warning": "",
        },
    }


def _default_prefs_path() -> Path:
    cfg_root = Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config"))
    return cfg_root / "mibuds-linux" / "preferences.json"


# ─────────────────────────────────────────────────────────────────────────────
# Stateful Service Bridging BlueZ RFCOMM (SAFER+) + Desktop UI State
# ─────────────────────────────────────────────────────────────────────────────
class RedmiBuds8ProService:
    """High-level controller bridging BlueZ RFCOMM + SAFER+ auth and UI state."""

    def __init__(
        self,
        state_path: Optional[Path] = None,
        enable_bluetooth_auto: bool = True,
        allow_offline: bool = False,
        enable_audio: bool = True,
        theme_callback: Optional[Callable[[dict[str, Any]], None]] = None,
    ) -> None:
        self._lock = threading.RLock()
        self._prefs_path = Path(state_path) if state_path else _default_prefs_path()
        self._allow_offline = bool(allow_offline)
        self._enable_audio = bool(enable_audio)
        self._theme_callback = theme_callback
        self._state = default_device_state()
        self._counter = 0x10
        self._conn: Optional[BluetoothConnection] = None
        self._rx_parser = RcspStreamParser()
        self._listener_thread: Optional[threading.Thread] = None
        self._running = False
        self._shutdown_event = threading.Event()
        self._manual_disconnect = False
        self._connecting = False
        self._load_preferences()
        self._commute_audio = (
            CommuteAudioPlayer(volume=self._state["immersive_commute_volume"] / 100.0)
            if self._enable_audio
            else None
        )
        if self._theme_callback is not None:
            try:
                self._theme_callback(deepcopy(self._state["theme"]))
            except Exception:
                pass
        if enable_bluetooth_auto:
            threading.Thread(target=self._auto_connect_loop, daemon=True).start()

    def shutdown(self) -> None:
        """Stop background auto-connect watcher, ambient audio, and RFCOMM socket."""
        self._shutdown_event.set()
        if self._commute_audio is not None:
            self._commute_audio.stop()
        self.disconnect_bluetooth(manual=True)

    def _auto_connect_loop(self) -> None:
        """Continuously detect connected supported earbuds in BlueZ and refresh live telemetry."""
        fast_attempts = 0
        last_battery_poll = 0.0
        while not self._shutdown_event.is_set():
            try:
                with self._lock:
                    is_live = self._is_live()
                    should_try = (
                        not is_live
                        and not self._manual_disconnect
                        and not self._connecting
                    )
                if is_live:
                    now = time.monotonic()
                    if now - last_battery_poll >= 30.0:
                        last_battery_poll = now
                        with self._lock:
                            if self._is_live():
                                self._record_tx("Periodic battery poll", build_identity_request(self._next_counter()))
                elif should_try:
                    devices = self.scan_bluetooth_devices()
                    target = next((d for d in devices if d["connected"] and d["supported"]), None)
                    if target is not None:
                        self.connect_bluetooth(
                            target["address"],
                            device_name=target["name"],
                            auto=True,
                        )
                        if self._is_live():
                            fast_attempts = 0
                            last_battery_poll = time.monotonic()
                        else:
                            fast_attempts += 1
                    else:
                        fast_attempts += 1
            except Exception:
                fast_attempts += 1

            # Retry quickly right after startup / case open, then poll gently every 3.5s
            delay = 1.5 if fast_attempts < 3 else 3.5
            self._shutdown_event.wait(delay)

    def _next_counter(self) -> int:
        val = self._counter
        self._counter = (self._counter + 1) & 0xFF
        return val

    def _load_preferences(self) -> None:
        """Load non-personal UI preferences only (never MAC, serial, or stale telemetry)."""
        try:
            source_path = self._prefs_path
            if not source_path.exists():
                legacy_path = source_path.parent.parent / "xiaomi-earbuds-linux" / "preferences.json"
                if legacy_path.exists():
                    source_path = legacy_path
            if source_path.exists():
                saved = json.loads(source_path.read_text(encoding="utf-8"))
                if isinstance(saved, dict):
                    color = saved.get("color")
                    if color in VALID_COLORS:
                        self._state["device"]["color"] = color
                    if "show_case" in saved:
                        self._state["battery"]["show_case"] = bool(saved["show_case"])
                    if "commute_volume" in saved:
                        try:
                            vol = max(0, min(100, int(saved["commute_volume"])))
                            self._state["immersive_commute_volume"] = vol
                        except (TypeError, ValueError):
                            pass
                    theme = saved.get("theme")
                    if isinstance(theme, dict):
                        target = self._state["theme"]
                        if theme.get("mode") in VALID_THEME_MODES:
                            target["mode"] = theme["mode"]
                        if theme.get("custom_base") in VALID_THEME_BASES:
                            target["custom_base"] = theme["custom_base"]
                        for key in ("accent", "bg", "card"):
                            val = theme.get(key)
                            if isinstance(val, str) and HEX_COLOR_RE.match(val):
                                target[key] = val.upper()
                if source_path != self._prefs_path:
                    self._save_preferences()
        except Exception:
            pass

    def _save_preferences(self) -> None:
        """Persist only UI appearance preferences to XDG config."""
        try:
            self._prefs_path.parent.mkdir(parents=True, exist_ok=True)
            payload = {
                "color": self._state["device"]["color"],
                "show_case": bool(self._state["battery"]["show_case"]),
                "commute_volume": int(self._state["immersive_commute_volume"]),
                "theme": deepcopy(self._state["theme"]),
            }
            self._prefs_path.write_text(
                json.dumps(payload, indent=2, ensure_ascii=False),
                encoding="utf-8",
            )
        except OSError:
            pass

    def get_state(self) -> dict[str, Any]:
        with self._lock:
            return deepcopy(self._state)

    def clear_tx_log(self) -> dict[str, Any]:
        with self._lock:
            bt = self._state["bluetooth"]
            bt["tx_log"] = []
            bt["last_tx_hex"] = ""
            bt["last_tx_label"] = ""
            bt["last_error"] = ""
            bt["warning"] = ""
            return deepcopy(self._state)

    def _is_live(self) -> bool:
        return bool(self._conn and self._conn.connected)

    def _require_connected(self) -> None:
        if not self._is_live() and not self._allow_offline:
            raise ConnectionError(
                "No earphones connected. Pair and connect your earbuds in Linux Bluetooth settings, then click Connect."
            )

    def _append_log(self, label: str, hex_str: str, transport: str) -> dict[str, Any]:
        bt = self._state["bluetooth"]
        bt["last_tx_hex"] = hex_str
        bt["last_tx_label"] = label
        entry = {
            "ts": time.strftime("%H:%M:%S"),
            "label": label,
            "hex": hex_str,
            "transport": transport,
        }
        bt["tx_log"] = ([entry] + bt["tx_log"])[:50]
        return entry

    def _record_tx(self, label: str, frame: bytes) -> dict[str, Any]:
        hex_str = format_hex(frame)
        is_live = self._is_live()
        entry = self._append_log(label, hex_str, "rfcomm" if is_live else "offline")
        if is_live and self._conn is not None:
            try:
                self._conn.send(frame)
            except Exception as exc:
                self._state["bluetooth"]["last_error"] = str(exc)
        return entry

    def _apply_catalog_metadata(self, device_name: str, vid: Optional[int] = None, pid: Optional[int] = None) -> None:
        """Populate model ID, sale model, Dolby badge, and func_list capabilities from catalog."""
        models: tuple[dict[str, Any], ...] = ()
        if vid is not None and pid is not None:
            models = get_device_models(vid, pid)
        if not models and device_name:
            models = get_device_models_by_name(device_name)

        matched: Optional[dict[str, Any]] = None
        if len(models) == 1:
            matched = models[0]
        elif len(models) > 1 and device_name:
            norm = " ".join(device_name.split()).casefold()
            matched = next((m for m in models if " ".join(m.get("name", "").split()).casefold() == norm), models[0])

        dev = self._state["device"]
        if matched:
            if matched.get("model"):
                dev["model_id"] = str(matched["model"])
            extra = matched.get("extra_info") or {}
            if isinstance(extra, dict) and extra.get("sale_model"):
                dev["sale_model"] = str(extra["sale_model"])
            dev["has_dolby_badge"] = bool(matched.get("icon_logo"))
            if not dev["name"] or dev["name"] == APP_DEFAULT_NAME:
                dev["name"] = str(matched.get("name") or APP_DEFAULT_NAME)

            func_ids = {
                fn.get("func_id")
                for fn in matched.get("func_list", [])
                if isinstance(fn, dict) and isinstance(fn.get("func_id"), int)
            }
            if func_ids:
                caps = resolve_capabilities(matched.get("name", device_name))
                self._state["capabilities"] = {
                    "anc": any(fid in func_ids for fid in (1002, 1003, 1006, 1007)),
                    "transparency": any(fid in func_ids for fid in (1004, 1005)),
                    "smart_anc": 1008 in func_ids,
                    "immersive_commute": 1009 in func_ids,
                    "spatial_audio": any(fid in func_ids for fid in (2001, 2002, 2003, 2005)),
                    "head_tracking": 2004 in func_ids,
                    "spatial_scene": 2009 in func_ids,
                    "adaptive_sound": 2008 in func_ids,
                    "eq": caps.supports("eq") or any(fid in func_ids for fid in (2006, 2016)),
                    "in_ear_detection": 3002 in func_ids,
                    "dual_connection": 3004 in func_ids,
                    "auto_answer": 3008 in func_ids,
                    "adaptive_volume": 2017 in func_ids,
                    "find_earphones": 5001 in func_ids,
                    "gestures": caps.supports("gestures") or any(fid in func_ids for fid in (4001, 4002, 4003, 4006, 4011)),
                }

    # ── BlueZ Discovery & Real RFCOMM Bridge ─────────────────────────────────
    def scan_bluetooth_devices(self) -> list[dict[str, Any]]:
        """Query paired and connected BlueZ devices via bluetoothctl."""
        with self._lock:
            self._state["bluetooth"]["scanning"] = True
        devices: list[dict[str, Any]] = []
        env = {**os.environ, "LC_ALL": "C"}
        try:
            connected_macs: Optional[set[str]] = None
            try:
                conn_out = subprocess.check_output(
                    ["bluetoothctl", "devices", "Connected"],
                    text=True,
                    timeout=3,
                    stderr=subprocess.DEVNULL,
                    env=env,
                )
                connected_macs = set()
                for line in conn_out.splitlines():
                    parts = line.strip().split(" ", 2)
                    if len(parts) >= 2 and parts[0] == "Device":
                        connected_macs.add(parts[1].upper())
            except Exception:
                connected_macs = None

            output = subprocess.check_output(
                ["bluetoothctl", "devices"],
                text=True,
                timeout=4,
                stderr=subprocess.DEVNULL,
                env=env,
            )
            for line in output.splitlines():
                parts = line.strip().split(" ", 2)
                if len(parts) == 3 and parts[0] == "Device":
                    mac, name = parts[1], parts[2]
                    if connected_macs is not None:
                        is_connected = mac.upper() in connected_macs
                    else:
                        state_info = BluetoothDiscovery.connection_state(mac)
                        is_connected = state_info.get("state") == "connected"
                    lowered = name.casefold()
                    is_xiaomi_family = any(
                        tok in lowered
                        for tok in ("redmi buds", "xiaomi buds", "xiaomi openwear", "poco buds", "poco pods")
                    )
                    devices.append({
                        "address": mac,
                        "name": name,
                        "connected": is_connected,
                        "supported": bool(BluetoothDiscovery._is_supported_device(name)) or is_xiaomi_family,
                    })
            devices.sort(key=lambda d: (not d["supported"], not d["connected"], d["name"].casefold()))
        except FileNotFoundError:
            with self._lock:
                self._state["bluetooth"]["last_error"] = "BlueZ CLI 'bluetoothctl' not found. Install the bluez package."
        except Exception as exc:
            with self._lock:
                self._state["bluetooth"]["last_error"] = str(exc)

        with self._lock:
            self._state["bluetooth"]["scanning"] = False
            self._state["bluetooth"]["paired_devices"] = devices
        return devices

    def connect_bluetooth(
        self,
        address: Optional[str] = None,
        device_name: Optional[str] = None,
        *,
        auto: bool = False,
    ) -> dict[str, Any]:
        """Open real BlueZ RFCOMM + SAFER+ auth session and start RCSP listener."""
        with self._lock:
            if not auto:
                self._manual_disconnect = False
            if self._connecting:
                return deepcopy(self._state)
            self._connecting = True

        try:
            self.disconnect_bluetooth(manual=False)

            target_addr = (address or "").strip() or None
            target_name = (device_name or "").strip() or None

            if target_addr and not target_name:
                with self._lock:
                    existing = next(
                        (d for d in self._state["bluetooth"]["paired_devices"] if d["address"].upper() == target_addr.upper()),
                        None,
                    )
                if existing is not None:
                    target_name = existing["name"]

            if not target_addr:
                devices = self.scan_bluetooth_devices()
                chosen = next((d for d in devices if d["connected"] and d["supported"]), None)
                if chosen is None:
                    chosen = next((d for d in devices if d["supported"]), None)
                if chosen is not None:
                    target_addr = chosen["address"]
                    target_name = chosen["name"]

            if not target_addr:
                with self._lock:
                    if not auto:
                        self._state["bluetooth"]["last_error"] = (
                            "No paired Xiaomi or Redmi earbuds found in BlueZ. "
                            "Pair and connect your earbuds in Linux Bluetooth settings first."
                        )
                    return deepcopy(self._state)

            resolved_name = target_name or APP_DEFAULT_NAME
            conn = BluetoothConnection()
            try:
                result = conn.connect(target_addr, device_name=resolved_name, session_policy=AuthPolicy.AUTO)
            except Exception as exc:
                friendly_err = self._format_connect_error(exc)
                with self._lock:
                    self._state["device"]["mode"] = "disconnected"
                    self._state["device"]["connected"] = False
                    self._state["device"]["authenticated"] = False
                    self._state["device"]["rfcomm_channel"] = None
                    self._state["bluetooth"]["last_error"] = friendly_err
                    return deepcopy(self._state)

            with self._lock:
                self._conn = conn
                self._running = True
                self._rx_parser.reset()
                dev = self._state["device"]
                dev["mode"] = "live"
                dev["connected"] = True
                dev["name"] = resolved_name
                dev["mac_address"] = target_addr
                dev["service_uuid"] = result.service_uuid or UUID_MIUI_SPP
                dev["rfcomm_channel"] = result.channel
                dev["authenticated"] = bool(conn.session_authenticated)
                self._apply_catalog_metadata(resolved_name)
                self._state["bluetooth"]["last_error"] = ""
                self._state["bluetooth"]["warning"] = ""
                self._append_log(
                    f"RFCOMM Connected (ch.{result.channel}, auth={dev['authenticated']})",
                    f"UUID: {dev['service_uuid']}",
                    "rfcomm",
                )

            self._listener_thread = threading.Thread(target=self._rx_loop, args=(conn,), daemon=True)
            self._listener_thread.start()
            threading.Thread(target=self._query_initial_device_state, daemon=True).start()
            return self.get_state()
        finally:
            with self._lock:
                self._connecting = False

    @staticmethod
    def _format_connect_error(exc: Exception) -> str:
        cause = exc.__cause__ or exc.__context__
        combined = f"{type(exc).__name__}: {exc}"
        if cause is not None:
            combined += f" ({type(cause).__name__}: {cause})"
        lowered = combined.casefold()
        if isinstance(cause, ConnectionRefusedError) or "connection refused" in lowered or "errno 111" in lowered:
            return (
                "Earbuds refused the RFCOMM control channel (Connection refused). "
                "If Dual-device connection is active, your phone or another app is likely holding the MIUI SPP channel — "
                "close Xiaomi Earbuds on your phone (or briefly disconnect the phone / reconnect earbuds on PC) and retry."
            )
        if isinstance(exc, TimeoutError) or isinstance(cause, TimeoutError) or "timed out" in lowered:
            return (
                "Connection timed out while contacting the earbuds. "
                "Ensure at least one earbud is awake (out of the closed case) and connected in Linux Bluetooth settings."
            )
        if cause is not None:
            return f"{exc} ({cause})"
        return f"{type(exc).__name__}: {exc}"

    def disconnect_bluetooth(self, *, manual: bool = False) -> dict[str, Any]:
        """Close active RFCOMM socket, stop ambient audio, and clear ephemeral hardware telemetry."""
        if self._commute_audio is not None:
            self._commute_audio.stop()
        with self._lock:
            if manual:
                self._manual_disconnect = True
            self._running = False
            conn, self._conn = self._conn, None
            self._rx_parser.reset()
        if conn is not None:
            try:
                conn.stop()
            except Exception:
                pass
        with self._lock:
            color = self._state["device"]["color"]
            show_case = bool(self._state["battery"]["show_case"])
            commute_volume = int(self._state["immersive_commute_volume"])
            theme = deepcopy(self._state["theme"])
            paired_devices = list(self._state["bluetooth"]["paired_devices"])
            tx_log = list(self._state["bluetooth"]["tx_log"])
            last_error = self._state["bluetooth"]["last_error"]

            self._state = default_device_state()
            self._state["device"]["color"] = color
            self._state["battery"]["show_case"] = show_case
            self._state["immersive_commute_volume"] = commute_volume
            self._state["theme"] = theme
            self._state["bluetooth"]["paired_devices"] = paired_devices
            self._state["bluetooth"]["tx_log"] = tx_log
            self._state["bluetooth"]["last_error"] = last_error
            return deepcopy(self._state)

    def _query_initial_device_state(self) -> None:
        """Query identity, battery, ANC, gestures, EQ, spatial audio, and wearing state on connect."""
        query_specs: list[tuple[str, Any]] = [
            ("GET_DEVICE_INFO", lambda c: build_identity_request(c)),
            ("GET_DEVICE_RUN_INFO", lambda c: build_run_info_request(c)),
            ("GET_CONFIG ANC (0x000B)", lambda c: build_get_config_frame(c, CONFIG_ANC)),
            ("GET_CONFIG SmartANC (0x0025)", lambda c: build_get_config_frame(c, CONFIG_ADAPTIVE_ANC)),
            ("GET_CONFIG Gestures (0x0002)", lambda c: build_get_config_frame(c, CONFIG_GESTURES)),
            ("GET_CONFIG LongPress (0x000A)", lambda c: build_get_config_frame(c, CONFIG_NOISE_LIST)),
            ("GET_CONFIG EQ Preset (0x0007)", lambda c: build_get_config_frame(c, CONFIG_EQ_PRESET)),
            ("GET_CONFIG DualConn (0x0004)", lambda c: build_get_config_frame(c, CONFIG_DUAL_CONNECTION)),
            ("GET_CONFIG AutoAnswer (0x0003)", lambda c: build_get_config_frame(c, CONFIG_AUTO_ANSWER)),
            ("GET_CONFIG Spatial (0x001E)", lambda c: build_get_config_frame(c, CONFIG_SPATIAL_STATE_GET)),
            ("GET_CONFIG SpatialScene (0x0036)", lambda c: build_get_config_frame(c, CONFIG_SPATIAL_SCENE)),
            ("GET_CONFIG AdaptiveSound (0x0029)", lambda c: build_get_config_frame(c, CONFIG_ADAPTIVE_SOUND)),
            ("GET_CONFIG AdaptiveVol (0x0048)", lambda c: build_get_config_frame(c, CONFIG_ADAPTIVE_VOLUME)),
            ("GET_CONFIG Immersive (0x004A)", lambda c: build_get_config_frame(c, CONFIG_IMMERSIVE_COMMUTE)),
            ("GET_CONFIG InEarState (0x000C)", lambda c: build_get_config_frame(c, CONFIG_IN_EAR_STATE)),
            ("GET_CONFIG Serial (0x0027)", lambda c: build_get_config_frame(c, CONFIG_SERIAL_NUMBER)),
        ]
        for label, builder in query_specs:
            with self._lock:
                if not self._running or not self._is_live():
                    return
                frame = builder(self._next_counter())
                self._record_tx(label, frame)
            time.sleep(0.08)

    def _rx_loop(self, conn: BluetoothConnection) -> None:
        """Dedicated reader loop decoding incoming RCSP frames from the earbuds."""
        while self._running and conn.connected:
            try:
                data = conn.receive()
                if not data:
                    raise ConnectionError("RFCOMM socket closed by earbuds")
                for packet in self._rx_parser.feed(data):
                    self._handle_rx_packet(conn, packet)
            except socket.timeout:
                continue
            except Exception as exc:
                with self._lock:
                    if self._conn is conn and self._running:
                        self._state["bluetooth"]["last_error"] = f"Disconnected: {exc}"
                if self._conn is conn:
                    self.disconnect_bluetooth()
                return

    # ── Incoming RCSP Frame Decoder ──────────────────────────────────────────
    def _handle_rx_packet(self, conn: Optional[BluetoothConnection], packet: RcspPacket) -> None:
        is_request = bool(packet.flags & 0x80)
        needs_ack = is_request and bool(packet.flags & 0x40)

        with self._lock:
            self._append_log(f"RX opcode=0x{packet.opcode:02X}", packet.raw_hex, "rfcomm-rx")

            if packet.opcode == OPCODE_GET_DEVICE_INFO and not is_request:
                if len(packet.payload) >= 2 and packet.payload[0] == 0:
                    self._decode_tlv_device_info(packet.payload[2:])

            elif packet.opcode == OPCODE_GET_DEVICE_RUN_INFO and not is_request:
                if len(packet.payload) >= 2 and packet.payload[0] == 0:
                    self._decode_tlv_run_info(packet.payload[2:])

            elif packet.opcode == OPCODE_REPORT_STATUS:
                if is_request and len(packet.payload) >= 1:
                    seq = packet.payload[0]
                    self._decode_tlv_status_notify(packet.payload[1:])
                    if needs_ack and conn is not None:
                        try:
                            conn.send(build_rcsp_ack(OPCODE_REPORT_STATUS, seq))
                        except Exception:
                            pass
                elif not is_request and len(packet.payload) >= 2 and packet.payload[0] == 0:
                    self._decode_tlv_status_notify(packet.payload[2:])

            elif packet.opcode == OPCODE_GET_CONFIG and not is_request:
                if len(packet.payload) >= 2 and packet.payload[0] == 0:
                    self._decode_config_payload(packet.payload[2:])

            elif packet.opcode == OPCODE_NOTIFY_CONFIG:
                if is_request and len(packet.payload) >= 1:
                    seq = packet.payload[0]
                    self._decode_config_payload(packet.payload[1:])
                    if needs_ack and conn is not None:
                        try:
                            conn.send(build_rcsp_ack(OPCODE_NOTIFY_CONFIG, seq))
                        except Exception:
                            pass
                elif not is_request and len(packet.payload) >= 2 and packet.payload[0] == 0:
                    self._decode_config_payload(packet.payload[2:])

    def _decode_tlv_device_info(self, body: bytes) -> None:
        pos = 0
        while pos < len(body):
            length = body[pos]
            end = pos + 1 + length
            if length < 1 or end > len(body):
                break
            tag = body[pos + 1]
            val = body[pos + 2:end]
            if tag == 0x01 and len(val) >= 2:
                self._state["device"]["firmware"] = decode_version(val[:2])
            elif tag == 0x03 and len(val) >= 4:
                vid = int.from_bytes(val[:2], "big")
                pid = int.from_bytes(val[2:4], "big")
                self._state["device"]["vid"] = f"0x{vid:04X}"
                self._state["device"]["pid"] = f"0x{pid:04X}"
                self._apply_catalog_metadata(self._state["device"]["name"], vid=vid, pid=pid)
            elif tag == 0x07 and len(val) >= 3:
                self._apply_battery_bytes(val[0], val[1], val[2])
            pos = end

    def _decode_tlv_run_info(self, body: bytes) -> None:
        pos = 0
        while pos < len(body):
            length = body[pos]
            end = pos + 1 + length
            if length < 1 or end > len(body):
                break
            tag = body[pos + 1]
            val = body[pos + 2:end]
            if tag == 0x09:
                if len(val) >= 2:
                    self._apply_anc_bytes(val[0], val[1])
                elif len(val) == 1:
                    mode = NOISE_MODE_BY_CODE.get(val[0])
                    if mode:
                        self._state["noise"]["mode"] = mode
            elif tag == 0x0A and len(val) >= 1:
                self._state["additional_settings"]["in_ear_detection"] = (val[0] == 0x00)
            pos = end

    def _decode_tlv_status_notify(self, body: bytes) -> None:
        pos = 0
        while pos < len(body):
            length = body[pos]
            end = pos + 1 + length
            if length < 1 or end > len(body):
                break
            tag = body[pos + 1]
            val = body[pos + 2:end]
            if tag in (0x00, 0x07) and len(val) >= 3:
                self._apply_battery_bytes(val[0], val[1], val[2])
            elif tag == 0x04 and len(val) >= 2:
                self._apply_anc_bytes(val[0], val[1])
            pos = end

    def _decode_config_payload(self, body: bytes) -> None:
        if not body:
            return
        try:
            records = parse_config_records(body)
        except ValueError:
            return

        for cfg_id, val in records.items():
            if cfg_id == CONFIG_ANC and len(val) >= 2:
                self._apply_anc_bytes(val[0], val[1])
            elif cfg_id == CONFIG_ADAPTIVE_ANC and len(val) >= 1:
                self._state["noise"]["smart_anc"] = val[0] == 1
            elif cfg_id == CONFIG_GESTURES and len(val) % 3 == 0:
                for offset in range(0, len(val), 3):
                    g_code, l_code, r_code = val[offset:offset + 3]
                    g_name = GESTURE_TYPE_BY_CODE.get(g_code)
                    if g_name:
                        if l_code in GESTURE_ACTION_BY_CODE:
                            self._state["gestures"][g_name]["left"] = GESTURE_ACTION_BY_CODE[l_code]
                        if r_code in GESTURE_ACTION_BY_CODE:
                            self._state["gestures"][g_name]["right"] = GESTURE_ACTION_BY_CODE[r_code]
            elif cfg_id == CONFIG_NOISE_LIST and len(val) >= 2:
                left_modes = decode_noise_cycle_mask(val[0])
                right_modes = decode_noise_cycle_mask(val[1])
                if len(left_modes) >= 2:
                    self._state["gestures"]["hold_modes"]["left"] = left_modes
                if len(right_modes) >= 2:
                    self._state["gestures"]["hold_modes"]["right"] = right_modes
            elif cfg_id == CONFIG_EQ_PRESET and len(val) >= 1:
                preset = EQ_PRESET_BY_CODE.get(val[0])
                if preset:
                    self._state["audio_effects"]["eq_preset"] = preset
            elif cfg_id == CONFIG_DUAL_CONNECTION and len(val) >= 1:
                self._state["additional_settings"]["dual_connection"] = val[0] == 1
            elif cfg_id == CONFIG_AUTO_ANSWER and len(val) >= 1:
                self._state["additional_settings"]["auto_answer"] = val[0] == 1
            elif cfg_id in (CONFIG_SPATIAL_STATE_GET, CONFIG_SPATIAL_STATE_SET) and len(val) >= 1:
                self._state["audio_effects"]["spatial_audio"] = val[0] in (0x03, 0x0B)
                self._state["audio_effects"]["head_tracking"] = val[0] == 0x0B
            elif cfg_id == CONFIG_SPATIAL_SCENE and len(val) >= 2:
                scene = SPATIAL_SCENE_BY_CODE.get(val[1])
                if scene:
                    self._state["audio_effects"]["spatial_scene"] = scene
            elif cfg_id == CONFIG_ADAPTIVE_SOUND and len(val) >= 1:
                self._state["audio_effects"]["adaptive_sound"] = val[0] == 1
            elif cfg_id == CONFIG_ADAPTIVE_VOLUME and len(val) >= 1:
                self._state["additional_settings"]["adaptive_volume"] = val[0] == 1
            elif cfg_id == CONFIG_IMMERSIVE_COMMUTE and len(val) >= 1:
                commute = IMMERSIVE_COMMUTE_BY_CODE.get(val[0])
                # Preserve active desktop ambient playback if firmware reports 0x00 on readback
                if commute and (commute != "off" or self._commute_audio is None or self._commute_audio.mode == "off"):
                    self._state["immersive_commute"] = commute
            elif cfg_id == CONFIG_IN_EAR_STATE and len(val) >= 1:
                self._apply_in_ear_byte(val[0])
            elif cfg_id == CONFIG_SERIAL_NUMBER and val:
                serial = val.decode("ascii", errors="ignore").strip("\x00 ")
                if serial:
                    self._state["device"]["serial"] = serial

    def _apply_in_ear_byte(self, state_byte: int) -> None:
        prev = self._state["device"].get("wearing", {})
        left = "in_ear" if (state_byte & 0x08) else ("in_case" if (state_byte & 0x02) else "out")
        right = "in_ear" if (state_byte & 0x04) else ("in_case" if (state_byte & 0x01) else "out")
        self._state["device"]["wearing"] = {"left": left, "right": right}
        if left == "in_ear" or right == "in_ear":
            self._state["bluetooth"]["warning"] = ""
        entered_case = (
            (left == "in_case" and prev.get("left") != "in_case")
            or (right == "in_case" and prev.get("right") != "in_case")
        )
        if entered_case and self._is_live():
            self._record_tx("Query battery (bud in case)", build_identity_request(self._next_counter()))

    def _readback_config(self, config_id: int, label: str) -> None:
        if self._is_live():
            self._record_tx(f"Readback {label}", build_get_config_frame(self._next_counter(), config_id))

    def _apply_battery_bytes(self, left_raw: int, right_raw: int, case_raw: int) -> None:
        bat = self._state["battery"]
        if left_raw != 0xFF and 0 <= (left_raw & 0x7F) <= 100:
            bat["left"] = left_raw & 0x7F
            bat["left_charging"] = bool(left_raw & 0x80)
        else:
            bat["left"] = None
            bat["left_charging"] = False
        if right_raw != 0xFF and 0 <= (right_raw & 0x7F) <= 100:
            bat["right"] = right_raw & 0x7F
            bat["right_charging"] = bool(right_raw & 0x80)
        else:
            bat["right"] = None
            bat["right_charging"] = False
        case_pct = case_raw & 0x7F
        case_chg = bool(case_raw & 0x80)
        if case_raw != 0xFF and 0 <= case_pct <= 100 and (case_pct > 0 or case_chg):
            bat["case"] = case_pct
            bat["case_charging"] = case_chg
            bat["case_available"] = True
            bat["case_stale"] = False
        else:
            bat["case_available"] = False
            bat["case_charging"] = False
            bat["case_stale"] = bat["case"] is not None

    def _apply_anc_bytes(self, mode_code: int, strength: int) -> None:
        mode = NOISE_MODE_BY_CODE.get(mode_code)
        if not mode:
            return
        self._state["noise"]["mode"] = mode
        if mode == "anc" and strength in ANC_LEVELS:
            self._state["noise"]["anc_level"] = strength
        elif mode == "transparency" and strength in TRANSPARENCY_LEVELS:
            self._state["noise"]["transparency_level"] = strength

    def _neither_bud_in_ear(self) -> bool:
        wearing = self._state["device"].get("wearing", {})
        return wearing.get("left") != "in_ear" and wearing.get("right") != "in_ear"

    # ── Feature Control Mutations ────────────────────────────────────────────
    def set_noise_control(
        self,
        *,
        mode: Optional[str] = None,
        smart_anc: Optional[bool] = None,
        anc_level: Optional[int] = None,
        transparency_level: Optional[int] = None,
    ) -> dict[str, Any]:
        with self._lock:
            self._require_connected()
            noise = self._state["noise"]
            self._state["bluetooth"]["warning"] = ""
            is_live = self._is_live()
            neither_in_ear = self._neither_bud_in_ear()

            if mode is not None:
                if mode not in NOISE_MODES:
                    raise ValueError(f"Unsupported noise mode: {mode}")
                noise["mode"] = mode
                if mode != "anc" and self._state["immersive_commute"] != "off":
                    self._state["immersive_commute"] = "off"
                    if self._commute_audio is not None:
                        self._commute_audio.stop()
                self._record_tx(
                    f"Noise mode (0x08) -> {mode}",
                    build_noise_mode(self._next_counter(), NOISE_MODES[mode]),
                )
                if mode == "off":
                    self._record_tx(
                        "Noise config (0x000B) -> off",
                        build_set_config_frame(self._next_counter(), CONFIG_ANC, bytes([0x00, 0x00])),
                    )
                elif mode == "anc":
                    self._record_tx(
                        f"Noise config (0x000B) -> anc/{noise['anc_level']}",
                        build_noise_level(
                            self._next_counter(),
                            NOISE_MODES["anc"],
                            noise["anc_level"],
                            ANC_LEVELS,
                        ),
                    )
                elif mode == "transparency":
                    self._record_tx(
                        f"Noise config (0x000B) -> transparency/{noise['transparency_level']}",
                        build_noise_level(
                            self._next_counter(),
                            NOISE_MODES["transparency"],
                            noise["transparency_level"],
                            TRANSPARENCY_LEVELS,
                        ),
                    )
                if is_live and mode in ("anc", "transparency") and neither_in_ear:
                    self._state["bluetooth"]["warning"] = ANC_WEAR_WARNING

            if smart_anc is not None:
                noise["smart_anc"] = bool(smart_anc)
                frame = build_smart_anc_frame(self._next_counter(), noise["smart_anc"])
                self._record_tx(f"Smart ANC -> {'ON' if noise['smart_anc'] else 'OFF'}", frame)
                self._readback_config(CONFIG_ADAPTIVE_ANC, "SmartANC (0x0025)")

            if anc_level is not None:
                lvl = int(anc_level)
                if lvl not in ANC_LEVELS:
                    raise ValueError("ANC level must be between 0 and 19")
                noise["anc_level"] = lvl
                noise["mode"] = "anc"
                frame = build_noise_level(self._next_counter(), NOISE_MODES["anc"], lvl, ANC_LEVELS)
                self._record_tx(f"ANC strength -> {lvl}/19", frame)
                if is_live and neither_in_ear:
                    self._state["bluetooth"]["warning"] = ANC_WEAR_WARNING

            if transparency_level is not None:
                lvl = int(transparency_level)
                if lvl not in TRANSPARENCY_LEVELS:
                    raise ValueError("Transparency level must be 0, 1, or 2")
                noise["transparency_level"] = lvl
                noise["mode"] = "transparency"
                frame = build_noise_level(
                    self._next_counter(),
                    NOISE_MODES["transparency"],
                    lvl,
                    TRANSPARENCY_LEVELS,
                )
                self._record_tx(f"Transparency -> {TRANSPARENCY_MODES[lvl]}", frame)
                if is_live and neither_in_ear:
                    self._state["bluetooth"]["warning"] = ANC_WEAR_WARNING

            if mode is not None or anc_level is not None or transparency_level is not None:
                self._readback_config(CONFIG_ANC, "ANC (0x000B)")

            return deepcopy(self._state)

    def set_immersive_commute(self, mode: str, volume: Optional[int] = None) -> dict[str, Any]:
        if mode not in IMMERSIVE_COMMUTE_MODES:
            raise ValueError(f"Unsupported immersive commute mode: {mode}")
        with self._lock:
            self._require_connected()
            self._state["bluetooth"]["warning"] = ""
            if volume is not None:
                clamped = max(0, min(100, int(volume)))
                self._state["immersive_commute_volume"] = clamped
                if self._commute_audio is not None:
                    self._commute_audio.set_volume(clamped / 100.0)
                self._save_preferences()

            self._state["immersive_commute"] = mode
            if mode != "off":
                self._state["noise"]["mode"] = "anc"
                self._record_tx(
                    "Noise mode (0x08) -> anc",
                    build_noise_mode(self._next_counter(), NOISE_MODES["anc"]),
                )
                self._record_tx(
                    f"Noise config (0x000B) -> anc/{self._state['noise']['anc_level']}",
                    build_noise_level(
                        self._next_counter(),
                        NOISE_MODES["anc"],
                        self._state["noise"]["anc_level"],
                        ANC_LEVELS,
                    ),
                )
                if self._is_live() and self._neither_bud_in_ear():
                    self._state["bluetooth"]["warning"] = ANC_WEAR_WARNING
            frame = build_immersive_commute_frame(self._next_counter(), mode)
            self._record_tx(f"Immersive commute -> {mode}", frame)
            if mode != "off":
                self._readback_config(CONFIG_ANC, "ANC (0x000B)")
            audio = self._commute_audio
            snapshot = deepcopy(self._state)

        # Start/stop soothing stereo desktop soundscape outside state lock
        if audio is not None:
            audio.play(mode)
        return snapshot

    def set_immersive_commute_volume(self, volume: int) -> dict[str, Any]:
        clamped = max(0, min(100, int(volume)))
        with self._lock:
            self._state["immersive_commute_volume"] = clamped
            if self._commute_audio is not None:
                self._commute_audio.set_volume(clamped / 100.0)
            self._save_preferences()
            return deepcopy(self._state)

    def set_theme(
        self,
        *,
        mode: Optional[str] = None,
        custom_base: Optional[str] = None,
        accent: Optional[str] = None,
        bg: Optional[str] = None,
        card: Optional[str] = None,
        reset: bool = False,
    ) -> dict[str, Any]:
        with self._lock:
            if reset:
                self._state["theme"] = deepcopy(DEFAULT_THEME)
            else:
                theme = self._state["theme"]
                if mode is not None:
                    if mode not in VALID_THEME_MODES:
                        raise ValueError(f"Unsupported theme mode: {mode}")
                    theme["mode"] = mode
                if custom_base is not None:
                    if custom_base not in VALID_THEME_BASES:
                        raise ValueError(f"Unsupported custom theme base: {custom_base}")
                    theme["custom_base"] = custom_base
                for key, val in (("accent", accent), ("bg", bg), ("card", card)):
                    if val is not None:
                        cleaned = str(val).strip()
                        if not HEX_COLOR_RE.match(cleaned):
                            raise ValueError(f"Invalid hex color for {key}: {val}")
                        theme[key] = cleaned.upper()
            self._save_preferences()
            theme_copy = deepcopy(self._state["theme"])
            cb = self._theme_callback
            snapshot = deepcopy(self._state)
        if cb is not None:
            try:
                cb(theme_copy)
            except Exception:
                pass
        return snapshot

    def set_gesture(self, gesture: str, side: str, action: str) -> dict[str, Any]:
        if gesture not in GESTURE_TYPES:
            raise ValueError(f"Unsupported gesture type: {gesture}")
        if side not in ("left", "right"):
            raise ValueError("Side must be 'left' or 'right'")
        if action not in GESTURE_ACTIONS:
            raise ValueError(f"Unsupported gesture action: {action}")

        allowed_by_gesture = {
            "single": ("none", "previous_song", "next_song", "volume_up", "volume_down", "play_pause"),
            "double": ("none", "previous_song", "next_song", "volume_up", "volume_down", "play_pause"),
            "triple": ("none", "previous_song", "next_song", "volume_up", "volume_down", "play_pause"),
            "hold": ("none", "voice_assistant", "noise_cancellation"),
            "swipe": ("adjust_volume", "none"),
        }
        if action not in allowed_by_gesture[gesture]:
            raise ValueError(f"Action '{action}' is not valid for '{gesture}'")

        with self._lock:
            self._require_connected()
            self._state["bluetooth"]["warning"] = ""
            self._state["gestures"][gesture][side] = action
            frame = build_gesture_assignment(
                self._next_counter(),
                GESTURE_TYPES[gesture],
                side,
                GESTURE_ACTIONS[action],
            )
            self._record_tx(f"Gesture {gesture}.{side} -> {action}", frame)
            self._readback_config(CONFIG_GESTURES, "Gestures (0x0002)")
            return deepcopy(self._state)

    def set_press_hold_modes(self, side: str, modes: list[str]) -> dict[str, Any]:
        if side not in ("left", "right"):
            raise ValueError("Side must be 'left' or 'right'")
        encode_noise_cycle_mask(modes)
        with self._lock:
            self._require_connected()
            self._state["bluetooth"]["warning"] = ""
            ordered = [m for m in ("anc", "transparency", "off") if m in modes]
            self._state["gestures"]["hold_modes"][side] = ordered
            frame = build_press_hold_cycle_frame(self._next_counter(), side, ordered)
            self._record_tx(f"Press&Hold cycle.{side} -> {','.join(ordered)}", frame)
            self._readback_config(CONFIG_NOISE_LIST, "LongPress (0x000A)")
            return deepcopy(self._state)

    def set_audio_effects(
        self,
        *,
        spatial_audio: Optional[bool] = None,
        head_tracking: Optional[bool] = None,
        spatial_scene: Optional[str] = None,
        eq_preset: Optional[str] = None,
        adaptive_sound: Optional[bool] = None,
    ) -> dict[str, Any]:
        with self._lock:
            self._require_connected()
            fx = self._state["audio_effects"]
            if spatial_audio is not None or head_tracking is not None:
                if spatial_audio is not None:
                    fx["spatial_audio"] = bool(spatial_audio)
                if head_tracking is not None:
                    fx["head_tracking"] = bool(head_tracking)
                if not fx["spatial_audio"]:
                    fx["head_tracking"] = False
                frame = build_spatial_audio_frame(
                    self._next_counter(),
                    fx["spatial_audio"],
                    fx["head_tracking"],
                )
                self._record_tx(
                    f"Spatial audio -> {'on' if fx['spatial_audio'] else 'off'}"
                    + (" + head tracking" if fx["head_tracking"] else ""),
                    frame,
                )
                self._readback_config(CONFIG_SPATIAL_STATE_GET, "Spatial (0x001E)")
            if spatial_scene is not None:
                if spatial_scene not in SPATIAL_SCENES:
                    raise ValueError(f"Unsupported spatial scene: {spatial_scene}")
                fx["spatial_scene"] = spatial_scene
                frame = build_spatial_scene_frame(self._next_counter(), spatial_scene)
                self._record_tx(f"Spatial scene -> {spatial_scene}", frame)
                self._readback_config(CONFIG_SPATIAL_SCENE, "SpatialScene (0x0036)")
            if eq_preset is not None:
                if eq_preset not in EQ_PRESETS:
                    raise ValueError(f"Unsupported EQ preset: {eq_preset}")
                fx["eq_preset"] = eq_preset
                frame = build_profile(self._next_counter(), EQ_PRESETS[eq_preset])
                self._record_tx(f"EQ preset -> {eq_preset}", frame)
                self._readback_config(CONFIG_EQ_PRESET, "EQ Preset (0x0007)")
            if adaptive_sound is not None:
                fx["adaptive_sound"] = bool(adaptive_sound)
                frame = build_adaptive_sound_frame(self._next_counter(), fx["adaptive_sound"])
                self._record_tx(f"Adaptive sound -> {'ON' if fx['adaptive_sound'] else 'OFF'}", frame)
                self._readback_config(CONFIG_ADAPTIVE_SOUND, "AdaptiveSound (0x0029)")

            return deepcopy(self._state)

    def set_additional_settings(
        self,
        *,
        in_ear_detection: Optional[bool] = None,
        dual_connection: Optional[bool] = None,
        auto_answer: Optional[bool] = None,
        adaptive_volume: Optional[bool] = None,
        color: Optional[str] = None,
        show_case: Optional[bool] = None,
    ) -> dict[str, Any]:
        with self._lock:
            has_hw_change = any(
                v is not None for v in (in_ear_detection, dual_connection, auto_answer, adaptive_volume)
            )
            if has_hw_change:
                self._require_connected()

            add = self._state["additional_settings"]
            if in_ear_detection is not None:
                add["in_ear_detection"] = bool(in_ear_detection)
                frame = build_in_ear_detection_frame(self._next_counter(), add["in_ear_detection"])
                self._record_tx(f"In-ear detection -> {'ON' if add['in_ear_detection'] else 'OFF'}", frame)
            if dual_connection is not None:
                add["dual_connection"] = bool(dual_connection)
                frame = build_dual_connection_frame(self._next_counter(), add["dual_connection"])
                self._record_tx(f"Dual connection -> {'ON' if add['dual_connection'] else 'OFF'}", frame)
                self._readback_config(CONFIG_DUAL_CONNECTION, "DualConn (0x0004)")
            if auto_answer is not None:
                add["auto_answer"] = bool(auto_answer)
                frame = build_auto_answer_frame(self._next_counter(), add["auto_answer"])
                self._record_tx(f"Auto-answer -> {'ON' if add['auto_answer'] else 'OFF'}", frame)
                self._readback_config(CONFIG_AUTO_ANSWER, "AutoAnswer (0x0003)")
            if adaptive_volume is not None:
                add["adaptive_volume"] = bool(adaptive_volume)
                frame = build_adaptive_volume_frame(self._next_counter(), add["adaptive_volume"])
                self._record_tx(f"Adaptive volume -> {'ON' if add['adaptive_volume'] else 'OFF'}", frame)
                self._readback_config(CONFIG_ADAPTIVE_VOLUME, "AdaptiveVol (0x0048)")

            prefs_changed = False
            if color is not None:
                if color not in VALID_COLORS:
                    raise ValueError(f"Unsupported color finish: {color}")
                self._state["device"]["color"] = color
                prefs_changed = True
            if show_case is not None:
                self._state["battery"]["show_case"] = bool(show_case)
                prefs_changed = True
            if prefs_changed:
                self._save_preferences()
            return deepcopy(self._state)

    def set_find_earphones(self, target: str, active: bool) -> dict[str, Any]:
        if target not in ("left", "right", "both"):
            raise ValueError("Target must be 'left', 'right', or 'both'")
        with self._lock:
            self._require_connected()
            fe = self._state["find_earphones"]
            if target in ("left", "both"):
                fe["ringing_left"] = bool(active)
            if target in ("right", "both"):
                fe["ringing_right"] = bool(active)
            if not fe["ringing_left"] and not fe["ringing_right"]:
                frame = build_find_earbuds_frame(self._next_counter(), False, "both")
                self._record_tx("Find earphones -> STOP", frame)
            else:
                active_target = (
                    "both"
                    if fe["ringing_left"] and fe["ringing_right"]
                    else ("left" if fe["ringing_left"] else "right")
                )
                frame = build_find_earbuds_frame(self._next_counter(), True, active_target)
                self._record_tx(f"Find earphones -> RING {active_target.upper()}", frame)
            return deepcopy(self._state)

    def refresh_wearing_state(self) -> dict[str, Any]:
        with self._lock:
            self._require_connected()
            frame = build_get_config_frame(self._next_counter(), CONFIG_IN_EAR_STATE)
            self._record_tx("Query InEarState (0x000C)", frame)
            return deepcopy(self._state)

    def refresh_battery(self) -> dict[str, Any]:
        with self._lock:
            self._require_connected()
            self._record_tx("Query DeviceInfo / Battery", build_identity_request(self._next_counter()))
            self._record_tx("Query RunInfo / ANC", build_run_info_request(self._next_counter()))
            self._record_tx("Query InEarState (0x000C)", build_get_config_frame(self._next_counter(), CONFIG_IN_EAR_STATE))
            return deepcopy(self._state)
