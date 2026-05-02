import sys
import json
import os
import sounddevice as sd
import numpy as np
from collections import OrderedDict
from PyQt5 import QtWidgets, QtCore, QtGui
from threading import Lock

SAMPLE_RATE   = 48000
BLOCK_SIZE    = 256
SETTINGS_FILE = "settings.json"

stream     = None
running    = False
state_lock = Lock()

# ==============================
# STATE
# ==============================

channel_levels = np.zeros(16)
left_meter  = 0
right_meter = 0
preamp_db   = -14
clipping    = False
last_gain   = 1.0

# ==============================
# SETTINGS
# ==============================

def load_settings():
    if os.path.exists(SETTINGS_FILE):
        try:
            with open(SETTINGS_FILE, "r") as f:
                return json.load(f)
        except Exception:
            return {}
    return {}

def save_settings(data):
    try:
        with open(SETTINGS_FILE, "w") as f:
            json.dump(data, f, indent=4)
    except Exception as e:
        print("Settings save error:", e)

# ==============================
# MATRIX
# ==============================

MATRIX = np.array([
    [1.0, 0.0], [0.0, 1.0],
    [0.7071, 0.7071],
    [2.2646, 2.2646],
    [1.0, 0.0], [0.0, 1.0],
    [1.0, 0.0], [0.0, 1.0],
    [1.0, 0.0], [0.0, 1.0],
    [1.0, 0.0], [0.0, 1.0],
    [1.0, 0.0], [0.0, 1.0],
    [1.0, 0.0], [0.0, 1.0],
], dtype=np.float32)

# ==============================
# UTILS
# ==============================

def to_db(x):
    return 20 * np.log10(max(x, 1e-6))

# ==============================
# DSP
# ==============================

def downmix(indata):
    global channel_levels, left_meter, right_meter
    global preamp_db, clipping, last_gain

    frames, ch = indata.shape

    with state_lock:
        for i in range(min(16, ch)):
            channel_levels[i] = np.max(np.abs(indata[:, i]))

    if ch < 16:
        padded = np.zeros((frames, 16), dtype=np.float32)
        padded[:, :ch] = indata
        indata = padded

    stereo = indata @ MATRIX
    L = stereo[:, 0]
    R = stereo[:, 1]

    gain = 10 ** (preamp_db / 20)
    L *= gain
    R *= gain

    max_val = max(np.max(np.abs(L)), np.max(np.abs(R)))

    # Denormal guard
    if max_val < 1e-8:
        max_val = 1.0

    target_gain = 1.0
    is_clipping = False

    if max_val > 1.0:
        target_gain = 1.0 / max_val
        is_clipping = True

    # Asymmetric alpha — fast attack, slow release
    alpha = 0.4 if target_gain < last_gain else 0.05
    last_gain = (1 - alpha) * last_gain + alpha * target_gain

    L *= last_gain
    R *= last_gain

    with state_lock:
        left_meter  = np.max(np.abs(L))
        right_meter = np.max(np.abs(R))
        clipping    = is_clipping

    return np.stack([L, R], axis=1)


def callback(indata, outdata, frames, time, status):
    if status:
        print(status)
    try:
        processed = downmix(indata)
        if processed.shape == outdata.shape:
            outdata[:] = processed
        else:
            outdata.fill(0)
    except Exception as e:
        print("DSP Error:", e)
        outdata.fill(0)

# ==============================
# DEVICES
# ==============================

def get_devices():
    """
    Returns (inputs, outputs) where each is a list of dicts:
      { id, name, hostapi, in_ch, out_ch, sr }
    Grouped internally by host API for display purposes.
    """
    raw_devices = sd.query_devices()
    hostapis    = sd.query_hostapis()
    inputs, outputs = [], []

    for i, dev in enumerate(raw_devices):
        in_ch  = dev['max_input_channels']
        out_ch = dev['max_output_channels']
        sr     = int(dev['default_samplerate'])
        ha     = hostapis[dev['hostapi']]['name']
        entry  = dict(id=i, name=dev['name'], hostapi=ha,
                      in_ch=in_ch, out_ch=out_ch, sr=sr)
        if in_ch  >= 2: inputs.append(entry)
        if out_ch >= 2: outputs.append(entry)

    return inputs, outputs


