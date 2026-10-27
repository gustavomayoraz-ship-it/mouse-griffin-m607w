@echo off
title Instalar Mouse Griffin M607W
rem Instala Mouse Griffin M607W sin armar el .exe: baja Python 3.14 y las librerias, y lo instala en Archivos de programa.
cd /d "%~dp0_archivos"
set PYX=
for %%V in (3.14 3.13 3.12 3.11 3.10) do (
  if not defined PYX (
    py -%%V -c "import tkinter" >nul 2>nul && set PYX=py -%%V
  )
)
if not defined PYX (
  python -c "import tkinter" >nul 2>nul && set PYX=python
)
if not defined PYX (
  echo.
  echo No se encontro Python en esta PC para abrir el instalador.
  echo Instala Python desde https://www.python.org/downloads/ y marca "tcl/tk and IDLE".
  echo O usa el archivo MouseGriffin-Setup.exe, que no necesita nada instalado.
  echo.
  pause
  exit /b 1
)
%PYX% MouseGriffinInstalador.py %*
if errorlevel 1 pause
