# Taran's 7.1 Downmix Renderer Suite

Premium Windows WASAPI downmix renderer for routing a multichannel VB-CABLE capture endpoint to a stereo DAC. This is a safe working copy; the original renderer is preserved in `reference/renderer_app_original.py`.

## Highlights

- OLED-black custom window frame with matching black title bar.
- WASAPI-only device lists to keep routing focused and clean.
- Sharur matrix preserved exactly from the original app and pinned by tests.
- Windows volume-key following through CoreAudio endpoint volume.
- Separate saved Suite Volume and Preamp controls.
- User-created preset buttons with create, update, delete, and one-click switching.
- Runtime smart preset switching when the active Windows output device changes.
- Optional system boot autostart via a Startup-folder launcher.
- Windows 7.1 channel view using stream order `FL FR FC LFE BL BR SL SR`.

## Quick Start

Run from source:

```powershell
cd "C:\Users\taran\Documents\Playground\downmix-renderer-research"
python renderer_app.py
```

Run the packaged app:

```powershell
cd "C:\Users\taran\Documents\Playground\downmix-renderer-research"
.\dist\TaransDownmixRendererSuite.exe
```

Recommended route:

- Input: `CABLE Output (VB-Audio Virtual Cable)` using `Windows WASAPI`.
- Output: your DAC/speakers using `Windows WASAPI`.
- Start with `7.1` channel view for Windows playback.

## Presets

The app starts with zero presets. Create only the presets you actually use:

1. Select the WASAPI input and output.
2. Set Preamp, Suite Volume, and channel layout.
3. Type a preset name and click `New`; it appears as a button.
4. Click a preset button to switch instantly.
5. Click `Update` to overwrite the active preset with the current controls.
6. Click `Delete` to remove the active preset.

Each preset saves device identities, preamp, Suite Volume, channel layout, and output-device matching hints. Settings are written atomically to avoid partial saves.

## Smart Switching

`Smart preset switching` matches the current Windows WASAPI default output to a saved preset. If you manually click another preset, the app respects that manual choice until Windows reports a different default output device.

`Auto Start Renderer on System Boot` writes a small launcher into the Windows Startup folder. It does not require admin rights.

## Channel Layouts

Default `7.1` view:

```text
FL FR FC LFE BL BR SL SR
```

`9.1.6 Monitor` keeps the original 16-channel Sharur labels for diagnostics. Matrix coefficients are unchanged in both views.

## Route Probe

Enumerate devices and format support:

```powershell
python -m downmix_renderer.route_probe --duration 0 --output route_probe_inventory.json
```

Capture channel activity while Apple Music Atmos is playing:

```powershell
python -m downmix_renderer.route_probe --duration 20 --output route_probe_apple_music.json
```

Truth criteria:

- `channels_above_8_detected`: the installed route delivered more than 7.1.
- `eight_or_fewer_channels`: Windows/VB-CABLE capped the route before the renderer.
- `no_signal`: Apple Music/Dolby Access/output routing is not feeding VB-CABLE.

## Development

Run tests:

```powershell
python -m unittest discover -s tests
```

Build the EXE:

```powershell
python scripts\make_icon.py
pyinstaller --noconfirm renderer_app.spec
```
