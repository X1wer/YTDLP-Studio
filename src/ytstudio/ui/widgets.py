"""Egyedi, témázható vezérlők a modern, letisztult felülethez."""
from __future__ import annotations

import unicodedata
import weakref
from typing import Iterable, Sequence

from PySide6.QtCore import (QAbstractListModel, QEvent, QModelIndex, QPointF, QRect, QRectF, QSize,
                            QSortFilterProxyModel, Qt, QTimer, Signal, Property, QPropertyAnimation,
                            QEasingCurve)
from PySide6.QtGui import (QColor, QFont, QFontMetrics, QKeyEvent, QMouseEvent, QPainter, QPainterPath,
                           QPen, QPixmap)
from PySide6.QtWidgets import (QAbstractButton, QAbstractItemView, QButtonGroup, QComboBox, QFrame,
                               QHBoxLayout, QLabel, QLineEdit, QListView, QPushButton, QSizePolicy,
                               QStyle, QStyledItemDelegate, QStyleOptionViewItem, QToolTip,
                               QVBoxLayout, QWidget)

from . import icons, theme
from ..core import fmt_duration, fmt_time, parse_time


# --------------------------------------------------------------------------- #
# Segédfüggvények
# --------------------------------------------------------------------------- #

def fold(text: str) -> str:
    """Ékezet- és kisbetű-érzéketlen kereséshez."""
    return "".join(ch for ch in unicodedata.normalize("NFKD", text.casefold()) if not unicodedata.combining(ch))


def label(text: str = "", role: str | None = None, *, wrap: bool = False, selectable: bool = False) -> QLabel:
    widget = QLabel(text)
    if role:
        widget.setProperty("role", role)
    widget.setWordWrap(wrap)
    if selectable:
        widget.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
    return widget


def button(text: str = "", variant: str | None = None, icon_name: str | None = None,
           icon_role: str = "text", tooltip: str = "", *, large: bool = False) -> QPushButton:
    widget = QPushButton(text)
    if variant:
        widget.setProperty("variant", variant)
    if large:
        widget.setProperty("size", "large")
    if icon_name:
        set_icon(widget, icon_name, "accent_text" if variant == "primary" else icon_role)
    if tooltip:
        widget.setToolTip(tooltip)
    widget.setCursor(Qt.CursorShape.PointingHandCursor)
    return widget


_icon_registry: "weakref.WeakKeyDictionary[QAbstractButton, tuple[str, str, int]]" = weakref.WeakKeyDictionary()


def set_icon(widget: QAbstractButton, name: str, role: str = "text", size: int = 18) -> None:
    _icon_registry[widget] = (name, role, size)
    widget.setIcon(icons.icon(name, theme.c(role), theme.c("faint"), size))
    widget.setIconSize(QSize(size, size))


def _refresh_icons() -> None:
    for widget, (name, role, size) in list(_icon_registry.items()):
        try:
            widget.setIcon(icons.icon(name, theme.c(role), theme.c("faint"), size))
        except RuntimeError:
            pass


theme.manager.changed.connect(_refresh_icons)


def hline() -> QFrame:
    line = QFrame()
    line.setObjectName("divider")
    line.setFrameShape(QFrame.Shape.NoFrame)
    return line


class IconLabel(QLabel):
    """Témaszínre színezett ikon."""

    def __init__(self, name: str, role: str = "muted", size: int = 18, parent=None):
        super().__init__(parent)
        self._spec = (name, role, size)
        self.setFixedSize(size, size)
        self._refresh()
        theme.manager.changed.connect(self._refresh)

    def set_spec(self, name: str, role: str | None = None) -> None:
        self._spec = (name, role or self._spec[1], self._spec[2])
        self._refresh()

    def _refresh(self) -> None:
        name, role, size = self._spec
        self.setPixmap(icons.pixmap(name, theme.c(role), size))


class Card(QFrame):
    """Lekerekített panel opcionális címsorral (ikon + cím + jobb oldali elemek)."""

    def __init__(self, title: str = "", icon_name: str | None = None, parent=None, *, margins: int = 16):
        super().__init__(parent)
        self.setObjectName("card")
        self.outer = QVBoxLayout(self)
        self.outer.setContentsMargins(margins, margins - 2, margins, margins)
        self.outer.setSpacing(10)
        self.header = None
        self.header_right = None
        if title:
            self.header = QHBoxLayout()
            self.header.setSpacing(8)
            if icon_name:
                self.header.addWidget(IconLabel(icon_name, "accent", 18))
            self.title_label = label(title, "h2")
            self.header.addWidget(self.title_label)
            self.header.addStretch(1)
            self.header_right = QHBoxLayout()
            self.header_right.setSpacing(6)
            self.header.addLayout(self.header_right)
            self.outer.addLayout(self.header)
        self.body = QVBoxLayout()
        self.body.setSpacing(10)
        self.outer.addLayout(self.body)


# --------------------------------------------------------------------------- #
# Választók
# --------------------------------------------------------------------------- #

