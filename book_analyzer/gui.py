from __future__ import annotations

import json
import re
import sys
import tempfile
from pathlib import Path
from urllib.parse import parse_qs, urlparse

import gdown
import requests

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from PySide6.QtCore import Qt, QThread, QTimer, Signal
from PySide6.QtGui import QAction, QDragEnterEvent, QDropEvent
from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QDoubleSpinBox,
    QFileDialog,
    QFormLayout,
    QFrame,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMenu,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QSpinBox,
    QTextEdit,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

if __package__ in (None, ""):
    from book_analyzer.audio_scan import scan_folder
    from book_analyzer.library import Library, compute_book_id
    from book_analyzer.parsers import get_parser
    from book_analyzer.schema import ParseResult, Progress
else:
    from .audio_scan import scan_folder
    from .library import Library, compute_book_id
    from .parsers import get_parser
    from .schema import ParseResult, Progress

SUPPORTED_EXTS = {".txt", ".docx", ".epub", ".pdf"}
_DRIVE_HOSTS = {"drive.google.com", "docs.google.com"}
_DRIVE_ID_RE = re.compile(r"/(?:file/d|document/d|presentation/d|spreadsheets/d)/([\w-]{20,})")


# ────────────────────────────────── theme ──────────────────────────────────


THEME_QSS = """
* { color: #22262a; }
QMainWindow, QDialog { background-color: #edf0f2; }
QWidget { font-family: "Segoe UI Variable Display", "Segoe UI", sans-serif; font-size: 10pt; }

/* labels/inputs must not paint a background — they sit on white cards */
QLabel { background: transparent; }
QScrollArea, QScrollArea > QWidget > QWidget { background: transparent; }

QGroupBox {
    background-color: #ffffff;
    border: 1px solid #dbdee2;
    border-radius: 11px;
    margin-top: 18px;
    padding: 18px 16px 16px 16px;
}
QGroupBox::title {
    subcontrol-origin: margin;
    subcontrol-position: top left;
    left: 2px; top: 0px;
    padding: 0;
    color: #707378;
    font-size: 8.5pt;
    letter-spacing: 1.5px;
    background: transparent;
}

QLineEdit, QComboBox, QSpinBox, QDoubleSpinBox {
    background-color: #ffffff;
    border: 1px solid #c4c8cc;
    border-radius: 8px;
    padding: 6px 9px;
    selection-background-color: #395d85;
    selection-color: #ffffff;
}
QLineEdit:focus, QComboBox:focus, QSpinBox:focus, QDoubleSpinBox:focus {
    border: 1px solid #395d85;
}
QSpinBox#inlineNumber, QDoubleSpinBox#inlineNumber {
    border: none;
    background: transparent;
    border-bottom: 1px solid #dbdee2;
    border-radius: 0;
    padding: 2px 2px;
    font-family: "Cascadia Code", "Consolas", monospace;
    font-size: 14pt;
    font-weight: 600;
    color: #22262a;
}
QSpinBox#inlineNumber:focus, QDoubleSpinBox#inlineNumber:focus {
    border-bottom: 1px solid #395d85;
}
QComboBox::drop-down { border: none; width: 18px; }
QComboBox QAbstractItemView {
    background: #ffffff;
    border: 1px solid #dbdee2;
    selection-background-color: #f3f5f8;
    selection-color: #22262a;
    outline: none;
}

QPushButton {
    background-color: #ffffff;
    border: 1px solid #c4c8cc;
    border-radius: 8px;
    padding: 7px 14px;
    color: #22262a;
}
QPushButton:hover  { background-color: #f4f7f9; border-color: #707378; }
QPushButton:pressed { background-color: #e9ecef; }

QPushButton#primary {
    background-color: #395d85; color: #ffffff; border: 1px solid #395d85;
    font-weight: 600;
}
QPushButton#primary:hover { background-color: #28486c; border-color: #28486c; }
QPushButton#primary:pressed { background-color: #22406b; }

QPushButton#danger {
    background-color: #ffffff; color: #b4524a;
    border: 1px solid #e5cbc8;
}
QPushButton#danger:hover { background-color: #fbf4f3; border-color: #b4524a; }

QPushButton#ghost {
    background-color: transparent; border: 1px solid #dbdee2;
}
QPushButton#ghost:hover { background-color: #f4f7f9; }

QPushButton#bookSelector {
    background-color: transparent;
    border: none;
    text-align: left;
    padding: 4px 10px 4px 4px;
    font-size: 14pt;
    font-weight: 700;
    color: #22262a;
}
QPushButton#bookSelector:hover { color: #28486c; }
QPushButton#bookSelector::menu-indicator { image: none; width: 0; }

QToolButton {
    background: transparent; border: 1px solid #dbdee2; border-radius: 8px;
    padding: 6px 8px; color: #4a4d52;
}
QToolButton:hover { background-color: #f4f7f9; color: #22262a; }
QToolButton#iconOnly { border: none; padding: 4px; }
QToolButton#iconOnly:hover { background-color: #f4f7f9; }

QTextEdit {
    background-color: #ffffff;
    border: 1px solid #dbdee2;
    border-radius: 9px;
    selection-background-color: #395d85;
    selection-color: #ffffff;
    padding: 6px;
}

QLabel#statLabel, QLabel#chipLabel, QLabel#subBrand {
    color: #707378; font-size: 8.5pt;
    letter-spacing: 1.5px;
}
QLabel#statValue {
    color: #22262a;
    font-family: "Cascadia Code", "Consolas", "JetBrains Mono", monospace;
    font-size: 13pt;
    font-weight: 700;
}
QLabel#statValueAccent {
    color: #395d85;
    font-family: "Cascadia Code", "Consolas", monospace;
    font-size: 13pt;
    font-weight: 700;
}
QLabel#statValueDim {
    color: #707378;
    font-family: "Cascadia Code", "Consolas", monospace;
    font-size: 9.5pt;
}
QLabel#chipValue {
    color: #22262a;
    font-family: "Cascadia Code", "Consolas", monospace;
    font-size: 11pt;
    font-weight: 600;
}
QLabel#heroPercent {
    color: #22262a;
    font-family: "Cascadia Code", "Consolas", monospace;
    font-size: 26pt;
    font-weight: 700;
}
QLabel#heroPercentMark {
    color: #395d85;
    font-family: "Cascadia Code", "Consolas", monospace;
    font-size: 14pt;
    font-weight: 700;
}
QLabel#caption {
    color: #707378; font-size: 9.5pt;
}
QLabel#inlineLabel {
    color: #707378; font-size: 9pt;
    letter-spacing: 1px;
}
QLabel#dropHint {
    color: #8b8e92; font-size: 8.5pt; font-style: italic;
}

QFrame#divider { background-color: #dbdee2; max-height: 1px; }
QFrame#vDivider { background-color: #dbdee2; max-width: 1px; }
QFrame#statCell {
    background-color: #ffffff;
    border: 1px solid #dbdee2;
    border-radius: 9px;
}
QFrame#statCellHighlight {
    background-color: #f3f5f8;
    border: 1px solid #c9d3e0;
    border-radius: 9px;
}
QFrame#metaCell {
    background-color: #ffffff;
    border: 1px solid #dbdee2;
    border-radius: 9px;
}
QFrame#narratorCard {
    background-color: #ffffff;
    border: 1px solid #dbdee2;
    border-radius: 9px;
}
QFrame#narratorCardActive {
    background-color: #f3f5f8;
    border: 1px solid #395d85;
    border-radius: 9px;
}
QFrame#avatar {
    border-radius: 15px;
}

QProgressBar {
    background-color: #e9ecef;
    border: 1px solid #dbdee2;
    border-radius: 6px;
    height: 11px;
    text-align: center;
    color: transparent;
}
QProgressBar::chunk {
    background-color: #395d85;
    border-radius: 5px;
}
QProgressBar#thin { height: 5px; border-radius: 3px; }
QProgressBar#thin::chunk { border-radius: 3px; }

QCheckBox#switch {
    spacing: 8px;
}
QCheckBox#switch::indicator {
    width: 40px; height: 22px;
    border-radius: 11px;
    background-color: #c4c8cc;
    border: 1px solid #c4c8cc;
}
QCheckBox#switch::indicator:checked {
    background-color: #395d85;
    border-color: #395d85;
}

QStatusBar { background-color: #edf0f2; color: #8b8e92; border-top: 1px solid #dbdee2; }
QScrollBar:vertical { background: transparent; width: 10px; border: none; }
QScrollBar::handle:vertical { background: #c4c8cc; border-radius: 5px; min-height: 20px; }
QScrollBar::handle:vertical:hover { background: #707378; }
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0; }

QMenu {
    background-color: #ffffff;
    border: 1px solid #dbdee2;
    padding: 4px;
}
QMenu::item {
    padding: 7px 18px;
    border-radius: 6px;
}
QMenu::item:selected { background-color: #f3f5f8; }
QMenu::separator { height: 1px; background: #dbdee2; margin: 4px 6px; }
"""


