#!/usr/bin/python3
"""
    Bandmap view for Tlf

    Usage:  ./tlf_bandmap.py [band]

    Needs PyQt5: apt install python3-pyqt5
"""

import sys, os
from PyQt5.QtWidgets import QWidget, QApplication, QComboBox, QDesktopWidget
from PyQt5.QtGui import QPainter, QColor, QFont, QPen
from PyQt5.QtCore import Qt, QTimer, QDateTime, QFileSystemWatcher, QMutex

BMDATA_FILE = os.path.expanduser('~/.bmdata.dat')

#############
class Band:
    def __init__(self, meter, fmin, fmax):
        self.meter = meter
        self.fmin = fmin
        self.fmax = fmax

# focusing on CW
BANDS = [
    Band(160, 1_800_000,  1_838_000),
    Band(80,  3_500_000,  3_580_000),
    Band(40,  7_000_000,  7_040_000),
    Band(20, 14_000_000, 14_070_000),
    Band(15, 21_000_000, 21_070_000),
    Band(10, 28_000_000, 28_070_000),
]

#############
class Spot:
    def __init__(self, freq, call, timeout, dupe):
        self.freq = freq
        self.call = call
        self.timeout = timeout
        self.dupe = dupe

    @staticmethod
    def parse(input):
        a = input.split(';')
        if len(a) < 10:
            return None

        return Spot(int(a[1]), a[0], int(a[5]), a[6] != '0')

