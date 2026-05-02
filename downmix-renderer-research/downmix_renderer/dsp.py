from __future__ import annotations

from dataclasses import dataclass
from threading import Lock

import numpy as np

from .constants import DEFAULT_PREAMP_DB, MAX_INPUT_CHANNELS, OUTPUT_CHANNELS
from .matrix import MATRIX


def db_to_linear(db_value: float) -> float:
    return float(10 ** (db_value / 20.0))


def linear_to_db(value: float) -> float:
    return float(20.0 * np.log10(max(float(value), 1e-6)))


@dataclass(frozen=True)
class DspSnapshot:
    channel_levels: np.ndarray
    left_meter: float
    right_meter: float
    preamp_db: float
    limiter_gain: float
    clipping: bool
    user_volume: float
    master_volume: float
    master_muted: bool

    @property
    def active_channel_count(self) -> int:
        return int(np.count_nonzero(self.channel_levels > 1e-4))


class DownmixProcessor:
    """Real-time-safe 16ch-to-stereo downmixer.

    The matrix is fixed. Preamp provides renderer headroom. Master volume is
    intentionally separate so Windows media keys can control loudness without
    changing the Sharur matrix or the saved preamp value.
    """

    def __init__(
        self,
        preamp_db: float = DEFAULT_PREAMP_DB,
        matrix: np.ndarray = MATRIX,
        max_channels: int = MAX_INPUT_CHANNELS,
    ) -> None:
        self.matrix = np.asarray(matrix, dtype=np.float32)
        if self.matrix.shape != (max_channels, OUTPUT_CHANNELS):
            raise ValueError("matrix must be 16x2")

        self.max_channels = max_channels
        self._config_lock = Lock()
        self._state_lock = Lock()
        self._preamp_db = float(preamp_db)
        self._preamp_gain = db_to_linear(preamp_db)
        self._user_volume = 1.0
        self._master_volume = 1.0
        self._master_muted = False
        self._limiter_gain = 1.0

        self._scratch_frames = 0
        self._input16 = np.zeros((0, max_channels), dtype=np.float32)
        self._stereo = np.zeros((0, OUTPUT_CHANNELS), dtype=np.float32)

        self._channel_levels = np.zeros(max_channels, dtype=np.float32)
        self._left_meter = 0.0
        self._right_meter = 0.0
        self._clipping = False

    def set_preamp_db(self, db_value: float) -> None:
        with self._config_lock:
            self._preamp_db = float(db_value)
            self._preamp_gain = db_to_linear(self._preamp_db)

    def set_master_volume(self, scalar: float, muted: bool = False) -> None:
        scalar = min(1.0, max(0.0, float(scalar)))
        with self._config_lock:
            self._master_volume = scalar
            self._master_muted = bool(muted)

    def set_user_volume(self, scalar: float) -> None:
        scalar = min(1.0, max(0.0, float(scalar)))
        with self._config_lock:
            self._user_volume = scalar

    def reset_limiter(self) -> None:
        self._limiter_gain = 1.0

    def process(self, indata: np.ndarray, outdata: np.ndarray | None = None) -> np.ndarray:
        if indata.ndim != 2:
            raise ValueError("indata must be a frames x channels array")

        frames, channels = indata.shape
        self._ensure_scratch(frames)
        input16 = self._prepare_input(indata, frames, channels)

        with self._config_lock:
            preamp_gain = self._preamp_gain
            preamp_db = self._preamp_db
            user_volume = self._user_volume
            master_volume = self._master_volume
            master_muted = self._master_muted

        np.dot(input16, self.matrix, out=self._stereo[:frames])
        self._stereo[:frames] *= preamp_gain

        peak_before_limiter = float(np.max(np.abs(self._stereo[:frames]))) if frames else 0.0
        target_gain = 1.0
        clipping = False
        if peak_before_limiter > 1.0:
            target_gain = 1.0 / peak_before_limiter
            clipping = True

        alpha = 0.4 if target_gain < self._limiter_gain else 0.05
        smoothed_gain = (1.0 - alpha) * self._limiter_gain + alpha * target_gain
        applied_limiter_gain = min(smoothed_gain, target_gain) if clipping else smoothed_gain
        self._limiter_gain = smoothed_gain

        self._stereo[:frames] *= applied_limiter_gain
        if master_muted:
            self._stereo[:frames] *= 0.0
        else:
            self._stereo[:frames] *= master_volume * user_volume

        if outdata is None:
            rendered = self._stereo[:frames].copy()
        else:
            outdata.fill(0.0)
            if outdata.shape[0] != frames or outdata.shape[1] < OUTPUT_CHANNELS:
                raise ValueError("outdata must match frames and have at least 2 channels")
            outdata[:, :OUTPUT_CHANNELS] = self._stereo[:frames]
            rendered = outdata[:, :OUTPUT_CHANNELS]

        channel_levels = (
            np.max(np.abs(input16), axis=0).astype(np.float32, copy=False)
            if frames
            else np.zeros(self.max_channels, dtype=np.float32)
        )
        left_meter = float(np.max(np.abs(rendered[:, 0]))) if frames else 0.0
        right_meter = float(np.max(np.abs(rendered[:, 1]))) if frames else 0.0

        with self._state_lock:
            self._channel_levels[:] = channel_levels
            self._left_meter = left_meter
            self._right_meter = right_meter
            self._clipping = clipping
            self._snapshot_preamp_db = preamp_db
            self._snapshot_user_volume = user_volume
            self._snapshot_master_volume = master_volume
            self._snapshot_master_muted = master_muted

        return rendered

    def snapshot(self) -> DspSnapshot:
        with self._state_lock:
            preamp_db = getattr(self, "_snapshot_preamp_db", self._preamp_db)
            user_volume = getattr(self, "_snapshot_user_volume", self._user_volume)
            master_volume = getattr(self, "_snapshot_master_volume", self._master_volume)
            master_muted = getattr(self, "_snapshot_master_muted", self._master_muted)
            return DspSnapshot(
                channel_levels=self._channel_levels.copy(),
                left_meter=float(self._left_meter),
                right_meter=float(self._right_meter),
                preamp_db=float(preamp_db),
                limiter_gain=float(self._limiter_gain),
                clipping=bool(self._clipping),
                user_volume=float(user_volume),
                master_volume=float(master_volume),
                master_muted=bool(master_muted),
            )

    def _ensure_scratch(self, frames: int) -> None:
        if frames <= self._scratch_frames:
            return
        self._scratch_frames = frames
        self._input16 = np.zeros((frames, self.max_channels), dtype=np.float32)
        self._stereo = np.zeros((frames, OUTPUT_CHANNELS), dtype=np.float32)

    def _prepare_input(self, indata: np.ndarray, frames: int, channels: int) -> np.ndarray:
        if channels == self.max_channels and indata.dtype == np.float32:
            return indata[:, : self.max_channels]

        input16 = self._input16[:frames]
        input16.fill(0.0)
        copy_channels = min(channels, self.max_channels)
        input16[:, :copy_channels] = indata[:, :copy_channels]
        return input16
