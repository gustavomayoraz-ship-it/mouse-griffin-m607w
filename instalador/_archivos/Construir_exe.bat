@echo off
rem Arma dist\MouseGriffin-Setup.exe (el instalador). Necesita internet para bajar PyInstaller.
cd /d "%~dp0"
set PYX=
for %%V in (3.14 3.13 3.12) do (
  if not defined PYX (
    py -%%V -c "import tkinter" >nul 2>nul && set PYX=py -%%V
  )
)
if not defined PYX set PYX=python
echo Usando: %PYX%
%PYX% --version
%PYX% -m pip install --upgrade pyinstaller || goto :error
%PYX% -m PyInstaller --onefile --noconsole --uac-admin --clean --name MouseGriffin-Setup --add-data "..\..\mouse.py;." MouseGriffinInstalador.py || goto :error
echo.
echo Listo: %~dp0dist\MouseGriffin-Setup.exe
pause
exit /b 0
:error
echo.
echo Algo fallo. Mira el mensaje de arriba.
pause
exit /b 1
