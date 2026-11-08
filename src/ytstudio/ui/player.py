"""Beépített előnézet-lejátszó (Qt Multimedia), a vágási pontok kijelöléséhez is.

Csak a felhasználó kérésére jön létre, így nem foglal memóriát és hálózatot,
ha nincs rá szükség. A lejátszó a videó kis felbontású, hangot is tartalmazó
változatát streameli; ha ez nem sikerül, a felület böngészős megnyitást ajánl.
"""
from __future__ import annotations

from PySide6.QtCore import Qt, QUrl, Signal
from PySide6.QtMultimedia import QAudioOutput, QMediaPlayer
from PySide6.QtMultimediaWidgets import QVideoWidget
from PySide6.QtWidgets import QHBoxLayout, QSlider, QVBoxLayout, QWidget

from .widgets import button, label, set_icon
from ..core import fmt_time


class PreviewPlayer(QWidget):
    markIn = Signal(float)
    markOut = Signal(float)
    positionChanged = Signal(float)
    closed = Signal()
    failed = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("transparent")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)
        self.video = QVideoWidget()
        self.video.setMinimumHeight(180)
        self.video.setStyleSheet("background: black; border-radius: 10px;")
        layout.addWidget(self.video, 1)
        self.player = QMediaPlayer(self)
        self.audio = QAudioOutput(self)
        self.audio.setVolume(0.8)
        self.player.setAudioOutput(self.audio)
        self.player.setVideoOutput(self.video)
        controls = QHBoxLayout()
        controls.setSpacing(4)
        self.play_button = button("", "ghost", "play", "text", "Lejátszás / szünet")
        self.play_button.setFixedSize(34, 32)
        self.play_button.clicked.connect(self.toggle)
        controls.addWidget(self.play_button)
        self.slider = QSlider(Qt.Orientation.Horizontal)
        self.slider.setRange(0, 0)
        self.slider.sliderMoved.connect(lambda v: self.player.setPosition(v))
        controls.addWidget(self.slider, 1)
        self.time = label("00:00:00", "caption")
        controls.addWidget(self.time)
        self.mute = button("", "ghost", "volume", "muted", "Némítás")
        self.mute.setFixedSize(32, 32)
        self.mute.clicked.connect(self._toggle_mute)
        controls.addWidget(self.mute)
        layout.addLayout(controls)
        marks = QHBoxLayout()
        marks.setSpacing(6)
        self.in_button = button("Kezdőpont ide", None, "mark-in", "accent",
                                "A vágás kezdete a lejátszó aktuális pozíciója lesz")
        self.out_button = button("Végpont ide", None, "mark-out", "accent",
                                 "A vágás vége a lejátszó aktuális pozíciója lesz")
        self.in_button.clicked.connect(lambda: self.markIn.emit(self.seconds()))
        self.out_button.clicked.connect(lambda: self.markOut.emit(self.seconds()))
        close = button("Bezárás", "ghost", "close", "muted")
        close.clicked.connect(self.close_player)
        marks.addWidget(self.in_button)
        marks.addWidget(self.out_button)
        marks.addStretch(1)
        marks.addWidget(close)
        layout.addLayout(marks)
        self.player.positionChanged.connect(self._position)
        self.player.durationChanged.connect(lambda d: self.slider.setRange(0, int(d)))
        self.player.playbackStateChanged.connect(self._state)
        self.player.errorOccurred.connect(self._error)

    def load(self, url: str, start: float = 0.0) -> None:
        self.player.setSource(QUrl(url))
        if start:
            self.player.setPosition(int(start * 1000))
        self.player.play()

    def seconds(self) -> float:
        return self.player.position() / 1000.0

    def seek(self, seconds: float) -> None:
        self.player.setPosition(int(max(0.0, seconds) * 1000))

    def toggle(self) -> None:
        if self.player.playbackState() == QMediaPlayer.PlaybackState.PlayingState:
            self.player.pause()
        else:
            self.player.play()

    def _toggle_mute(self) -> None:
        self.audio.setMuted(not self.audio.isMuted())
        set_icon(self.mute, "mute" if self.audio.isMuted() else "volume", "muted")

    def _position(self, ms: int) -> None:
        if not self.slider.isSliderDown():
            self.slider.setValue(ms)
        self.time.setText(fmt_time(ms / 1000))
        self.positionChanged.emit(ms / 1000)

    def _state(self, state) -> None:
        playing = state == QMediaPlayer.PlaybackState.PlayingState
        set_icon(self.play_button, "pause" if playing else "play", "text")

    def _error(self, _error, message: str) -> None:
        self.failed.emit(message or "A videó nem játszható le.")

    def close_player(self) -> None:
        self.player.stop()
        self.player.setSource(QUrl())
        self.closed.emit()