class SegmentedControl(QWidget):
    """Kizárólagos választó szegmensgombokkal (legördülő menü helyett, rövid listákhoz)."""

    changed = Signal(str)

    def __init__(self, options: Sequence[tuple[str, str]] = (), *, large: bool = False,
                 icons_map: dict[str, str] | None = None, parent=None):
        super().__init__(parent)
        self.setObjectName("segmented")
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self._layout = QHBoxLayout(self)
        self._layout.setContentsMargins(3, 3, 3, 3)
        self._layout.setSpacing(2)
        self._group = QButtonGroup(self)
        self._group.setExclusive(True)
        self._buttons: dict[str, QPushButton] = {}
        self._large = large
        self._icons = icons_map or {}
        self._group.buttonClicked.connect(self._clicked)
        self.set_options(options)
        self.setSizePolicy(QSizePolicy.Policy.Maximum, QSizePolicy.Policy.Fixed)

    def set_options(self, options: Sequence[tuple[str, str]]) -> None:
        current = self.value()
        for b in self._buttons.values():
            self._group.removeButton(b)
            b.deleteLater()
        self._buttons.clear()
        for value, text in options:
            b = QPushButton(text)
            b.setCheckable(True)
            b.setProperty("segment", "true")
            if self._large:
                b.setProperty("large", "true")
            b.setCursor(Qt.CursorShape.PointingHandCursor)
            b.setProperty("value", value)
            if value in self._icons:
                set_icon(b, self._icons[value], "muted", 18)
            self._group.addButton(b)
            self._layout.addWidget(b)
            self._buttons[value] = b
        if current in self._buttons:
            self._buttons[current].setChecked(True)
        elif self._buttons:
            next(iter(self._buttons.values())).setChecked(True)

    def _clicked(self, b) -> None:
        self.changed.emit(str(b.property("value")))

    def value(self) -> str:
        b = self._group.checkedButton() if hasattr(self, "_group") else None
        return str(b.property("value")) if b else ""

    def set_value(self, value: str, emit: bool = False) -> None:
        b = self._buttons.get(value)
        if b is not None and b.isEnabled():
            b.setChecked(True)
            if emit:
                self.changed.emit(value)

    def set_option_enabled(self, value: str, enabled: bool, tooltip: str = "") -> None:
        b = self._buttons.get(value)
        if b is not None:
            b.setEnabled(enabled)
            b.setToolTip(tooltip)

    def button(self, value: str) -> QPushButton | None:
        return self._buttons.get(value)

    def values(self) -> list[str]:
        return list(self._buttons)


class ChoiceBox(QComboBox):
    """Legördülő lista érték–felirat párokkal."""

    def __init__(self, items: Iterable[tuple[str, str]] = (), parent=None):
        super().__init__(parent)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setSizeAdjustPolicy(QComboBox.SizeAdjustPolicy.AdjustToContents)
        self.setMaxVisibleItems(14)
        self.set_items(items)

    def set_items(self, items: Iterable[tuple[str, str]], keep: bool = True) -> None:
        current = self.value() if keep else None
        self.blockSignals(True)
        self.clear()
        for value, text in items:
            self.addItem(text, value)
        self.blockSignals(False)
        if current is not None and self.findData(current) >= 0:
            self.setCurrentIndex(self.findData(current))
        elif self.count():
            self.setCurrentIndex(0)

    def value(self) -> str:
        data = self.currentData()
        return "" if data is None else str(data)

    def set_value(self, value: str) -> bool:
        index = self.findData(value)
        if index >= 0:
            self.setCurrentIndex(index)
            return True
        return False


class ToggleSwitch(QAbstractButton):
    """Animált be/ki kapcsoló."""

    def __init__(self, text: str = "", parent=None):
        super().__init__(parent)
        self.setCheckable(True)
        self.setText(text)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self._pos = 0.0
        self._anim = QPropertyAnimation(self, b"knob", self)
        self._anim.setDuration(140)
        self._anim.setEasingCurve(QEasingCurve.Type.OutCubic)
        self.toggled.connect(self._animate)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        theme.manager.changed.connect(self.update)

    def _get_knob(self) -> float:
        return self._pos

    def _set_knob(self, value: float) -> None:
        self._pos = value
        self.update()

    knob = Property(float, _get_knob, _set_knob)

    def _animate(self, checked: bool) -> None:
        self._anim.stop()
        self._anim.setStartValue(self._pos)
        self._anim.setEndValue(1.0 if checked else 0.0)
        self._anim.start()

    def setChecked(self, checked: bool) -> None:  # noqa: N802 - Qt API
        super().setChecked(checked)
        self._anim.stop()
        self._pos = 1.0 if checked else 0.0
        self.update()

    def sizeHint(self) -> QSize:
        fm = QFontMetrics(self.font())
        text_w = fm.horizontalAdvance(self.text()) + 10 if self.text() else 0
        return QSize(40 + text_w, max(24, fm.height() + 4))

    def paintEvent(self, _event) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        h = 20
        y = (self.height() - h) / 2
        track = QRectF(1, y, 36, h)
        on = theme.qc("accent")
        off = theme.qc("border_strong")
        color = QColor(
            int(off.red() + (on.red() - off.red()) * self._pos),
            int(off.green() + (on.green() - off.green()) * self._pos),
            int(off.blue() + (on.blue() - off.blue()) * self._pos))
        if not self.isEnabled():
            color = theme.qc("border")
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(color)
        p.drawRoundedRect(track, h / 2, h / 2)
        knob_x = track.left() + 3 + self._pos * (track.width() - h)
        p.setBrush(QColor("#ffffff"))
        p.drawEllipse(QRectF(knob_x, y + 3, h - 6, h - 6))
        if self.hasFocus():
            p.setPen(QPen(theme.qc("accent", 120), 1.5))
            p.setBrush(Qt.BrushStyle.NoBrush)
            p.drawRoundedRect(track.adjusted(-2, -2, 2, 2), h / 2 + 2, h / 2 + 2)
        if self.text():
            p.setPen(theme.qc("text") if self.isEnabled() else theme.qc("faint"))
            p.drawText(QRect(int(track.right()) + 10, 0, self.width(), self.height()),
                       Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft, self.text())

    def hitButton(self, pos) -> bool:  # noqa: N802 - Qt API
        return self.rect().contains(pos)


