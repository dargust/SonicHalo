@echo off
REM Windows setup script for Sonic Halo Audio Visualizer

echo ===================================
echo Sonic Halo - Windows Setup
echo ===================================

REM Check if Python is installed
python --version >nul 2>&1
if errorlevel 1 (
    echo Python not found. Please install Python 3.8+ from python.org
    pause
    exit /b 1
)

REM Create virtual environment
echo Creating Python virtual environment...
python -m venv venv

REM Activate virtual environment
echo Activating virtual environment...
call venv\Scripts\activate.bat

REM Upgrade pip
echo Upgrading pip...
python -m pip install --upgrade pip

REM Install Python dependencies
echo Installing Python dependencies...
pip install -r requirements.txt

REM Try to install Windows-specific audio packages
echo Installing Windows-specific audio packages...
pip install pyaudiowpatch pywin32 winsdk

REM Create batch file for easy launching
echo Creating launcher batch file...
echo @echo off > sonic_halo.bat
echo cd /d "%~dp0" >> sonic_halo.bat
echo call venv\Scripts\activate.bat >> sonic_halo.bat
echo python sonic_halo_launcher.py >> sonic_halo.bat
echo pause >> sonic_halo.bat

REM Make the batch file executable
attrib +r sonic_halo.bat

REM Create desktop shortcut (requires VBS)
echo Creating desktop shortcut...
set SCRIPT="%TEMP%\%RANDOM%-%RANDOM%-%RANDOM%-%RANDOM%.vbs"
echo Set oWS = WScript.CreateObject("WScript.Shell") >> %SCRIPT%
echo sLinkFile = "%USERPROFILE%\Desktop\Sonic Halo.lnk" >> %SCRIPT%
echo Set oLink = oWS.CreateShortcut(sLinkFile) >> %SCRIPT%
echo oLink.TargetPath = "%CD%\sonic_halo.bat" >> %SCRIPT%
echo oLink.WorkingDirectory = "%CD%" >> %SCRIPT%
echo oLink.IconLocation = "%CD%\media\sonic_halo_2.ico" >> %SCRIPT%
echo oLink.Description = "Sonic Halo Audio Visualizer" >> %SCRIPT%
echo oLink.Save >> %SCRIPT%
cscript /nologo %SCRIPT%
del %SCRIPT%

echo ===================================
echo Setup complete!
echo.
echo To run Sonic Halo:
echo 1. Double-click "sonic_halo.bat"
echo    OR double-click the desktop shortcut
echo    OR run: python sonic_halo_launcher.py
echo.
echo For system audio capture:
echo 1. The app will automatically use WASAPI loopback
echo 2. If that fails, install VB-Cable or enable Stereo Mix
echo.
echo VB-Cable download: https://vb-audio.com/Cable/
echo ===================================
pause