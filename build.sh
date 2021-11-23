#!/bin/bash
python -m nuitka --plugin-enable=pylint-warnings --plugin-enable=pkg-resources --onefile --linux-onefile-icon icon.png -o accumen_camera.bin app.py
