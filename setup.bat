@echo off
rem Shu's DLSS 5 Switch - opens the Switch. Installs Python first if this PC doesn't have it.
cd /d "%~dp0"
set "PYL=%LOCALAPPDATA%\Programs\Python\Launcher"

where py >nul 2>nul && goto havepy
if exist "%PYL%\py.exe" goto addpath

echo Python 3 is needed and isn't installed on this PC.
where winget >nul 2>nul || goto manual
choice /c YN /m "Install Python 3.12 now from the official Python package (winget)"
if errorlevel 2 goto manual
winget install --id Python.Python.3.12 --source winget --scope user --silent --accept-package-agreements --accept-source-agreements
if exist "%PYL%\py.exe" goto addpath
where py >nul 2>nul && goto havepy
echo The install didn't finish.

:manual
echo Opening the Python download page. Tick "Add python.exe to PATH" when you install it, then run setup.bat again.
start "" https://www.python.org/downloads/
pause
exit /b

:addpath
rem a fresh install isn't on this window's PATH yet
set "PATH=%PYL%;%PATH%"

:havepy
rem Desktop shortcut, made once
set "LNK=%USERPROFILE%\Desktop\Shu's DLSS 5 Switch.lnk"
set "APPDIR=%~dp0"
if not exist "%LNK%" powershell -NoProfile -Command "$w=New-Object -ComObject WScript.Shell; $s=$w.CreateShortcut($env:LNK); $s.TargetPath=(Get-Command pyw).Source; $s.Arguments=[char]34+$env:APPDIR+'tools\dlss5switch.py'+[char]34; $s.WorkingDirectory=$env:APPDIR; $s.IconLocation=$env:SystemRoot+'\System32\imageres.dll,186'; $s.Description='Flick DLSS 5 on and off per game'; $s.Save()"
start "" pyw tools\dlss5switch.py