# --------------------------------------------------------------------------- #
# Kereshető, jelölőnégyzetes lista
# --------------------------------------------------------------------------- #

KEY_ROLE = Qt.ItemDataRole.UserRole + 1
DETAIL_ROLE = Qt.ItemDataRole.UserRole + 2
KIND_ROLE = Qt.ItemDataRole.UserRole + 3
SEARCH_ROLE = Qt.ItemDataRole.UserRole + 4
STAR_ROLE = Qt.ItemDataRole.UserRole + 5


class CheckModel(QAbstractListModel):
    checkedChanged = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._items: list[dict] = []
        self._checked: set[str] = set()

    def set_items(self, items: list[dict]) -> None:
        self.beginResetModel()
        self._items = list(items)
        keys = [i["key"] for i in items]
        if len(keys) != len(set(keys)):
            raise ValueError("A listaelemek kulcsai nem egyediek.")
        self._checked = set()
        self.endResetModel()
        self.checkedChanged.emit()

    def rowCount(self, parent=QModelIndex()) -> int:  # noqa: N802
        return 0 if parent.isValid() else len(self._items)

    def data(self, index: QModelIndex, role=Qt.ItemDataRole.DisplayRole):
        if not index.isValid():
            return None
        item = self._items[index.row()]
        if role == Qt.ItemDataRole.DisplayRole:
            return item["text"]
        if role == Qt.ItemDataRole.CheckStateRole:
            return Qt.CheckState.Checked if item["key"] in self._checked else Qt.CheckState.Unchecked
        if role == KEY_ROLE:
            return item["key"]
        if role == DETAIL_ROLE:
            return item.get("detail", "")
        if role == KIND_ROLE:
            return item.get("kind", "")
        if role == STAR_ROLE:
            return item.get("star", False)
        if role == SEARCH_ROLE:
            return fold(item["text"] + " " + item.get("detail", "") + " " + item.get("search", ""))
        if role == Qt.ItemDataRole.ToolTipRole:
            return item.get("tooltip") or None
        return None

    def flags(self, index: QModelIndex):
        return (Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsSelectable | Qt.ItemFlag.ItemIsUserCheckable)

    def setData(self, index: QModelIndex, value, role=Qt.ItemDataRole.EditRole) -> bool:  # noqa: N802
        if role != Qt.ItemDataRole.CheckStateRole or not index.isValid():
            return False
        key = self._items[index.row()]["key"]
        checked = value in (Qt.CheckState.Checked, Qt.CheckState.Checked.value, 2, True)
        if checked:
            self._checked.add(key)
        else:
            self._checked.discard(key)
        self.dataChanged.emit(index, index, [Qt.ItemDataRole.CheckStateRole])
        self.checkedChanged.emit()
        return True

    def toggle(self, row: int) -> None:
        index = self.index(row)
        key = self._items[row]["key"]
        self.setData(index, Qt.CheckState.Unchecked if key in self._checked else Qt.CheckState.Checked,
                     Qt.ItemDataRole.CheckStateRole)

    def set_checked(self, keys: Iterable[str], checked: bool = True) -> None:
        keys = set(keys)
        if checked:
            self._checked |= keys & {i["key"] for i in self._items}
        else:
            self._checked -= keys
        if self._items:
            self.dataChanged.emit(self.index(0), self.index(len(self._items) - 1),
                                  [Qt.ItemDataRole.CheckStateRole])
        self.checkedChanged.emit()

    def checked_keys(self) -> list[str]:
        return [i["key"] for i in self._items if i["key"] in self._checked]

    def is_checked(self, key: str) -> bool:
        return key in self._checked

    def items(self) -> list[dict]:
        return list(self._items)


