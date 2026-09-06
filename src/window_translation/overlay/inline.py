"""Click-through translation panels in original text coordinates."""
from PySide6.QtCore import Qt, QRectF
from PySide6.QtGui import QColor, QFont, QFontMetricsF, QPainter
from PySide6.QtWidgets import QWidget


class InlineOverlay(QWidget):
    def __init__(self, settings):
        super().__init__()
        self.settings = settings
        self.blocks = []
        self.image_size = (1, 1)
        self.setWindowFlags(Qt.WindowType.FramelessWindowHint | Qt.WindowType.Tool |
                            Qt.WindowType.WindowStaysOnTopHint | Qt.WindowType.WindowTransparentForInput |
                            Qt.WindowType.WindowDoesNotAcceptFocus)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)

    def present(self, blocks, image_size, region):
        self.blocks, self.image_size = blocks, image_size
        self.place(region)
        self.update()

    def place(self, region):
        self.setGeometry(region.left, region.top, region.width, region.height)

    def clear(self):
        self.blocks = []
        self.hide()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.TextAntialiasing)
        sx, sy = self.width()/self.image_size[0], self.height()/self.image_size[1]
        flags = Qt.AlignmentFlag.AlignCenter | Qt.TextFlag.TextWordWrap
        for block, translated in self.blocks:
            rect = QRectF(block.left*sx-3, block.top*sy-3,
                          block.width*sx+6, block.height*sy+6).intersected(QRectF(self.rect()))
            if rect.isEmpty():
                continue
            font = QFont(self.settings.overlay_font_family or 'Malgun Gothic')
            font.setPointSize(self.settings.overlay_font_size)
            while font.pointSize() > 6:
                metrics = QFontMetricsF(font)
                if metrics.boundingRect(rect.adjusted(3, 2, -3, -2), flags, translated).height() <= rect.height()-4:
                    break
                font.setPointSize(font.pointSize()-1)
            painter.save()
            painter.setClipRect(rect)
            painter.fillRect(rect, QColor(250, 250, 250, round(255*self.settings.overlay_opacity)))
            painter.setPen(QColor('#151515'))
            painter.setFont(font)
            painter.drawText(rect.adjusted(3, 2, -3, -2), flags, translated)
            painter.restore()
