@echo off
echo Installing requirements...
pip install pyinstaller PyQt6

echo.
echo Compiling GUI Tool...
pyinstaller --noconfirm --onefile --windowed --name "QuakeGameBuilder" --icon "favicon.ico" --add-data "gui;gui" --add-data "favicon.ico;." run_gui.py

echo.
if exist "dist\QuakeGameBuilder.exe" (
    echo SUCCESS: Executable created at dist\QuakeGameBuilder.exe
) else (
    echo FAILURE: Build failed.
)
pause