#############
class TlfBandmap(QWidget):

    def __init__(self, band):
        super().__init__()

        self.mutex = QMutex()
        self.band = None
        self.select_band(band)
        if not self.band:
            print(f'Unknown band {band}, exiting')
            sys.exit(1)

        self.spots = []

        self.fs_watcher = QFileSystemWatcher()
        self.fs_watcher.fileChanged.connect(self.file_changed)
        if os.path.exists(BMDATA_FILE):
            self.load_spots(BMDATA_FILE)
            self.fs_watcher.addPath(BMDATA_FILE)

        self.timer = QTimer()
        self.timer.timeout.connect(self.watchdog)
        self.timer.start(2000)

        current_index = [b.meter for b in BANDS].index(self.band)
        band_names = [f'{b.meter} m' for b in BANDS]

        self.comboBox = QComboBox(self)
        self.comboBox.setGeometry(125, 5, 70, 20)
        self.comboBox.addItems(band_names)
        self.comboBox.setCurrentIndex(current_index)
        self.comboBox.currentTextChanged.connect(self.on_band_changed)

        self.setGeometry(300, 300, 200, 500)
        self.setMinimumSize(200, 500)

        geo = self.frameGeometry()
        cp = QDesktopWidget().availableGeometry().center()
        geo.moveCenter(cp)
        self.move(geo.topLeft())

        self.show()


    def select_band(self, meter):
        for band in BANDS:
            if band.meter != meter:
                continue
            self.mutex.lock()
            self.band = meter
            self.FMIN = band.fmin
            self.FMAX = band.fmax
            self.f1 = band.fmin
            self.f2 = band.fmax
            self.set_ticks()
            self.mutex.unlock()
            break

    def px_per_hz(self):
        return self.size().height() / (self.f2 - self.f1)

    def paintEvent(self, event):
        qp = QPainter()
        qp.begin(self)
        self.draw_bandmap(qp)
        qp.end()

    def draw_bandmap(self, qp):
        size = self.size()
        if size.width() <= 1 or size.height() <= 1:
            return

        self.mutex.lock()

        #
        # draw frequency scale
        #
        scale_x = size.width()/3
        qp.setPen(QPen(Qt.black, 1, Qt.SolidLine))
        qp.drawLine(scale_x, 0, scale_x, size.height())
        qp.setFont(QFont('Decorative', 8))
        b = self.px_per_hz()
        tf1 = int(self.f1 / self.tick_minor) * self.tick_minor
        tf2 = (1 + int(self.f2 / self.tick_minor)) * self.tick_minor
        for f in range(tf1, tf2, self.tick_minor):
            if f < self.f1 or f > self.f2:
                continue
            y = b * (f - self.f1)
            tick_size = 5       # minor tick
            if (f % self.tick_major) == 0:
                tick_size = 10  # major tick
            qp.drawLine(scale_x - tick_size, y, scale_x, y)
            if (f % self.tick_major) != 0:
                continue
            qp.drawText(scale_x - 45, y + 8/2, f'{int(f/1000)}')

        #
        # show spots
        #
        non_dupe_color = QColor(168, 34, 3)
        dupe_color = Qt.gray
        new_color = Qt.blue
        normal_font = QFont('Monospace', 10)
        new_font = QFont('Monospace', 10, QFont.Bold, True)
        ymin = 0
        text_x = self.width()/2
        for s in self.spots:
            if s.freq < self.f1:
                continue
            if s.freq > self.f2 or ymin > self.height():
                break
            y = b * (s.freq - self.f1)
            text_y = y
            if text_y < ymin:
                text_y = ymin
            if s.dupe:
                qp.setPen(dupe_color)
                qp.setFont(normal_font)
            else:
                if s.timeout > 855:
                    qp.setPen(new_color)
                    qp.setFont(new_font)
                else:
                    qp.setPen(non_dupe_color)
                    qp.setFont(normal_font)
            qp.drawText(text_x, text_y + 5, s.call)
            qp.drawLine(scale_x + 5, y, text_x - 5, text_y)
            ymin = text_y + 10

        #
        # count spots
        #
        n_spots = 0
        for s in self.spots:
            if s.freq < self.FMIN:
                continue
            if s.freq > self.FMAX:
                break
            n_spots = n_spots + 1

        self.setWindowTitle(f'{self.band} m: {n_spots} spots')
        self.mutex.unlock()

    def on_band_changed(self,value):
        self.select_band(int(value.split(' ')[0]))
        self.repaint()

    def watchdog(self):
        files = self.fs_watcher.files()     # check fsWatcher
        if BMDATA_FILE in files:
            return
        if os.path.exists(BMDATA_FILE):
            self.fs_watcher.addPath(BMDATA_FILE)
            self.file_changed(BMDATA_FILE)
            

    def wheelEvent(self, event):
        factor = 1.2                    # down: zoom out
        if event.angleDelta().y() > 0:  # up: zoom in
            factor = 1 / factor

        self.mutex.lock()
        b = self.px_per_hz()
        f_center = self.f1 + event.y() / b
        f_diff1 = factor * (f_center - self.f1)
        f_diff2 = factor * (self.f2 - f_center)

        f1a = int(f_center - f_diff1)
        f2a = int(f_center + f_diff2)
        f_diff = f2a - f1a

        if f_diff > self.FMAX - self.FMIN:
            self.f1 = self.FMIN
            self.f2 = self.FMAX
            self.mutex.unlock()
            self.repaint()
            return

        if f_diff < 3_000:
            self.mutex.unlock()
            return

        d = 0
        if f1a < self.FMIN:
            d = self.FMIN - f1a
        if f2a > self.FMAX:
            d = self.FMAX - f2a

        f1a = f1a + d
        f2a = f2a + d

        self.f1 = f1a
        self.f2 = f2a
        self.set_ticks()
        self.mutex.unlock()
        self.repaint()


    def set_ticks(self):
        f_diff = self.f2 - self.f1
        if f_diff < 5_000:
            self.tick_major = 1_000
            self.tick_minor = 200
        elif f_diff < 10_000:
            self.tick_major = 2_000
            self.tick_minor = 500
        elif f_diff < 30_000:
            self.tick_major = 5_000
            self.tick_minor = 1_000
        else:
            self.tick_major = 10_000
            self.tick_minor = 2_000


    def keyPressEvent(self, event):
        if event.key() == Qt.Key_Escape:
            self.close()


    def file_changed(self, fname):
        size = 0
        if os.path.exists(fname):
            self.load_spots(fname)
        else:
            self.spots = []
        self.repaint()


    def load_spots(self, fname):
        with open(fname) as f:
            self.mutex.lock()
            self.spots = []
            for line in f:
                spot = Spot.parse(line)
                if spot:
                    self.spots.append(spot)

            self.mutex.unlock()



#################################################

def main():
    band = 40
    if len(sys.argv) >= 2:
        try:
            band = int(sys.argv[1])
        except ValueError:
            band = sys.argv[1]      # just to show the right error message

    app = QApplication(sys.argv)
    ex = TlfBandmap(band)
    sys.exit(app.exec_())


if __name__ == '__main__':
    main()

