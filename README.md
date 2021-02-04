# Bandmap view for Tlf logger

![Screenshot](doc/screenshot.png?raw=true)

## Usage
```./tlf_bandmap.py [band]```

Default band is 40. No further configation is needed, just start _tlf_ connected to the cluster.
Multiple instances can be started to watch the bands.

Mouse wheel scrolling zooms the view in/out. Band can be selected using drop-down menu.
Currently only contest bands are configured.

To terminate press `Esc` in the window.

## Issues
- current frequency is not shown
- no point-and-click tuning
- slow, updates each 10 sec

## Dependencies
Needs PyQt5:
```apt install python3-pyqt5```
