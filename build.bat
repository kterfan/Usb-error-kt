@echo off
rem Builds dist\USB-Fixer.exe (run on Windows, Python 3.9+ with tkinter installed)
python -m pip install -r requirements-dev.txt
python -m PyInstaller --noconfirm --onefile --windowed --name USB-Fixer ^
  --uac-admin ^
  --add-data "usb_fixer\data\knowledge.json;usb_fixer\data" ^
  run_usb_fixer.py
echo.
echo Done: dist\USB-Fixer.exe
