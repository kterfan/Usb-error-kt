; Inno Setup script: builds USB-Fixer-Setup-<version>.exe from dist\USB-Fixer.exe
; Build:  ISCC /DAppVersion=0.9.0 installer\usb_fixer.iss
; Author: Erfan Esmailzadeh (عرفان اسمعیل زاده) - https://github.com/kterfan

#ifndef AppVersion
  #define AppVersion "0.0.0"
#endif

[Setup]
AppId={{6C0B7E52-8E1F-4C55-9D5B-2F4A3B1E9A71}
AppName=USB Fixer
AppVersion={#AppVersion}
AppVerName=USB Fixer {#AppVersion}
AppPublisher=Erfan Esmailzadeh
AppPublisherURL=https://github.com/kterfan
AppSupportURL=https://github.com/kterfan/Usb-error-kt
AppUpdatesURL=https://github.com/kterfan/Usb-error-kt
AppCopyright=Copyright (c) 2026 Erfan Esmailzadeh
VersionInfoVersion={#AppVersion}
VersionInfoCompany=Erfan Esmailzadeh
VersionInfoDescription=USB Fixer setup
DefaultDirName={autopf}\USB Fixer
DefaultGroupName=USB Fixer
DisableProgramGroupPage=yes
PrivilegesRequired=admin
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
OutputDir=..\dist
OutputBaseFilename=USB-Fixer-Setup-{#AppVersion}
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
SetupIconFile=..\usb_fixer\data\icon.ico
UninstallDisplayIcon={app}\USB-Fixer.exe
UninstallDisplayName=USB Fixer {#AppVersion} (Erfan Esmailzadeh)

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Messages]
WelcomeLabel2=This will install [name/ver] on your computer.%n%nUSB Fixer finds and fixes USB port and device problems (Persian interface).%n%nMade by Erfan Esmailzadeh (عرفان اسمعیل زاده)%nhttps://github.com/kterfan

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"

[Files]
Source: "..\dist\USB-Fixer.exe"; DestDir: "{app}"; Flags: ignoreversion
Source: "..\README.md"; DestDir: "{app}"; Flags: ignoreversion
Source: "..\usb_fixer\data\fonts\OFL.txt"; DestDir: "{app}"; DestName: "Vazirmatn-OFL.txt"; Flags: ignoreversion

[Icons]
Name: "{group}\USB Fixer"; Filename: "{app}\USB-Fixer.exe"
Name: "{group}\{cm:UninstallProgram,USB Fixer}"; Filename: "{uninstallexe}"
Name: "{autodesktop}\USB Fixer"; Filename: "{app}\USB-Fixer.exe"; Tasks: desktopicon

[Run]
Filename: "{app}\USB-Fixer.exe"; Description: "{cm:LaunchProgram,USB Fixer}"; Flags: nowait postinstall skipifsilent shellexec

[UninstallRun]
; the optional logon guard task points at this exe, so it goes away with the program
Filename: "{sys}\schtasks.exe"; Parameters: "/Delete /TN ""USB Fixer Guard"" /F"; Flags: runhidden; RunOnceId: "RemoveGuardTask"