def build_device_model(device_list, mode):
    """
    Build a QStandardItemModel with host-API category headers.
    mode = 'input' or 'output' — controls which channel count is shown prominently.
    Each device item stores its device ID in Qt.UserRole.
    """
    model  = QtGui.QStandardItemModel()
    groups = OrderedDict()

    for dev in device_list:
        groups.setdefault(dev['hostapi'], []).append(dev)

    for hostapi_name, devs in groups.items():
        # ── Category header ────────────────────────────────────────────
        header = QtGui.QStandardItem(f"  ▸  {hostapi_name}")
        header.setEnabled(False)
        header.setForeground(QtGui.QColor(ACCENT))
        header.setBackground(QtGui.QColor("#0a0a0a"))
        font = QtGui.QFont("Arial", 9, QtGui.QFont.Bold)
        header.setFont(font)
        # Store sentinel so we can detect headers
        header.setData(-1, QtCore.Qt.UserRole)
        model.appendRow(header)

        for dev in devs:
            ch_info = (f"{dev['in_ch']}ch in"  if mode == 'input'
                       else f"{dev['out_ch']}ch out")
            label = f"    {dev['name']}   [{ch_info}  ·  {dev['sr']} Hz]"
            item = QtGui.QStandardItem(label)
            item.setData(dev['id'], QtCore.Qt.UserRole)
            item.setForeground(QtGui.QColor(TEXT))
            item.setBackground(QtGui.QColor(PANEL))
            model.appendRow(item)

    return model


def set_combo_by_device_id(combo, device_id):
    """Select the row whose UserRole data matches device_id."""
    model = combo.model()
    for row in range(model.rowCount()):
        if model.item(row).data(QtCore.Qt.UserRole) == device_id:
            combo.setCurrentIndex(row)
            return


def get_combo_device_id(combo):
    """Return the device ID stored in the current item's UserRole."""
    return combo.currentData(QtCore.Qt.UserRole)


# ==============================
# STYLES
# ==============================

DARK   = "#0d0d0d"
PANEL  = "#141414"
BORDER = "#222"
ACCENT = "#00e676"
TEXT   = "#cccccc"
DIM    = "#555"

BASE_STYLE = f"""
QWidget {{
    background-color: {DARK};
    color: {TEXT};
    font-family: Arial;
    font-size: 12px;
}}
QLabel#section {{
    color: {DIM};
    font-size: 10px;
    letter-spacing: 2px;
}}
QComboBox {{
    background-color: {PANEL};
    border: 1px solid {BORDER};
    border-radius: 5px;
    padding: 5px 10px;
    color: {TEXT};
    min-height: 28px;
}}
QComboBox::drop-down {{
    border: none;
    width: 24px;
}}
QComboBox::down-arrow {{
    image: none;
    border-left: 5px solid transparent;
    border-right: 5px solid transparent;
    border-top: 6px solid {DIM};
    margin-right: 6px;
}}
QComboBox QAbstractItemView {{
    background: #111;
    border: 1px solid {BORDER};
    selection-background-color: #003d22;
    selection-color: {ACCENT};
    padding: 2px;
    outline: none;
}}
QPushButton {{
    background-color: {PANEL};
    border: 1px solid {BORDER};
    border-radius: 6px;
    padding: 7px 18px;
    font-size: 12px;
    color: {TEXT};
}}
QPushButton:hover   {{ background-color: #222; border-color: #444; }}
QPushButton:pressed {{ background-color: #111; }}
QPushButton#start   {{ background-color: #00311a; border-color: #005c30; color: {ACCENT}; }}
QPushButton#start:hover {{ background-color: #004523; }}
QPushButton#stop    {{ background-color: #2d0a0a; border-color: #5c1a1a; color: #ff5252; }}
QPushButton#stop:hover  {{ background-color: #3d1010; }}
QSlider::groove:horizontal {{
    height: 4px; background: #2a2a2a; border-radius: 2px;
}}
QSlider::sub-page:horizontal {{
    background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
        stop:0 #005c30, stop:1 {ACCENT});
    border-radius: 2px;
}}
QSlider::handle:horizontal {{
    background: {ACCENT}; border: 2px solid #0d0d0d;
    width: 14px; height: 14px; margin: -5px 0; border-radius: 7px;
}}
QFrame#card {{
    background-color: {PANEL};
    border: 1px solid {BORDER};
    border-radius: 8px;
}}
QScrollBar:vertical {{
    background: {DARK};
    width: 6px;
    border-radius: 3px;
}}
QScrollBar::handle:vertical {{
    background: #333;
    border-radius: 3px;
    min-height: 20px;
}}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height: 0; }}
"""


