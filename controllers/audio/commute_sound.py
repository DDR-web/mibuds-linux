"""Native Linux ambient soundscape synthesizer and player for Immersive Commute.

Generates soothing, seamlessly looping stereo PCM soundscapes (Airplane,
Public transit, Train) using only Python's standard library and plays them
directly through PipeWire/PulseAudio/ALSA via GStreamer (with paplay/aplay
fallback) so audio routes cleanly to the connected earbuds without browser
autoplay restrictions.
"""

from __future__ import annotations

from array import array
import math
import random
import shutil
import subprocess
import threading
import time
from typing import Optional

try:
    import gi

    gi.require_version("Gst", "1.0")
    from gi.repository import Gst  # type: ignore

    Gst.init(None)
    _GST_AVAILABLE = bool(
        Gst.ElementFactory.find("appsrc")
        and Gst.ElementFactory.find("volume")
        and Gst.ElementFactory.find("autoaudiosink")
    )
except Exception:
    Gst = None  # type: ignore
    _GST_AVAILABLE = False

SAMPLE_RATE = 44100
CHANNELS = 2
SAMPLE_WIDTH = 2  # 16-bit signed little-endian
CHUNK_FRAMES = 4410  # 100 ms per chunk
CHUNK_BYTES = CHUNK_FRAMES * CHANNELS * SAMPLE_WIDTH
VALID_COMMUTE_MODES = ("off", "airplane", "public_transit", "train")


