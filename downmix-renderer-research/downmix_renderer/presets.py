from __future__ import annotations

from dataclasses import dataclass, field
from time import time
from uuid import uuid4

from .constants import DEFAULT_CHANNEL_CONFIG, DEFAULT_PREAMP_DB
from .devices import AudioDevice, find_saved_device

PRESET_SCHEMA_VERSION = 2


@dataclass
class Preset:
    id: str
    name: str
    input_device: dict[str, object] | None = None
    output_device: dict[str, object] | None = None
    preamp_db: int = DEFAULT_PREAMP_DB
    user_volume: float = 1.0
    channel_config: str = DEFAULT_CHANNEL_CONFIG
    output_keywords: list[str] = field(default_factory=list)
    user_created: bool = True

    @classmethod
    def from_dict(cls, data: dict[str, object]) -> "Preset":
        return cls(
            id=str(data.get("id") or f"preset-{uuid4().hex[:8]}"),
            name=str(data.get("name") or "Preset"),
            input_device=data.get("input_device") if isinstance(data.get("input_device"), dict) else None,
            output_device=data.get("output_device") if isinstance(data.get("output_device"), dict) else None,
            preamp_db=int(data.get("preamp_db", DEFAULT_PREAMP_DB)),
            user_volume=float(data.get("user_volume", 1.0)),
            channel_config=str(data.get("channel_config", DEFAULT_CHANNEL_CONFIG)),
            output_keywords=[str(item).lower() for item in data.get("output_keywords", [])],
            user_created=bool(data.get("user_created", True)),
        )

    def to_dict(self) -> dict[str, object]:
        return {
            "id": self.id,
            "name": self.name,
            "input_device": self.input_device,
            "output_device": self.output_device,
            "preamp_db": self.preamp_db,
            "user_volume": self.user_volume,
            "channel_config": self.channel_config,
            "output_keywords": self.output_keywords,
            "user_created": self.user_created,
        }


def load_presets(settings: dict[str, object], devices: list[AudioDevice]) -> list[Preset]:
    if int(settings.get("preset_schema_version", 0) or 0) != PRESET_SCHEMA_VERSION:
        return []
    raw_presets = settings.get("presets")
    if isinstance(raw_presets, list) and raw_presets:
        return [Preset.from_dict(item) for item in raw_presets if isinstance(item, dict)]
    return []


def preset_from_current(
    name: str,
    input_device: AudioDevice | None,
    output_device: AudioDevice | None,
    preamp_db: int,
    user_volume: float,
    channel_config: str,
) -> Preset:
    return Preset(
        id=f"preset-{int(time())}-{uuid4().hex[:6]}",
        name=name.strip() or "Preset",
        input_device=_identity(input_device, "input"),
        output_device=_identity(output_device, "output"),
        preamp_db=preamp_db,
        user_volume=user_volume,
        channel_config=channel_config,
        output_keywords=_keywords_for(output_device),
    )


def update_preset_from_current(
    preset: Preset,
    input_device: AudioDevice | None,
    output_device: AudioDevice | None,
    preamp_db: int,
    user_volume: float,
    channel_config: str,
) -> None:
    preset.input_device = _identity(input_device, "input")
    preset.output_device = _identity(output_device, "output")
    preset.preamp_db = preamp_db
    preset.user_volume = user_volume
    preset.channel_config = channel_config
    preset.output_keywords = _keywords_for(output_device)


def match_preset_for_output(
    presets: list[Preset],
    active_output: AudioDevice | None,
    devices: list[AudioDevice],
) -> Preset | None:
    if active_output is None:
        return None

    best: tuple[int, Preset] | None = None
    active_name = active_output.name.lower()
    for preset in presets:
        score = 0
        preset_output = find_saved_device(devices, preset.output_device, "output")
        if preset_output and preset_output.name == active_output.name:
            score += 100
        if preset_output and preset_output.hostapi == active_output.hostapi:
            score += 10
        for keyword in preset.output_keywords:
            if keyword and keyword in active_name:
                score += 5
        if score and (best is None or score > best[0]):
            best = (score, preset)
    return best[1] if best else None


def _identity(device: AudioDevice | None, mode: str) -> dict[str, object] | None:
    return device.identity(mode) if device else None


def _keywords_for(device: AudioDevice | None) -> list[str]:
    if device is None:
        return []
    lower = device.name.lower()
    keywords = []
    for keyword in ("qudelix", "bluetooth", "bt", "usb", "dac", "speaker", "realtek"):
        if keyword in lower:
            keywords.append(keyword)
    return keywords
