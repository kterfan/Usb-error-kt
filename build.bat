@echo off
rem Builds dist\USB-Fixer.exe (run on Windows, Python 3.9+) and, if Inno Setup 6 is installed, the installer.
python -m pip install -r requirements-dev.txt
python tools\version_info.py version_info.txt
python -m PyInstaller --noconfirm --onefile --windowed --name USB-Fixer ^
  --uac-admin ^
  --version-file version_info.txt ^
  --icon usb_fixer\data\icon.ico ^
  --add-data "usb_fixer\data\icon.png;usb_fixer\data" ^
  --exclude-module tkinter ^
  --add-data "usb_fixer\data\knowledge.json;usb_fixer\data" ^
  --add-data "usb_fixer\data\fonts;usb_fixer\data\fonts" ^
  run_usb_fixer.py
for /f %%v in ('python -c "import usb_fixer; print(usb_fixer.__version__)"') do set VER=%%v
if exist "%ProgramFiles(x86)%\Inno Setup 6\ISCC.exe" "%ProgramFiles(x86)%\Inno Setup 6\ISCC.exe" /DAppVersion=%VER% installer\usb_fixer.iss
echo.
echo Done: dist\USB-Fixer.exe (and dist\USB-Fixer-Setup-%VER%.exe if Inno Setup is installed)
