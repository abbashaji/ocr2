"""Image viewer: zoom, pan, word overlays with selection sync."""

from __future__ import annotations

from typing import Optional

from PySide6.QtCore import QEasingCurve, QPointF, QRectF, Qt, QVariantAnimation, Signal
from PySide6.QtGui import QBrush, QImage, QPainter, QPen, QPixmap, QTransform, QWheelEvent
from PySide6.QtWidgets import (
    QFrame, QGraphicsPixmapItem, QGraphicsRectItem, QGraphicsScene, QGraphicsView,
    QHBoxLayout, QLabel, QStackedLayout, QVBoxLayout, QWidget,
)

from matnyab.api import OcrResult
from matnyab.ui import theme
from matnyab.ui.format import fa_percent
from matnyab.ui.models import uncertain_level
from matnyab.ui.strings import S
from matnyab.ui.widgets import IconLabel, tool_button

__all__ = ["ImageView", "ViewerPane", "MIN_ZOOM", "MAX_ZOOM"]

MIN_ZOOM, MAX_ZOOM = 0.05, 8.0
FIT_MARGIN = 12
FIT_MAX = 2.0
WHEEL_STEP = 1.18


class ImageView(QGraphicsView):
    zoomChanged = Signal(float)
    wordClicked = Signal(int)
    fitModeChanged = Signal(bool)

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        # Images are never mirrored: keep the view itself left-to-right so that
        # scrollbars and panning behave naturally.
        self.setLayoutDirection(Qt.LeftToRight)
        self._scene = QGraphicsScene(self)
        self.setScene(self._scene)
        self.setAcceptDrops(False)
        self.viewport().setAcceptDrops(False)
        self.setRenderHints(QPainter.Antialiasing | QPainter.SmoothPixmapTransform)
        self.setDragMode(QGraphicsView.ScrollHandDrag)
        self.setAlignment(Qt.AlignCenter)
        self.setFrameShape(QFrame.NoFrame)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        self.setTransformationAnchor(QGraphicsView.NoAnchor)
        self.setResizeAnchor(QGraphicsView.NoAnchor)
        self.setFocusPolicy(Qt.StrongFocus)
        self.setAccessibleName(S.viewer_access)
        self.setAccessibleDescription(S.viewer_access_desc)

        self._pix_item: Optional[QGraphicsPixmapItem] = None
        self._image_size = (0, 0)
        self._zoom = 1.0
        self._fit = True
        self._target = 1.0
        self._words: list[tuple[QRectF, float, str]] = []
        self._word_items: list[QGraphicsRectItem] = []
        self._line_items: list[QGraphicsRectItem] = []
        self._sel_item: Optional[QGraphicsRectItem] = None
        self._selected = -1
        self._highlight = True
        self._show_boxes = False
        self._press_pos: Optional[QPointF] = None
        self._anim = QVariantAnimation(self)
        self._anim.setDuration(140)
        self._anim.setEasingCurve(QEasingCurve.OutCubic)
        self._anim.valueChanged.connect(self._on_anim)
        self._anim_anchor: Optional[tuple[QPointF, QPointF]] = None
        theme.manager().changed.connect(self._restyle)

    # ------------------------------------------------------------ image ---
    @property
    def has_image(self) -> bool:
        return self._pix_item is not None

    @property
    def zoom(self) -> float:
        return self._zoom

    @property
    def fit_mode(self) -> bool:
        return self._fit

    def set_image(self, image: Optional[QImage]) -> None:
        self._anim.stop()
        self._scene.clear()
        self._pix_item = None
        self._word_items, self._line_items, self._sel_item = [], [], None
        self._words = []
        self._selected = -1
        if image is None or image.isNull():
            self._image_size = (0, 0)
            self.setSceneRect(QRectF())
            return
        pix = QPixmap.fromImage(image)
        self._pix_item = self._scene.addPixmap(pix)
        self._pix_item.setTransformationMode(Qt.SmoothTransformation)
        self._pix_item.setZValue(0)
        self._image_size = (image.width(), image.height())
        self.setSceneRect(QRectF(0, 0, image.width(), image.height()))
        self._fit = True
        self.fit_to_window()

    def clear(self) -> None:
        self.set_image(None)

    # ---------------------------------------------------------- overlays ---
    def set_result(self, result: Optional[OcrResult]) -> None:
        for it in self._word_items + self._line_items:
            self._scene.removeItem(it)
        if self._sel_item is not None:
            self._scene.removeItem(self._sel_item)
        self._word_items, self._line_items, self._sel_item = [], [], None
        self._words = []
        self._selected = -1
        if result is None or self._pix_item is None:
            return
        for line in result.lines:
            if line.box is not None:
                r = QRectF(line.box[0], line.box[1], line.box[2] - line.box[0], line.box[3] - line.box[1])
                item = self._scene.addRect(r)
                item.setZValue(1)
                self._line_items.append(item)
            for word in line.words:
                if word.box is None:
                    self._words.append((QRectF(), word.confidence, word.text))
                    continue
                b = word.box
                rect = QRectF(b[0], b[1], b[2] - b[0], b[3] - b[1])
                self._words.append((rect, word.confidence, word.text))
        for rect, conf, text in self._words:
            item = self._scene.addRect(rect)
            item.setZValue(2)
            item.setToolTip(f"{text}\n{S.chip_confidence.format(label=S.conf_low if conf < 80 else S.conf_high, pct=fa_percent(conf))}")
            self._word_items.append(item)
        self._sel_item = self._scene.addRect(QRectF())
        self._sel_item.setZValue(3)
        self._sel_item.setVisible(False)
        self._restyle()

    def _restyle(self) -> None:
        c = theme.color
        for item in self._line_items:
            pen = QPen(c("accent", 150), 1, Qt.DotLine)
            pen.setCosmetic(True)
            item.setPen(pen)
            item.setBrush(Qt.NoBrush)
            item.setVisible(self._show_boxes)
        for item, (rect, conf, _t) in zip(self._word_items, self._words):
            level = uncertain_level(conf)
            item.setVisible(not rect.isNull() and (self._show_boxes or (self._highlight and level > 0)))
            if level == 2:
                pen = QPen(c("error_line"), 3, Qt.DashLine)
                brush = QBrush(c("error_line", 70))
            elif level == 1:
                pen = QPen(c("warning_line"), 2, Qt.SolidLine)
                brush = QBrush(c("warning_line", 60))
            else:
                pen = QPen(c("text_muted", 170), 1)
                brush = Qt.NoBrush
            pen.setCosmetic(True)
            item.setPen(pen)
            item.setBrush(brush)
        if self._sel_item is not None:
            pen = QPen(c("accent"), 3)
            pen.setCosmetic(True)
            self._sel_item.setPen(pen)
            self._sel_item.setBrush(QBrush(c("accent", 45)))
        self.viewport().update()

    def set_highlight(self, on: bool) -> None:
        self._highlight = on
        self._restyle()

    def set_show_boxes(self, on: bool) -> None:
        self._show_boxes = on
        self._restyle()

    @property
    def visible_overlay_count(self) -> int:
        return sum(1 for it in self._word_items if it.isVisible())

    @property
    def selected_word(self) -> int:
        return self._selected

    def set_selected_word(self, index: int, ensure_visible: bool = True) -> None:
        self._selected = index
        if self._sel_item is None:
            return
        if 0 <= index < len(self._words) and not self._words[index][0].isNull():
            rect = self._words[index][0].adjusted(-3, -3, 3, 3)
            self._sel_item.setRect(rect)
            self._sel_item.setVisible(True)
            if ensure_visible:
                visible = self.mapToScene(self.viewport().rect()).boundingRect()
                if not visible.contains(rect):
                    self.ensureVisible(rect, 60, 60)
        else:
            self._sel_item.setVisible(False)

    def word_at(self, scene_pos: QPointF) -> int:
        best, best_area = -1, 0.0
        for i, (rect, _c, _t) in enumerate(self._words):
            if not rect.isNull() and rect.contains(scene_pos):
                area = rect.width() * rect.height()
                if best < 0 or area < best_area:
                    best, best_area = i, area
        return best

    def word_rect(self, index: int) -> QRectF:
        return self._words[index][0]

    # -------------------------------------------------------------- zoom ---
    def _fit_scale(self) -> float:
        iw, ih = self._image_size
        if iw <= 0 or ih <= 0:
            return 1.0
        vw = max(1, self.viewport().width() - 2 * FIT_MARGIN)
        vh = max(1, self.viewport().height() - 2 * FIT_MARGIN)
        return max(MIN_ZOOM, min(FIT_MAX, vw / iw, vh / ih))

    def _apply_scale(self, scale: float, anchor: Optional[tuple[QPointF, QPointF]] = None) -> None:
        scale = max(MIN_ZOOM, min(MAX_ZOOM, scale))
        self.setTransform(QTransform.fromScale(scale, scale))
        self._zoom = scale
        if anchor is not None:
            scene_pt, view_pt = anchor
            centre = QPointF(self.viewport().width() / 2, self.viewport().height() / 2)
            self.centerOn(scene_pt + (centre - view_pt) / scale)
        self.zoomChanged.emit(scale)

    def fit_to_window(self) -> None:
        self._anim.stop()
        if not self._fit:
            self._fit = True
            self.fitModeChanged.emit(True)
        self._apply_scale(self._fit_scale())
        self._target = self._zoom
        if self._pix_item is not None:
            self.centerOn(self._pix_item)

    def set_zoom(self, scale: float, anchor_view: Optional[QPointF] = None, animated: bool = True) -> None:
        if not self.has_image:
            return
        scale = max(MIN_ZOOM, min(MAX_ZOOM, scale))
        if self._fit:
            self._fit = False
            self.fitModeChanged.emit(False)
        if anchor_view is None:
            anchor_view = QPointF(self.viewport().width() / 2, self.viewport().height() / 2)
        anchor = (self.mapToScene(anchor_view.toPoint()), anchor_view)
        self._target = scale
        self._anim.stop()
        if not animated or not theme.animations_enabled() or abs(scale - self._zoom) < 1e-3:
            self._apply_scale(scale, anchor)
            return
        self._anim_anchor = anchor
        self._anim.setStartValue(self._zoom)
        self._anim.setEndValue(scale)
        self._anim.start()

    def _on_anim(self, value) -> None:
        self._apply_scale(float(value), self._anim_anchor)

    def zoom_in(self) -> None:
        self.set_zoom(self._target * WHEEL_STEP)

    def zoom_out(self) -> None:
        self.set_zoom(self._target / WHEEL_STEP)

    def actual_size(self) -> None:
        self.set_zoom(1.0)

    # ------------------------------------------------------------ events ---
    def wheelEvent(self, event: QWheelEvent) -> None:
        if event.modifiers() & Qt.ControlModifier:
            notches = event.angleDelta().y() / 120.0
            if notches:
                self.set_zoom(self._target * (WHEEL_STEP ** notches), event.position())
            event.accept()
            return
        super().wheelEvent(event)

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        if self._fit and self.has_image:
            self._apply_scale(self._fit_scale())
            self._target = self._zoom
            if self._pix_item is not None:
                self.centerOn(self._pix_item)

    def mousePressEvent(self, event) -> None:
        if event.button() == Qt.LeftButton:
            self._press_pos = event.position()
        super().mousePressEvent(event)

    def mouseReleaseEvent(self, event) -> None:
        was_click = (
            event.button() == Qt.LeftButton and self._press_pos is not None
            and (event.position() - self._press_pos).manhattanLength() < 5
        )
        super().mouseReleaseEvent(event)
        if was_click and self.has_image:
            idx = self.word_at(self.mapToScene(event.position().toPoint()))
            if idx >= 0:
                self.set_selected_word(idx, ensure_visible=False)
                self.wordClicked.emit(idx)
        self._press_pos = None


