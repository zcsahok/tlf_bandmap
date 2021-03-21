#!/usr/bin/python3
"""
    Bandmap view for Tlf

    Usage:  ./tlf_bandmap.py [-d DIR] [-w] [-c | -s | -m] [band]

    Needs PyQt5 and hamlib: apt install python3-pyqt5 python3-libhamlib2
"""

import sys, os, argparse, math, signal
from PyQt5.QtWidgets import QWidget, QApplication, QComboBox, QDesktopWidget
from PyQt5.QtWidgets import QCheckBox
from PyQt5.QtGui import QPainter, QColor, QFont, QPen, QPolygon, QBrush
from PyQt5.QtCore import Qt, QTimer, QDateTime, QFileSystemWatcher, QMutex, pyqtSignal, QPoint

import Hamlib

BMDATA_FILE = '.bmdata.dat'

#############
class Band:
    def __init__(self, meter, fmin, fcw, fssb, fmax, warc):
        self.meter = meter
        self.fmin = fmin
        self.fcw = fcw
        self.fssb = fssb
        self.fmax = fmax
        self.warc = warc

    def __str__(self):
        return f'{self.meter} m'

BANDS = [
    Band(160, 1_800_000,  1_838_000,  1_840_000,  2_000_000, False),
    Band(80,  3_500_000,  3_580_000,  3_600_000,  4_000_000, False),
    Band(60,  5_250_000,  5_354_000,  5_354_000,  5_450_000, True),
    Band(40,  7_000_000,  7_040_000,  7_040_000,  7_300_000, False),
    Band(30, 10_100_000, 10_140_000,       None, 10_150_000, True),
    Band(20, 14_000_000, 14_070_000, 14_100_000, 14_350_000, False),
    Band(17, 18_068_000, 18_095_000, 18_120_000, 18_168_000, True),
    Band(15, 21_000_000, 21_070_000, 21_150_000, 21_450_000, False),
    Band(12, 24_890_000, 24_915_000, 24_930_000, 24_990_000, True),
    Band(10, 28_000_000, 28_070_000, 28_300_000, 29_700_000, False),
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

    qsy = pyqtSignal(int)

    def __init__(self, args):
        super().__init__()

        self.mutex = QMutex()

        if args.ssb:
            self.mode = 'ssb'
        elif args.mixed:
            self.mode = 'mixed'
        else:
            self.mode = 'cw'

        self.freq_store = {}
        self.select_band(args.band)
        self.spots = []
        self.bmdata = args.bmdata
        self.pan_base_y = None
        self.pan_base_f1 = None
        self.pan_base_f2 = None
        self.current_frequency = 0

        self.fs_watcher = QFileSystemWatcher()
        self.fs_watcher.fileChanged.connect(self.file_changed)
        if os.path.exists(self.bmdata):
            self.load_spots(self.bmdata)
            self.fs_watcher.addPath(self.bmdata)

        self.timer = QTimer()
        self.timer.timeout.connect(self.watchdog)
        self.timer.start(2000)

        if args.warc:
            self.meter_list = [b.meter for b in BANDS]
            if self.mode == 'ssb':
                self.meter_list.remove(30)
        else:
            self.meter_list = list(
                                map(lambda b: b.meter,
                                    filter(lambda b: not b.warc,
                                        BANDS)))

        current_index = self.meter_list.index(self.band)
        band_names = [f' {m:>3} m' for m in self.meter_list]

        self.comboBox = QComboBox(self)
        self.comboBox.setGeometry(125, 5, 70, 20)
        self.comboBox.addItems(band_names)
        self.comboBox.setCurrentIndex(current_index)
        self.comboBox.currentTextChanged.connect(self.on_band_changed)
        self.comboBox.setStyleSheet("QComboBox{"
                                     "background-color: lightgray;"
                                     "}")

        self.dupeSwitch = QCheckBox('Dupes', self)
        self.dupeSwitch.setGeometry(160, 30, 70, 20)
        self.dupeSwitch.setChecked(True)
        self.dupeSwitch.stateChanged.connect(self.on_dupe_toggled)

        self.setGeometry(300, 300, 230, 500)
        self.setMinimumSize(200, 500)
        self.setStyleSheet("background-color: #aaaaaa;")

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
            if self.mode == 'ssb':
                self.FMIN = band.fssb
                self.FMAX = band.fmax
            elif self.mode == 'mixed':
                self.FMIN = band.fmin
                self.FMAX = band.fmax
            elif self.mode == 'cw':
                self.FMIN = band.fmin
                self.FMAX = band.fcw

            if self.band in self.freq_store:
                (fa, fb) = self.freq_store[self.band]
            else:
                fa = self.FMIN
                fb = self.FMAX

            self.set_range(fa, fb)
            self.mutex.unlock()
            break

    def set_range(self, f1, f2):
        self.f1 = f1
        self.f2 = f2
        self.freq_store[self.band] = (self.f1, self.f2)
        self.set_ticks()

    def px_per_hz(self):
        return self.size().height() / (self.f2 - self.f1)

    def paintEvent(self, event):
        qp = QPainter()
        qp.begin(self)
        self.draw_bandmap(qp)
        self.comboBox.setGeometry(self.size().width() - 75, 5, 70, 20)
        qp.end()

    def draw_bandmap(self, qp):
        size = self.size()
        if size.width() <= 1 or size.height() <= 1:
            return

        self.mutex.lock()

        #
        # draw frequency scale
        #
        scale_x = size.width() * 0.25
        qp.setPen(QPen(Qt.black, 1, Qt.SolidLine))
        qp.drawLine(scale_x, 0, scale_x, size.height())
        qp.setFont(QFont('Decorative', 8))
        b = self.px_per_hz()

        if self.current_frequency > 0:
            y = b * (self.current_frequency - self.f1)
            qp.setBrush(QBrush(Qt.yellow, Qt.SolidPattern))
            points = QPolygon([
                QPoint(40, y - 5),
                QPoint(50, y),
                QPoint(40, y + 5)
            ])
            qp.drawPolygon(points)

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
            qp.drawText(scale_x - 45, y + 8/2, f'{int(f/1000):>5}')

        #
        # show spots
        #
        new_color = QColor('#55ffff')
        normal_color = QColor('#0505aa')
        old_color = QColor('#aa5500')
        dupe_color = QColor('#666666')
        normal_font = QFont('Monospace', 10)
        new_font = QFont('Monospace', 10, QFont.Bold, True)
        ymin = 0
        text_x = self.width() * 0.4
        show_dupes = self.dupeSwitch.isChecked()
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
                if not show_dupes:
                    continue
                qp.setPen(dupe_color)
                qp.setFont(normal_font)
            else:
                if s.timeout > 855:     # 95%
                    qp.setPen(new_color)
                    qp.setFont(new_font)
                elif s.timeout > 600:   # 67%
                    qp.setPen(normal_color)
                    qp.setFont(normal_font)
                else:
                    qp.setPen(old_color)
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
        self.select_band(int(value.replace('m','')))
        self.repaint()

    def on_dupe_toggled(self):
        self.repaint()

    def watchdog(self):
        files = self.fs_watcher.files()     # check fsWatcher
        if self.bmdata in files:
            return
        if os.path.exists(self.bmdata):
            self.fs_watcher.addPath(self.bmdata)
            self.file_changed(self.bmdata)
            

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
            self.set_range(self.FMIN, self.FMAX)
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

        self.set_range(f1a, f2a)
        self.mutex.unlock()
        self.repaint()


    def set_ticks(self):
        raw_tick = (self.f2 - self.f1) / 3
        tenpwr = int(10**int(math.log10(raw_tick)))
        mantissa = raw_tick / tenpwr

        if mantissa < 2:
            self.tick_major = tenpwr
            self.tick_minor = self.tick_major // 5
        elif mantissa < 5:
            self.tick_major = 2 * tenpwr
            self.tick_minor = self.tick_major // 4
        else:
            self.tick_major = 5 * tenpwr
            self.tick_minor = self.tick_major // 5


    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.pan_base_y = event.y()     # remember current position
            self.pan_base_f1 = self.f1
            self.pan_base_f2 = self.f2
            self.setMouseTracking(True)     # start panning
        elif event.button() == Qt.RightButton:
            f = int(event.y() / self.px_per_hz() + self.f1)
            self.qsy.emit(f)

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.setMouseTracking(False)    # stop panning
            self.pan_base_y = None

    def mouseMoveEvent(self, event):
        if not self.pan_base_y:
            return
        shift = int((self.pan_base_y - event.y()) / self.px_per_hz())
        shift = max(shift, self.FMIN - self.pan_base_f1)
        shift = min(shift, self.FMAX - self.pan_base_f2)
        self.f1 = self.pan_base_f1 + shift
        self.f2 = self.pan_base_f2 + shift
        self.repaint()

    def keyPressEvent(self, event):
        if event.key() == Qt.Key_Escape:
            self.close()
        elif event.key() == Qt.Key_Left:
            self.switch_band(-1)
        elif event.key() == Qt.Key_Right:
            self.switch_band(+1)
        else:
            pass

    def switch_band(self, direction):
        current_index = self.meter_list.index(self.band)
        current_index = (current_index + direction) % len(self.meter_list)
        self.comboBox.setCurrentIndex(current_index)
        self.select_band(self.meter_list[current_index])
        self.repaint()

    def file_changed(self, fname):
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

    def update_frequency(self, value):
        if value != self.current_frequency:
            self.current_frequency = value
            self.repaint()


class RigctldHandler(QWidget):

    update_frequency = pyqtSignal(int)

    def __init__(self, args):
        super().__init__()

        self.timer = QTimer()
        self.timer.timeout.connect(self.poll)
        self.timer.start(500)

        Hamlib.rig_set_debug(Hamlib.RIG_DEBUG_NONE)
        self.connect()

    def connect(self):
        self.rig = Hamlib.Rig(Hamlib.RIG_MODEL_NETRIGCTL)
        self.rig.open()
        self.error_count = 0    # poll() will reconnect if there was an error

    def poll(self):
        f = self.rig.get_freq()
        if self.rig.error_status == Hamlib.RIG_OK:
            self.update_frequency.emit(int(f))
        else:
            self.update_frequency.emit(0)
            self.error_count = self.error_count + 1
            if self.error_count > 10:
                self.connect()

    def set_frequency(self, value):
        if self.error_count > 0:
            return
        self.rig.set_freq(Hamlib.RIG_VFO_CURR, value)



#################################################

def process_args():
    parser = argparse.ArgumentParser(description='Bandmap view for Tlf ')
    meters = sorted([b.meter for b in BANDS])
    parser.add_argument('band', metavar='band', nargs='?', type=int,
                    choices=meters, default=40,
                    help=f'band to display {meters} (default: 40)')
    parser.add_argument('-d', '--dir', metavar='DIR',
                    help='working directory of Tlf (default: current directory)')
    parser.add_argument('-w', '--warc', action='store_true',
                    help='enable WARC bands')

    mode_group = parser.add_mutually_exclusive_group(required=False)
    mode_group.add_argument('-c', '--cw', action='store_true',
                    help='show CW segment (default)')
    mode_group.add_argument('-s', '--ssb', action='store_true',
                    help='show SSB segment')
    mode_group.add_argument('-m', '--mixed', action='store_true',
                    help='show whole band')

    parsed_args, unparsed_args = parser.parse_known_args()
    if '-?' in unparsed_args:
        parser.print_help()
        sys.exit(1)

    return parsed_args, unparsed_args


def main():
    parsed_args, unparsed_args = process_args()

    band = next(b for b in BANDS if b.meter == parsed_args.band)

    if not band.fssb and parsed_args.ssb:
        print(f'No SSB on {band.meter} m, exiting')
        sys.exit(1)

    if band.warc and not parsed_args.warc:
        parsed_args.warc = True

    if parsed_args.dir:
        parsed_args.bmdata = os.path.expanduser(parsed_args.dir + '/' + BMDATA_FILE)
    else:
        parsed_args.bmdata = BMDATA_FILE

    # to avoid crashing on Ctrl-C...
    signal.signal(signal.SIGINT, signal.SIG_DFL)

    app = QApplication(sys.argv)

    tlf_bandmap = TlfBandmap(parsed_args)
    rigctld_handler = RigctldHandler(parsed_args)

    rigctld_handler.update_frequency.connect(tlf_bandmap.update_frequency)
    tlf_bandmap.qsy.connect(rigctld_handler.set_frequency)

    sys.exit(app.exec_())


if __name__ == '__main__':
    main()

