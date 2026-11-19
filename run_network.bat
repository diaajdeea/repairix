@echo off
chcp 65001 >nul
pip install -r requirements.txt
pip install waitress qrcode
python serve.py
pause
