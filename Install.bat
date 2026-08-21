@echo off
set "Installer=%~dp0dist\VoiceNotes-Setup.exe"

if not exist "%Installer%" (
    echo VoiceNotes-Setup.exe was not found.
    echo Build it with "Build Installer.bat" on the development computer.
    exit /b 1
)

start "" "%Installer%"
