"""
Mouse Griffin M607W - Instalador.

Instala todo lo que el programa necesita, sin que tengas que instalar nada antes:
  1. Python 3.14 completo (componentes oficiales de python.org, con tkinter y pip) en una carpeta propia del programa;
     no se registra en Windows ni toca los Python que ya tengas.
  2. El programa (mouse.py).
  3. Las librerias: pydirectinput, pynput, psutil, pystray, Pillow, pywin32.
Se instala en "Archivos de programa\\Mouse Griffin M607W", crea los accesos directos (Escritorio y menu Inicio) y
se registra en "Aplicaciones instaladas" de Windows para poder desinstalarlo desde ahi. Despues abre el programa.
Si ya esta todo instalado, solo abre el programa.

Opciones:
  --sin-ventana   instala sin ventana (para pruebas); el detalle queda en cache\\instalacion.log
  --no-lanzar     no abre el programa al terminar
  --carpeta RUTA  instala en esa carpeta (en vez de Archivos de programa)
  --ventana       muestra la ventana aunque ya este todo instalado
"""
import ctypes
import hashlib
import os
import re
import shutil
import struct
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Callable, Optional
import tkinter as tk
from tkinter import messagebox, ttk

# ----------------------------------------------------------------------------------------------------
# Configuracion
# ----------------------------------------------------------------------------------------------------
APP_NOMBRE = "Mouse Griffin M607W"
APP_VERSION = "1.0.0"
APP_EDITOR = "Gustavo Mayoraz"
CLAVE_DESINSTALAR = r"Software\Microsoft\Windows\CurrentVersion\Uninstall\MouseGriffinM607W"
PY_SERIE = "3.14"
DLL_PYTHON = "python" + PY_SERIE.replace(".", "") + "*.dll"
PY_FTP = "https://www.python.org/ftp/python/"
PY_EXE_URL = PY_FTP + "{v}/python-{v}-amd64.exe"
PY_RESPALDO = [f"{PY_SERIE}.{n}" for n in range(15, 0, -1)]   # si no se puede leer el indice de python.org, se prueban estas
# Componentes que se descomprimen del instalador oficial: (nombre, texto del nombre del producto dentro del .msi)
MSI_NECESARIOS = [("core", b"Core Interpreter"), ("exe", b"Executables"), ("lib", b"Standard Library"), ("tcltk", b"Tcl/Tk Support")]

# (nombre, import_name, paquete pip): las librerias de ESTE programa
DEPENDENCIAS = [("pydirectinput", "pydirectinput", "pydirectinput"), ("pynput", "pynput", "pynput"),
                ("psutil", "psutil", "psutil"), ("pystray", "pystray", "pystray"),
                ("Pillow", "PIL", "Pillow"), ("pywin32", "win32com", "pywin32")]
FILA_PYTHON = f"Python {PY_SERIE}"
FILA_PROGRAMA = "Programa"

CREATE_NO_WINDOW = 0x08000000
DETACHED_PROCESS = 0x00000008


# ----------------------------------------------------------------------------------------------------
# Utilidades
# ----------------------------------------------------------------------------------------------------
def entorno_limpio() -> dict:
    """Entorno sin variables PYTHON*: asi ninguna otra version de Python instalada se mete en la app."""
    return {k: v for k, v in os.environ.items() if not k.upper().startswith("PYTHON")}


def es_admin() -> bool:
    try:
        return bool(ctypes.windll.shell32.IsUserAnAdmin())
    except (AttributeError, OSError):
        return False


def relanzar_como_admin(argv: list) -> None:
    """Vuelve a abrir este mismo programa pidiendo permisos de administrador (necesarios para Archivos de programa)."""
    if getattr(sys, "frozen", False):
        exe, params = sys.executable, subprocess.list2cmdline(argv)
    else:
        exe, params = sys.executable, subprocess.list2cmdline([str(Path(__file__).resolve())] + argv)
    ctypes.windll.shell32.ShellExecuteW(None, "runas", exe, params, None, 1)


def recurso(nombre: str) -> Path:
    """Archivo incluido dentro del instalador (mouse.py)."""
    base = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent))
    for carpeta in (base, base.parent.parent):          # empaquetado: junto al instalador; repositorio: dos carpetas arriba
        if (carpeta / nombre).is_file():
            return carpeta / nombre
    return base / nombre