class CheckFilter(QSortFilterProxyModel):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.query = ""
        self.kind = ""
        self.only_checked = False

    def refresh(self) -> None:
        if hasattr(self, "beginFilterChange"):
            self.beginFilterChange()
            self.endFilterChange()
        else:  # Qt < 6.10
            self.invalidateFilter()

    def set_filter(self, *, query: str | None = None, kind: str | None = None,
                   only_checked: bool | None = None) -> None:
        if hasattr(self, "beginFilterChange"):
            self.beginFilterChange()
        if query is not None:
            self.query = fold(query.strip())
        if kind is not None:
            self.kind = kind
        if only_checked is not None:
            self.only_checked = only_checked
        if hasattr(self, "endFilterChange"):
            self.endFilterChange()
        else:
            self.invalidateFilter()

    def filterAcceptsRow(self, row: int, parent: QModelIndex) -> bool:  # noqa: N802
        model = self.sourceModel()
        index = model.index(row, 0, parent)
        if self.only_checked and index.data(Qt.ItemDataRole.CheckStateRole) != Qt.CheckState.Checked:
            return False
        if self.kind and index.data(KIND_ROLE) != self.kind:
            return False
        if self.query:
            return all(part in index.data(SEARCH_ROLE) for part in self.query.split())
        return True


KIND_COLORS = {"manual": "success", "original": "success", "auto": "accent", "translated": "warning",
               "dubbed": "accent", "dubbed-auto": "warning", "descriptive": "muted", "default": "muted"}