def section_label(text):
    lbl = QtWidgets.QLabel(text.upper())
    lbl.setObjectName("section")
    lbl.setContentsMargins(0, 8, 0, 2)
    return lbl


def card(layout):
    frame = QtWidgets.QFrame()
    frame.setObjectName("card")
    frame.setLayout(layout)
    return frame


# ==============================
# CUSTOM WIDGETS
# ==============================

class VUMeter(QtWidgets.QWidget):
    def __init__(self, label="L", parent=None):
        super().__init__(parent)
        self.label = label
        self.level = 0.0
        self.peak  = 0.0
        self._peak_timer = 0
        self.setMinimumSize(28, 180)
        self.setMaximumWidth(36)

    def set_level(self, linear):
        self.level = max(0.0, min(1.0, linear))
        if self.level >= self.peak:
            self.peak = self.level
            self._peak_timer = 40
        else:
            if self._peak_timer > 0:
                self._peak_timer -= 1
            else:
                self.peak = max(self.peak - 0.01, self.level)
        self.update()

    def paintEvent(self, event):
        p = QtGui.QPainter(self)
        p.setRenderHint(QtGui.QPainter.Antialiasing)
        w, h  = self.width(), self.height()
        bar_h = h - 24

        p.setPen(QtCore.Qt.NoPen)
        p.setBrush(QtGui.QColor("#141414"))
        p.drawRoundedRect(4, 4, w - 8, bar_h - 8, 3, 3)

        fill_h = int((bar_h - 8) * self.level)
        if fill_h > 0:
            grad = QtGui.QLinearGradient(0, bar_h - 8, 0, 0)
            grad.setColorAt(0.0,  QtGui.QColor("#00e676"))
            grad.setColorAt(0.65, QtGui.QColor("#ffee58"))
            grad.setColorAt(1.0,  QtGui.QColor("#ff1744"))
            p.setBrush(grad)
            top = bar_h - 8 - fill_h
            p.drawRoundedRect(4, 4 + top, w - 8, fill_h, 3, 3)

        if self.peak > 0.01:
            peak_y = 4 + int((bar_h - 8) * (1.0 - self.peak))
            color  = QtGui.QColor("#ff1744") if self.peak > 0.85 else QtGui.QColor("#ffffff")
            p.setPen(QtGui.QPen(color, 2))
            p.drawLine(5, peak_y, w - 5, peak_y)

        p.setPen(QtGui.QColor("#888"))
        p.setFont(QtGui.QFont("Arial", 9, QtGui.QFont.Bold))
        p.drawText(0, h - 10, w, 14, QtCore.Qt.AlignCenter, self.label)
        p.end()


class ChannelTile(QtWidgets.QWidget):
    INACTIVE = "#1a1a1a"
    ACTIVE   = "#003d22"
    HOT      = "#00e676"

    def __init__(self, name, parent=None):
        super().__init__(parent)
        self.name   = name
        self._level = 0.0
        self.setMinimumSize(70, 52)
        self.setSizePolicy(QtWidgets.QSizePolicy.Expanding,
                           QtWidgets.QSizePolicy.Fixed)

    def set_level(self, v):
        self._level = max(0.0, min(1.0, v))
        self.update()

    def paintEvent(self, event):
        p = QtGui.QPainter(self)
        p.setRenderHint(QtGui.QPainter.Antialiasing)
        w, h   = self.width(), self.height()
        active = self._level > 0.01

        p.setPen(QtCore.Qt.NoPen)
        p.setBrush(QtGui.QColor(self.ACTIVE if active else self.INACTIVE))
        p.drawRoundedRect(1, 1, w - 2, h - 2, 5, 5)

        p.setPen(QtGui.QPen(QtGui.QColor(self.HOT if active else "#2a2a2a"), 1))
        p.setBrush(QtCore.Qt.NoBrush)
        p.drawRoundedRect(1, 1, w - 2, h - 2, 5, 5)

        p.setPen(QtGui.QColor("#00e676" if active else "#555"))
        p.setFont(QtGui.QFont("Arial", 10, QtGui.QFont.Bold))
        p.drawText(0, 4, w, 20, QtCore.Qt.AlignCenter, self.name)

        bar_w = w - 12
        bar_h = 5
        bar_y = h - 13
        p.setPen(QtCore.Qt.NoPen)
        p.setBrush(QtGui.QColor("#222"))
        p.drawRoundedRect(6, bar_y, bar_w, bar_h, 2, 2)
        if self._level > 0.005:
            grad = QtGui.QLinearGradient(6, 0, 6 + bar_w, 0)
            grad.setColorAt(0.0,  QtGui.QColor("#00e676"))
            grad.setColorAt(0.75, QtGui.QColor("#ffee58"))
            grad.setColorAt(1.0,  QtGui.QColor("#ff1744"))
            p.setBrush(grad)
            p.drawRoundedRect(6, bar_y, max(4, int(bar_w * self._level)), bar_h, 2, 2)

        db_str = f"{to_db(self._level):.0f}" if self._level > 0.001 else "—"
        p.setPen(QtGui.QColor("#444" if not active else "#aaa"))
        p.setFont(QtGui.QFont("Arial", 7))
        p.drawText(0, bar_y - 2, w, 12, QtCore.Qt.AlignCenter, f"{db_str} dB")
        p.end()


