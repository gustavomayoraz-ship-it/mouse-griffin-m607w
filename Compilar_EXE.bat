@echo off
chcp 65001 >nul
setlocal
cd /d "%~dp0"
title Crear instalador MouseGriffin - Python 3.14

echo ==========================================
echo   Compilando MouseGriffin.exe con Python 3.14
echo ==========================================
echo.

set "PY=py -3.14"
%PY% --version >nul 2>&1
if errorlevel 1 (
    echo [ERROR] No se encontro Python 3.14 en esta PC.
    echo Instalalo desde python.org y tilda "Install launcher for all users".
    echo Despues volve a ejecutar este archivo.
    goto :fin
)
%PY% --version

echo.
echo [1/3] Instalando dependencias y PyInstaller...
%PY% -m pip install --upgrade pip pyinstaller pydirectinput pynput psutil pystray Pillow pywin32
if errorlevel 1 goto :error

echo.
echo [2/3] Compilando el .exe...
%PY% -m PyInstaller --noconfirm --clean --onefile --noconsole ^
    --name MouseGriffin ^
    --distpath dist --workpath build --specpath build ^
    --hidden-import pystray._win32 ^
    --hidden-import win32com.client ^
    --hidden-import win32gui ^
    --hidden-import win32process ^
    --collect-submodules pynput ^
    mouse.py
if errorlevel 1 goto :error

echo.
echo [3/3] Creando el instalador para Windows (Archivos de programa)...
set "ISCC=%ProgramFiles(x86)%\Inno Setup 6\ISCC.exe"
if not exist "%ISCC%" set "ISCC=%ProgramFiles%\Inno Setup 6\ISCC.exe"
if not exist "%ISCC%" (
    echo [AVISO] No esta instalado Inno Setup 6, asi que solo se creo el .exe suelto.
    echo Instalalo desde https://jrsoftware.org/isdl.php y volve a ejecutar este archivo
    echo para obtener dist\MouseGriffin_Setup.exe
    goto :fin_ok
)
"%ISCC%" installer.iss
if errorlevel 1 goto :error

echo.
echo ==========================================
echo   LISTO: dist\MouseGriffin_Setup.exe  (instalador)
echo ==========================================
:fin_ok
explorer dist
goto :fin

:error
echo.
echo [ERROR] Algo fallo durante la compilacion. Revisa los mensajes de arriba.

:fin
echo.
pause
endlocal