class CheckDelegate(QStyledItemDelegate):
    """Kétsoros listaelem saját jelölőnégyzettel; az egész sorra kattintva vált."""

    ROW_HEIGHT = 44

    def sizeHint(self, option, index) -> QSize:
        return QSize(option.rect.width(), self.ROW_HEIGHT)

    def paint(self, painter: QPainter, option: QStyleOptionViewItem, index: QModelIndex) -> None:
        painter.save()
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        rect = option.rect.adjusted(4, 2, -4, -2)
        checked = index.data(Qt.ItemDataRole.CheckStateRole) == Qt.CheckState.Checked
        hovered = bool(option.state & QStyle.StateFlag.State_MouseOver)
        if checked:
            painter.setBrush(theme.qc("accent_soft"))
        elif hovered:
            painter.setBrush(theme.qc("hover"))
        else:
            painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.drawRoundedRect(QRectF(rect), 7, 7)
        box = QRectF(rect.left() + 10, rect.center().y() - 8, 16, 16)
        if checked:
            painter.setBrush(theme.qc("accent"))
            painter.setPen(Qt.PenStyle.NoPen)
            painter.drawRoundedRect(box, 4, 4)
            pen = QPen(QColor(theme.c("accent_text")), 2)
            pen.setCapStyle(Qt.PenCapStyle.RoundCap)
            pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
            painter.setPen(pen)
            path = QPainterPath(QPointF(box.left() + 4, box.top() + 8.5))
            path.lineTo(box.left() + 7, box.top() + 11.5)
            path.lineTo(box.left() + 12.5, box.top() + 5)
            painter.drawPath(path)
        else:
            painter.setBrush(theme.qc("surface"))
            painter.setPen(QPen(theme.qc("border_strong"), 1.5))
            painter.drawRoundedRect(box, 4, 4)
        x = int(box.right()) + 12
        text_rect = QRect(x, rect.top() + 4, rect.right() - x - 8, rect.height() // 2 - 2)
        font = QFont(option.font)
        title = index.data(Qt.ItemDataRole.DisplayRole) or ""
        if index.data(STAR_ROLE):
            title = "★ " + title
        font.setWeight(QFont.Weight.DemiBold if checked else QFont.Weight.Medium)
        painter.setFont(font)
        painter.setPen(theme.qc("text"))
        fm = QFontMetrics(font)
        painter.drawText(text_rect, Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
                         fm.elidedText(title, Qt.TextElideMode.ElideRight, text_rect.width()))
        detail = index.data(DETAIL_ROLE) or ""
        kind = index.data(KIND_ROLE) or ""
        small = QFont(option.font)
        small.setPointSizeF(max(7.5, option.font.pointSizeF() - 1.2))
        painter.setFont(small)
        detail_rect = QRect(x, rect.top() + rect.height() // 2, rect.right() - x - 8, rect.height() // 2 - 4)
        if kind:
            dot = QRectF(x, detail_rect.center().y() - 3, 6, 6)
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(theme.qc(KIND_COLORS.get(kind, "muted")))
            painter.drawEllipse(dot)
            detail_rect.setLeft(x + 11)
        painter.setPen(theme.qc("muted"))
        sfm = QFontMetrics(small)
        painter.drawText(detail_rect, Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
                         sfm.elidedText(detail, Qt.TextElideMode.ElideRight, detail_rect.width()))
        painter.restore()

    def editorEvent(self, event, model, option, index) -> bool:  # noqa: N802
        if event.type() == QEvent.Type.MouseButtonRelease and event.button() == Qt.MouseButton.LeftButton:
            source = model
            source_index = index
            while isinstance(source, QSortFilterProxyModel):
                source_index = source.mapToSource(source_index)
                source = source.sourceModel()
            source.toggle(source_index.row())
            return True
        if event.type() == QEvent.Type.MouseButtonDblClick:
            return True
        if event.type() == QEvent.Type.KeyPress and event.key() in (Qt.Key.Key_Space, Qt.Key.Key_Select):
            source, source_index = model, index
            while isinstance(source, QSortFilterProxyModel):
                source_index = source.mapToSource(source_index)
                source = source.sourceModel()
            source.toggle(source_index.row())
            return True
        return False

    def helpEvent(self, event, view, option, index) -> bool:  # noqa: N802
        if event.type() == QEvent.Type.ToolTip:
            text = index.data(Qt.ItemDataRole.ToolTipRole) or f"{index.data()}\n{index.data(DETAIL_ROLE)}"
            QToolTip.showText(event.globalPos(), text, view)
            return True
        return super().helpEvent(event, view, option, index)


class CheckList(QWidget):
    """Kereshető, görgethető lista valódi többes kijelöléssel (Ctrl/Shift nélkül).

    A kijelölés a stabil kulcsokhoz kötődik a forrásmodellben, ezért a szűrés,
    a keresés és a „csak kijelöltek” nézet sosem változtatja meg a választást.
    """

    selectionChanged = Signal()

    def __init__(self, *, placeholder: str = "Keresés…", empty_text: str = "Nincs elérhető elem.",
                 kinds: Sequence[tuple[str, str]] = (), parent=None):
        super().__init__(parent)
        self.model = CheckModel(self)
        self.proxy = CheckFilter(self)
        self.proxy.setSourceModel(self.model)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)
        tools = QHBoxLayout()
        tools.setSpacing(6)
        self.search = QLineEdit()
        self.search.setPlaceholderText(placeholder)
        self.search.setClearButtonEnabled(True)
        self.search_action = self.search.addAction(icons.icon("search", theme.c("faint")),
                                                   QLineEdit.ActionPosition.LeadingPosition)
        self.search.textChanged.connect(lambda text: self._refilter(query=text))
        tools.addWidget(self.search, 1)
        self.kind_box = None
        if kinds:
            self.kind_box = ChoiceBox([("", "Minden típus")] + list(kinds))
            self.kind_box.currentIndexChanged.connect(lambda _i: self._refilter(kind=self.kind_box.value()))
            tools.addWidget(self.kind_box)
        layout.addLayout(tools)
        self.view = QListView()
        self.view.setModel(self.proxy)
        self.view.setItemDelegate(CheckDelegate(self.view))
        self.view.setMouseTracking(True)
        self.view.setUniformItemSizes(True)
        self.view.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.view.setVerticalScrollMode(QAbstractItemView.ScrollMode.ScrollPerPixel)
        self.view.setSelectionMode(QAbstractItemView.SelectionMode.NoSelection)
        self.view.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.view.viewport().setAttribute(Qt.WidgetAttribute.WA_Hover, True)
        layout.addWidget(self.view, 1)
        self.empty = label(empty_text, "muted", wrap=True)
        self.empty.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.empty.setMinimumHeight(60)
        layout.addWidget(self.empty, 1)
        footer = QHBoxLayout()
        footer.setSpacing(4)
        self.count_label = label("", "caption")
        footer.addWidget(self.count_label)
        footer.addStretch(1)
        self.only_checked = QPushButton("Csak kijelöltek")
        self.only_checked.setProperty("variant", "ghost")
        self.only_checked.setCheckable(True)
        self.only_checked.toggled.connect(lambda on: self._refilter(only_checked=on))
        self.only_checked.setCursor(Qt.CursorShape.PointingHandCursor)
        self.clear_button = button("Törlés", "ghost", tooltip="Minden kijelölés törlése")
        self.clear_button.clicked.connect(self.clear_selection)
        footer.addWidget(self.only_checked)
        footer.addWidget(self.clear_button)
        layout.addLayout(footer)
        self.footer = footer
        self.model.checkedChanged.connect(self._changed)
        theme.manager.changed.connect(self._on_theme)
        self._update_state()

    def _on_theme(self) -> None:
        self.search_action.setIcon(icons.icon("search", theme.c("faint")))
        self.view.viewport().update()

    def _refilter(self, **kwargs) -> None:
        self.proxy.set_filter(**kwargs)
        self._update_state()

    def _changed(self) -> None:
        if self.proxy.only_checked:
            self.proxy.refresh()
        self._update_state()
        self.selectionChanged.emit()

    def _update_state(self) -> None:
        total = self.model.rowCount()
        checked = len(self.model.checked_keys())
        visible = self.proxy.rowCount()
        has_items = total > 0
        self.view.setVisible(has_items and visible > 0)
        self.empty.setVisible(not has_items or visible == 0)
        if has_items and visible == 0:
            self.empty.setText("Nincs a szűrésnek megfelelő elem.")
        elif not has_items:
            self.empty.setText(self._empty_text)
        self.search.setEnabled(has_items)
        if self.kind_box:
            self.kind_box.setEnabled(has_items)
        self.only_checked.setEnabled(has_items)
        self.clear_button.setEnabled(checked > 0)
        text = f"{checked} kijelölve / {total}" if has_items else ""
        if has_items and visible != total:
            text += f" · {visible} látható"
        self.count_label.setText(text)

    @property
    def _empty_text(self) -> str:
        return getattr(self, "_empty", "Nincs elérhető elem.")

    def set_empty_text(self, text: str) -> None:
        self._empty = text
        self._update_state()

    def set_items(self, items: list[dict]) -> None:
        self.search.blockSignals(True)
        self.search.clear()
        self.search.blockSignals(False)
        self.only_checked.blockSignals(True)
        self.only_checked.setChecked(False)
        self.only_checked.blockSignals(False)
        self.proxy.set_filter(query="", kind="", only_checked=False)
        if self.kind_box:
            self.kind_box.blockSignals(True)
            self.kind_box.setCurrentIndex(0)
            self.kind_box.blockSignals(False)
        self.model.set_items(items)
        self.view.scrollToTop()
        self._update_state()

    def checked_keys(self) -> list[str]:
        return self.model.checked_keys()

    def set_checked(self, keys: Iterable[str], checked: bool = True) -> None:
        self.model.set_checked(keys, checked)

    def clear_selection(self) -> None:
        self.model.set_checked([i["key"] for i in self.model.items()], False)

    def select_visible(self) -> None:
        keys = [self.proxy.index(r, 0).data(KEY_ROLE) for r in range(self.proxy.rowCount())]
        self.model.set_checked(keys, True)

    def visible_keys(self) -> list[str]:
        return [self.proxy.index(r, 0).data(KEY_ROLE) for r in range(self.proxy.rowCount())]


# --------------------------------------------------------------------------- #
# Idővonal és időmezők
# --------------------------------------------------------------------------- #

class RangeSlider(QWidget):
    """Idővonal két húzható végponttal és fejezetjelölőkkel."""

    rangeChanged = Signal(float, float)

    HANDLE = 9

    def __init__(self, parent=None):
        super().__init__(parent)
        self.duration = 0.0
        self.start = 0.0
        self.end = 0.0
        self.chapters: list[float] = []
        self.position: float | None = None
        self._drag: str | None = None
        self._focus = "start"
        self.setMinimumHeight(44)
        self.setMouseTracking(True)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        theme.manager.changed.connect(self.update)

    def set_duration(self, duration: float, chapters: Sequence[float] = ()) -> None:
        self.duration = max(0.0, duration or 0.0)
        self.chapters = [c for c in chapters if 0 < c < self.duration]
        self.start, self.end = 0.0, self.duration
        self.update()

    def set_range(self, start: float, end: float, emit: bool = False) -> None:
        if self.duration <= 0:
            return
        start = min(max(0.0, start), self.duration)
        end = min(max(0.0, end), self.duration)
        if end < start:
            start, end = end, start
        self.start, self.end = start, end
        self.update()
        if emit:
            self.rangeChanged.emit(self.start, self.end)

    def set_position(self, seconds: float | None) -> None:
        self.position = seconds
        self.update()

    def _track(self) -> QRectF:
        m = self.HANDLE + 3
        return QRectF(m, self.height() / 2 - 3, self.width() - 2 * m, 6)

    def _x(self, seconds: float) -> float:
        track = self._track()
        if self.duration <= 0:
            return track.left()
        return track.left() + track.width() * seconds / self.duration

    def _seconds(self, x: float) -> float:
        track = self._track()
        if track.width() <= 0:
            return 0.0
        ratio = min(1.0, max(0.0, (x - track.left()) / track.width()))
        return round(ratio * self.duration, 1)

    def paintEvent(self, _event) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        track = self._track()
        enabled = self.isEnabled() and self.duration > 0
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(theme.qc("track"))
        p.drawRoundedRect(track, 3, 3)
        sel = QRectF(self._x(self.start), track.top(), self._x(self.end) - self._x(self.start), track.height())
        p.setBrush(theme.qc("accent") if enabled else theme.qc("border_strong"))
        p.drawRoundedRect(sel, 3, 3)
        p.setPen(QPen(theme.qc("surface"), 2))
        for ch in self.chapters:
            x = self._x(ch)
            p.drawLine(QPointF(x, track.top()), QPointF(x, track.bottom()))
        if self.position is not None and self.duration > 0:
            x = self._x(self.position)
            p.setPen(QPen(theme.qc("text"), 2))
            p.drawLine(QPointF(x, track.top() - 7), QPointF(x, track.bottom() + 7))
        for name, value in (("start", self.start), ("end", self.end)):
            center = QPointF(self._x(value), track.center().y())
            p.setBrush(theme.qc("surface"))
            color = theme.qc("accent") if enabled else theme.qc("border_strong")
            p.setPen(QPen(color, 3 if (self.hasFocus() and self._focus == name) else 2))
            p.drawEllipse(center, self.HANDLE, self.HANDLE)

    def mousePressEvent(self, event: QMouseEvent) -> None:  # noqa: N802
        if not self.isEnabled() or self.duration <= 0:
            return
        x = event.position().x()
        ds, de = abs(x - self._x(self.start)), abs(x - self._x(self.end))
        self._drag = "start" if ds < de or (ds == de and x < self._x(self.start)) else "end"
        self._focus = self._drag
        self._move_to(x)

    def mouseMoveEvent(self, event: QMouseEvent) -> None:  # noqa: N802
        x = event.position().x()
        if self._drag:
            self._move_to(x)
        if self.duration > 0:
            QToolTip.showText(event.globalPosition().toPoint(), fmt_time(self._seconds(x)), self)

    def mouseReleaseEvent(self, _event) -> None:  # noqa: N802
        self._drag = None

    def _move_to(self, x: float) -> None:
        value = self._seconds(x)
        if self._drag == "start":
            self.start = min(value, max(0.0, self.end - 0.5))
        else:
            self.end = max(value, min(self.duration, self.start + 0.5))
        self.update()
        self.rangeChanged.emit(self.start, self.end)

    def keyPressEvent(self, event: QKeyEvent) -> None:  # noqa: N802
        step = 10.0 if event.modifiers() & Qt.KeyboardModifier.ShiftModifier else 1.0
        if event.key() == Qt.Key.Key_Tab and self._focus == "start":
            self._focus = "end"
            self.update()
            return
        if event.key() in (Qt.Key.Key_Left, Qt.Key.Key_Right):
            delta = -step if event.key() == Qt.Key.Key_Left else step
            if self._focus == "start":
                self.set_range(min(self.start + delta, self.end - 0.5), self.end, emit=True)
            else:
                self.set_range(self.start, max(self.end + delta, self.start + 0.5), emit=True)
            return
        super().keyPressEvent(event)

    def sizeHint(self) -> QSize:
        return QSize(400, 44)


class TimeEdit(QLineEdit):
    """ÓÓ:PP:MM formátumú időmező ellenőrzéssel."""

    timeChanged = Signal(object)

    def __init__(self, placeholder: str = "00:00:00", parent=None):
        super().__init__(parent)
        self.setPlaceholderText(placeholder)
        self.setMaximumWidth(120)
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.editingFinished.connect(self._commit)
        self._value: float | None = None

    def value(self) -> float | None:
        return self._value

    def set_value(self, seconds: float | None) -> None:
        self._value = seconds
        self.setText(fmt_time(seconds) if seconds is not None else "")
        self._mark(False)

    def _mark(self, invalid: bool) -> None:
        self.setProperty("invalid", "true" if invalid else "false")
        theme.refresh_style(self)

    def _commit(self) -> None:
        try:
            value = parse_time(self.text())
        except ValueError as exc:
            self._mark(True)
            self.setToolTip(str(exc))
            return
        self.setToolTip("")
        self._mark(False)
        self._value = value
        if value is not None:
            self.setText(fmt_time(value))
        self.timeChanged.emit(value)


# --------------------------------------------------------------------------- #
# Állapotjelzők
# --------------------------------------------------------------------------- #

class Spinner(QWidget):
    def __init__(self, size: int = 18, parent=None):
        super().__init__(parent)
        self.setFixedSize(size, size)
        self._angle = 0
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._tick)

    def start(self) -> None:
        self._timer.start(30)
        self.show()

    def stop(self) -> None:
        self._timer.stop()
        self.hide()

    def _tick(self) -> None:
        self._angle = (self._angle + 12) % 360
        self.update()

    def paintEvent(self, _event) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        pen = QPen(theme.qc("accent"), 2.4)
        pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        p.setPen(pen)
        r = self.rect().adjusted(3, 3, -3, -3)
        p.drawArc(r, -self._angle * 16, 270 * 16)