def calcular_raiz(argv: list) -> Path:
    if "--carpeta" in argv and argv.index("--carpeta") + 1 < len(argv):
        return Path(argv[argv.index("--carpeta") + 1]).expanduser().resolve()
    base = os.environ.get("ProgramW6432") or os.environ.get("ProgramFiles") or r"C:\Program Files"
    return Path(base) / APP_NOMBRE


def clave_version(v: str) -> tuple:
    return tuple(int(x) for x in v.split("."))


def sha(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


# ----------------------------------------------------------------------------------------------------
# Logica de instalacion (sin ventana)
# ----------------------------------------------------------------------------------------------------
class Instalacion:
    def __init__(self, raiz: Path) -> None:
        self.raiz = raiz
        self.py_dir = raiz / "python"
        self.py_exe = self.py_dir / "python.exe"
        self.pyw_exe = self.py_dir / "pythonw.exe"
        self.site = self.py_dir / "Lib" / "site-packages"
        self.programa = raiz / "mouse.py"
        self.proc_actual: Optional[subprocess.Popen] = None
        self.cancelado = False

    def log(self, texto: str) -> None:
        try:
            carpeta = self.raiz / "cache"
            carpeta.mkdir(parents=True, exist_ok=True)
            with open(carpeta / "instalacion.log", "a", encoding="utf-8") as f:
                f.write(time.strftime("%Y-%m-%d %H:%M:%S") + "  " + texto + "\n")
        except OSError:
            pass

    # ---------- verificaciones ----------
    def python_ok(self) -> bool:
        return (self.py_exe.is_file() and self.pyw_exe.is_file() and any(self.py_dir.glob(DLL_PYTHON))
                and (self.py_dir / "DLLs" / "_tkinter.pyd").is_file() and (self.py_dir / "tcl").is_dir()
                and (self.site / "pip").is_dir())

    def programa_ok(self) -> bool:
        try:
            return self.programa.is_file() and sha(self.programa) == sha(recurso("mouse.py"))
        except OSError:
            return False

    def dep_ok(self, import_name: str) -> bool:
        return (self.site / import_name).is_dir() or (self.site / (import_name + ".py")).is_file()

    def todo_ok(self) -> bool:
        return self.python_ok() and self.programa_ok() and all(self.dep_ok(i) for _n, i, _p in DEPENDENCIAS)

    # ---------- descargas y procesos ----------
    def descargar(self, url: str, destino: Path, avance: Optional[Callable[[Optional[int]], None]] = None) -> None:
        destino.parent.mkdir(parents=True, exist_ok=True)
        parcial = destino.with_name(destino.name + ".part")
        req = urllib.request.Request(url, headers={"User-Agent": "MouseGriffin-Instalador"})
        try:
            with urllib.request.urlopen(req, timeout=30) as r, open(parcial, "wb") as f:
                total = int(r.headers.get("Content-Length") or 0)
                hecho, ultimo = 0, -1
                while True:
                    if self.cancelado:
                        raise RuntimeError("cancelado")
                    bloque = r.read(65536)
                    if not bloque:
                        break
                    f.write(bloque)
                    hecho += len(bloque)
                    if avance:
                        pct = int(100 * hecho / total) if total else None
                        if pct != ultimo:
                            ultimo = pct if pct is not None else -1
                            avance(pct)
            os.replace(parcial, destino)
        finally:
            parcial.unlink(missing_ok=True)

    def _correr(self, cmd, **kw) -> subprocess.CompletedProcess:
        flags = CREATE_NO_WINDOW if os.name == "nt" else 0
        self.proc_actual = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, stdin=subprocess.DEVNULL,
                                            text=True, errors="replace", creationflags=flags, env=entorno_limpio(), **kw)
        try:
            try:
                salida, _ = self.proc_actual.communicate(timeout=900)          # nada debe quedar colgado para siempre
            except subprocess.TimeoutExpired:
                self.proc_actual.kill()
                raise RuntimeError("Un paso tardo mas de 15 minutos y se cancelo: " + (cmd if isinstance(cmd, str) else " ".join(map(str, cmd)))[:200])
            return subprocess.CompletedProcess(cmd, self.proc_actual.returncode, salida or "")
        finally:
            self.proc_actual = None

    # ---------- Python 3.14 portable completo (componentes oficiales de python.org; no se registra en Windows) ----------
    @property
    def cache(self) -> Path:
        return self.raiz / "cache"

    def faltantes_python(self) -> list:
        """Qué le falta al Python instalado (para mostrar un error claro)."""
        pedidos = [("python.exe", self.py_exe), ("pythonw.exe", self.pyw_exe),
                   ("DLLs\\_tkinter.pyd (Tkinter)", self.py_dir / "DLLs" / "_tkinter.pyd"),
                   ("tcl (Tkinter)", self.py_dir / "tcl"), ("pip", self.site / "pip")]
        falta = [n for n, ruta in pedidos if not ruta.exists()]
        if not any(self.py_dir.glob(DLL_PYTHON)):
            falta.append(DLL_PYTHON)
        return falta

    def _versiones_python(self) -> list:
        """Versiones de la serie publicadas en python.org, de la más nueva a la más vieja."""
        try:
            with urllib.request.urlopen(urllib.request.Request(PY_FTP, headers={"User-Agent": "MouseGriffin-Instalador"}),
                                        timeout=30) as r:
                html = r.read().decode("utf-8", errors="replace")
            lista = sorted({m for m in re.findall(r'href="(' + re.escape(PY_SERIE) + r'\.\d+)/"', html)},
                           key=clave_version, reverse=True)
            if lista:
                return lista
        except OSError:
            pass
        return PY_RESPALDO

    def _normalizar_extraccion(self) -> None:
        """Si msiexec dejó los archivos dentro de una subcarpeta, se suben a la raíz de python."""
        if self.py_exe.is_file():
            return
        for exe in self.py_dir.rglob("python.exe"):
            origen = exe.parent
            for hijo in list(origen.iterdir()):
                destino = self.py_dir / hijo.name
                if not destino.exists():
                    shutil.move(str(hijo), str(destino))
            break

    @staticmethod
    def cabinas_del_exe(datos: bytes) -> list:
        """El instalador de Python (WiX Burn) lleva sus componentes en cabinas (.cab) pegadas dentro del propio .exe.
        Devuelve [(desde, hasta)] de cada cabina válida, la más grande primero (esa es la de los componentes)."""
        out = []
        for m in re.finditer(b"MSCF\x00\x00\x00\x00", datos):
            o = m.start()
            if o + 36 > len(datos):
                continue
            tam = struct.unpack_from("<I", datos, o + 8)[0]
            if 1_000_000 < tam and o + tam <= len(datos):
                out.append((o, o + tam))
        return sorted(out, key=lambda t: t[1] - t[0], reverse=True)

    @staticmethod
    def identificar_msi(datos: bytes) -> Optional[str]:
        """Qué componente es este archivo (core, exe, lib, tcltk) según el nombre de producto guardado en el .msi."""
        if datos[:4] != bytes.fromhex("d0cf11e0"):
            return None
        for nombre, clave in MSI_NECESARIOS:
            if clave in datos:
                return nombre
        return None

    def _expandir_cab(self, cab: Path, destino: Path) -> subprocess.CompletedProcess:
        destino.mkdir(parents=True, exist_ok=True)
        if os.name == "nt":
            return self._correr(["expand.exe", str(cab), "-F:*", str(destino)])     # expand.exe viene con Windows
        return self._correr(["cabextract", "-q", "-d", str(destino), str(cab)])    # (solo para las pruebas en Linux)

    def sacar_msi_del_exe(self, exe: Path, avance: Callable[[str], None]) -> dict:
        """Extrae del instalador los .msi de los componentes necesarios. Devuelve {nombre: ruta}."""
        avance("📦 Abriendo el instalador de Python...")
        datos = exe.read_bytes()
        trabajo = exe.parent / "componentes"
        encontrados: dict = {}
        for n, (desde, hasta) in enumerate(self.cabinas_del_exe(datos)):
            cab = exe.parent / f"contenedor{n}.cab"
            cab.write_bytes(datos[desde:hasta])
            carpeta = trabajo / str(n)
            r = self._expandir_cab(cab, carpeta)
            self.log(f"expand contenedor{n} -> {r.returncode} {r.stdout[-200:]}")
            for f in sorted(carpeta.iterdir()) if carpeta.is_dir() else []:
                if f.is_file() and f.stat().st_size > 10_000:
                    with open(f, "rb") as fh:
                        cabecera = fh.read(4)
                    if cabecera != bytes.fromhex("d0cf11e0"):
                        continue
                    nombre = self.identificar_msi(f.read_bytes())
                    if nombre and nombre not in encontrados:
                        encontrados[nombre] = f.with_name(f.name + ".msi")
                        f.rename(encontrados[nombre])
            if len(encontrados) == len(MSI_NECESARIOS):
                break
        return encontrados

    def extraer_msi(self, msis: dict, avance: Callable[[str], None]) -> None:
        """Descomprime los componentes (.msi) con 'msiexec /a' (instalación administrativa: solo extrae los archivos,
        no registra nada en Windows ni toca los Python que ya tengas)."""
        faltan = [n for n, _c in MSI_NECESARIOS if n not in msis]
        if faltan:
            raise RuntimeError("El instalador de Python no tiene estos componentes: " + ", ".join(faltan))
        if self.py_dir.exists():
            shutil.rmtree(self.py_dir, ignore_errors=True)
        self.py_dir.mkdir(parents=True, exist_ok=True)
        for n, _c in MSI_NECESARIOS:
            avance(f"📦 Descomprimiendo Python ({n})...")
            # como texto (no lista) y con TARGETDIR="..." entre comillas: si la ruta tiene espacios (Archivos de programa),
            # msiexec no entiende "TARGETDIR=C:\\Program Files\\..." entero entre comillas y se queda esperando
            r = self._correr(f'msiexec /a "{msis[n]}" /qn /norestart TARGETDIR="{self.py_dir}"')
            self.log(f"msiexec /a {n} -> {r.returncode} {r.stdout[-300:]}")
            if r.returncode not in (0, 3010):
                raise RuntimeError(f"msiexec falló con {n} (código {r.returncode}):\n" + r.stdout[-1200:])
        self._normalizar_extraccion()
        # los .msi administrativos dejan una copia de sí mismos junto a los archivos: se borra
        for m in self.py_dir.glob("*.msi"):
            m.unlink(missing_ok=True)

    def instalar_python(self, avance: Callable[[str], None]) -> None:
        desc = self.raiz / "_descargas"
        exe = None
        ultimo = None
        for v in self._versiones_python()[:8]:
            destino = desc / f"python-{v}-amd64.exe"
            try:
                avance(f"⬇️ Descargando Python {v}...")
                self.descargar(PY_EXE_URL.format(v=v), destino,
                               lambda p, v=v: avance(f"⬇️ Descargando Python {v}... {p}%" if p is not None else f"⬇️ Descargando Python {v}..."))
                exe = destino
                break
            except urllib.error.HTTPError as e:
                ultimo = e
                if e.code != 404:                       # 404: esa versión no tiene instalador de Windows, se prueba la anterior
                    raise
        if exe is None:
            raise RuntimeError(f"No se encontró el instalador de Python {PY_SERIE} en python.org ({ultimo})")
        try:
            msis = self.sacar_msi_del_exe(exe, avance)
            self.log(f"componentes encontrados: {sorted(msis)}")
            self.extraer_msi(msis, avance)
            self.asegurar_aislamiento()
            if not (self.site / "pip").is_dir():
                avance("📦 Instalando pip...")
                r = self._correr([str(self.py_exe), "-m", "ensurepip", "--upgrade", "--default-pip"], cwd=str(self.py_dir))
                self.log(f"ensurepip -> {r.returncode} {r.stdout[-300:]}")
        except OSError as e:
            raise RuntimeError(f"No se pudo preparar Python: {e}") from e
        if not self.python_ok():
            self.log(f"faltan: {self.faltantes_python()}")
            raise RuntimeError("El Python quedó incompleto. Falta: " + ", ".join(self.faltantes_python())
                               + f"\n(El registro está en {self.raiz / 'cache' / 'instalacion.log'})")
        shutil.rmtree(desc, ignore_errors=True)

    SITECUSTOMIZE = (
        "# Lo crea el instalador de Mouse Griffin M607W: este Python NO debe ver las librerias de otros Python de la PC\n"
        "# (la carpeta de usuario de site-packages), para que use solo las suyas.\n"
        "import sys, site\n"
        "try:\n"
        "    _u = site.getusersitepackages()\n"
        "    sys.path[:] = [p for p in sys.path if p != _u]\n"
        "    site.ENABLE_USER_SITE = False\n"
        "except Exception:\n"
        "    pass\n")

    def asegurar_aislamiento(self) -> None:
        """Pone en Lib\\site-packages un sitecustomize.py que saca del camino la carpeta de usuario de otros Python.
        Sin esto, pip ve las librerías que ya tenés instaladas en tu Python, dice 'ya instalado' y no instala nada."""
        try:
            if self.py_dir.is_dir():
                self.site.mkdir(parents=True, exist_ok=True)
                f = self.site / "sitecustomize.py"
                if not f.is_file() or f.read_text(encoding="utf-8", errors="replace") != self.SITECUSTOMIZE:
                    f.write_text(self.SITECUSTOMIZE, encoding="utf-8")
        except OSError:
            pass

    # ---------- programa ----------
    def instalar_programa(self, avance: Callable[[str], None]) -> None:
        avance("📦 Copiando el programa...")
        self.raiz.mkdir(parents=True, exist_ok=True)
        shutil.copy2(recurso("mouse.py"), self.programa)
        if not self.programa_ok():
            raise RuntimeError("No se pudo copiar mouse.py a " + str(self.raiz))

    # ---------- librerias ----------
    def instalar_dependencia(self, nombre: str, pip_name: str) -> tuple:
        ok, det = False, None
        try:
            r = self._correr([str(self.py_exe), "-m", "pip", "install", "--disable-pip-version-check",
                              "--no-warn-script-location", pip_name])
            ok = (r.returncode == 0)
            det = None if ok else (r.stdout or "pip no devolvio detalle.").strip()[-1500:]
        except (OSError, RuntimeError) as e:
            ok, det = False, str(e)
        self.log(f"pip {pip_name}: " + ("OK" if ok else "ERROR\n" + str(det)))
        return ok, det

    # ---------- accesos directos, desinstalador y arranque ----------
    def _ruta_acceso(self) -> Path:
        base = os.environ.get("ProgramData", r"C:\ProgramData")
        return Path(base) / "Microsoft" / "Windows" / "Start Menu" / "Programs" / f"{APP_NOMBRE}.lnk"

    def crear_accesos(self) -> None:
        """Acceso directo en el Escritorio (de todos los usuarios) y en el menu Inicio."""
        if os.name != "nt":
            return

        def ps(s) -> str:
            return "'" + str(s).replace("'", "''") + "'"
        guion = (
            "$w = New-Object -ComObject WScript.Shell; "
            "foreach ($d in @([Environment]::GetFolderPath('CommonDesktopDirectory'), [Environment]::GetFolderPath('CommonPrograms'))) { "
            f"$l = $w.CreateShortcut((Join-Path $d {ps(APP_NOMBRE + '.lnk')})); "
            f"$l.TargetPath = {ps(self.pyw_exe)}; $l.Arguments = {ps(chr(34) + str(self.programa) + chr(34))}; "
            f"$l.WorkingDirectory = {ps(self.raiz)}; $l.IconLocation = {ps(str(self.pyw_exe) + ',0')}; "
            f"$l.Description = {ps(APP_NOMBRE)}; $l.Save() }}")
        try:
            r = subprocess.run(["powershell", "-NoProfile", "-NonInteractive", "-Command", guion], capture_output=True,
                               text=True, creationflags=CREATE_NO_WINDOW, timeout=60)
            self.log("accesos directos: " + ("OK" if r.returncode == 0 else "ERROR " + (r.stderr or r.stdout)[-300:]))
        except (OSError, subprocess.TimeoutExpired) as e:
            self.log(f"accesos directos: ERROR {e}")

    def registrar_desinstalador(self) -> None:
        """Agrega el programa a 'Aplicaciones instaladas' (Configuracion > Aplicaciones) para desinstalarlo desde ahi."""
        if os.name != "nt":
            return
        import winreg
        r = str(self.raiz)
        script = (
            "@echo off\r\n"
            'if not "%~1"=="x" (copy /y "%~f0" "%TEMP%\\mg_desinstalar.cmd" >nul & start "" "%TEMP%\\mg_desinstalar.cmd" x %~1 & exit /b)\r\n'
            "net session >nul 2>&1\r\n"
            'if errorlevel 1 (powershell -NoProfile -Command "Start-Process -FilePath \'%~f0\' -ArgumentList \'x %~2\' -Verb RunAs" & exit /b)\r\n'
            f"title Desinstalar {APP_NOMBRE}\r\n"
            f"echo Se va a desinstalar {APP_NOMBRE} de: {r}\r\n"
            'if "%~2"=="s" goto :borrar\r\n'
            f'choice /m "Desinstalar {APP_NOMBRE}"\r\n'
            "if errorlevel 2 exit /b 0\r\n"
            ":borrar\r\n"
            f"powershell -NoProfile -Command \"Get-Process | Where-Object {{ $_.Path -like '{r}\\*' }} | Stop-Process -Force\" >nul 2>nul\r\n"
            "ping -n 3 127.0.0.1 >nul\r\n"
            f'rmdir /s /q "{r}"\r\n'
            f'del "%PUBLIC%\\Desktop\\{APP_NOMBRE}.lnk" 2>nul\r\n'
            f'del "%ProgramData%\\Microsoft\\Windows\\Start Menu\\Programs\\{APP_NOMBRE}.lnk" 2>nul\r\n'
            f'reg delete "HKLM\\{CLAVE_DESINSTALAR}" /f >nul 2>nul\r\n'
            f"echo Listo, {APP_NOMBRE} fue desinstalado.\r\n"
            'if not "%~2"=="s" pause\r\n'
        )
        try:
            ruta = self.raiz / "desinstalar.cmd"
            ruta.write_bytes(script.encode("cp1252", errors="replace"))
            with winreg.CreateKeyEx(winreg.HKEY_LOCAL_MACHINE, CLAVE_DESINSTALAR, 0,
                                    winreg.KEY_WRITE | winreg.KEY_WOW64_64KEY) as k:
                for nombre, valor in (("DisplayName", APP_NOMBRE), ("DisplayVersion", APP_VERSION), ("Publisher", APP_EDITOR),
                                      ("InstallLocation", r), ("DisplayIcon", str(self.pyw_exe)),
                                      ("UninstallString", f'"{ruta}"')):
                    winreg.SetValueEx(k, nombre, 0, winreg.REG_SZ, valor)
                for nombre in ("NoModify", "NoRepair"):
                    winreg.SetValueEx(k, nombre, 0, winreg.REG_DWORD, 1)
            self.log("desinstalador registrado: OK")
        except OSError as e:
            self.log(f"desinstalador: ERROR {e}")

    def lanzar_app(self) -> None:
        """Abre el programa SIN permisos de administrador (si no, no podria hacer clics en otras ventanas normales)."""
        flags = (CREATE_NO_WINDOW | DETACHED_PROCESS) if os.name == "nt" else 0
        acceso = self._ruta_acceso()
        try:
            if os.name == "nt" and acceso.exists():
                subprocess.Popen(["explorer.exe", str(acceso)], close_fds=True)      # explorer lo abre con el usuario normal
                return
        except OSError:
            pass
        subprocess.Popen([str(self.pyw_exe if self.pyw_exe.exists() else self.py_exe), str(self.programa)],
                         cwd=str(self.raiz), creationflags=flags, close_fds=True, env=entorno_limpio())

    # ---------- paso a paso (compartido por la ventana y el modo sin ventana) ----------
    def hacer_paso(self, tipo: str, nombre: str, import_name: str, pip_name: str, avance: Callable[[str], None]) -> str:
        """Verifica e instala un requisito. Devuelve 'ya' o 'nuevo'; si falla lanza RuntimeError."""
        if tipo == "python":
            ok = self.python_ok()
        elif tipo == "programa":
            ok = self.programa_ok()
        else:
            ok = self.dep_ok(import_name)
        if ok:
            return "ya"
        if tipo == "python":
            self.instalar_python(avance)
        elif tipo == "programa":
            self.instalar_programa(avance)
        else:
            if not self.python_ok():
                raise RuntimeError("No se puede instalar sin Python 3.14.")
            ok2, det = self.instalar_dependencia(nombre, pip_name)
            if not ok2 or not self.dep_ok(import_name):
                raise RuntimeError(det or "El paquete se instalo pero no aparece en site-packages.")
        return "nuevo"

    def finalizar(self) -> None:
        self.crear_accesos()
        self.registrar_desinstalador()


