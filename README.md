# Bandmap view for Tlf logger

Usage:
```./tlf_bandmap.py [band]```

Default band is 40 m. No further configation is needed, just start _tlf_ connected to the cluster.
Multiple instances can be started to watch the bands.

Mouse wheel scrolling zooms the view in/out.

Issues
- current frequency is not shown
- no point-and-clink tuning
- slow, updates each 10 sec

Needs PyQt5:
```apt install python3-pyqt5```
