@echo off
rmdir /s /q build
rmdir /s /q dist
pyinstaller src\pyqt5_audio_visualiser_optimise.py ^
--onefile ^
--hide-console minimize-late ^
-n SonicHalo ^
--icon=media\sonic_halo_2.ico ^
--add-data ".\media\Px437_IBM_VGA_8x14.ttf;media" ^
--add-data ".\media\sonic_halo_2.ico;media" ^
--hidden-import=winsdk.windows.media.control ^
--hidden-import=winsdk.windows.media ^
--hidden-import=winsdk.windows ^
--version-file version.txt
REM pyinstaller src\pyqt5_audio_visualiser_optimise.py --onefile --hide-console minimize-late -n SonicHalo --icon=media\sonic_halo_2.ico --add-data "media/Px437_IBM_VGA_8x14.ttf;." --hidden-import=winsdk.windows.media.control --hidden-import=winsdk.windows.media --hidden-import=winsdk.windows
certs\code_sign.bat