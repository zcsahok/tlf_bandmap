# Bandmap view for Tlf logger

![Screenshot](doc/screenshot.png?raw=true)

## Usage
```./tlf_bandmap.py [-d DIR] [-w] [-c | -s | -m] [band]```

Default band is 40. No further configuration is needed,
just start _tlf_ in the same directory connected to the cluster.
Multiple instances can be started to watch the bands.

A different working directory can be selected with `-d` option.

Mouse wheel scrolling zooms the view in/out.
Holding left mouse button down and moving mouse up/down pans the view.
Band can be selected using drop-down menu.
Cursor Left/Right switches to next band.
Dupes can be displayed or suppressed.

To terminate press `Esc` in the window.

## Issues
- current frequency is not shown
- no point-and-click tuning
- slow, updates each 10 sec

## Dependencies
Needs PyQt5:
```apt install python3-pyqt5```
