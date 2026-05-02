from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Iterable

import sounddevice as sd

WASAPI_HOSTAPI = "Windows WASAPI"


@dataclass(frozen=True)
class AudioDevice:
    id: int
    name: str
    hostapi: str
    max_input_channels: int
    max_output_channels: int
    default_samplerate: int
    default_low_input_latency: float
    default_low_output_latency: float
    default_high_input_latency: float
    default_high_output_latency: float

    @property
    def input_label(self) -> str:
        return (
            f"{self.name} | {self.hostapi} | "
            f"{self.max_input_channels}ch in | {self.default_samplerate} Hz"
        )

    @property
    def output_label(self) -> str:
        return (
            f"{self.name} | {self.hostapi} | "
            f"{self.max_output_channels}ch out | {self.default_samplerate} Hz"
        )

    def identity(self, mode: str) -> dict[str, object]:
        return {
            "id": self.id,
            "name": self.name,
            "hostapi": self.hostapi,
            "mode": mode,
            "max_input_channels": self.max_input_channels,
            "max_output_channels": self.max_output_channels,
            "default_samplerate": self.default_samplerate,
        }

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


def list_devices() -> list[AudioDevice]:
    raw_devices = sd.query_devices()
    hostapis = sd.query_hostapis()
    devices: list[AudioDevice] = []

    for device_id, dev in enumerate(raw_devices):
        hostapi = hostapis[dev["hostapi"]]["name"]
        devices.append(
            AudioDevice(
                id=device_id,
                name=str(dev["name"]),
                hostapi=str(hostapi),
                max_input_channels=int(dev["max_input_channels"]),
                max_output_channels=int(dev["max_output_channels"]),
                default_samplerate=int(dev["default_samplerate"]),
                default_low_input_latency=float(dev["default_low_input_latency"]),
                default_low_output_latency=float(dev["default_low_output_latency"]),
                default_high_input_latency=float(dev["default_high_input_latency"]),
                default_high_output_latency=float(dev["default_high_output_latency"]),
            )
        )
    return devices


def input_devices(devices: Iterable[AudioDevice]) -> list[AudioDevice]:
    return [dev for dev in devices if dev.max_input_channels >= 2]


def output_devices(devices: Iterable[AudioDevice]) -> list[AudioDevice]:
    return [dev for dev in devices if dev.max_output_channels >= 2]


def wasapi_devices(devices: Iterable[AudioDevice]) -> list[AudioDevice]:
    return [dev for dev in devices if dev.hostapi == WASAPI_HOSTAPI]


def renderer_input_devices(devices: Iterable[AudioDevice]) -> list[AudioDevice]:
    return [dev for dev in wasapi_devices(devices) if dev.max_input_channels >= 16]


def renderer_output_devices(devices: Iterable[AudioDevice]) -> list[AudioDevice]:
    return [dev for dev in wasapi_devices(devices) if dev.max_output_channels >= 2]


def find_saved_device(
    devices: Iterable[AudioDevice],
    saved: dict[str, object] | int | None,
    mode: str,
) -> AudioDevice | None:
    if saved is None:
        return None

    candidates = list(renderer_input_devices(devices) if mode == "input" else renderer_output_devices(devices))

    if isinstance(saved, int):
        return next((dev for dev in candidates if dev.id == saved), None)

    saved_name = str(saved.get("name", ""))
    saved_hostapi = str(saved.get("hostapi", ""))
    saved_sr = int(saved.get("default_samplerate", 0) or 0)
    saved_id = saved.get("id")

    exact = [
        dev
        for dev in candidates
        if dev.name == saved_name
        and dev.hostapi == saved_hostapi
        and (saved_sr == 0 or dev.default_samplerate == saved_sr)
    ]
    if exact:
        return exact[0]

    name_host = [dev for dev in candidates if dev.name == saved_name and dev.hostapi == saved_hostapi]
    if name_host:
        return name_host[0]

    if isinstance(saved_id, int):
        return next((dev for dev in candidates if dev.id == saved_id), None)

    return None


def preferred_input(devices: Iterable[AudioDevice]) -> AudioDevice | None:
    inputs = renderer_input_devices(devices)
    ranked = sorted(
        inputs,
        key=lambda dev: (
            "CABLE Output" not in dev.name,
            "Windows WASAPI" not in dev.hostapi,
            dev.max_input_channels < 16,
            dev.default_samplerate != 48000,
            dev.id,
        ),
    )
    return ranked[0] if ranked else None


def preferred_output(devices: Iterable[AudioDevice]) -> AudioDevice | None:
    outputs = renderer_output_devices(devices)
    if not outputs:
        return None

    dac_keywords = ("qudelix", "dac", "speakers")
    ranked = sorted(
        outputs,
        key=lambda dev: (
            not any(keyword in dev.name.lower() for keyword in dac_keywords),
            "Windows WASAPI" not in dev.hostapi,
            dev.max_output_channels < 2,
            dev.id,
        ),
    )
    return ranked[0]


def default_wasapi_output(devices: Iterable[AudioDevice]) -> AudioDevice | None:
    try:
        hostapis = sd.query_hostapis()
    except Exception:
        return None

    default_id: int | None = None
    for hostapi in hostapis:
        if hostapi.get("name") == WASAPI_HOSTAPI:
            raw_id = hostapi.get("default_output_device", -1)
            if isinstance(raw_id, int) and raw_id >= 0:
                default_id = raw_id
            break
    if default_id is None:
        return None
    return next((dev for dev in devices if dev.id == default_id), None)


def check_format_support(device_id: int, mode: str, channels: int, samplerate: int) -> tuple[bool, str]:
    try:
        if mode == "input":
            sd.check_input_settings(
                device=device_id,
                channels=channels,
                samplerate=samplerate,
                dtype="float32",
            )
        elif mode == "output":
            sd.check_output_settings(
                device=device_id,
                channels=channels,
                samplerate=samplerate,
                dtype="float32",
            )
        else:
            raise ValueError("mode must be input or output")
    except Exception as exc:
        return False, f"{type(exc).__name__}: {str(exc).splitlines()[0]}"
    return True, "OK"