# ==============================
# MAIN WINDOW
# ==============================

class RendererUI(QtWidgets.QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Downmix Renderer PRO")
        self.setMinimumSize(980, 640)
        self.setStyleSheet(BASE_STYLE)

        self.inputs, self.outputs = get_devices()
        self.settings = load_settings()

        root = QtWidgets.QHBoxLayout(self)
        root.setSpacing(12)
        root.setContentsMargins(16, 16, 16, 16)

        # ── Left column ────────────────────────────────────────────────
        left = QtWidgets.QVBoxLayout()
        left.setSpacing(6)

        # ── I/O card ───────────────────────────────────────────────────
        io_l = QtWidgets.QVBoxLayout()
        io_l.setSpacing(6)
        io_l.setContentsMargins(12, 10, 12, 12)
        io_l.addWidget(section_label("Audio I/O"))

        io_l.addWidget(QtWidgets.QLabel("Input Device"))
        self.input_combo = QtWidgets.QComboBox()
        self.input_combo.setModel(build_device_model(self.inputs, 'input'))
        self.input_combo.setMaxVisibleItems(20)
        self.input_combo.currentIndexChanged.connect(
            lambda idx: self._skip_headers(self.input_combo, idx))
        io_l.addWidget(self.input_combo)

        io_l.addWidget(QtWidgets.QLabel("Output Device"))
        self.output_combo = QtWidgets.QComboBox()
        self.output_combo.setModel(build_device_model(self.outputs, 'output'))
        self.output_combo.setMaxVisibleItems(20)
        self.output_combo.currentIndexChanged.connect(
            lambda idx: self._skip_headers(self.output_combo, idx))
        io_l.addWidget(self.output_combo)

        left.addWidget(card(io_l))

        # Restore saved devices
        saved_input  = self.settings.get("input_device")
        saved_output = self.settings.get("output_device")
        if saved_input  is not None: set_combo_by_device_id(self.input_combo,  saved_input)
        if saved_output is not None: set_combo_by_device_id(self.output_combo, saved_output)

        # ── Transport card ─────────────────────────────────────────────
        tr_l = QtWidgets.QVBoxLayout()
        tr_l.setSpacing(6)
        tr_l.setContentsMargins(12, 10, 12, 12)
        tr_l.addWidget(section_label("Transport"))

        btn_row = QtWidgets.QHBoxLayout()
        self.start_btn = QtWidgets.QPushButton("▶  Start")
        self.stop_btn  = QtWidgets.QPushButton("■  Stop")
        self.start_btn.setObjectName("start")
        self.stop_btn.setObjectName("stop")
        self.start_btn.setMinimumHeight(36)
        self.stop_btn.setMinimumHeight(36)
        btn_row.addWidget(self.start_btn)
        btn_row.addWidget(self.stop_btn)
        tr_l.addLayout(btn_row)

        self.status_dot  = QtWidgets.QLabel("●")
        self.status_text = QtWidgets.QLabel("Stopped")
        self.status_dot.setStyleSheet("color:#ff5252; font-size:14px;")
        self.status_text.setStyleSheet(f"color:{DIM}; font-size:11px;")
        sr_row = QtWidgets.QHBoxLayout()
        sr_row.setSpacing(6)
        sr_row.addWidget(self.status_dot)
        sr_row.addWidget(self.status_text)
        sr_row.addStretch()
        tr_l.addLayout(sr_row)
        left.addWidget(card(tr_l))

        # ── Preamp card ────────────────────────────────────────────────
        pre_l = QtWidgets.QVBoxLayout()
        pre_l.setSpacing(6)
        pre_l.setContentsMargins(12, 10, 12, 12)
        pre_l.addWidget(section_label("Preamp Gain"))

        gain_row = QtWidgets.QHBoxLayout()
        gain_row.addWidget(QtWidgets.QLabel("Gain"))
        gain_row.addStretch()
        self.preamp_label = QtWidgets.QLabel("-14 dB")
        self.preamp_label.setStyleSheet(
            f"color:{ACCENT}; font-size:14px; font-weight:bold;")
        gain_row.addWidget(self.preamp_label)
        pre_l.addLayout(gain_row)

        self.slider = QtWidgets.QSlider(QtCore.Qt.Horizontal)
        self.slider.setMinimum(-20)
        self.slider.setMaximum(0)
        saved_preamp = self.settings.get("preamp_db", -14)
        self.slider.setValue(saved_preamp)
        self.preamp_label.setText(f"{saved_preamp} dB")
        self.slider.setMinimumHeight(28)
        pre_l.addWidget(self.slider)

        tick_row = QtWidgets.QHBoxLayout()
        for val in ["-20", "-15", "-10", "-5", "0"]:
            t = QtWidgets.QLabel(val)
            t.setStyleSheet(f"color:{DIM}; font-size:9px;")
            t.setAlignment(QtCore.Qt.AlignCenter)
            tick_row.addWidget(t)
        pre_l.addLayout(tick_row)
        left.addWidget(card(pre_l))

        left.addStretch()
        info = QtWidgets.QLabel(f"SR: {SAMPLE_RATE} Hz  ·  Block: {BLOCK_SIZE}")
        info.setStyleSheet(f"color:{DIM}; font-size:10px;")
        left.addWidget(info)

        root.addLayout(left, 3)

        # ── Right column ───────────────────────────────────────────────
        right = QtWidgets.QVBoxLayout()
        right.setSpacing(10)

        # Channel grid card
        ch_l = QtWidgets.QVBoxLayout()
        ch_l.setSpacing(6)
        ch_l.setContentsMargins(12, 10, 12, 12)
        ch_l.addWidget(section_label("Input Channels"))

        grid = QtWidgets.QGridLayout()
        grid.setSpacing(5)
        names = ["FL","FR","FC","LFE","BL","BR","BLC","BRC",
                 "SL","SR","TFL","TFR","TSL","TSR","TBL","TBR"]
        self.tiles = []
        for i, name in enumerate(names):
            tile = ChannelTile(name)
            grid.addWidget(tile, i // 8, i % 8)
            self.tiles.append(tile)
        ch_l.addLayout(grid)
        right.addWidget(card(ch_l))

        # Output meters card
        mt_l = QtWidgets.QVBoxLayout()
        mt_l.setSpacing(6)
        mt_l.setContentsMargins(12, 10, 12, 12)
        mt_l.addWidget(section_label("Output Level"))

        meters_row = QtWidgets.QHBoxLayout()
        meters_row.setSpacing(8)
        self.vu_left  = VUMeter("L")
        self.vu_right = VUMeter("R")
        meters_row.addWidget(self.vu_left)
        meters_row.addWidget(self.vu_right)

        scale_col = QtWidgets.QVBoxLayout()
        scale_col.setSpacing(0)
        for db_val in ["0", "-6", "-12", "-20", "-40", "-60"]:
            lbl = QtWidgets.QLabel(db_val)
            lbl.setStyleSheet(f"color:{DIM}; font-size:8px;")
            lbl.setAlignment(QtCore.Qt.AlignLeft | QtCore.Qt.AlignVCenter)
            scale_col.addWidget(lbl)
        meters_row.addLayout(scale_col)
        meters_row.addStretch()
        mt_l.addLayout(meters_row)

        readout_row = QtWidgets.QHBoxLayout()
        self.db_left_label  = QtWidgets.QLabel("L: — dB")
        self.db_right_label = QtWidgets.QLabel("R: — dB")
        for lbl in (self.db_left_label, self.db_right_label):
            lbl.setStyleSheet(
                f"color:{ACCENT}; font-size:11px; font-family:monospace;")
        readout_row.addWidget(self.db_left_label)
        readout_row.addSpacing(16)
        readout_row.addWidget(self.db_right_label)
        readout_row.addStretch()
        mt_l.addLayout(readout_row)
        right.addWidget(card(mt_l))

        right.addStretch()
        root.addLayout(right, 7)

        # ── Wire up ────────────────────────────────────────────────────
        self.start_btn.clicked.connect(self.start_audio)
        self.stop_btn.clicked.connect(self.stop_audio)
        self.slider.valueChanged.connect(self.update_preamp)

        self.timer = QtCore.QTimer()
        self.timer.timeout.connect(self.update_ui)
        self.timer.start(40)

    # ── Helpers ────────────────────────────────────────────────────────

    @staticmethod
    def _skip_headers(combo, index):
        """If user lands on a category header, jump to the next real item."""
        model = combo.model()
        item  = model.item(index)
        if item is None or item.data(QtCore.Qt.UserRole) == -1:
            # Try forward first, then backward
            for delta, rng in [(1, range(index + 1, model.rowCount())),
                               (-1, range(index - 1, -1, -1))]:
                for row in rng:
                    candidate = model.item(row)
                    if candidate and candidate.data(QtCore.Qt.UserRole) != -1:
                        combo.setCurrentIndex(row)
                        return

    # ── Slots ──────────────────────────────────────────────────────────

    def update_preamp(self, val):
        global preamp_db
        preamp_db = val
        sign = "+" if val > 0 else ""
        self.preamp_label.setText(f"{sign}{val} dB")

    def start_audio(self):
        global stream, running

        input_dev  = get_combo_device_id(self.input_combo)
        output_dev = get_combo_device_id(self.output_combo)

        if input_dev is None or output_dev is None:
            self._set_status("error", "Select valid devices first")
            return

        try:
            if sd.query_devices(input_dev)['max_input_channels'] < 16:
                raise Exception("Input must support 16 channels")

            stream = sd.Stream(
                samplerate=SAMPLE_RATE,
                blocksize=BLOCK_SIZE,
                channels=(16, 2),
                device=(input_dev, output_dev),
                dtype='float32',
                latency='low',
                callback=callback
            )
            stream.start()
            running = True

            # Persist settings on successful start
            save_settings({
                "input_device":  input_dev,
                "output_device": output_dev,
                "preamp_db":     preamp_db
            })

            self._set_status("running", "Running")

        except Exception as e:
            self._set_status("error", str(e))

    def stop_audio(self):
        global stream, running, clipping
        if stream is not None:
            stream.stop()
            stream.close()
        stream  = None
        running = False
        with state_lock:
            clipping = False
        self._set_status("stopped", "Stopped")

    def _set_status(self, state, text):
        colors = {
            "running": (ACCENT,   ACCENT),
            "stopped": ("#ff5252", DIM),
            "error":   ("#ff9800", "#ff9800"),
            "limit":   ("#ff9800", "#ff9800"),
        }
        dot_col, txt_col = colors.get(state, ("#ff5252", DIM))
        self.status_dot.setStyleSheet(f"color:{dot_col}; font-size:14px;")
        self.status_text.setStyleSheet(f"color:{txt_col}; font-size:11px;")
        self.status_text.setText(text)

    def update_ui(self):
        with state_lock:
            levels = channel_levels.copy()
            l      = left_meter
            r      = right_meter
            clip   = clipping

        for i, tile in enumerate(self.tiles):
            tile.set_level(float(levels[i]))

        self.vu_left.set_level(l)
        self.vu_right.set_level(r)

        def fmt_db(v):
            return f"{to_db(v):+.1f} dB" if v > 1e-5 else "—"

        self.db_left_label.setText(f"L: {fmt_db(l)}")
        self.db_right_label.setText(f"R: {fmt_db(r)}")

        if running:
            if clip:
                self._set_status("limit", "Limiting")
            else:
                self._set_status("running", "Running")


# ==============================
# RUN
# ==============================

app = QtWidgets.QApplication(sys.argv)
window = RendererUI()
window.show()
sys.exit(app.exec_())
