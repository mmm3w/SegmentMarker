import json
import os
import sys
import vlc

from PyQt6.QtCore import (
    QAbstractItemModel,
    QEvent,
    QModelIndex,
    QRect,
    QRectF,
    QSize,
    Qt,
    QUrl,
    QTimer,
)
from PyQt6.QtGui import (
    QBrush,
    QColor,
    QDragEnterEvent,
    QDragLeaveEvent,
    QDropEvent,
    QFont,
    QIntValidator,
    QMouseEvent,
    QPaintEvent,
    QPainter,
    QPen,
    QStandardItem,
    QStandardItemModel,
    QGuiApplication,
    QCursor,
    QWheelEvent,
)
from PyQt6.QtWidgets import (
    QApplication,
    QCheckBox,
    QComboBox,
    QFileDialog,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidgetItem,
    QListView,
    QMainWindow,
    QMenu,
    QSlider,
    QPushButton,
    QStyleOptionViewItem,
    QVBoxLayout,
    QWidget,
    QStyleOptionSlider,
    QFrame,
    QStyle,
    QListWidget,
)


class App(QMainWindow):
    def __init__(self):
        super().__init__()
        self.title = "Cutting Board"

        self.width = 800
        self.height = 640

        cp = QGuiApplication.primaryScreen().availableGeometry().center()
        self.left = cp.x() - self.width // 2
        self.top = cp.y() - self.height // 2

        self.setWindowTitle(self.title)
        self.setGeometry(self.left, self.top, self.width, self.height)
        self.setCentralWidget(MyWidget(self))

        self.show()


