#!/bin/sh
cd "$(dirname "$0")"
pip install -r requirements.txt waitress qrcode
python3 serve.py
