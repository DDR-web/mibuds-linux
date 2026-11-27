"""Unit tests for Xiaomi/Redmi RCSP protocol packets and Linux desktop service."""

import json
import tempfile
import unittest
from pathlib import Path

from controllers.bluetooth.rcsp import RcspPacket
from controllers.bluetooth.redmi_buds_8_pro import (
    OPCODE_GET_CONFIG,
    OPCODE_GET_DEVICE_INFO,
    OPCODE_GET_DEVICE_RUN_INFO,
    RedmiBuds8ProService,
    build_adaptive_sound_frame,
    build_adaptive_volume_frame,
    build_auto_answer_frame,
    build_dual_connection_frame,
    build_find_earbuds_frame,
    build_immersive_commute_frame,
    build_in_ear_detection_frame,
    build_press_hold_cycle_frame,
    build_smart_anc_frame,
    build_spatial_audio_frame,
    build_spatial_scene_frame,
    decode_noise_cycle_mask,
    encode_noise_cycle_mask,
)


class RedmiBuds8ProProtocolTests(unittest.TestCase):
    def test_smart_anc_frames(self):
        self.assertEqual(build_smart_anc_frame(0x12, True).hex(), "fedcbac4f200051203002501ef")
        self.assertEqual(build_smart_anc_frame(0x13, False).hex(), "fedcbac4f200051303002500ef")

    def test_immersive_commute_frames(self):
        self.assertEqual(build_immersive_commute_frame(0x20, "off").hex(), "fedcbac4f200052003004a00ef")
        self.assertEqual(build_immersive_commute_frame(0x21, "airplane").hex(), "fedcbac4f200052103004a01ef")
        self.assertEqual(build_immersive_commute_frame(0x22, "public_transit").hex(), "fedcbac4f200052203004a02ef")
        self.assertEqual(build_immersive_commute_frame(0x23, "train").hex(), "fedcbac4f200052303004a03ef")

    def test_press_hold_cycle_bitmask_matches_xiaomitws(self):
        # Transparency (bit 2 = 4) + Off (bit 0 = 1) => 0x05; right unchanged => 0xFF
        mask = encode_noise_cycle_mask(["transparency", "off"])
        self.assertEqual(mask, 0x05)
        self.assertEqual(decode_noise_cycle_mask(mask), ["transparency", "off"])
        frame = build_press_hold_cycle_frame(0x30, "left", ["transparency", "off"])
        self.assertEqual(frame.hex(), "fedcbac4f200063004000a05ffef")
        with self.assertRaises(ValueError):
            encode_noise_cycle_mask(["off"])

    def test_spatial_audio_and_other_configs(self):
        self.assertEqual(build_spatial_audio_frame(0x40, False, False).hex(), "fedcbac4f200054003001d02ef")
        self.assertEqual(build_spatial_audio_frame(0x41, True, False).hex(), "fedcbac4f200054103001d03ef")
        self.assertEqual(build_spatial_audio_frame(0x42, True, True).hex(), "fedcbac4f200054203001d0bef")
        self.assertEqual(build_spatial_scene_frame(0x43, "music").hex(), "fedcbac4f20006430400360102ef")
        self.assertEqual(build_adaptive_sound_frame(0x44, True).hex(), "fedcbac4f200054403002901ef")
        self.assertEqual(build_in_ear_detection_frame(0x45, False).hex(), "fedcbac408000445020601ef")
        self.assertEqual(build_dual_connection_frame(0x46, True).hex(), "fedcbac4f200054603000401ef")
        self.assertEqual(build_auto_answer_frame(0x47, True).hex(), "fedcbac4f200054703000301ef")
        self.assertEqual(build_adaptive_volume_frame(0x48, True).hex(), "fedcbac4f200054803004801ef")
        self.assertEqual(build_find_earbuds_frame(0x49, True, "left").hex(), "fedcbac4f20006490400090101ef")

    def test_clean_disconnected_defaults_and_preferences_only_persistence(self):
        with tempfile.TemporaryDirectory() as tmp:
            prefs_file = Path(tmp) / "preferences.json"
            svc = RedmiBuds8ProService(state_path=prefs_file, enable_bluetooth_auto=False, enable_audio=False)
            state = svc.get_state()

            # Zero fake placeholders when disconnected
            self.assertFalse(state["device"]["connected"])
            self.assertEqual(state["device"]["mode"], "disconnected")
            self.assertEqual(state["device"]["firmware"], "")
            self.assertEqual(state["device"]["serial"], "")
            self.assertIsNone(state["battery"]["left"])
            self.assertIsNone(state["battery"]["right"])
            self.assertIsNone(state["battery"]["case"])

            # Hardware controls require a live connection by default
            with self.assertRaises(ConnectionError):
                svc.set_noise_control(mode="anc")

            # UI preferences work offline and persist without personal device telemetry
            updated = svc.set_additional_settings(color="blue", show_case=True)
            self.assertEqual(updated["device"]["color"], "blue")
            self.assertTrue(updated["battery"]["show_case"])

            raw = json.loads(prefs_file.read_text(encoding="utf-8"))
            self.assertEqual(set(raw.keys()), {"color", "show_case", "commute_volume", "theme"})

            svc2 = RedmiBuds8ProService(state_path=prefs_file, enable_bluetooth_auto=False, enable_audio=False)
            reloaded = svc2.get_state()
            self.assertEqual(reloaded["device"]["color"], "blue")
            self.assertTrue(reloaded["battery"]["show_case"])

    def test_service_state_transitions_and_custom_eq_disabled(self):
        with tempfile.TemporaryDirectory() as tmp:
            prefs_file = Path(tmp) / "preferences.json"
            svc = RedmiBuds8ProService(
                state_path=prefs_file,
                enable_bluetooth_auto=False,
                allow_offline=True,
                enable_audio=False,
            )

            s = svc.set_noise_control(mode="anc", anc_level=15, smart_anc=True)
            self.assertEqual(s["noise"]["mode"], "anc")
            self.assertEqual(s["noise"]["anc_level"], 15)
            self.assertTrue(s["noise"]["smart_anc"])

            s = svc.set_noise_control(mode="transparency", transparency_level=2)
            self.assertEqual(s["noise"]["mode"], "transparency")
            self.assertEqual(s["noise"]["transparency_level"], 2)

            s = svc.set_immersive_commute("train")
            self.assertEqual(s["immersive_commute"], "train")
            self.assertEqual(s["noise"]["mode"], "anc")

            s = svc.set_gesture("swipe", "left", "none")
            self.assertEqual(s["gestures"]["swipe"]["left"], "none")
            self.assertIn("05 00 02 05 08 FF EF", s["bluetooth"]["last_tx_hex"])

            s = svc.set_press_hold_modes("left", ["anc", "transparency", "off"])
            self.assertEqual(s["gestures"]["hold_modes"]["left"], ["anc", "transparency", "off"])

            # Custom EQ (profile 10) must be rejected
            with self.assertRaises(ValueError):
                svc.set_audio_effects(eq_preset="custom")

    def test_rx_decoders_identity_run_info_and_wearing(self):
        with tempfile.TemporaryDirectory() as tmp:
            svc = RedmiBuds8ProService(
                state_path=Path(tmp) / "preferences.json",
                enable_bluetooth_auto=False,
                enable_audio=False,
            )

            # DeviceInfo response (0x02): fw 3.2.2.6 (0x3226), VID 0x2717 / PID 0x50E5, battery L=90 R=85+chg Case=70
            dev_info_payload = bytes([
                0x00, 0x10,
                0x03, 0x01, 0x32, 0x26,
                0x05, 0x03, 0x27, 0x17, 0x50, 0xE5,
                0x04, 0x07, 90, 0x80 | 85, 70,
            ])
            svc._handle_rx_packet(None, RcspPacket(0x04, OPCODE_GET_DEVICE_INFO, dev_info_payload))

            st = svc.get_state()
            self.assertEqual(st["device"]["firmware"], "3.2.2.6")
            self.assertEqual(st["device"]["vid"], "0x2717")
            self.assertEqual(st["device"]["pid"], "0x50E5")
            self.assertEqual(st["device"]["model_id"], "miwear.headphone.p76gl")
            self.assertEqual(st["device"]["sale_model"], "M2535E1")
            self.assertEqual(st["battery"]["left"], 90)
            self.assertFalse(st["battery"]["left_charging"])
            self.assertEqual(st["battery"]["right"], 85)
            self.assertTrue(st["battery"]["right_charging"])
            self.assertEqual(st["battery"]["case"], 70)
            self.assertTrue(st["battery"]["case_available"])

            # RunInfo response (0x09): tag 0x09 (1-byte mode=anc), tag 0x0A (in-ear detection off = 0x01)
            run_info_payload = bytes([0x00, 0x11, 0x02, 0x09, 0x01, 0x02, 0x0A, 0x01])
            svc._handle_rx_packet(None, RcspPacket(0x04, OPCODE_GET_DEVICE_RUN_INFO, run_info_payload))
            st = svc.get_state()
            self.assertEqual(st["noise"]["mode"], "anc")
            self.assertFalse(st["additional_settings"]["in_ear_detection"])

            # Config 0x000C (InEarState): left in_ear (0x08), right in_case (0x01)
            in_ear_payload = bytes([0x00, 0x12, 0x03, 0x00, 0x0C, 0x09])
            svc._handle_rx_packet(None, RcspPacket(0x04, OPCODE_GET_CONFIG, in_ear_payload))
            st = svc.get_state()
            self.assertEqual(st["device"]["wearing"], {"left": "in_ear", "right": "in_case"})


if __name__ == "__main__":
    unittest.main()