class Banner(QFrame):
    """Szöveges visszajelzés (hiba, figyelmeztetés, információ) műveletgombokkal."""

    ICONS = {"error": ("error", "danger"), "warning": ("alert", "warning"),
             "info": ("info", "accent"), "success": ("check-circle", "success")}

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("banner")
        layout = QHBoxLayout(self)
        layout.setContentsMargins(12, 10, 10, 10)
        layout.setSpacing(10)
        self.icon = IconLabel("info", "accent", 20)
        layout.addWidget(self.icon, 0, Qt.AlignmentFlag.AlignTop)
        texts = QVBoxLayout()
        texts.setSpacing(2)
        self.title = label("", "bannerTitle", wrap=True)
        self.message = label("", None, wrap=True)
        texts.addWidget(self.title)
        texts.addWidget(self.message)
        layout.addLayout(texts, 1)
        self.actions = QHBoxLayout()
        self.actions.setSpacing(6)
        layout.addLayout(self.actions)
        self.close_button = button("", "ghost", "close", "muted", "Bezárás")
        self.close_button.setFixedSize(30, 30)
        self.close_button.clicked.connect(self.hide)
        layout.addWidget(self.close_button, 0, Qt.AlignmentFlag.AlignTop)
        self.hide()

    def show_message(self, kind: str, title: str, message: str = "",
                     actions: Sequence[tuple[str, object]] = ()) -> None:
        self.setProperty("kind", kind)
        name, role = self.ICONS.get(kind, self.ICONS["info"])
        self.icon.set_spec(name, role)
        self.title.setText(title)
        self.message.setText(message)
        self.message.setVisible(bool(message))
        while self.actions.count():
            item = self.actions.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        for text, callback in actions:
            b = button(text)
            b.clicked.connect(callback)
            self.actions.addWidget(b, 0, Qt.AlignmentFlag.AlignTop)
        theme.refresh_style(self)
        self.show()