def _synthesize_loop_pcm(mode: str) -> bytes:
    """Synthesize a seamless 4.5-second stereo 16-bit PCM ambient loop for the given mode."""
    duration_s = 4.5  # Exact multiple of 1.5s train cadence for seamless looping
    total_frames = int(SAMPLE_RATE * duration_s)
    xfade_frames = int(SAMPLE_RATE * 0.45)
    gen_frames = total_frames + xfade_frames

    rng = random.Random({"airplane": 101, "public_transit": 202, "train": 303}.get(mode, 7))
    raw_l = [0.0] * gen_frames
    raw_r = [0.0] * gen_frames

    # Filter states per channel (decorrelated stereo for wide, calming ambience)
    lp1_l = lp1_r = 0.0
    lp2_l = lp2_r = 0.0
    air_l = air_r = 0.0
    p0_l = p1_l = p2_l = 0.0
    p0_r = p1_r = p2_r = 0.0

    two_pi = 2.0 * math.pi

    if mode == "airplane":
        # Warm deep cabin rumble + soft high-altitude air vent hiss
        a_deep = 0.032
        a_mid = 0.09
        a_air = 0.22
        for i in range(gen_frames):
            w_common = rng.uniform(-1.0, 1.0)
            wl = 0.65 * w_common + 0.35 * rng.uniform(-1.0, 1.0)
            wr = 0.65 * w_common + 0.35 * rng.uniform(-1.0, 1.0)

            lp1_l += a_deep * (wl - lp1_l)
            lp2_l += a_deep * (lp1_l - lp2_l)
            air_l += a_air * (wl - air_l)
            vent_l = (air_l - lp1_l) * 0.24

            lp1_r += a_deep * (wr - lp1_r)
            lp2_r += a_deep * (lp1_r - lp2_r)
            air_r += a_air * (wr - air_r)
            vent_r = (air_r - lp1_r) * 0.24

            # Very gentle engine hum (112 Hz + 168 Hz)
            t = i / SAMPLE_RATE
            hum = 0.028 * math.sin(two_pi * 112.0 * t) + 0.014 * math.sin(two_pi * 168.0 * t)

            # Soft gentle cabin air drift
            drift = 0.94 + 0.06 * math.sin(two_pi * (t / duration_s))
            raw_l[i] = (lp2_l * 3.1 + vent_l + hum) * drift
            raw_r[i] = (lp2_r * 3.1 + vent_r + hum) * drift

    elif mode == "public_transit":
        # Smooth broadband pink-brown noise masking voices & urban transit clatter
        a_smooth = 0.12
        a_low = 0.028
        for i in range(gen_frames):
            w_common = rng.uniform(-1.0, 1.0)
            wl = 0.55 * w_common + 0.45 * rng.uniform(-1.0, 1.0)
            wr = 0.55 * w_common + 0.45 * rng.uniform(-1.0, 1.0)

            p0_l = 0.997 * p0_l + wl * 0.099
            p1_l = 0.963 * p1_l + wl * 0.296
            p2_l = 0.570 * p2_l + wl * 0.600
            pink_l = (p0_l + p1_l + p2_l) * 0.22
            lp1_l += a_smooth * (pink_l - lp1_l)
            lp2_l += a_low * (wl - lp2_l)

            p0_r = 0.997 * p0_r + wr * 0.099
            p1_r = 0.963 * p1_r + wr * 0.296
            p2_r = 0.570 * p2_r + wr * 0.600
            pink_r = (p0_r + p1_r + p2_r) * 0.22
            lp1_r += a_smooth * (pink_r - lp1_r)
            lp2_r += a_low * (wr - lp2_r)

            t = i / SAMPLE_RATE
            swell = 0.93 + 0.07 * math.sin(two_pi * (t / duration_s))
            raw_l[i] = (lp1_l * 1.45 + lp2_l * 1.95) * swell
            raw_r[i] = (lp1_r * 1.45 + lp2_r * 1.95) * swell

    else:  # "train"
        # Cozy train cabin noise with soothing rhythmic double-pulse rail cadence (every 1.5s)
        a_cabin = 0.055
        a_rail = 0.16
        cycle_s = 1.5
        for i in range(gen_frames):
            w_common = rng.uniform(-1.0, 1.0)
            wl = 0.62 * w_common + 0.38 * rng.uniform(-1.0, 1.0)
            wr = 0.62 * w_common + 0.38 * rng.uniform(-1.0, 1.0)

            lp1_l += a_cabin * (wl - lp1_l)
            lp2_l += a_cabin * (lp1_l - lp2_l)
            air_l += a_rail * (wl - air_l)

            lp1_r += a_cabin * (wr - lp1_r)
            lp2_r += a_cabin * (lp1_r - lp2_r)
            air_r += a_rail * (wr - air_r)

            # Soft double-pulse rail joint envelope at t=0.25s and t=0.47s in each 1.5s bar
            phase = (i / SAMPLE_RATE) % cycle_s
            p1 = math.exp(-((phase - 0.25) / 0.055) ** 2)
            p2 = math.exp(-((phase - 0.47) / 0.065) ** 2) * 0.78
            rail_env = 1.0 + 0.42 * (p1 + p2)
            thump = 0.065 * (p1 + p2) * math.sin(two_pi * 64.0 * phase)

            raw_l[i] = lp2_l * 2.55 * rail_env + (air_l - lp1_l) * 0.22 + thump
            raw_r[i] = lp2_r * 2.55 * rail_env + (air_r - lp1_r) * 0.22 + thump

    # Seamless equal-power crossfade over xfade_frames so loop boundary is completely silent
    for i in range(xfade_frames):
        frac = i / xfade_frames
        fade_in = math.sin(frac * math.pi * 0.5)
        fade_out = math.cos(frac * math.pi * 0.5)
        tail_idx = total_frames + i
        raw_l[i] = raw_l[i] * fade_in + raw_l[tail_idx] * fade_out
        raw_r[i] = raw_r[i] * fade_in + raw_r[tail_idx] * fade_out

    # Normalize safely to comfortable RMS (~ -15 dBFS) without clipping
    peak = max(
        max((abs(v) for v in raw_l[:total_frames]), default=1.0),
        max((abs(v) for v in raw_r[:total_frames]), default=1.0),
        1e-6,
    )
    scale = (0.48 / peak) * 32767.0

    pcm = array("h", [0] * (total_frames * CHANNELS))
    for i in range(total_frames):
        sl = int(max(-32767, min(32767, raw_l[i] * scale)))
        sr = int(max(-32767, min(32767, raw_r[i] * scale)))
        pcm[i * 2] = sl
        pcm[i * 2 + 1] = sr
    return pcm.tobytes()