class VlcController:
    def __init__(self, callback) -> None:
        self.vlcinstance = vlc.Instance()
        self.media = None
        self.mediaplayer = self.vlcinstance.media_player_new()
        self.ispaused = False

        eventmanager = self.mediaplayer.event_manager()
        print(
            "attach position changed",
            eventmanager.event_attach(
                vlc.EventType.MediaPlayerPositionChanged,
                self.poscallback,
                self.mediaplayer,
            ),
        )

        print(
            "attach playing",
            eventmanager.event_attach(
                vlc.EventType.MediaPlayerPlaying,
                self.playingcallback,
            ),
        )

        print(
            "attach pause",
            eventmanager.event_attach(
                vlc.EventType.MediaPlayerPaused,
                self.pausecallback,
            ),
        )

        self.callback = callback

    def loadmedia(self, url, videoframe):
        if not self.ispaused:
            self.play()
            
        if self.media:
            self.media.event_manager().event_detach(vlc.EventType.MediaParsedChanged)
            self.media.release()

        self.media = self.mediaplayer.set_mrl(url)
        eventmanager = self.media.event_manager()
        print(
            "attach media parsed changed",
            eventmanager.event_attach(
                vlc.EventType.MediaParsedChanged, self.parsecallback
            ),
        )
        self.media.parse()
        self.mediaplayer.set_hwnd(int(videoframe.winId()))
        self.play()

    def play(self):
        if self.mediaplayer.is_playing():
            self.mediaplayer.pause()
            self.ispaused = True
        else:
            if self.mediaplayer.play() >= 0:
                self.ispaused = False

    def getvolume(self):
        return self.mediaplayer.audio_get_volume()

    def setvolume(self, vol):
        self.mediaplayer.audio_set_volume(vol)

    def getrate(self):
        return self.mediaplayer.get_rate()

    def gettime(self):
        return self.mediaplayer.get_time()

    def getpostion(self):
        return self.mediaplayer.get_position()

    def setrate(self, rate):
        self.mediaplayer.set_rate(rate)

    def mspf(self):
        return int(1000 // (self.mediaplayer.get_fps() or 25))

    def seekoffset(self, t):
        self.seektime(self.mediaplayer.get_time() + t)

    def seektime(self, t):
        self.mediaplayer.set_time(t)
        if self.ispaused:
            self.callback(
                "Pos",
                {
                    "position": self.mediaplayer.get_position(),
                    "time": self.timeformat(self.mediaplayer.get_time()),
                },
            )

    def seekpostion(self, pos):
        self.mediaplayer.set_position(pos)
        if self.ispaused:
            self.callback(
                "Pos",
                {
                    "position": self.mediaplayer.get_position(),
                    "time": self.timeformat(self.mediaplayer.get_time()),
                },
            )

    ########
    def endcallback(self, event):
        pass

    def playingcallback(self, event):
        self.callback("Playing", None)

    def pausecallback(self, event):
        self.callback("Pause", None)

    def poscallback(self, event, player):
        self.callback(
            "Pos",
            {
                "position": event.u.new_position,
                "time": self.timeformat(player.get_time()),
            },
        )

    def parsecallback(self, event):
        self.callback(
            "Load",
            {
                "length": self.timeformat(self.media.get_duration()),
                "name": self.media.get_meta(0),
            },
        )

    ########
    def timeformat(self, time):
        return "%02d:%02d:%02d.%03d" % (
            time // 3600000,
            time // 60000 % 60,
            time // 1000 % 60,
            time % 1000,
        )


class DisableClickSilder(QSlider):
    def mousePressEvent(self, event: QMouseEvent | None) -> None:
        option = QStyleOptionSlider()
        self.initStyleOption(option)
        rect = self.style().subControlRect(
            QStyle.ComplexControl.CC_Slider,
            option,
            QStyle.SubControl.SC_SliderHandle,
            self,
        )
        if rect.contains(event.pos()):
            super(DisableClickSilder, self).mousePressEvent(event)
            return


class PartMarkSilder(DisableClickSilder):
    def __init__(self, parent):
        super().__init__(parent)
        self.start = -1
        self.end = -1.0
        self.qpen = QPen(QColor(255, 0, 0), 1)

    def paintEvent(self, ev: QPaintEvent | None) -> None:
        super().paintEvent(ev)
        if self.start >= 0 or self.end >= 0:
            markpainter = QPainter(self)
            markpainter.setPen(self.qpen)
            rect: QRectF = self.rect().toRectF()
            rect.adjust(6, 0, -6, 0)
            w = rect.width()
            if self.start >= 0:
                rect.adjust(w * self.start, 0, 0, 0)
                markpainter.drawText(
                    rect,
                    Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft,
                    "|->",
                )

            if self.end >= 0:
                rect.adjust(0, 0, (self.end - 1) * w, 0)
                markpainter.drawText(
                    rect,
                    Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignRight,
                    "<-|",
                )

    def setstart(self, s):
        if s is not None:
            if self.end < 0 or s <= self.end:
                self.start = s
                self.update()
                return True
        return False

    def setend(self, e):
        if e is not None:
            if self.start < 0 or e >= self.start:
                self.end = e
                self.update()
                return True
        return False

    def clearmark(self):
        self.start = -1
        self.end = -1
        self.update()


class SilderLabel(QLabel):
    def __init__(self, text, action):
        super().__init__(text)
        self.action = action

    def wheelEvent(self, ev: QWheelEvent | None) -> None:
        if ev.angleDelta().y() > 0:
            self.action(False)
        elif ev.angleDelta().y() < 0:
            self.action(True)
        else:
            pass


class MyWidget(QWidget):
    def __init__(self, parent: QWidget | None = ...) -> None:
        super().__init__(parent)
        self.setAcceptDrops(True)
        self.support = [".json", ".mp4",".mkv"]
        self.vlccontroller = VlcController(self.vlcevent)
        self.tempstart = -1
        self.tempend = -1
        self.filename = None
        self.filepath = None

        layout = QVBoxLayout()

        self.videoframe = QFrame()
        self.videoframe.setAutoFillBackground(True)
        layout.addWidget(self.videoframe, 1)

        self.positionslider = PartMarkSilder(self)
        self.positionslider.setMaximum(10000)
        self.positionslider.setOrientation(Qt.Orientation.Horizontal)
        self.positionslider.sliderMoved.connect(self.setposition)
        self.positionslider.sliderPressed.connect(self.setposition)
        layout.addWidget(self.positionslider)
        self.seektag = False

        playlayout = QHBoxLayout()
        self.time = QLabel("00:00:00.000")
        self.time.setAlignment(
            Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter
        )
        playlayout.addWidget(self.time, 1)
        self.length = QLabel("/ 00:00:00.000")
        self.length.setAlignment(
            Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter
        )
        playlayout.addWidget(self.length, 1)

        self.title = QLabel()
        self.title.setWordWrap(True)
        playlayout.addWidget(self.title, 4)

        self.playbtn = QPushButton("Play")
        self.playbtn.clicked.connect(lambda e: self.vlccontroller.play())
        playlayout.addWidget(self.playbtn, 1)

        playlayout.addWidget(QLabel("Vol"))
        self.volsilder = DisableClickSilder(self)
        self.volsilder.setOrientation(Qt.Orientation.Horizontal)
        self.volsilder.setMaximum(100)
        self.volsilder.setValue(self.vlccontroller.getvolume())
        self.volsilder.valueChanged.connect(lambda e: self.vlccontroller.setvolume(e))

        playlayout.addWidget(self.volsilder, 1)

        layout.addLayout(playlayout)

        contentlayout = QHBoxLayout()

        seeklayout = QVBoxLayout()
        frameseek = SilderLabel(
            "Frame",
            lambda tag: self.vlccontroller.seekoffset(
                self.vlccontroller.mspf() * (1 if tag else -1)
            ),
        )
        frameseek.setStyleSheet("QLabel{background:#fff;}")
        frameseek.setAlignment(Qt.AlignmentFlag.AlignCenter)
        seeklayout.addWidget(frameseek, 1)

        secseek = SilderLabel(
            "Sec", lambda tag: self.vlccontroller.seekoffset(1000 if tag else -1000)
        )
        secseek.setStyleSheet("QLabel{background:#fff;}")
        secseek.setAlignment(Qt.AlignmentFlag.AlignCenter)
        seeklayout.addWidget(secseek, 1)

        contentlayout.addLayout(seeklayout, 1)

        marklayout = QVBoxLayout()

        self.markstart = QPushButton("Mark Start")
        self.markstart.clicked.connect(lambda: self.marktag(True))
        marklayout.addWidget(self.markstart)
        self.markend = QPushButton("Mark End")
        self.markend.clicked.connect(lambda: self.marktag(False))
        marklayout.addWidget(self.markend)

        self.seekstart = QPushButton("Seek to Start")
        self.seekstart.clicked.connect(lambda: self.seektomark(True))
        marklayout.addWidget(self.seekstart)
        self.seekend = QPushButton("Seek to End")
        self.seekend.clicked.connect(lambda: self.seektomark(False))
        marklayout.addWidget(self.seekend)
        self.addnew = QPushButton("Add New")
        self.addnew.clicked.connect(self.adddata)
        marklayout.addWidget(self.addnew)
        self.exportbutton = QPushButton("Export")
        self.exportbutton.clicked.connect(self.export)
        marklayout.addWidget(self.exportbutton)
        contentlayout.addLayout(marklayout, 1)

        self.listdata = QListWidget(self)
        self.listdata.itemDoubleClicked.connect(self.restoremark)
        self.listdata.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.listdata.customContextMenuRequested.connect(self.deloption)
        contentlayout.addWidget(self.listdata, 2)

        layout.addLayout(contentlayout)
        self.setLayout(layout)

    def vlcevent(self, tag, data):
        if tag == "Load":
            self.title.setText(data["name"])
            self.length.setText("/ " + data["length"])
            self.filename = data["name"]
            self.positionslider.clearmark()
        elif tag == "Pos":
            self.time.setText(data["time"])
            if not self.seektag:
                self.positionslider.setValue(int(data["position"] * 10000))
        elif tag == "Playing":
            self.playbtn.setText("Pause")
        elif tag == "Pause":
            self.playbtn.setText("Play")

    def dragEnterEvent(self, ev: QDragEnterEvent | None) -> None:
        mimedata = ev.mimeData()
        url: QUrl = mimedata.urls()[0]
        suffix = os.path.splitext(url.fileName())[-1]
        if suffix in self.support:
            ev.accept()
            self.setStyleSheet("QWidget{background:#fff6f6;}")

    def dragLeaveEvent(self, ev: QDragLeaveEvent | None) -> None:
        ev.ignore()
        self.setStyleSheet("QWidget{background:#fff;}")

    def dropEvent(self, ev: QDropEvent | None) -> None:
        self.setStyleSheet("QWidget{}")
        mimedata = ev.mimeData()
        url: QUrl = mimedata.urls()[0]
        self.filepath = url.path()[1:]
        if os.path.splitext(url.fileName())[-1] != ".json":
            self.listdata.clear()
            self.vlccontroller.loadmedia(self.filepath, self.videoframe)
        else:
            with open(self.filepath, "r", encoding="utf-8") as f:
                data = json.load(f)
                if data["filepath"] and os.path.exists(data["filepath"]):
                    self.listdata.clear()
                    self.filepath = data["filepath"]
                    list = data["clip"]
                    for item in list:
                        data = QListWidgetItem(
                            "{0}~{1}".format(
                                self.vlccontroller.timeformat(item["start"]),
                                self.vlccontroller.timeformat(item["end"]),
                            )
                        )

                        data.setData(Qt.ItemDataRole.UserRole, item)

                        self.listdata.addItem(data)
                    self.vlccontroller.loadmedia(self.filepath, self.videoframe)

    def setposition(self):
        self.seektag = True
        pos = self.positionslider.value()
        self.vlccontroller.seekpostion(pos / 10000)
        self.seektag = False

    def marktag(self, isstart):
        t = self.vlccontroller.gettime()
        pos = self.vlccontroller.getpostion()

        if isstart:
            if self.positionslider.setstart(pos):
                self.tempstart = t
        else:
            if self.positionslider.setend(pos):
                self.tempend = t

    def seektomark(self, isstart):
        if isstart:
            if self.tempstart >= 0:
                self.vlccontroller.seektime(self.tempstart)
        else:
            if self.tempend >= 0:
                self.vlccontroller.seektime(self.tempend)

    def adddata(self):
        if self.tempstart >= 0 and self.tempend >= 0:
            data = QListWidgetItem(
                "{0}~{1}".format(
                    self.vlccontroller.timeformat(self.tempstart),
                    self.vlccontroller.timeformat(self.tempend),
                )
            )

            data.setData(
                Qt.ItemDataRole.UserRole,
                {
                    "start": self.tempstart,
                    "startpos": self.positionslider.start,
                    "end": self.tempend,
                    "endpos": self.positionslider.end,
                },
            )

            self.listdata.addItem(data)

            self.tempstart = -1
            self.tempend = -1
            self.positionslider.clearmark()

    def restoremark(self, item: QListWidgetItem):
        data = item.data(Qt.ItemDataRole.UserRole)
        currenttime = self.vlccontroller.gettime()
        if self.positionslider.setstart(data["startpos"]):
            self.tempstart = data["start"]

        if self.positionslider.setend(data["endpos"]):
            self.tempend = data["end"]

        if currenttime < self.tempstart or currenttime > self.tempend:
            self.vlccontroller.seektime(self.tempstart)

    def deloption(self):
        row = self.listdata.currentRow()
        if row >= 0:
            menu = QMenu()
            delaction = menu.addAction("Delete")
            action = menu.exec(QCursor.pos())
            if action == delaction:
                self.listdata.takeItem(row)

    def export(self):
        if self.filename and self.filepath and self.listdata.count() > 0:
            p = os.path.join(
                os.path.dirname(self.filepath),
                os.path.splitext(self.filename)[0] + ".json",
            )
            dir = QFileDialog.getSaveFileName(
                self, "Save To...", p, "Json Files (*.json);"
            )
            if dir[0]:
                outputdata = {
                    "filename": self.filename,
                    "filepath": self.filepath,
                }

                clip = []

                for i in range(self.listdata.count()):
                    clip.append(self.listdata.item(i).data(Qt.ItemDataRole.UserRole))
                outputdata["clip"] = clip

                with open(dir[0], "wb") as fd:
                    fd.write(json.dumps(outputdata, ensure_ascii=False).encode("utf-8"))


if __name__ == "__main__":
    # log_dir = os.path.join(os.getcwd(), "log")
    # if not os.path.exists(log_dir):
    #     os.mkdir(log_dir)
    # cgitb.enable(format="txt", logdir=log_dir)

    app = QApplication(sys.argv)
    ex = App()
    sys.exit(app.exec())