class ThumbnailView(QWidget):
    """16:9 arányú, lekerekített bélyegkép időtartam-címkével és lejátszás-gombbal."""

    clicked = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._pixmap: QPixmap | None = None
        self.badge = ""
        self.playable = False
        self.placeholder = ""
        self._hover = False
        self.setMinimumSize(240, 135)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        theme.manager.changed.connect(self.update)

    def hasHeightForWidth(self) -> bool:  # noqa: N802
        return True

    def heightForWidth(self, width: int) -> int:  # noqa: N802
        return int(width * 9 / 16)

    def sizeHint(self) -> QSize:
        return QSize(400, 225)

    def set_pixmap(self, pixmap: QPixmap | None) -> None:
        self._pixmap = pixmap
        self.update()

    def set_playable(self, playable: bool) -> None:
        self.playable = playable
        self.setCursor(Qt.CursorShape.PointingHandCursor if playable else Qt.CursorShape.ArrowCursor)
        self.setToolTip("Előnézet lejátszása" if playable else "")
        self.update()

    def enterEvent(self, _event) -> None:  # noqa: N802
        self._hover = True
        self.update()

    def leaveEvent(self, _event) -> None:  # noqa: N802
        self._hover = False
        self.update()

    def mouseReleaseEvent(self, event) -> None:  # noqa: N802
        if self.playable and event.button() == Qt.MouseButton.LeftButton:
            self.clicked.emit()

    def paintEvent(self, _event) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        w = self.width()
        h = min(self.height(), int(w * 9 / 16))
        rect = QRectF(0, (self.height() - h) / 2, w, h)
        path = QPainterPath()
        path.addRoundedRect(rect, 10, 10)
        p.setClipPath(path)
        p.fillRect(rect, theme.qc("track"))
        if self._pixmap and not self._pixmap.isNull():
            scaled = self._pixmap.scaled(rect.size().toSize() * self.devicePixelRatioF(),
                                         Qt.AspectRatioMode.KeepAspectRatioByExpanding,
                                         Qt.TransformationMode.SmoothTransformation)
            scaled.setDevicePixelRatio(self.devicePixelRatioF())
            sw = scaled.width() / scaled.devicePixelRatio()
            sh = scaled.height() / scaled.devicePixelRatio()
            p.drawPixmap(QPointF(rect.center().x() - sw / 2, rect.center().y() - sh / 2), scaled)
        else:
            p.drawPixmap(QPointF(rect.center().x() - 20, rect.center().y() - 28), icons.pixmap("film", theme.c("faint"), 40))
            if self.placeholder:
                p.setPen(theme.qc("muted"))
                p.drawText(rect.adjusted(10, 40, -10, 0), Qt.AlignmentFlag.AlignCenter, self.placeholder)
        if self.playable:
            radius = 28 if self._hover else 25
            center = rect.center()
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(QColor(0, 0, 0, 150))
            p.drawEllipse(center, radius, radius)
            p.drawPixmap(QPointF(center.x() - 13, center.y() - 14), icons.pixmap("play", "#ffffff", 28))
        if self.badge:
            font = QFont(self.font())
            font.setPointSizeF(9)
            font.setWeight(QFont.Weight.DemiBold)
            p.setFont(font)
            fm = QFontMetrics(font)
            bw = fm.horizontalAdvance(self.badge) + 12
            badge = QRectF(rect.right() - bw - 8, rect.bottom() - 26, bw, 20)
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(QColor(0, 0, 0, 180))
            p.drawRoundedRect(badge, 5, 5)
            p.setPen(QColor("#ffffff"))
            p.drawText(badge, Qt.AlignmentFlag.AlignCenter, self.badge)


class Collapsible(QWidget):
    """Összecsukható szakasz a ritkán használt beállításokhoz."""

    def __init__(self, title: str, parent=None):
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)
        self.toggle = QPushButton(title)
        self.toggle.setProperty("variant", "ghost")
        self.toggle.setCheckable(True)
        self.toggle.setCursor(Qt.CursorShape.PointingHandCursor)
        self.toggle.setStyleSheet("text-align: left; padding-left: 2px;")
        set_icon(self.toggle, "chevron-right", "muted", 16)
        self.toggle.toggled.connect(self._toggled)
        layout.addWidget(self.toggle, 0, Qt.AlignmentFlag.AlignLeft)
        self.content = QWidget()
        self.content.setObjectName("transparent")
        self.body = QVBoxLayout(self.content)
        self.body.setContentsMargins(4, 0, 0, 0)
        self.body.setSpacing(10)
        layout.addWidget(self.content)
        self.content.hide()

    def _toggled(self, on: bool) -> None:
        set_icon(self.toggle, "chevron-down" if on else "chevron-right", "muted", 16)
        self.content.setVisible(on)


def duration_text(seconds: float | None) -> str:
    return fmt_duration(seconds)