# ──────────────────────────── helpers ────────────────────────────


def _extract_drive_id(url: str) -> str | None:
    parsed = urlparse(url)
    if parsed.netloc not in _DRIVE_HOSTS:
        return None
    m = _DRIVE_ID_RE.search(parsed.path)
    if m:
        return m.group(1)
    qs = parse_qs(parsed.query)
    if "id" in qs:
        return qs["id"][0]
    return None


def fmt_hm(hours: float) -> str:
    """Format hours as '19h 09m' (e.g. 19.15 → '19h 09m')."""
    if hours <= 0:
        return "—"
    h = int(hours)
    m = int(round((hours - h) * 60))
    if m == 60:
        h += 1
        m = 0
    return f"{h}h {m:02d}m"


def _short(s: str, n: int) -> str:
    return s if len(s) <= n else s[: n - 1] + "…"


# ──────────────────────────── workers ────────────────────────────


class ParseWorker(QThread):
    finished_ok = Signal(object, str)
    failed = Signal(str)
    progress = Signal(str)

    def __init__(self, source: str, library: Library) -> None:
        super().__init__()
        self.source = source
        self.library = library

    def run(self) -> None:
        try:
            path, label = self._resolve_source()
            self.progress.emit("Computing book id…")
            book_id = compute_book_id(path)
            if self.library.has_book(book_id):
                self.progress.emit("Loading cached metadata…")
                result = self.library.load_metadata(book_id)
                self.finished_ok.emit(result, label)
                return
            self.progress.emit(f"Parsing {path.name}…")
            parser = get_parser(path)
            result = parser.parse()
            result.book_metadata.book_id = book_id
            self.library.save_metadata(result)
            self.finished_ok.emit(result, label)
        except Exception as e:
            self.failed.emit(f"{type(e).__name__}: {e}")

    def _resolve_source(self) -> tuple[Path, str]:
        if self.source.startswith(("http://", "https://")):
            drive_id = _extract_drive_id(self.source)
            if drive_id:
                self.progress.emit("Downloading from Google Drive…")
                return self._download_drive(drive_id), self.source
            self.progress.emit("Downloading…")
            return self._download_http(self.source), self.source
        p = Path(self.source)
        if not p.exists():
            raise FileNotFoundError(self.source)
        return p, str(p)

    def _download_drive(self, file_id: str) -> Path:
        out_dir = Path(tempfile.gettempdir()) / "book_analyzer_drive"
        out_dir.mkdir(parents=True, exist_ok=True)
        for f in out_dir.iterdir():
            try:
                f.unlink()
            except OSError:
                pass
        result = gdown.download(id=file_id, output=str(out_dir) + "/", quiet=True)
        if not result:
            raise RuntimeError(
                "Google Drive download failed. Set sharing to 'Anyone with the link'."
            )
        path = Path(result)
        if path.suffix.lower() not in SUPPORTED_EXTS:
            raise ValueError(f"Downloaded extension {path.suffix!r} unsupported.")
        return path

    def _download_http(self, url: str) -> Path:
        parsed = urlparse(url)
        suffix = Path(parsed.path).suffix.lower() or ".bin"
        if suffix not in SUPPORTED_EXTS:
            raise ValueError(f"URL extension {suffix!r} not supported.")
        tmp = Path(tempfile.gettempdir()) / f"book_analyzer_dl{suffix}"
        with requests.get(url, stream=True, timeout=60) as r:
            r.raise_for_status()
            with open(tmp, "wb") as f:
                for chunk in r.iter_content(chunk_size=64 * 1024):
                    f.write(chunk)
        return tmp


class AudioScanWorker(QThread):
    finished_ok = Signal(float, int, list)
    failed = Signal(str)

    def __init__(self, folder: Path) -> None:
        super().__init__()
        self.folder = folder

    def run(self) -> None:
        try:
            total, count, errors = scan_folder(self.folder)
            self.finished_ok.emit(total, count, errors)
        except Exception as e:
            self.failed.emit(f"{type(e).__name__}: {e}")


# ──────────────────────────── new-book dialog ────────────────────────────


