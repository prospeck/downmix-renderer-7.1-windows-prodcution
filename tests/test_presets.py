from __future__ import annotations

import unittest

from downmix_renderer.devices import AudioDevice
from downmix_renderer.presets import (
    PRESET_SCHEMA_VERSION,
    load_presets,
    preset_from_current,
    update_preset_from_current,
)


def fake_output(name: str = "Speakers (Qudelix-5K USB DAC 48KHz)") -> AudioDevice:
    return AudioDevice(
        id=18,
        name=name,
        hostapi="Windows WASAPI",
        max_input_channels=0,
        max_output_channels=2,
        default_samplerate=48000,
        default_low_input_latency=0.0,
        default_low_output_latency=0.003,
        default_high_input_latency=0.0,
        default_high_output_latency=0.01,
    )


def fake_input() -> AudioDevice:
    return AudioDevice(
        id=24,
        name="CABLE Output (VB-Audio Virtual Cable)",
        hostapi="Windows WASAPI",
        max_input_channels=16,
        max_output_channels=0,
        default_samplerate=48000,
        default_low_input_latency=0.003,
        default_low_output_latency=0.0,
        default_high_input_latency=0.01,
        default_high_output_latency=0.0,
    )


class PresetTests(unittest.TestCase):
    def test_no_presets_are_created_without_v2_schema(self) -> None:
        self.assertEqual(load_presets({}, [fake_input(), fake_output()]), [])

    def test_v2_presets_are_loaded_only_when_user_saved(self) -> None:
        preset = preset_from_current("Qudelix", fake_input(), fake_output(), -7, 0.42, "windows_7_1")
        settings = {"preset_schema_version": PRESET_SCHEMA_VERSION, "presets": [preset.to_dict()]}
        loaded = load_presets(settings, [fake_input(), fake_output()])
        self.assertEqual(len(loaded), 1)
        self.assertEqual(loaded[0].preamp_db, -7)
        self.assertAlmostEqual(loaded[0].user_volume, 0.42)

    def test_update_overwrites_all_audio_parameters(self) -> None:
        preset = preset_from_current("Daily", fake_input(), fake_output(), -14, 1.0, "windows_7_1")
        update_preset_from_current(preset, fake_input(), fake_output("Speakers (Realtek(R) Audio)"), -3, 0.6, "sharur_9_1_6")
        self.assertEqual(preset.preamp_db, -3)
        self.assertAlmostEqual(preset.user_volume, 0.6)
        self.assertEqual(preset.channel_config, "sharur_9_1_6")
        self.assertIn("Realtek", str(preset.output_device))


if __name__ == "__main__":
    unittest.main()