class CommuteAudioPlayer:
    """Thread-safe Linux desktop ambient sound player (GStreamer primary, paplay/aplay fallback)."""

    def __init__(self, volume: float = 0.65) -> None:
        self._lock = threading.RLock()
        self._volume = max(0.0, min(1.0, float(volume)))
        self._mode = "off"
        self._cache: dict[str, bytes] = {}
        self._stop_event = threading.Event()
        self._worker: Optional[threading.Thread] = None
        self._pipeline = None
        self._vol_elem = None
        self._proc: Optional[subprocess.Popen[bytes]] = None

    @property
    def mode(self) -> str:
        with self._lock:
            return self._mode

    @property
    def volume(self) -> float:
        with self._lock:
            return self._volume

    def set_volume(self, volume: float) -> float:
        """Update playback volume smoothly (0.0..1.0)."""
        clamped = max(0.0, min(1.0, float(volume)))
        with self._lock:
            self._volume = clamped
            if self._vol_elem is not None:
                try:
                    self._vol_elem.set_property("volume", clamped)
                except Exception:
                    pass
            return self._volume

    def play(self, mode: str) -> None:
        """Start playing soothing ambient soundscape for mode, or stop when mode == 'off'."""
        if mode not in VALID_COMMUTE_MODES:
            raise ValueError(f"Unsupported commute sound mode: {mode}")
        if mode == "off":
            self.stop()
            return

        with self._lock:
            if self._mode == mode and self._worker is not None and self._worker.is_alive():
                return

        self.stop()
        pcm = self._get_loop_pcm(mode)

        with self._lock:
            self._mode = mode
            self._stop_event = threading.Event()
            stop_ev = self._stop_event
            if _GST_AVAILABLE:
                self._worker = threading.Thread(
                    target=self._run_gstreamer,
                    args=(pcm, stop_ev),
                    daemon=True,
                )
            else:
                self._worker = threading.Thread(
                    target=self._run_subprocess_fallback,
                    args=(pcm, stop_ev),
                    daemon=True,
                )
            self._worker.start()

    def stop(self) -> None:
        """Immediately stop any active ambient sound playback and release audio sink."""
        with self._lock:
            self._mode = "off"
            self._stop_event.set()
            pipeline, self._pipeline = self._pipeline, None
            self._vol_elem = None
            proc, self._proc = self._proc, None
            worker, self._worker = self._worker, None

        if pipeline is not None:
            try:
                pipeline.set_state(Gst.State.NULL)
            except Exception:
                pass
        if proc is not None:
            try:
                if proc.stdin:
                    proc.stdin.close()
                proc.terminate()
                proc.wait(timeout=0.5)
            except Exception:
                try:
                    proc.kill()
                except Exception:
                    pass
        if worker is not None and worker is not threading.current_thread():
            worker.join(timeout=0.6)

    def _get_loop_pcm(self, mode: str) -> bytes:
        with self._lock:
            cached = self._cache.get(mode)
        if cached is not None:
            return cached
        pcm = _synthesize_loop_pcm(mode)
        with self._lock:
            self._cache[mode] = pcm
        return pcm

    def _run_gstreamer(self, pcm: bytes, stop_ev: threading.Event) -> None:
        pipeline = None
        try:
            pipeline = Gst.parse_launch(
                "appsrc name=src is-live=true block=true format=time "
                f"! audio/x-raw,format=S16LE,channels={CHANNELS},rate={SAMPLE_RATE},layout=interleaved "
                "! volume name=vol ! autoaudiosink"
            )
            appsrc = pipeline.get_by_name("src")
            vol_elem = pipeline.get_by_name("vol")
            appsrc.set_property("max-bytes", CHUNK_BYTES * 4)
            vol_elem.set_property("volume", 0.0)

            with self._lock:
                if stop_ev.is_set():
                    return
                self._pipeline = pipeline
                self._vol_elem = vol_elem

            pipeline.set_state(Gst.State.PLAYING)

            # Gentle 350ms fade-in to target volume
            offset = 0
            pcm_len = len(pcm)
            pts = 0
            chunk_dur_ns = int((CHUNK_FRAMES / SAMPLE_RATE) * 1_000_000_000)
            fade_steps = 4
            step = 0

            while not stop_ev.is_set():
                if step < fade_steps:
                    step += 1
                    with self._lock:
                        target_vol = self._volume
                    vol_elem.set_property("volume", target_vol * (step / fade_steps))

                end = offset + CHUNK_BYTES
                if end <= pcm_len:
                    chunk = pcm[offset:end]
                    offset = 0 if end == pcm_len else end
                else:
                    rem = end - pcm_len
                    chunk = pcm[offset:] + pcm[:rem]
                    offset = rem

                buf = Gst.Buffer.new_allocate(None, len(chunk), None)
                buf.fill(0, chunk)
                buf.pts = pts
                buf.duration = chunk_dur_ns
                pts += chunk_dur_ns

                ret = appsrc.emit("push-buffer", buf)
                if ret != Gst.FlowReturn.OK:
                    break
        except Exception:
            if not stop_ev.is_set():
                self._run_subprocess_fallback(pcm, stop_ev)
        finally:
            if pipeline is not None:
                try:
                    pipeline.set_state(Gst.State.NULL)
                except Exception:
                    pass
            with self._lock:
                if self._pipeline is pipeline:
                    self._pipeline = None
                    self._vol_elem = None

    def _run_subprocess_fallback(self, pcm: bytes, stop_ev: threading.Event) -> None:
        cmd: Optional[list[str]] = None
        if shutil.which("paplay"):
            cmd = [
                "paplay",
                "--raw",
                f"--rate={SAMPLE_RATE}",
                f"--channels={CHANNELS}",
                "--format=s16le",
                "--client-name=MiBuds Linux",
                "--stream-name=Immersive commute",
                "-",
            ]
        elif shutil.which("aplay"):
            cmd = [
                "aplay",
                "-q",
                "-f",
                "S16_LE",
                "-r",
                str(SAMPLE_RATE),
                "-c",
                str(CHANNELS),
                "-t",
                "raw",
                "-",
            ]
        if cmd is None:
            return

        proc = None
        try:
            proc = subprocess.Popen(
                cmd,
                stdin=subprocess.PIPE,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            with self._lock:
                if stop_ev.is_set():
                    proc.terminate()
                    return
                self._proc = proc

            offset = 0
            pcm_len = len(pcm)
            while not stop_ev.is_set() and proc.poll() is None and proc.stdin is not None:
                end = offset + CHUNK_BYTES
                if end <= pcm_len:
                    chunk = pcm[offset:end]
                    offset = 0 if end == pcm_len else end
                else:
                    rem = end - pcm_len
                    chunk = pcm[offset:] + pcm[:rem]
                    offset = rem

                with self._lock:
                    vol = self._volume
                if vol < 0.99:
                    samples = array("h")
                    samples.frombytes(chunk)
                    for idx in range(len(samples)):
                        samples[idx] = int(samples[idx] * vol)
                    chunk = samples.tobytes()

                proc.stdin.write(chunk)
                proc.stdin.flush()
                time.sleep(0.02)
        except Exception:
            pass
        finally:
            if proc is not None:
                try:
                    if proc.stdin:
                        proc.stdin.close()
                    proc.terminate()
                except Exception:
                    pass
            with self._lock:
                if self._proc is proc:
                    self._proc = None
