@echo off
rem One-time setup: links the add-in into Fusion and puts the Apex Orders shortcut in Desktop\Apex Prints.
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0tools\install.ps1"
pause
