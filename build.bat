@echo off
rem Builds dist\USB-Fixer.exe (run on Windows, Python 3.9+)
python -m pip install -r requirements-dev.txt
python -m PyInstaller --noconfirm --onefile --windowed --name USB-Fixer ^
  --uac-admin ^
  --exclude-module tkinter ^
  --add-data "usb_fixer\data\knowledge.json;usb_fixer\data" ^
  --add-data "usb_fixer\data\fonts;usb_fixer\data\fonts" ^
  run_usb_fixer.py
echo.
echo Done: dist\USB-Fixer.exe