class NewBookDialog(QDialog):
    def __init__(self, library: Library, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.library = library
        self.setWindowTitle("New book")
        self.setModal(True)
        self.setMinimumWidth(540)

        root = QVBoxLayout(self)
        root.setContentsMargins(22, 20, 22, 16)
        root.setSpacing(16)

        title = QLabel("Add a new book")
        title.setStyleSheet("font-size: 16pt; font-weight: 700; color: #22262a;")
        sub = QLabel("source · narrator · audio")
        sub.setObjectName("subBrand")
        root.addWidget(title)
        root.addWidget(sub)

        div = QFrame(); div.setObjectName("divider"); div.setFixedHeight(1)
        root.addWidget(div)

        form = QFormLayout()
        form.setSpacing(10)

        # source
        src_row = QHBoxLayout()
        self.source_edit = QLineEdit()
        self.source_edit.setPlaceholderText("Local path, https://… , or Google Drive link")
        src_browse = QPushButton("Browse")
        src_browse.clicked.connect(self.on_source_browse)
        src_row.addWidget(self.source_edit, 1)
        src_row.addWidget(src_browse)
        form.addRow("Source", _wrap(src_row))

        # narrator
        nar_box = QVBoxLayout()
        nar_box.setSpacing(3)
        self.narrator_combo = QComboBox()
        self.narrator_combo.setEditable(True)
        existing = self.library.list_narrators()
        for n in existing:
            label = n["name"]
            if n["book_count"]:
                label += f"   — {n['avg_chars_per_hour']:,.0f} c/h × {n['book_count']}"
            self.narrator_combo.addItem(label, userData=n["name"])
        self.narrator_combo.setEditText("")
        self.narrator_combo.setMinimumWidth(280)
        nar_box.addWidget(self.narrator_combo)
        if existing:
            hint = QLabel(f"{len(existing)} narrator(s) on file — pick from list, "
                         f"or type a new name")
            hint.setObjectName("caption")
            nar_box.addWidget(hint)
        else:
            hint = QLabel("No narrators yet — type a name to start one")
            hint.setObjectName("caption")
            nar_box.addWidget(hint)
        form.addRow("Narrator", _wrap(nar_box))

        # audio folder
        audio_row = QHBoxLayout()
        self.audio_edit = QLineEdit()
        self.audio_edit.setPlaceholderText("Optional — folder of recordings to sum")
        audio_browse = QPushButton("Browse")
        audio_browse.clicked.connect(self.on_audio_browse)
        audio_row.addWidget(self.audio_edit, 1)
        audio_row.addWidget(audio_browse)
        form.addRow("Audio folder", _wrap(audio_row))

        root.addLayout(form)
        root.addStretch(1)

        buttons = QDialogButtonBox(QDialogButtonBox.Cancel)
        self.create_btn = QPushButton("Add book")
        self.create_btn.setObjectName("primary")
        self.create_btn.setDefault(True)
        self.create_btn.clicked.connect(self.accept)
        buttons.addButton(self.create_btn, QDialogButtonBox.AcceptRole)
        buttons.rejected.connect(self.reject)
        root.addWidget(buttons)

    def on_source_browse(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self, "Select book", "", "Books (*.txt *.docx *.epub *.pdf);;All (*.*)"
        )
        if path:
            self.source_edit.setText(path)

    def on_audio_browse(self) -> None:
        folder = QFileDialog.getExistingDirectory(
            self, "Select audio folder", "", QFileDialog.ShowDirsOnly
        )
        if folder:
            self.audio_edit.setText(folder)

    def get_values(self) -> dict:
        idx = self.narrator_combo.currentIndex()
        if idx >= 0 and self.narrator_combo.itemData(idx) and \
           self.narrator_combo.itemText(idx) == self.narrator_combo.currentText():
            narrator = self.narrator_combo.itemData(idx)
        else:
            narrator = self.narrator_combo.currentText().strip()
        return {
            "source": self.source_edit.text().strip(),
            "narrator": narrator,
            "audio_folder": self.audio_edit.text().strip(),
        }

    def accept(self) -> None:
        if not self.source_edit.text().strip():
            QMessageBox.warning(self, "Source required", "Pick a file or paste a URL.")
            return
        super().accept()


# ──────────────────────────── settings dialog ────────────────────────────


class BookSettingsDialog(QDialog):
    """Gear-button modal: active narrator + audio folder + auto-scan."""

    def __init__(self, library: Library, progress: Progress,
                 parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.library = library
        self.progress = progress
        self.setWindowTitle("Book settings")
        self.setModal(True)
        self.setMinimumWidth(480)

        root = QVBoxLayout(self)
        root.setContentsMargins(20, 18, 20, 14)
        root.setSpacing(18)

        title = QLabel("⚙  Book settings")
        title.setStyleSheet("font-size: 14pt; font-weight: 700; color: #22262a;")
        root.addWidget(title)

        # ── Active narrator ──
        nar_label = QLabel("ACTIVE NARRATOR")
        nar_label.setObjectName("statLabel")
        root.addWidget(nar_label)
        self.narrator_combo = QComboBox()
        self.narrator_combo.setEditable(True)
        for n in library.list_narrators():
            label = n["name"]
            if n["book_count"]:
                label += f"   — {n['avg_chars_per_hour']:,.0f} c/h × {n['book_count']}"
            self.narrator_combo.addItem(label, userData=n["name"])
        self.narrator_combo.setEditText(progress.narrator)
        root.addWidget(self.narrator_combo)
        hint = QLabel("Who is recording right now. Add or edit narrators from the Book panel.")
        hint.setObjectName("caption")
        hint.setWordWrap(True)
        root.addWidget(hint)

        # ── Audio folder ──
        af_label = QLabel("AUDIO FOLDER")
        af_label.setObjectName("statLabel")
        root.addWidget(af_label)
        af_row = QHBoxLayout()
        self.folder_edit = QLineEdit(progress.audio_folder)
        self.folder_edit.setStyleSheet("font-family: Consolas, monospace;")
        browse = QPushButton("Browse…")
        browse.clicked.connect(self.on_browse)
        af_row.addWidget(self.folder_edit, 1)
        af_row.addWidget(browse)
        root.addLayout(af_row)
        hint2 = QLabel("Recorded files here are scanned to total your audio hours.")
        hint2.setObjectName("caption")
        hint2.setWordWrap(True)
        root.addWidget(hint2)

        # ── Auto-scan toggle ──
        self.auto_scan = QCheckBox("Auto-scan on open")
        self.auto_scan.setObjectName("switch")
        self.auto_scan.setChecked(progress.auto_scan)
        root.addWidget(self.auto_scan)
        hint3 = QLabel("Re-scan the audio folder each time this book is opened.")
        hint3.setObjectName("caption")
        hint3.setWordWrap(True)
        root.addWidget(hint3)

        root.addStretch(1)

        # footer
        div = QFrame(); div.setObjectName("divider"); div.setFixedHeight(1)
        root.addWidget(div)
        btn_row = QHBoxLayout()
        cancel = QPushButton("Cancel")
        cancel.clicked.connect(self.reject)
        save = QPushButton("Save settings")
        save.setObjectName("primary")
        save.setDefault(True)
        save.clicked.connect(self.accept)
        btn_row.addStretch(1)
        btn_row.addWidget(cancel)
        btn_row.addWidget(save)
        root.addLayout(btn_row)

    def on_browse(self) -> None:
        folder = QFileDialog.getExistingDirectory(
            self, "Select audio folder", self.folder_edit.text() or "",
            QFileDialog.ShowDirsOnly,
        )
        if folder:
            self.folder_edit.setText(folder)

    def get_values(self) -> dict:
        idx = self.narrator_combo.currentIndex()
        if idx >= 0 and self.narrator_combo.itemData(idx) and \
           self.narrator_combo.itemText(idx) == self.narrator_combo.currentText():
            narrator = self.narrator_combo.itemData(idx)
        else:
            narrator = self.narrator_combo.currentText().strip()
        return {
            "narrator": narrator,
            "audio_folder": self.folder_edit.text().strip(),
            "auto_scan": self.auto_scan.isChecked(),
        }


# ──────────────────────────── small UI helpers ────────────────────────────


def _wrap(layout) -> QWidget:
    w = QWidget()
    w.setLayout(layout)
    layout.setContentsMargins(0, 0, 0, 0)
    return w


def make_stat_cell(label: str, highlight: bool = False, dot_color: str = "#9c9fa2"
                   ) -> tuple[QFrame, QLabel, QLabel]:
    f = QFrame()
    f.setObjectName("statCellHighlight" if highlight else "statCell")
    v = QVBoxLayout(f)
    v.setContentsMargins(13, 11, 13, 11)
    v.setSpacing(4)
    head = QHBoxLayout()
    head.setSpacing(6)
    dot = QLabel("●")
    dot.setStyleSheet(f"color: {dot_color}; font-size: 9pt;")
    head.addWidget(dot)
    lbl = QLabel(label.upper())
    lbl.setObjectName("statLabel")
    head.addWidget(lbl)
    head.addStretch(1)
    v.addLayout(head)
    primary = QLabel("—")
    primary.setObjectName("statValueAccent" if highlight else "statValue")
    v.addWidget(primary)
    secondary = QLabel("")
    secondary.setObjectName("statValueDim")
    v.addWidget(secondary)
    return f, primary, secondary


def make_meta_cell(label: str, value: str = "—") -> tuple[QFrame, QLabel]:
    f = QFrame()
    f.setObjectName("metaCell")
    v = QVBoxLayout(f)
    v.setContentsMargins(11, 9, 11, 9)
    v.setSpacing(3)
    lbl = QLabel(label.upper())
    lbl.setObjectName("statLabel")
    val = QLabel(value)
    val.setObjectName("chipValue")
    val.setWordWrap(True)
    v.addWidget(lbl)
    v.addWidget(val)
    return f, val


# ──────────────────────────── narrator card ────────────────────────────


class NarratorCard(QFrame):
    """Card representing the active narrator with edit / remove inline."""

    narrator_changed = Signal(str)
    remove_requested = Signal()
    mark_complete_requested = Signal()

    def __init__(self, library: Library, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.library = library
        self.name = ""
        self.pages_done = 0
        self.pages_total = 0
        self.chars_narrated = 0
        self.tempo = 0.0
        self.percent = 0.0
        self.active = True
        self._editing = False
        self.setObjectName("narratorCardActive")
        self._build()

    def _build(self) -> None:
        self.layout_v = QVBoxLayout(self)
        self.layout_v.setContentsMargins(13, 11, 13, 11)
        self.layout_v.setSpacing(8)
        self._build_view_mode()

    def _build_view_mode(self) -> None:
        # clear
        while self.layout_v.count():
            item = self.layout_v.takeAt(0)
            w = item.widget()
            if w:
                w.deleteLater()
            else:
                lay = item.layout()
                if lay:
                    self._clear_layout(lay)

        # Top row
        top = QHBoxLayout()
        top.setSpacing(10)
        # Avatar
        self.avatar = QLabel()
        self.avatar.setObjectName("avatar")
        self.avatar.setFixedSize(30, 30)
        self.avatar.setAlignment(Qt.AlignCenter)
        self._refresh_avatar()
        top.addWidget(self.avatar)

        name_block = QVBoxLayout()
        name_block.setSpacing(2)
        row1 = QHBoxLayout()
        row1.setSpacing(8)
        self.name_lbl = QLabel(self.name or "(no narrator)")
        self.name_lbl.setStyleSheet("font-size: 11pt; font-weight: 700; color: #22262a;")
        row1.addWidget(self.name_lbl)
        self.status_chip = QLabel("recording")
        self.status_chip.setStyleSheet(
            "background-color: #f3f5f8; color: #395d85; "
            "padding: 2px 8px; border-radius: 8px; font-size: 8.5pt; letter-spacing: 0.5px;"
        )
        row1.addWidget(self.status_chip)
        row1.addStretch(1)
        name_block.addLayout(row1)
        self.sub_lbl = QLabel("")
        self.sub_lbl.setStyleSheet(
            "font-family: Consolas, monospace; color: #707378; font-size: 9pt;"
        )
        name_block.addWidget(self.sub_lbl)
        top.addLayout(name_block, 1)

        self.percent_lbl = QLabel("—")
        self.percent_lbl.setStyleSheet(
            "color: #395d85; font-weight: 700; font-size: 12pt; "
            "font-family: Consolas, monospace;"
        )
        top.addWidget(self.percent_lbl)
        self.mark_complete_btn = QPushButton("✓ Mark complete")
        self.mark_complete_btn.setObjectName("ghost")
        self.mark_complete_btn.setToolTip(
            "Lock current audio hours as final, compute chars/hour, "
            "save under this narrator's history."
        )
        self.mark_complete_btn.clicked.connect(
            lambda: self.mark_complete_requested.emit()
        )
        top.addWidget(self.mark_complete_btn)
        self.edit_btn = QToolButton()
        self.edit_btn.setText("✎")
        self.edit_btn.setObjectName("iconOnly")
        self.edit_btn.clicked.connect(self._enter_edit)
        top.addWidget(self.edit_btn)
        self.layout_v.addLayout(top)

        # Stats row
        stats_row = QHBoxLayout()
        stats_row.setSpacing(16)
        for label, key in [
            ("Pages done", "pages"),
            ("Chars narrated", "chars"),
            ("Tempo", "tempo"),
        ]:
            col = QVBoxLayout()
            col.setSpacing(2)
            lbl = QLabel(label.upper())
            lbl.setObjectName("statLabel")
            val = QLabel("—")
            val.setStyleSheet(
                "font-family: Consolas, monospace; font-size: 10.5pt; "
                "font-weight: 600; color: #22262a;"
            )
            col.addWidget(lbl)
            col.addWidget(val)
            stats_row.addLayout(col, 1)
            setattr(self, f"_stat_{key}", val)
        self.layout_v.addLayout(stats_row)

        # Progress bar
        self.bar = QProgressBar()
        self.bar.setObjectName("thin")
        self.bar.setRange(0, 1000)
        self.bar.setValue(0)
        self.bar.setTextVisible(False)
        self.layout_v.addWidget(self.bar)

        self._editing = False
        self.refresh()

    def _enter_edit(self) -> None:
        # Clear and rebuild as edit form
        while self.layout_v.count():
            item = self.layout_v.takeAt(0)
            w = item.widget()
            if w:
                w.deleteLater()
            else:
                lay = item.layout()
                if lay:
                    self._clear_layout(lay)

        lbl = QLabel("EDIT NARRATOR")
        lbl.setObjectName("statLabel")
        self.layout_v.addWidget(lbl)
        self.name_edit = QLineEdit(self.name)
        self.name_edit.setPlaceholderText("Narrator name")
        self.layout_v.addWidget(self.name_edit)

        # autocomplete combo for picking existing
        existing_row = QHBoxLayout()
        existing_label = QLabel("Pick existing:")
        existing_label.setObjectName("caption")
        existing_row.addWidget(existing_label)
        self.existing_combo = QComboBox()
        self.existing_combo.addItem("— choose —", userData="")
        for n in self.library.list_narrators():
            self.existing_combo.addItem(
                f"{n['name']}  ({n['avg_chars_per_hour']:,.0f} c/h × {n['book_count']})",
                userData=n["name"],
            )
        self.existing_combo.currentIndexChanged.connect(self._on_pick_existing)
        existing_row.addWidget(self.existing_combo, 1)
        self.layout_v.addLayout(existing_row)

        # action row
        actions = QHBoxLayout()
        cancel = QPushButton("Cancel")
        cancel.clicked.connect(self._build_view_mode)
        save = QPushButton("Save")
        save.setObjectName("primary")
        save.clicked.connect(self._save_edit)
        remove = QToolButton()
        remove.setText("🗑")
        remove.setObjectName("iconOnly")
        remove.setToolTip("Remove narrator from this book")
        remove.clicked.connect(self._on_remove)
        actions.addWidget(remove)
        actions.addStretch(1)
        actions.addWidget(cancel)
        actions.addWidget(save)
        self.layout_v.addLayout(actions)

        self._editing = True
        self.name_edit.setFocus()

    def _on_pick_existing(self, idx: int) -> None:
        if idx <= 0:
            return
        name = self.existing_combo.itemData(idx)
        if name:
            self.name_edit.setText(name)

    def _save_edit(self) -> None:
        new_name = self.name_edit.text().strip()
        self.name = new_name
        self._build_view_mode()
        self.narrator_changed.emit(new_name)

    def _on_remove(self) -> None:
        self.name = ""
        self._build_view_mode()
        self.remove_requested.emit()

    @staticmethod
    def _clear_layout(layout) -> None:
        while layout.count():
            item = layout.takeAt(0)
            w = item.widget()
            if w:
                w.deleteLater()
            else:
                inner = item.layout()
                if inner:
                    NarratorCard._clear_layout(inner)

    def _refresh_avatar(self) -> None:
        initial = (self.name[:1] or "?").upper()
        color = "#395d85" if self.active else "#707378"
        self.avatar.setText(initial)
        self.avatar.setStyleSheet(
            f"background-color: {color}; color: #ffffff; "
            f"font-weight: 700; font-size: 12pt; "
            f"border-radius: 15px; min-width: 30px; max-width: 30px;"
            f"min-height: 30px; max-height: 30px;"
        )

    def set_data(self, name: str, pages_done: int, pages_total: int,
                 chars_narrated: int, tempo: float, percent: float) -> None:
        self.name = name or ""
        self.pages_done = pages_done
        self.pages_total = pages_total
        self.chars_narrated = chars_narrated
        self.tempo = tempo
        self.percent = percent
        if not self._editing:
            self.refresh()

    def refresh(self) -> None:
        if self._editing:
            return
        if not hasattr(self, "name_lbl"):
            return
        self.name_lbl.setText(self.name or "(no narrator)")
        self._refresh_avatar()
        # only show the complete button when a narrator is set
        if hasattr(self, "mark_complete_btn"):
            self.mark_complete_btn.setVisible(bool(self.name))
        if self.pages_total:
            self.sub_lbl.setText(
                f"pages 1–{self.pages_total} · {self.pages_total} pp assigned"
            )
        else:
            self.sub_lbl.setText("")
        self.percent_lbl.setText(f"{self.percent:.1f}%" if self.pages_total else "—")
        self._stat_pages.setText(
            f"{self.pages_done} / {self.pages_total}" if self.pages_total else "—"
        )
        self._stat_chars.setText(f"{self.chars_narrated:,}")
        self._stat_tempo.setText(f"{self.tempo:,.0f} ch/h" if self.tempo else "—")
        self.bar.setValue(int(self.percent * 10))


# ──────────────────────────── main window ────────────────────────────


class MainWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("Book Analyzer")
        self.resize(1080, 720)
        self.setMinimumSize(640, 420)
        self.setAcceptDrops(True)
        self.result: ParseResult | None = None
        self.parse_worker: ParseWorker | None = None
        self.audio_worker: AudioScanWorker | None = None
        self.library = Library()
        self.progress_state: Progress | None = None
        self._pending_audio_folder: str | None = None
        self._narrator_to_set: str | None = None

        self._save_timer = QTimer(self)
        self._save_timer.setSingleShot(True)
        self._save_timer.setInterval(500)
        self._save_timer.timeout.connect(self._flush_progress)

        # central holds a fixed top bar + a scroll area for the rest, so the
        # window can shrink freely vertically and content scrolls.
        central = QWidget()
        self.setCentralWidget(central)
        outer = QVBoxLayout(central)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        topbar_host = QWidget()
        root_top = QVBoxLayout(topbar_host)
        root_top.setContentsMargins(22, 10, 22, 8)
        root_top.setSpacing(8)

        body_host = QWidget()
        root = QVBoxLayout(body_host)
        root.setContentsMargins(22, 6, 22, 12)
        root.setSpacing(10)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        scroll.setWidget(body_host)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        outer.addWidget(topbar_host)
        outer.addWidget(scroll, 1)

        # ── Top bar ──
        topbar = QHBoxLayout()
        topbar.setSpacing(8)
        self.book_selector = QPushButton("Select a book   ▾")
        self.book_selector.setObjectName("bookSelector")
        self.book_menu = QMenu(self.book_selector)
        self.book_selector.setMenu(self.book_menu)
        topbar.addWidget(self.book_selector)
        topbar.addStretch(1)

        self.settings_btn = QToolButton()
        self.settings_btn.setText("⚙")
        self.settings_btn.setToolTip("Book settings")
        self.settings_btn.clicked.connect(self.on_open_settings)
        topbar.addWidget(self.settings_btn)

        self.new_book_btn = QPushButton("＋  New book")
        self.new_book_btn.setObjectName("primary")
        self.new_book_btn.clicked.connect(self.on_new_book)
        topbar.addWidget(self.new_book_btn)
        root_top.addLayout(topbar)

        div = QFrame(); div.setObjectName("divider"); div.setFixedHeight(1)
        root_top.addWidget(div)

        # ── Hero: Audiobook progress card ──
        self.hero = QGroupBox("AUDIOBOOK PROGRESS")
        self.hero.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Maximum)
        hl = QVBoxLayout(self.hero)
        hl.setContentsMargins(2, 2, 2, 2)
        hl.setSpacing(10)

        # Row A
        rowA = QHBoxLayout()
        rowA.setSpacing(18)
        # Left: caption + big percent
        left_col = QVBoxLayout()
        left_col.setSpacing(2)
        cap = QLabel("NARRATED")
        cap.setObjectName("statLabel")
        left_col.addWidget(cap)
        pct_row = QHBoxLayout()
        pct_row.setSpacing(2)
        pct_row.setAlignment(Qt.AlignBottom)
        self.hero_pct = QLabel("—")
        self.hero_pct.setObjectName("heroPercent")
        pct_row.addWidget(self.hero_pct)
        self.hero_pct_mark = QLabel("%")
        self.hero_pct_mark.setObjectName("heroPercentMark")
        pct_row.addWidget(self.hero_pct_mark)
        pct_row.addStretch(1)
        left_col.addLayout(pct_row)
        rowA.addLayout(left_col)
        rowA.addStretch(1)

        # Right: inline editors
        ed_row = QHBoxLayout()
        ed_row.setSpacing(14)
        # Page
        pg_block = QVBoxLayout()
        pg_block.setSpacing(2)
        pg_lbl = QLabel("PAGE")
        pg_lbl.setObjectName("inlineLabel")
        pg_block.addWidget(pg_lbl)
        pg_h = QHBoxLayout()
        pg_h.setSpacing(6)
        self.page_spin = QSpinBox()
        self.page_spin.setObjectName("inlineNumber")
        self.page_spin.setRange(0, 100_000)
        self.page_spin.setFixedWidth(90)
        self.page_spin.setButtonSymbols(QSpinBox.NoButtons)
        self.page_spin.valueChanged.connect(self.on_progress_changed)
        pg_h.addWidget(self.page_spin)
        self.page_max_lbl = QLabel("/ —")
        self.page_max_lbl.setStyleSheet(
            "color:#707378; font-family: Consolas, monospace; font-size: 13pt;"
        )
        pg_h.addWidget(self.page_max_lbl)
        pg_block.addLayout(pg_h)
        ed_row.addLayout(pg_block)

        vsep = QFrame(); vsep.setFrameShape(QFrame.VLine); vsep.setObjectName("vDivider")
        ed_row.addWidget(vsep)

        # Audio
        ah_block = QVBoxLayout()
        ah_block.setSpacing(2)
        ah_lbl = QLabel("RECORDED (h)")
        ah_lbl.setObjectName("inlineLabel")
        ah_block.addWidget(ah_lbl)
        ah_h = QHBoxLayout()
        ah_h.setSpacing(6)
        self.audio_spin = QDoubleSpinBox()
        self.audio_spin.setObjectName("inlineNumber")
        self.audio_spin.setRange(0, 10_000)
        self.audio_spin.setDecimals(2)
        self.audio_spin.setSingleStep(0.25)
        self.audio_spin.setFixedWidth(100)
        self.audio_spin.setButtonSymbols(QDoubleSpinBox.NoButtons)
        self.audio_spin.valueChanged.connect(self.on_progress_changed)
        ah_h.addWidget(self.audio_spin)
        self.audio_browse_btn = QToolButton()
        self.audio_browse_btn.setText("📁")
        self.audio_browse_btn.setObjectName("iconOnly")
        self.audio_browse_btn.setToolTip("Scan folder for audio duration")
        self.audio_browse_btn.clicked.connect(self.on_audio_browse)
        ah_h.addWidget(self.audio_browse_btn)
        ah_block.addLayout(ah_h)
        ed_row.addLayout(ah_block)

        rowA.addLayout(ed_row)
        hl.addLayout(rowA)

        # Row B: progress bar
        self.hero_bar = QProgressBar()
        self.hero_bar.setRange(0, 1000)
        self.hero_bar.setValue(0)
        self.hero_bar.setTextVisible(False)
        hl.addWidget(self.hero_bar)

        # Row C: stat grid (4 cells)
        self.stat_grid = QGridLayout()
        self.stat_grid.setHorizontalSpacing(1)
        self.stat_grid.setVerticalSpacing(0)
        self.cell_recorded, self.rec_val, self.rec_sub = make_stat_cell(
            "Recorded", dot_color="#395d85"
        )
        self.cell_remaining, self.rem_val, self.rem_sub = make_stat_cell(
            "Remaining", highlight=True, dot_color="#9c9fa2"
        )
        self.cell_tempo, self.tempo_val, self.tempo_sub = make_stat_cell(
            "Tempo", dot_color="#395d85"
        )
        self.cell_eta, self.eta_val, self.eta_sub = make_stat_cell(
            "Est. total", dot_color="#9c9fa2"
        )
        self.stat_grid.addWidget(self.cell_recorded, 0, 0)
        self.stat_grid.addWidget(self.cell_remaining, 0, 1)
        self.stat_grid.addWidget(self.cell_tempo, 0, 2)
        self.stat_grid.addWidget(self.cell_eta, 0, 3)
        for i in range(4):
            self.stat_grid.setColumnStretch(i, 1)
        hl.addLayout(self.stat_grid)

        self.hero.setEnabled(False)
        root.addWidget(self.hero)

        # ── Book & file details ──
        self.book_box = QGroupBox("BOOK && FILE DETAILS")
        self.book_box.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Maximum)
        bbl = QVBoxLayout(self.book_box)
        bbl.setContentsMargins(2, 2, 2, 2)
        bbl.setSpacing(8)

        head_row = QHBoxLayout()
        self.book_file_lbl = QLabel("—")
        self.book_file_lbl.setObjectName("caption")
        head_row.addWidget(self.book_file_lbl)
        head_row.addStretch(1)
        self.lib_delete_btn = QPushButton("🗑  Remove book")
        self.lib_delete_btn.setObjectName("danger")
        self.lib_delete_btn.setToolTip("Remove this book from your library")
        self.lib_delete_btn.clicked.connect(self.on_library_delete)
        head_row.addWidget(self.lib_delete_btn, 0, Qt.AlignTop)
        bbl.addLayout(head_row)

        # Meta grid (3 columns × variable rows for now; collapse-aware)
        meta_grid = QGridLayout()
        meta_grid.setHorizontalSpacing(1)
        meta_grid.setVerticalSpacing(1)
        self.meta_cells: dict[str, QLabel] = {}
        cells_spec = [
            ("file", "File", 0, 0, 1, 2),
            ("format", "Format", 0, 2, 1, 1),
            ("pages", "Pages", 0, 3, 1, 1),
            ("images", "Images", 0, 4, 1, 1),
            ("tables", "Tables", 0, 5, 1, 1),
            ("body", "Body chars", 1, 0, 1, 2),
            ("raw", "Raw chars", 1, 2, 1, 2),
            ("perpage", "Chars / page", 1, 4, 1, 2),
        ]
        for key, label, r, c, rs, cs in cells_spec:
            frame, val_lbl = make_meta_cell(label)
            self.meta_cells[key] = val_lbl
            meta_grid.addWidget(frame, r, c, rs, cs)
        for i in range(6):
            meta_grid.setColumnStretch(i, 1)
        bbl.addLayout(meta_grid)

        # Visual elements compact
        self.visual_label = QLabel("VISUAL ELEMENTS")
        self.visual_label.setObjectName("statLabel")
        bbl.addWidget(self.visual_label)
        self.elements_view = QTextEdit()
        self.elements_view.setReadOnly(True)
        self.elements_view.setMaximumHeight(110)
        self.elements_view.setMinimumHeight(40)
        bbl.addWidget(self.elements_view)

        # Narration sub-block (separator + header + card)
        n_div = QFrame(); n_div.setObjectName("divider"); n_div.setFixedHeight(1)
        bbl.addWidget(n_div)

        n_head = QHBoxLayout()
        self.narration_label = QLabel("NARRATION · 0 NARRATORS ON THIS BOOK")
        self.narration_label.setObjectName("statLabel")
        n_head.addWidget(self.narration_label)
        n_head.addStretch(1)
        self.add_narrator_btn = QPushButton("＋  Add narrator")
        self.add_narrator_btn.setObjectName("ghost")
        self.add_narrator_btn.clicked.connect(self.on_add_narrator)
        n_head.addWidget(self.add_narrator_btn)
        bbl.addLayout(n_head)

        self.narrator_card = NarratorCard(self.library)
        self.narrator_card.narrator_changed.connect(self.on_narrator_card_changed)
        self.narrator_card.remove_requested.connect(self.on_narrator_card_remove)
        self.narrator_card.mark_complete_requested.connect(self.on_mark_complete)
        bbl.addWidget(self.narrator_card)

        root.addWidget(self.book_box)
        root.addStretch(1)

        # ── Drop hint (in status bar area) ──
        drop_hint = QLabel("drop a .txt / .docx / .epub / .pdf anywhere on this window")
        drop_hint.setObjectName("dropHint")
        drop_hint.setAlignment(Qt.AlignCenter)
        root.addWidget(drop_hint)

        self.statusBar().showMessage("Ready")
        self.setStyleSheet(THEME_QSS)
        self.refresh_library()

    # ────────────────── drag & drop ──────────────────

    def dragEnterEvent(self, event: QDragEnterEvent) -> None:
        if event.mimeData().hasUrls():
            event.acceptProposedAction()

    def dropEvent(self, event: QDropEvent) -> None:
        urls = event.mimeData().urls()
        if not urls:
            return
        local = urls[0].toLocalFile()
        if local:
            self.analyze_source(local)

    # ────────────────── top-bar actions ──────────────────

    def on_new_book(self) -> None:
        dlg = NewBookDialog(self.library, self)
        if dlg.exec() != QDialog.Accepted:
            return
        vals = dlg.get_values()
        if vals["narrator"]:
            self.library.ensure_narrator(vals["narrator"])
        self._pending_audio_folder = vals["audio_folder"] or None
        self._narrator_to_set = vals["narrator"] or None
        self.analyze_source(vals["source"])

    def on_open_settings(self) -> None:
        if not self.result or not self.progress_state:
            QMessageBox.information(self, "No book", "Load a book first.")
            return
        dlg = BookSettingsDialog(self.library, self.progress_state, self)
        if dlg.exec() != QDialog.Accepted:
            return
        vals = dlg.get_values()
        if vals["narrator"]:
            self.library.ensure_narrator(vals["narrator"])
        self.progress_state.narrator = vals["narrator"]
        self.progress_state.audio_folder = vals["audio_folder"]
        self.progress_state.auto_scan = vals["auto_scan"]
        self._flush_progress()
        self.update_narrator_card()
        if vals["audio_folder"] and vals["auto_scan"]:
            self._launch_audio_scan(Path(vals["audio_folder"]))

    def analyze_source(self, src: str) -> None:
        if self.parse_worker and self.parse_worker.isRunning():
            return
        self.new_book_btn.setEnabled(False)
        self.statusBar().showMessage("Working…")
        self.parse_worker = ParseWorker(src, self.library)
        self.parse_worker.progress.connect(self.statusBar().showMessage)
        self.parse_worker.finished_ok.connect(self.on_parse_finished)
        self.parse_worker.failed.connect(self.on_parse_failed)
        self.parse_worker.start()

    def on_parse_finished(self, result: ParseResult, label: str) -> None:
        self.result = result
        self.new_book_btn.setEnabled(True)
        self.statusBar().showMessage(f"Loaded: {label}")
        self.render_metadata(result)
        self.render_elements(result)
        self.load_progress_for_current()
        self.refresh_library(select_id=result.book_metadata.book_id)
        if self._narrator_to_set:
            if self.progress_state:
                self.progress_state.narrator = self._narrator_to_set
                self._flush_progress()
                self.update_narrator_card()
            self._narrator_to_set = None
        if self._pending_audio_folder:
            folder = self._pending_audio_folder
            self._pending_audio_folder = None
            if self.progress_state:
                self.progress_state.audio_folder = folder
                self._flush_progress()
            self._launch_audio_scan(Path(folder))
        elif self.progress_state and self.progress_state.auto_scan and \
             self.progress_state.audio_folder:
            self._launch_audio_scan(Path(self.progress_state.audio_folder))

    def on_parse_failed(self, msg: str) -> None:
        self.new_book_btn.setEnabled(True)
        self.statusBar().showMessage("Failed.")
        QMessageBox.critical(self, "Parse error", msg)

    # ────────────────── rendering ──────────────────

    def render_metadata(self, result: ParseResult) -> None:
        m = result.book_metadata
        self.meta_cells["file"].setText(m.file_name)
        self.book_file_lbl.setText(m.file_name)
        self.meta_cells["format"].setText(m.file_format.upper())
        self.meta_cells["pages"].setText(str(m.total_pages) if m.total_pages else "—")
        self.meta_cells["images"].setText(str(m.total_images))
        self.meta_cells["tables"].setText(str(m.total_tables))
        self.meta_cells["body"].setText(f"{m.body_character_count:,}")
        self.meta_cells["raw"].setText(f"{m.raw_character_count:,}")
        if m.total_pages:
            per_page = m.body_character_count // m.total_pages
            self.meta_cells["perpage"].setText(f"{per_page:,}")
        else:
            self.meta_cells["perpage"].setText("—")
        # Book selector text
        self.book_selector.setText(f"{_short(m.file_name, 48)}   ▾")

    def render_elements(self, result: ParseResult) -> None:
        m = result.book_metadata
        n_img, n_tbl = m.total_images, m.total_tables
        if not result.visual_elements:
            self.visual_label.setText("VISUAL ELEMENTS")
            self.elements_view.setHtml(
                "<div style='color:#8b8e92;font-style:italic;padding:6px;font-size:9.5pt'>"
                "no images, tables, or charts detected</div>"
            )
            return
        self.visual_label.setText(
            f"VISUAL ELEMENTS · {n_img} IMAGE{'S' if n_img!=1 else ''}, "
            f"{n_tbl} TABLE{'S' if n_tbl!=1 else ''}"
        )
        total_pages = m.total_pages
        body = max(m.body_character_count, 1)
        rows = ["<div style='font-family:Segoe UI,sans-serif;font-size:9.5pt'>"]
        for ve in result.visual_elements:
            loc = ve.location
            label = ve.element_type.upper()
            if loc.page and total_pages:
                pct = loc.page / total_pages * 100
                where = (
                    f"<span style='color:#395d85;font-family:Consolas,monospace'>"
                    f"p. {loc.page}</span> "
                    f"<span style='color:#707378'>/ {total_pages} · {pct:.0f}% in</span>"
                )
            elif loc.page:
                where = f"<span style='color:#395d85'>p. {loc.page}</span>"
            else:
                pct = ve.global_character_offset / body * 100
                where = f"<span style='color:#395d85'>{pct:.0f}%</span>"
            chip = (
                f"<span style='background:#f3f5f8;color:#395d85;"
                f"padding:1px 6px;border-radius:6px;font-size:8.5pt'>{label}</span>"
            )
            ctx = ""
            if ve.context_before or ve.context_after:
                ca = (ve.context_after or "").replace("<", "&lt;")[:80]
                cb = (ve.context_before or "").replace("<", "&lt;")[-30:]
                ctx = (
                    f"<div style='color:#8b8e92;margin:1px 0 6px 0;font-size:8.5pt;font-style:italic'>"
                    f"…{cb} {ca}…</div>"
                )
            rows.append(
                f"<div style='margin:4px 0'>"
                f"{chip} <b style='color:#22262a'>{ve.element_type.capitalize()} #{ve.id}</b> "
                f"<span style='color:#9c9fa2'>·</span> {where} "
                f"<span style='color:#9c9fa2'>·</span> "
                f"<i style='color:#707378'>{loc.chapter}</i>"
                f"</div>{ctx}"
            )
        rows.append("</div>")
        self.elements_view.setHtml("".join(rows))

    # ────────────────── library / menu ──────────────────

    def refresh_library(self, select_id: str | None = None) -> None:
        self.book_menu.clear()
        books = self.library.list_books()
        if not books:
            empty = QAction("— no books yet —", self.book_menu)
            empty.setEnabled(False)
            self.book_menu.addAction(empty)
        else:
            for entry in books:
                label = entry["file_name"]
                fmt = Path(entry["file_name"]).suffix.lstrip(".").upper() or "?"
                pp = entry.get("total_pages")
                sub = f"{fmt}" + (f" · {pp} pp" if pp else "")
                act = QAction(f"{label}    ·  {sub}", self.book_menu)
                act.setData(entry["book_id"])
                if entry["book_id"] == select_id:
                    act.setText(f"✓ {act.text()}")
                act.triggered.connect(
                    lambda _checked=False, bid=entry["book_id"]: self.load_book_by_id(bid)
                )
                self.book_menu.addAction(act)
        self.book_menu.addSeparator()
        add_act = QAction("＋  Add a book…", self.book_menu)
        add_act.triggered.connect(self.on_new_book)
        self.book_menu.addAction(add_act)

    def load_book_by_id(self, book_id: str) -> None:
        try:
            result = self.library.load_metadata(book_id)
        except Exception as e:
            QMessageBox.warning(self, "Load failed", str(e))
            return
        self.result = result
        self.statusBar().showMessage(f"Loaded: {result.book_metadata.file_name}")
        self.render_metadata(result)
        self.render_elements(result)
        self.load_progress_for_current()
        self.refresh_library(select_id=book_id)
        if self.progress_state and self.progress_state.auto_scan and \
           self.progress_state.audio_folder:
            self._launch_audio_scan(Path(self.progress_state.audio_folder))

    def on_library_delete(self) -> None:
        if not self.result:
            return
        m = self.result.book_metadata
        if QMessageBox.question(
            self, "Remove book",
            f"Remove '{m.file_name}' from your library?\n"
            "(Source file on disk is not deleted.)"
        ) != QMessageBox.Yes:
            return
        self.library.delete_book(m.book_id)
        self.result = None
        self.progress_state = None
        for v in self.meta_cells.values():
            v.setText("—")
        self.book_file_lbl.setText("—")
        self.elements_view.clear()
        self.hero_pct.setText("—")
        self.hero_bar.setValue(0)
        for v in (self.rec_val, self.rem_val, self.tempo_val, self.eta_val):
            v.setText("—")
        for v in (self.rec_sub, self.rem_sub, self.tempo_sub, self.eta_sub):
            v.setText("")
        self.narrator_card.set_data("", 0, 0, 0, 0.0, 0.0)
        self.hero.setEnabled(False)
        self.book_selector.setText("Select a book   ▾")
        self.refresh_library()

    # ────────────────── progress ──────────────────

    def load_progress_for_current(self) -> None:
        if not self.result or not self.result.book_metadata.book_id:
            self.hero.setEnabled(False)
            return
        m = self.result.book_metadata
        self.progress_state = self.library.load_progress(m.book_id)
        self.hero.setEnabled(True)
        if m.total_pages:
            self.page_spin.setMaximum(m.total_pages)
            self.page_max_lbl.setText(f"/ {m.total_pages}")
        else:
            self.page_spin.setMaximum(max(m.total_paragraphs, 1))
            self.page_max_lbl.setText(f"/ {m.total_paragraphs} ¶")
        self.page_spin.blockSignals(True)
        self.audio_spin.blockSignals(True)
        self.page_spin.setValue(self.progress_state.current_page)
        self.audio_spin.setValue(self.progress_state.audio_hours)
        self.page_spin.blockSignals(False)
        self.audio_spin.blockSignals(False)
        self.update_narrator_card()
        self.recompute_readouts()

    def on_progress_changed(self) -> None:
        if not self.progress_state or not self.result:
            return
        self.progress_state.current_page = self.page_spin.value()
        self.progress_state.audio_hours = self.audio_spin.value()
        self.recompute_readouts()
        self.update_narrator_card()
        self._save_timer.start()

    def _flush_progress(self) -> None:
        if self.progress_state and self.result and self.result.book_metadata.book_id:
            self.library.save_progress(
                self.result.book_metadata.book_id, self.progress_state
            )
            self.statusBar().showMessage("Progress saved", 1500)

    def recompute_readouts(self) -> None:
        if not self.result or not self.progress_state:
            return
        m = self.result.book_metadata
        body = m.body_character_count
        raw = m.raw_character_count
        cur = self.page_spin.value()
        unit_total = m.total_pages if m.total_pages else max(m.total_paragraphs, 1)
        frac = min(cur / unit_total, 1.0) if unit_total else 0
        body_done = int(body * frac)
        body_left = body - body_done
        raw_done = int(raw * frac)
        audio_h = self.progress_state.audio_hours
        tempo_body = body_done / audio_h if audio_h > 0 else 0.0
        tempo_raw = raw_done / audio_h if audio_h > 0 else 0.0
        audio_left = body_left / tempo_body if tempo_body > 0 else 0.0
        est_total = body / tempo_body if tempo_body > 0 else 0.0
        pct = frac * 100

        self.hero_pct.setText(f"{pct:.1f}")
        self.hero_bar.setValue(int(pct * 10))

        self.rec_val.setText(fmt_hm(audio_h))
        self.rec_sub.setText(f"{body_done:,} chars")
        self.rem_val.setText(fmt_hm(audio_left))
        self.rem_sub.setText(f"{body_left:,} chars")
        self.tempo_val.setText(f"{tempo_body:,.0f} ch/h" if tempo_body else "—")
        self.tempo_sub.setText(
            f"body · {tempo_raw:,.0f} raw" if tempo_raw else "body · — raw"
        )
        self.eta_val.setText(fmt_hm(est_total))
        self.eta_sub.setText("at current tempo")

    # ────────────────── narrator card ──────────────────

    def update_narrator_card(self) -> None:
        if not self.result or not self.progress_state:
            self.narrator_card.set_data("", 0, 0, 0, 0.0, 0.0)
            self.narration_label.setText("NARRATION · 0 NARRATORS ON THIS BOOK")
            return
        m = self.result.book_metadata
        body = m.body_character_count
        cur = self.page_spin.value()
        unit_total = m.total_pages if m.total_pages else max(m.total_paragraphs, 1)
        frac = min(cur / unit_total, 1.0) if unit_total else 0
        body_done = int(body * frac)
        audio_h = self.progress_state.audio_hours
        tempo = body_done / audio_h if audio_h > 0 else 0.0
        pct = frac * 100
        self.narrator_card.set_data(
            name=self.progress_state.narrator,
            pages_done=cur,
            pages_total=m.total_pages or m.total_paragraphs,
            chars_narrated=body_done,
            tempo=tempo,
            percent=pct,
        )
        nn = 1 if self.progress_state.narrator else 0
        self.narration_label.setText(
            f"NARRATION · {nn} NARRATOR{'S' if nn!=1 else ''} ON THIS BOOK"
        )

    def on_narrator_card_changed(self, new_name: str) -> None:
        if not self.progress_state:
            return
        new_name = new_name.strip()
        if new_name:
            self.library.ensure_narrator(new_name)
        self.progress_state.narrator = new_name
        self._flush_progress()
        self.update_narrator_card()

    def on_narrator_card_remove(self) -> None:
        if not self.progress_state:
            return
        self.progress_state.narrator = ""
        self._flush_progress()
        self.update_narrator_card()

    def on_add_narrator(self) -> None:
        self.narrator_card._enter_edit()

    def on_mark_complete(self) -> None:
        if not self.result or not self.progress_state:
            return
        narrator = (self.progress_state.narrator or "").strip()
        if not narrator:
            QMessageBox.warning(
                self, "Narrator required",
                "Set a narrator on this book before marking complete."
            )
            return
        audio_h = self.progress_state.audio_hours
        if audio_h <= 0:
            QMessageBox.warning(
                self, "Audio hours required",
                "Set the recorded audio hours (or scan a folder) first."
            )
            return
        m = self.result.book_metadata
        body = m.body_character_count
        cph = body / audio_h
        self.progress_state.completed = True
        self.progress_state.final_chars_per_hour = cph
        if m.total_pages:
            self.page_spin.blockSignals(True)
            self.page_spin.setValue(m.total_pages)
            self.page_spin.blockSignals(False)
            self.progress_state.current_page = m.total_pages
        self.library.ensure_narrator(narrator)
        self.library.record_narrator_tempo(narrator, m.book_id, cph)
        self.library.save_progress(m.book_id, self.progress_state)
        self.recompute_readouts()
        self.update_narrator_card()
        QMessageBox.information(
            self, "Book completed",
            f"Final tempo: {cph:,.0f} chars/h\nSaved under narrator: {narrator}"
        )

    # ────────────────── audio scan ──────────────────

    def on_audio_browse(self) -> None:
        folder = QFileDialog.getExistingDirectory(
            self, "Select audio folder", "", QFileDialog.ShowDirsOnly
        )
        if folder:
            if self.progress_state:
                self.progress_state.audio_folder = folder
                self._flush_progress()
            self._launch_audio_scan(Path(folder))

    def _launch_audio_scan(self, folder: Path) -> None:
        if self.audio_worker and self.audio_worker.isRunning():
            return
        self.audio_browse_btn.setEnabled(False)
        self.statusBar().showMessage(f"Scanning {folder}…")
        self.audio_worker = AudioScanWorker(folder)
        self.audio_worker.finished_ok.connect(
            lambda s, c, e, f=str(folder): self.on_audio_scanned(s, c, e, f)
        )
        self.audio_worker.failed.connect(self.on_audio_failed)
        self.audio_worker.start()

    def on_audio_scanned(self, total_seconds: float, count: int,
                         errors: list, folder: str) -> None:
        self.audio_browse_btn.setEnabled(True)
        self.audio_spin.setValue(total_seconds / 3600.0)
        h = int(total_seconds // 3600)
        m = int((total_seconds % 3600) // 60)
        s = int(total_seconds % 60)
        self.statusBar().showMessage(
            f"{count} files · {h:02d}:{m:02d}:{s:02d}", 4000
        )
        if errors and len(errors) <= 5:
            QMessageBox.warning(self, "Some files skipped", "\n".join(errors))

    def on_audio_failed(self, msg: str) -> None:
        self.audio_browse_btn.setEnabled(True)
        QMessageBox.critical(self, "Audio scan failed", msg)

    def closeEvent(self, event) -> None:
        if self._save_timer.isActive():
            self._save_timer.stop()
            self._flush_progress()
        super().closeEvent(event)


def main() -> int:
    app = QApplication(sys.argv)
    app.setStyle("Fusion")
    win = MainWindow()
    win.show()
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
