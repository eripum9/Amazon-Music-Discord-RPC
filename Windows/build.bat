@echo off
setlocal
set "SCRIPT_DIR=%~dp0"
set "ROOT_DIR=%SCRIPT_DIR%.."
pushd "%ROOT_DIR%"

echo === Building EXE with PyInstaller ===
python -m PyInstaller Windows\AmazonMusicRPC.spec --noconfirm --workpath Windows\build --distpath Windows\dist
if %ERRORLEVEL% neq 0 (
    echo PyInstaller build failed!
    popd
    pause
    exit /b 1
)

echo.
echo === Building Installer with Inno Setup ===
"%LOCALAPPDATA%\Programs\Inno Setup 6\ISCC.exe" Windows\installer.iss
if %ERRORLEVEL% neq 0 (
    echo Inno Setup build failed!
    popd
    pause
    exit /b 1
)

echo.
echo === Build complete! ===
echo EXE: Windows\dist\AmazonMusicRPC.exe
echo Installer: Windows\installer_output\AmazonMusicRPC_Setup.exe
popd
pause