# ----------------------------------------------------------------------------------------------------
# Ventana (plantilla VentanaVerificacion, sin proxy)
# ----------------------------------------------------------------------------------------------------
class VentanaVerificacion:
    ANCHO = 400

    def __init__(self, inst: Instalacion) -> None:
        self.inst = inst
        self.iniciar = False
        self.errores: dict = {}
        self._pending_after_ids: list = []

        self.ventana = tk.Tk()
        self.ventana.title("🔍 Verificación de dependencias")
        self.ventana.resizable(False, False)
        self.ventana.configure(bg="#f8f9fa")
        self.ventana.attributes("-topmost", True)
        self.ventana.protocol("WM_DELETE_WINDOW", self._al_cerrar)

        cont = tk.Frame(self.ventana, bg="#f8f9fa", padx=10, pady=10)
        cont.pack(fill="both", expand=True)

        tk.Label(cont, text="📦 Verificando dependencias", font=("Segoe UI", 14, "bold"), bg="#f8f9fa", fg="#2c3e50").pack(anchor="w")
        tk.Label(cont, text="Asegurando que todo esté listo para comenzar", font=("Segoe UI", 9), bg="#f8f9fa", fg="#7f8c8d").pack(anchor="w", pady=(0, 8))

        self.labels_estado: dict = {}
        self.filas = [(FILA_PYTHON, "python", "", ""), (FILA_PROGRAMA, "programa", "", "")] + \
                     [(n, "pip", i, p) for n, i, p in DEPENDENCIAS]
        for nombre, _t, _i, _p in self.filas:
            fila = tk.Frame(cont, bg="#f8f9fa")
            fila.pack(fill="x", pady=1)
            tk.Label(fila, text=nombre, font=("Segoe UI", 9, "bold"), bg="#f8f9fa", fg="#2c3e50", width=14, anchor="w").pack(side="left")
            lbl = tk.Label(fila, text="⏳ Pendiente", font=("Segoe UI", 9), bg="#f8f9fa", fg="#7f8c8d", anchor="w")
            lbl.pack(side="left", fill="x", expand=True)
            lbl.bind("<Button-1>", lambda _e, n=nombre: self._detalle(n))
            self.labels_estado[nombre] = lbl

        self.barra = ttk.Progressbar(cont, mode="determinate", length=380)
        self.barra.pack(pady=(8, 4))

        self.lbl_general = tk.Label(cont, text="🔍 Verificando...", font=("Segoe UI", 9), bg="#f8f9fa", fg="#2c3e50",
                                    anchor="w", justify="left", wraplength=370)
        self.lbl_general.pack(fill="x", pady=(0, 6))

        self.frame_botones = tk.Frame(cont, bg="#f8f9fa")
        self.frame_botones.pack(fill="x", pady=(0, 6))
        self.Iniciar_app = tk.Button(self.frame_botones, text="🚀 Iniciar aplicación", font=("Segoe UI", 9, "bold"), bg="#95a5a6", fg="white",
                                     relief="flat", padx=10, pady=5, state="disabled", command=self._iniciar_app)
        self.Iniciar_app.pack(side="left")
        self.btn_reintentar = tk.Button(self.frame_botones, text="🔄 Reintentar", font=("Segoe UI", 9, "bold"), bg="#95a5a6", fg="white",
                                        relief="flat", padx=10, pady=5, state="disabled", command=self._reintentar)
        self.btn_reintentar.pack(side="left", padx=(8, 0))

        self.ventana.update_idletasks()
        alto = self.ventana.winfo_reqheight() + 16
        x = (self.ventana.winfo_screenwidth() - self.ANCHO) // 2
        y = (self.ventana.winfo_screenheight() - alto) // 2
        self.ventana.geometry(f"{self.ANCHO}x{alto}+{x}+{y}")

        self._programar(150, self._lanzar)

    # ---------- utilidades de la plantilla ----------
    def _programar(self, ms: int, fn: Callable[[], None]):
        caja: list = []

        def correr() -> None:
            if caja and caja[0] in self._pending_after_ids:
                self._pending_after_ids.remove(caja[0])
            fn()
        try:
            id_ = self.ventana.after(ms, correr)
        except (tk.TclError, RuntimeError):
            return None
        caja.append(id_)
        self._pending_after_ids.append(id_)
        return id_

    def _cancelar_pendientes(self) -> None:
        for id_ in self._pending_after_ids:
            try:
                self.ventana.after_cancel(id_)
            except (tk.TclError, RuntimeError):
                pass
        self._pending_after_ids.clear()

    @staticmethod
    def _config_seguro(widget, **kwargs) -> None:
        try:
            if widget.winfo_exists():
                widget.config(**kwargs)
        except (tk.TclError, RuntimeError):
            pass

    def _ui(self, widget, **kwargs) -> None:
        self._programar(0, lambda: self._config_seguro(widget, **kwargs))

    def _detalle(self, nombre: str) -> None:
        if self.errores.get(nombre):
            messagebox.showerror(f"Error en '{nombre}'", self.errores[nombre], parent=self.ventana)

    # ---------- verificacion (hilo) ----------
    def _lanzar(self) -> None:
        self.inst.cancelado = False
        self.errores.clear()
        for nombre, _t, _i, _p in self.filas:
            self._config_seguro(self.labels_estado[nombre], text="⏳ Pendiente", fg="#7f8c8d")
        self._config_seguro(self.barra, value=0)
        self._config_seguro(self.Iniciar_app, state="disabled", bg="#95a5a6")
        self._config_seguro(self.btn_reintentar, state="disabled", bg="#95a5a6")
        threading.Thread(target=self._trabajo, daemon=True).start()

    def _trabajo(self) -> None:
        total = len(self.filas)
        nuevos = ya = fallos = 0
        general = self.lbl_general
        for idx, (nombre, tipo, imp, pip_name) in enumerate(self.filas):
            if self.inst.cancelado:
                return
            lbl = self.labels_estado[nombre]
            self._ui(general, text=f"🔍 Verificando {nombre}...")
            try:
                necesita = not {"python": self.inst.python_ok, "programa": self.inst.programa_ok}.get(
                    tipo, lambda i=imp: self.inst.dep_ok(i))()
                if necesita:
                    self._ui(lbl, text="⏳ Instalando...", fg="#e67e22")
                    self._ui(general, text=f"📦 Instalando {nombre} (puede tardar unos minutos)...")
                r = self.inst.hacer_paso(tipo, nombre, imp, pip_name, lambda t: self._ui(general, text=t))
                self._ui(lbl, text="✅ Instalado", fg="#27ae60")
                if r == "ya":
                    ya += 1
                else:
                    nuevos += 1
            except (OSError, RuntimeError, urllib.error.URLError) as e:
                self.errores[nombre] = str(e)
                self.inst.log(f"ERROR en {nombre}: {e}")
                self._ui(lbl, text="❌ Error -- click acá para ver el detalle", fg="#e74c3c")
                fallos += 1
            self._ui(self.barra, value=((idx + 1) / total) * 100)
        if fallos == 0:
            self._ui(general, text="🔧 Creando accesos directos y desinstalador...")
            self.inst.finalizar()
            self._programar(0, lambda: self._terminar(True, f"✅ Todo listo: {nuevos} instalado(s), {ya} ya estaban."))
        else:
            self._programar(0, lambda: self._terminar(False, f"❌ Hubo {fallos} error(es): tocá el ❌ para ver el detalle y reintentá."))

    def _terminar(self, ok: bool, resumen: str) -> None:
        self._config_seguro(self.lbl_general, text=resumen)
        if ok:
            self._config_seguro(self.Iniciar_app, state="normal", bg="#27ae60")
            self._programar(800, self._iniciar_app)                 # todo en orden: arranca sola, sin esperar el boton
        else:
            self._config_seguro(self.btn_reintentar, state="normal", bg="#e67e22")

    def _reintentar(self) -> None:
        self._lanzar()

    def _iniciar_app(self) -> None:
        if self.iniciar:
            return
        self._cancelar_pendientes()
        self.iniciar = True
        self.ventana.quit()
        self.ventana.destroy()

    def _al_cerrar(self) -> None:
        self._cancelar_pendientes()
        self.inst.cancelado = True
        p = self.inst.proc_actual
        if p is not None:
            try:
                p.kill()
            except OSError:
                pass
        sys.exit(0)


