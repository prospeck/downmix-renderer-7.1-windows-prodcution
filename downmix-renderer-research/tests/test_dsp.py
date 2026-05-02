from __future__ import annotations

import ast
import unittest
from pathlib import Path

import numpy as np

from downmix_renderer.constants import MAX_INPUT_CHANNELS
from downmix_renderer.constants import CHANNEL_LAYOUTS
from downmix_renderer.dsp import DownmixProcessor, db_to_linear
from downmix_renderer.matrix import MATRIX, MATRIX_LITERAL


def original_matrix_literal() -> tuple[tuple[float, float], ...]:
    source_path = Path(__file__).resolve().parents[1] / "reference" / "renderer_app_original.py"
    tree = ast.parse(source_path.read_text(encoding="utf-8", errors="replace"))
    for node in tree.body:
        if isinstance(node, ast.Assign):
            if any(isinstance(target, ast.Name) and target.id == "MATRIX" for target in node.targets):
                if isinstance(node.value, ast.Call):
                    values = ast.literal_eval(node.value.args[0])
                    return tuple(tuple(float(item) for item in row) for row in values)
    raise AssertionError("MATRIX assignment not found in reference renderer")


class MatrixTests(unittest.TestCase):
    def test_matrix_literal_matches_original_renderer(self) -> None:
        self.assertEqual(MATRIX_LITERAL, original_matrix_literal())

    def test_matrix_shape_and_dtype(self) -> None:
        self.assertEqual(MATRIX.shape, (16, 2))
        self.assertEqual(MATRIX.dtype, np.float32)

    def test_windows_7_1_layout_uses_first_eight_stream_channels(self) -> None:
        layout = CHANNEL_LAYOUTS["windows_7_1"]
        self.assertEqual(tuple(layout["indices"]), tuple(range(8)))
        self.assertEqual(tuple(layout["names"]), ("FL", "FR", "FC", "LFE", "BL", "BR", "SL", "SR"))


class DspTests(unittest.TestCase):
    def test_front_left_maps_to_left_only(self) -> None:
        processor = DownmixProcessor(preamp_db=0)
        data = np.zeros((8, MAX_INPUT_CHANNELS), dtype=np.float32)
        data[:, 0] = 0.25
        out = processor.process(data)
        np.testing.assert_allclose(out[:, 0], 0.25, rtol=0, atol=1e-7)
        np.testing.assert_allclose(out[:, 1], 0.0, rtol=0, atol=1e-7)

    def test_center_maps_to_both_channels_with_original_coefficient(self) -> None:
        processor = DownmixProcessor(preamp_db=0)
        data = np.zeros((8, MAX_INPUT_CHANNELS), dtype=np.float32)
        data[:, 2] = 0.5
        out = processor.process(data)
        np.testing.assert_allclose(out[:, 0], 0.5 * 0.7071, rtol=0, atol=1e-6)
        np.testing.assert_allclose(out[:, 1], 0.5 * 0.7071, rtol=0, atol=1e-6)

    def test_preamp_is_applied_before_output(self) -> None:
        processor = DownmixProcessor(preamp_db=-6)
        data = np.zeros((4, MAX_INPUT_CHANNELS), dtype=np.float32)
        data[:, 0] = 0.5
        out = processor.process(data)
        expected = 0.5 * db_to_linear(-6)
        np.testing.assert_allclose(out[:, 0], expected, rtol=0, atol=1e-6)

    def test_fewer_channels_are_padded(self) -> None:
        processor = DownmixProcessor(preamp_db=0)
        data = np.zeros((4, 2), dtype=np.float32)
        data[:, 0] = 0.2
        data[:, 1] = 0.3
        out = processor.process(data)
        np.testing.assert_allclose(out[:, 0], 0.2, rtol=0, atol=1e-7)
        np.testing.assert_allclose(out[:, 1], 0.3, rtol=0, atol=1e-7)

    def test_master_volume_and_mute_are_separate_from_preamp(self) -> None:
        processor = DownmixProcessor(preamp_db=0)
        processor.set_master_volume(0.25, muted=False)
        data = np.zeros((4, MAX_INPUT_CHANNELS), dtype=np.float32)
        data[:, 0] = 0.8
        out = processor.process(data)
        np.testing.assert_allclose(out[:, 0], 0.2, rtol=0, atol=1e-6)

        processor.set_master_volume(1.0, muted=True)
        out = processor.process(data)
        np.testing.assert_allclose(out, 0.0, rtol=0, atol=1e-7)

    def test_limiter_never_outputs_above_full_scale_on_hot_blocks(self) -> None:
        processor = DownmixProcessor(preamp_db=0)
        data = np.ones((8, MAX_INPUT_CHANNELS), dtype=np.float32)
        out = processor.process(data)
        self.assertLessEqual(float(np.max(np.abs(out))), 1.0 + 1e-6)
        self.assertTrue(processor.snapshot().clipping)


if __name__ == "__main__":
    unittest.main()