class ViewerPane(QWidget):
    """Toolbar + image view + placeholder page."""

    wordClicked = Signal(int)

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setObjectName("viewerPane")
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        bar = QFrame()
        bar.setObjectName("toolbar")
        bar.setFixedHeight(48)
        bl = QHBoxLayout(bar)
        bl.setContentsMargins(theme.SP_2, theme.SP_1, theme.SP_2, theme.SP_1)
        bl.setSpacing(2)
        self.btn_out = tool_button("zoom_out", S.zoom_out, "Ctrl+-")
        self.zoom_btn = tool_button(None, S.zoom_actual, "Ctrl+1", label=fa_percent(100))
        self.zoom_btn.setMinimumWidth(52)
        self.zoom_btn.setAccessibleName(S.zoom_label_access)
        self.btn_in = tool_button("zoom_in", S.zoom_in, "Ctrl+=")
        self.btn_fit = tool_button("fit", S.zoom_fit, "Ctrl+0", checkable=True)
        self.btn_highlight = tool_button("highlight", S.highlight_uncertain, checkable=True)
        self.btn_boxes = tool_button("boxes", S.show_boxes, checkable=True)
        self.btn_highlight.setChecked(True)
        for b in (self.btn_out, self.zoom_btn, self.btn_in, self.btn_fit):
            bl.addWidget(b)
        bl.addSpacing(theme.SP_1)
        bl.addWidget(self.btn_highlight)
        bl.addWidget(self.btn_boxes)
        bl.addStretch(1)
        root.addWidget(bar)

        host = QWidget()
        self._stack = QStackedLayout(host)
        self.view = ImageView()
        self._placeholder = QWidget()
        pl = QVBoxLayout(self._placeholder)
        pl.setAlignment(Qt.AlignCenter)
        pl.setSpacing(theme.SP_2)
        self._ph_icon = IconLabel("photo_off", "text_muted", 40)
        self._ph_title = QLabel(S.viewer_no_image)
        self._ph_title.setProperty("role", "h3")
        self._ph_title.setAlignment(Qt.AlignCenter)
        self._ph_hint = QLabel(S.viewer_no_image_hint)
        self._ph_hint.setProperty("role", "muted")
        self._ph_hint.setAlignment(Qt.AlignCenter)
        self._ph_hint.setWordWrap(True)
        pl.addWidget(self._ph_icon, 0, Qt.AlignHCenter)
        pl.addWidget(self._ph_title)
        pl.addWidget(self._ph_hint)
        self._stack.addWidget(self.view)
        self._stack.addWidget(self._placeholder)
        root.addWidget(host, 1)

        self.btn_out.clicked.connect(self.view.zoom_out)
        self.btn_in.clicked.connect(self.view.zoom_in)
        self.zoom_btn.clicked.connect(self.view.actual_size)
        self.btn_fit.clicked.connect(self._on_fit_clicked)
        self.btn_highlight.toggled.connect(self.view.set_highlight)
        self.btn_boxes.toggled.connect(self.view.set_show_boxes)
        self.view.zoomChanged.connect(self._on_zoom)
        self.view.fitModeChanged.connect(self.btn_fit.setChecked)
        self.view.wordClicked.connect(self.wordClicked)
        self.btn_fit.setChecked(True)
        self.setTabOrder(self.btn_out, self.zoom_btn)
        self.setTabOrder(self.zoom_btn, self.btn_in)
        self.setTabOrder(self.btn_in, self.btn_fit)
        self.setTabOrder(self.btn_fit, self.btn_highlight)
        self.setTabOrder(self.btn_highlight, self.btn_boxes)
        self.setTabOrder(self.btn_boxes, self.view)

    def _on_fit_clicked(self) -> None:
        self.view.fit_to_window()
        self.btn_fit.setChecked(True)

    def _on_zoom(self, z: float) -> None:
        self.zoom_btn.setText(fa_percent(z * 100))

    def show_image(self, image: Optional[QImage]) -> None:
        self.view.set_image(image)
        self._stack.setCurrentWidget(self.view)

    def show_placeholder(self, title: str, hint: str, icon: str = "photo_off") -> None:
        self.view.clear()
        self._ph_title.setText(title)
        self._ph_hint.setText(hint)
        self._ph_icon.set_icon(icon)
        self._stack.setCurrentWidget(self._placeholder)

    @property
    def placeholder_visible(self) -> bool:
        return self._stack.currentWidget() is self._placeholder

    def set_enabled_tools(self, enabled: bool) -> None:
        for b in (self.btn_out, self.btn_in, self.zoom_btn, self.btn_fit,
                  self.btn_highlight, self.btn_boxes):
            b.setEnabled(enabled)