# ----------------------------------------------------------------------------------------------------
# Programa
# ----------------------------------------------------------------------------------------------------
def instalar_sin_ventana(inst: Instalacion) -> int:
    filas = [(FILA_PYTHON, "python", "", ""), (FILA_PROGRAMA, "programa", "", "")] + [(n, "pip", i, p) for n, i, p in DEPENDENCIAS]
    for nombre, tipo, imp, pip_name in filas:
        try:
            r = inst.hacer_paso(tipo, nombre, imp, pip_name, lambda t: inst.log(t))
            inst.log(f"{nombre}: {r}")
        except (OSError, RuntimeError, urllib.error.URLError) as e:
            inst.log(f"ERROR en {nombre}: {e}")
            return 1
    inst.finalizar()
    return 0


def main(argv: list) -> int:
    if os.name == "nt" and not es_admin():
        relanzar_como_admin(argv)
        return 0
    inst = Instalacion(calcular_raiz(argv))
    if "--sin-ventana" in argv:
        codigo = instalar_sin_ventana(inst)
        if codigo == 0 and "--no-lanzar" not in argv:
            inst.lanzar_app()
        return codigo
    if inst.todo_ok() and "--ventana" not in argv:
        inst.finalizar()
        if "--no-lanzar" not in argv:
            inst.lanzar_app()
        return 0
    win = VentanaVerificacion(inst)
    win.ventana.mainloop()
    if win.iniciar and "--no-lanzar" not in argv:
        inst.lanzar_app()
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
