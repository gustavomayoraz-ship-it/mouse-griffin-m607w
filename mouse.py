import tkinter as tk
from tkinter import ttk, messagebox
import threading
import time
import time as time_module
import sys
import os
import subprocess
import importlib.util

# =====================================================
#   CONFIGURACIÓN INICIAL - OCULTAR CONSOLA EN WINDOWS
# =====================================================
if sys.platform == "win32":
    try:
        import ctypes
        whnd = ctypes.windll.kernel32.GetConsoleWindow()
        if whnd != 0:
            ctypes.windll.user32.ShowWindow(whnd, 0)
    except:
        pass

# =====================================================
#   MÓDULOS QUE SE CARGAN DESPUÉS DE VERIFICAR/INSTALAR
#   LAS DEPENDENCIAS (ver VentanaVerificacion y
#   cargar_modulos_post_verificacion más abajo)
# =====================================================
pydirectinput = None
Listener = None
Button = None
psutil = None
pystray = None
item = None
Image = None
ImageDraw = None
DETECCION_MEJORADA_DISPONIBLE = False
SYSTEM_TRAY_DISPONIBLE = False

# Máximo de clics por segundo permitido (cada clic dura ~21ms con pydirectinput,
# así que ~45 CPS es el techo técnico; 25 deja margen de seguridad entre clics)
MAX_CPS = 25

# Dependencias que necesita esta app: (nombre a mostrar, nombre de import, paquete pip)
DEPENDENCIAS_APP = [
    ("pydirectinput", "pydirectinput", "pydirectinput"),
    ("pynput", "pynput", "pynput"),
    ("psutil", "psutil", "psutil"),
    ("pystray", "pystray", "pystray"),
    ("Pillow", "PIL", "Pillow"),
    ("pywin32", "win32com", "pywin32"),
]


def cargar_modulos_post_verificacion():
    """
    Importa los módulos ya verificados/instalados por VentanaVerificacion y
    define las banderas de disponibilidad. Se llama una sola vez, después de
    cerrar la ventana de verificación y antes de abrir la app principal.
    """
    global pydirectinput, Listener, Button, psutil
    global DETECCION_MEJORADA_DISPONIBLE, SYSTEM_TRAY_DISPONIBLE
    global pystray, item, Image, ImageDraw

    try:
        import pydirectinput as _pydirectinput
        pydirectinput = _pydirectinput
    except ImportError:
        pydirectinput = None

    try:
        from pynput.mouse import Listener as _Listener, Button as _Button
        Listener = _Listener
        Button = _Button
    except ImportError:
        Listener = None
        Button = None

    try:
        import psutil as _psutil
        psutil = _psutil
    except ImportError:
        psutil = None

    try:
        import win32com.client  # noqa: F401
        import win32gui  # noqa: F401
        import win32process  # noqa: F401
        DETECCION_MEJORADA_DISPONIBLE = True
    except ImportError:
        DETECCION_MEJORADA_DISPONIBLE = False

    try:
        import pystray as _pystray
        from pystray import MenuItem as _item
        from PIL import Image as _Image, ImageDraw as _ImageDraw
        pystray = _pystray
        item = _item
        Image = _Image
        ImageDraw = _ImageDraw
        SYSTEM_TRAY_DISPONIBLE = True
    except ImportError:
        SYSTEM_TRAY_DISPONIBLE = False

    return pydirectinput is not None and Listener is not None and psutil is not None


# =====================================================
#   VENTANA DE VERIFICACIÓN / INSTALACIÓN DE DEPENDENCIAS
# =====================================================

class VentanaVerificacion:
    """Ventana estándar de verificación/instalación de dependencias."""

    def __init__(self, ventana, dependencias, al_completar):
        self.ventana = ventana
        self.dependencias = dependencias
        self.al_completar = al_completar

        self._pending_after_ids = []
        self.labels_estado = {}

        self.ventana.title("🔍 Verificación de dependencias")
        self.ventana.resizable(False, False)
        self.ventana.configure(bg="#f8f9fa")
        self.ventana.attributes('-topmost', True)
        self.ventana.protocol('WM_DELETE_WINDOW', self._cerrar_ventana)

        self._construir_ui()
        self._centrar_ventana()

        threading.Thread(target=self._verificar_dependencias, daemon=True).start()

    # ---------- utilidades de hilo/ventana seguras ----------

    def _programar(self, ms, fn):
        after_id = self.ventana.after(ms, fn)
        self._pending_after_ids.append(after_id)
        return after_id

    def _cancelar_pendientes(self):
        for after_id in self._pending_after_ids:
            try:
                self.ventana.after_cancel(after_id)
            except Exception:
                pass
        self._pending_after_ids = []

    def _config_seguro(self, widget, **kwargs):
        try:
            if widget.winfo_exists():
                widget.config(**kwargs)
        except Exception:
            pass

    def _centrar_ventana(self):
        self.ventana.update_idletasks()
        ancho = 400
        alto = self.ventana.winfo_reqheight() + 16
        x = (self.ventana.winfo_screenwidth() // 2) - (ancho // 2)
        y = (self.ventana.winfo_screenheight() // 2) - (alto // 2)
        self.ventana.geometry(f"{ancho}x{alto}+{x}+{y}")

    # ---------- construcción de la interfaz ----------

    def _construir_ui(self):
        cont = tk.Frame(self.ventana, bg="#f8f9fa")
        cont.pack(fill="both", expand=True, padx=16, pady=12)

        tk.Label(cont, text="📦 Verificando dependencias", font=("Segoe UI", 14, "bold"),
                 fg="#2c3e50", bg="#f8f9fa").pack(anchor="w")
        tk.Label(cont, text="Asegurando que todo esté listo para comenzar",
                 font=("Segoe UI", 9), fg="#7f8c8d", bg="#f8f9fa").pack(anchor="w", pady=(0, 10))

        for nombre, import_name, package_name in self.dependencias:
            fila = tk.Frame(cont, bg="#f8f9fa")
            fila.pack(fill="x", pady=2)
            tk.Label(fila, text=nombre, font=("Segoe UI", 9, "bold"), width=14,
                     anchor="w", bg="#f8f9fa", fg="#2c3e50").pack(side="left")
            lbl_estado = tk.Label(fila, text="⏳ Pendiente", font=("Segoe UI", 9),
                                   bg="#f8f9fa", fg="#7f8c8d")
            lbl_estado.pack(side="left")
            self.labels_estado[nombre] = lbl_estado

        self.progreso = ttk.Progressbar(cont, mode="determinate", length=380)
        self.progreso.pack(pady=(8, 6))

        self.estado_general_var = tk.StringVar(value="🔍 Iniciando verificación...")
        tk.Label(cont, textvariable=self.estado_general_var, font=("Segoe UI", 9),
                 bg="#f8f9fa", fg="#2c3e50").pack(pady=(0, 8))

        frame_botones = tk.Frame(cont, bg="#f8f9fa")
        frame_botones.pack(fill="x")

        self.btn_iniciar = tk.Button(frame_botones, text="🚀 Iniciar aplicación",
                                      state="disabled", bg="#95a5a6", fg="white",
                                      font=("Segoe UI", 9, "bold"), relief="raised", bd=2,
                                      command=self._iniciar_app)
        self.btn_iniciar.pack(fill="x", expand=True)

    # ---------- verificación e instalación de dependencias ----------

    def _modulo_disponible(self, import_name):
        try:
            if import_name == "PIL":
                import PIL  # noqa: F401
            else:
                importlib.import_module(import_name)
            return True
        except ImportError:
            return False

    def _instalar_paquete(self, package_name):
        try:
            cmd = [sys.executable, "-m", "pip", "install", package_name,
                   "--quiet", "--no-warn-script-location"]
            kwargs = {"creationflags": 0x08000000} if sys.platform == "win32" else {}
            subprocess.check_call(cmd, **kwargs)
            return True
        except Exception:
            return False

    def _verificar_dependencias(self):
        total = len(self.dependencias)

        for idx, (nombre, import_name, package_name) in enumerate(self.dependencias):
            self._programar(0, lambda n=nombre: self._config_seguro(
                self.labels_estado[n], text="🔍 Verificando...", fg="#2c3e50"))
            self._programar(0, lambda n=nombre: self.estado_general_var.set(f"🔍 Verificando {n}..."))

            if self._modulo_disponible(import_name):
                self._programar(0, lambda n=nombre: self._config_seguro(
                    self.labels_estado[n], text="✅ Instalado", fg="#27ae60"))
            else:
                self._programar(0, lambda n=nombre: self._config_seguro(
                    self.labels_estado[n], text="📦 Instalando...", fg="#e67e22"))
                self._programar(0, lambda n=nombre: self.estado_general_var.set(f"📦 Instalando {n}..."))

                if self._instalar_paquete(package_name):
                    self._programar(0, lambda n=nombre: self._config_seguro(
                        self.labels_estado[n], text="✅ Instalado", fg="#27ae60"))
                else:
                    self._programar(0, lambda n=nombre: self._config_seguro(
                        self.labels_estado[n], text="❌ Error", fg="#c0392b"))

            progreso_pct = ((idx + 1) / total) * 100
            self._programar(0, lambda p=progreso_pct: self._config_seguro(self.progreso, value=p))

        self._programar(0, self._finalizar_verificacion)

    def _finalizar_verificacion(self):
        todas_ok = all(self.labels_estado[n]["text"].startswith("✅") for n, _, _ in self.dependencias)
        self._config_seguro(self.btn_iniciar, state="normal", bg="#27ae60")
        if todas_ok:
            self.estado_general_var.set("✅ Todo listo, iniciando...")
            # Todo en orden: inicia la app sola (una pausa mínima para ver el ✅)
            self._programar(300, self._iniciar_app)
        else:
            self.estado_general_var.set("⚠️ Algunas dependencias fallaron, podés continuar de todas formas")

    # ---------- acciones de la ventana ----------

    def _iniciar_app(self):
        self._cancelar_pendientes()
        self.ventana.quit()
        self.ventana.destroy()
        if self.al_completar:
            self.al_completar()

    def _cerrar_ventana(self):
        self._cancelar_pendientes()
        sys.exit(0)

# =====================================================
#   CLASE PRINCIPAL DE LA APLICACIÓN
# =====================================================

class MouseConfigApp:
    def __init__(self, root):
        # Configuración inicial de la ventana
        self.root = root
        self.root.title("Mouse Griffin M607W")
        self.root.geometry("490x400")
        self.root.resizable(False, False)
        self.root.eval('tk::PlaceWindow . center')
        
        # Configuración de cierre
        # La X cierra la aplicación; el botón 📌 es el que manda al tray
        self.root.protocol('WM_DELETE_WINDOW', self.cerrar_aplicacion)
        
        # Variables de estado de la aplicación
        self.ejecutandose = True
        self.monitor_thread = None
        self.deteccion_thread = None
        self.animacion_thread = None
        self.listener = None
        self.icono_tray = None
        self.minimizado_tray = False
        self.boton_hover = None
        
        # CONFIGURACIÓN PARA CPS REALES (máximo: MAX_CPS)
        # Usamos tiempo de pulsación mínimo (1ms)
        self.TIEMPO_PULSACION = 0.001  # 1ms
        
        # Variables para congelar cursor
        self.cursor_congelado = False
        self.posicion_congelada = None
        self.congelar_thread = None
        self.detener_congelar = False
        
        # Variables para periodo de gracia
        self.tiempo_activacion_manual = {"x1": 0, "x2": 0}
        self.periodo_gracia = 1.0
        
        # Inicialización de configuraciones y estados
        self.inicializar_configuraciones()
        self.inicializar_estados()
        
        # Configuración de la interfaz y funcionalidades
        self.setup_ui_compacta()
        self.cargar_configuracion()
        self.iniciar_servicios()

    def inicializar_configuraciones(self):
        """Inicializa las configuraciones de los botones"""
        self.configuraciones = {
            "left": {
                "tipo": "mouse", "tecla": "left", 
                "modo": "intervalo", "intervalo": 5, "cps": 5, "activo": False
            },
            "right": {
                "tipo": "mouse", "tecla": "right", 
                "modo": "intervalo", "intervalo": 5, "cps": 5, "activo": False
            },
            "middle": {
                "tipo": "mouse", "tecla": "middle", 
                "modo": "intervalo", "intervalo": 5, "cps": 5, "activo": False
            },
            "x1": {
                "tipo": "teclado", "tecla": "m", 
                "modo": "intervalo", "intervalo": 5, "cps": 5, "activo": False,
                "congelar_cursor": False
            },
            "x2": {
                "tipo": "teclado", "tecla": "n", 
                "modo": "intervalo", "intervalo": 5, "cps": 5, "activo": False,
                "congelar_cursor": False
            }
        }

    def inicializar_estados(self):
        """Inicializa los estados de los botones y variables de control"""
        self.botones_presionados = {
            "left": False, "right": False, "middle": False, "x1": False, "x2": False
        }
        self.botones_activados = {"x1": False, "x2": False}
        self.modo_manual_activo = {"x1": False, "x2": False}
        self.hilos_manual = {"x1": None, "x2": None}
        self.detener_manual = {"x1": False, "x2": False}
        # Trackea el hilo de auto-click de cada botón para evitar que se
        # dupliquen si el botón se activa/desactiva muy rápido
        self.hilos_auto = {"left": None, "right": None, "middle": None, "x1": None, "x2": None}
        self.ultima_accion_time = time_module.time()
        self.estado_global = "desactivado"
        self.boton_x1_desactivado = False
        self.boton_x2_desactivado = False
        self.boton_actual = None

    def iniciar_servicios(self):
        """Inicia todos los servicios en segundo plano"""
        self.iniciar_monitoreo()
        self.iniciar_deteccion_usb()
        self.iniciar_animacion_botones()
        
        if SYSTEM_TRAY_DISPONIBLE:
            self.crear_icono_tray()
            self.iniciar_monitoreo_estado_tray()

    # =====================================================
    #   INTERFAZ DE USUARIO COMPACTA
    # =====================================================

    def setup_ui_compacta(self):
        """Configura la interfaz de usuario compacta"""
        self.configurar_estilos_botones()
        
        main_frame = ttk.Frame(self.root, padding="5")
        main_frame.pack(fill=tk.BOTH, expand=True)
        
        self.setup_titulo(main_frame)
        
        content_frame = ttk.Frame(main_frame)
        content_frame.pack(fill=tk.BOTH, expand=True)
        
        self.setup_columna_izquierda(content_frame)
        self.setup_columna_derecha(content_frame)
        self.setup_barra_inferior(main_frame)

    def setup_titulo(self, parent):
        """Configura el frame del título con estado USB"""
        title_frame = ttk.Frame(parent)
        title_frame.pack(fill=tk.X, pady=(0, 5))
        
        title_label = ttk.Label(title_frame, text="Mouse Griffin M607W",
                               font=("Segoe UI", 12, "bold"))
        title_label.pack(side=tk.LEFT)
        
        self.usb_status_var = tk.StringVar(value="🔍 Conectando...")
        usb_status = ttk.Label(title_frame, textvariable=self.usb_status_var,
                              font=("Segoe UI", 8), foreground="gray")
        usb_status.pack(side=tk.RIGHT)

    def setup_columna_izquierda(self, parent):
        """Configura la columna izquierda con el mouse interactivo"""
        left_frame = ttk.LabelFrame(parent, text="Botones", padding="5")
        left_frame.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=(0, 5))
        
        self.canvas = tk.Canvas(left_frame, width=235, height=205, bg="#eef1f3",
                               relief="flat", bd=0, highlightthickness=0)
        self.canvas.pack(pady=5)
        self.dibujar_mouse_compacto()
        
        self.setup_indicadores_estado(left_frame)
        self.setup_botones_desactivacion(left_frame)

    def setup_indicadores_estado(self, parent):
        """Configura los indicadores de estado X1 y X2"""
        status_frame = ttk.Frame(parent)
        status_frame.pack(fill=tk.X, pady=2)
        
        self.estado_x1_var = tk.StringVar(value="X1: OFF")
        self.estado_x2_var = tk.StringVar(value="X2: OFF")
        
        estado_x1_label = ttk.Label(status_frame, textvariable=self.estado_x1_var,
                                   font=("Segoe UI", 8, "bold"), foreground="red")
        estado_x1_label.pack(side=tk.LEFT)
        
        estado_x2_label = ttk.Label(status_frame, textvariable=self.estado_x2_var,
                                   font=("Segoe UI", 8, "bold"), foreground="red")
        estado_x2_label.pack(side=tk.RIGHT)

    def setup_botones_desactivacion(self, parent):
        """Configura los botones para desactivar/activar X1 y X2 individualmente"""
        botones_frame = ttk.Frame(parent)
        botones_frame.pack(fill=tk.X, pady=(5, 0))
        
        self.desactivar_x1_btn = tk.Button(botones_frame, text="🔒 X1", 
                                          font=("Segoe UI", 9, "bold"),
                                          bg="#4CAF50", fg="white",
                                          relief="raised", bd=2,
                                          command=self.toggle_desactivar_x1)
        self.desactivar_x1_btn.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 5))
        
        self.desactivar_x2_btn = tk.Button(botones_frame, text="🔒 X2",
                                          font=("Segoe UI", 9, "bold"),
                                          bg="#4CAF50", fg="white",
                                          relief="raised", bd=2,
                                          command=self.toggle_desactivar_x2)
        self.desactivar_x2_btn.pack(side=tk.RIGHT, fill=tk.X, expand=True, padx=(5, 0))
        
        self.actualizar_estilo_botones_desactivacion()

    def setup_columna_derecha(self, parent):
        """Configura la columna derecha con controles de configuración"""
        right_frame = ttk.LabelFrame(parent, text="Configuración", padding="5")
        right_frame.pack(side=tk.RIGHT, fill=tk.BOTH, expand=True)
        
        self.control_frame = ttk.Frame(right_frame)
        self.control_frame.pack(fill=tk.BOTH, expand=True)
        self.setup_controles_compactos()

    def setup_barra_inferior(self, parent):
        """Configura la barra inferior con estado y botones de acción"""
        bottom_frame = ttk.Frame(parent)
        bottom_frame.pack(fill=tk.X, pady=(5, 0))
        
        self.status_var = tk.StringVar(value="Selecciona un botón")
        status_label = ttk.Label(bottom_frame, textvariable=self.status_var,
                                font=("Segoe UI", 8), foreground="blue")
        status_label.pack(side=tk.LEFT)
        
        btn_frame = ttk.Frame(bottom_frame)
        btn_frame.pack(side=tk.RIGHT)
        
        botones = [
            ("💾", self.guardar_configuracion),
            ("📂", self.cargar_configuracion)
        ]
        
        if SYSTEM_TRAY_DISPONIBLE:
            botones.append(("📌", self.minimizar_a_tray))
        else:
            botones.append(("❌", self.cerrar_aplicacion))
        
        for texto, comando in botones:
            btn = ttk.Button(btn_frame, text=texto, width=3, command=comando)
            btn.pack(side=tk.LEFT, padx=(2, 0))

    def _puntos_rect_redondeado(self, x1, y1, x2, y2, r):
        """Puntos de control para un rectángulo con esquinas redondeadas,
        pensados para create_polygon(..., smooth=True)."""
        return self._puntos_trapecio_redondeado(x1, x2, x1, x2, y1, y2, r)

    def _puntos_trapecio_redondeado(self, x1_arriba, x2_arriba, x1_abajo, x2_abajo, y1, y2, r):
        """Puntos de control para un trapecio con esquinas redondeadas (el
        cuerpo del mouse: más ancho arriba -donde están los botones- y más
        angosto abajo). Con smooth=True, Tkinter convierte estos puntos en
        curvas suaves en cada esquina en vez de vértices en ángulo recto."""
        return [
            x1_arriba + r, y1,
            x2_arriba - r, y1,
            x2_arriba, y1,
            x2_arriba, y1 + r,
            x2_abajo, y2 - r,
            x2_abajo, y2,
            x2_abajo - r, y2,
            x1_abajo + r, y2,
            x1_abajo, y2,
            x1_abajo, y2 - r,
            x1_arriba, y1 + r,
            x1_arriba, y1,
        ]

    def dibujar_mouse_compacto(self):
        """Dibuja la representación gráfica del mouse: una silueta redondeada
        (cuerpo + botones L/R insertados + rueda + los 2 laterales X1/X2),
        en vez del óvalo con rectángulos encima de la versión anterior (los
        rectángulos tenían esquinas cuadradas que se salían del contorno
        redondeado del óvalo, por eso se veía mal)."""
        self.canvas.delete("all")

        mouse_color = "#2C3E50"
        borde_color = "#1C2833"
        button_color = "#34495E"
        wheel_color = "#7F8C8D"
        wheel_notch = "#5D6A72"
        lateral_color = "#E74C3C"
        sombra_color = "#dde2e6"

        # Sombra suave debajo del cuerpo para dar sensación de profundidad
        self.canvas.create_polygon(
            self._puntos_rect_redondeado(55, 172, 185, 192, 9),
            fill=sombra_color, outline="", smooth=True, tags="decoracion"
        )

        # Cuerpo del mouse: trapecio redondeado, más ancho en la parte de
        # arriba (hombros, donde están L/R) y más angosto hacia abajo
        self.canvas.create_polygon(
            self._puntos_trapecio_redondeado(38, 200, 58, 180, 12, 172, 32),
            fill=mouse_color, outline=borde_color, width=1, smooth=True, tags="mouse_cuerpo"
        )

        # Botones izquierdo y derecho, insertados dentro del cuerpo (con
        # margen suficiente para que sus esquinas nunca sobresalgan del
        # contorno del cuerpo)
        self.boton_left = self.canvas.create_polygon(
            self._puntos_rect_redondeado(46, 18, 116, 80, 14),
            fill=button_color, outline="", smooth=True, tags="left"
        )
        self.boton_right = self.canvas.create_polygon(
            self._puntos_rect_redondeado(122, 18, 192, 80, 14),
            fill=button_color, outline="", smooth=True, tags="right"
        )
        self.canvas.create_line(119, 22, 119, 78, fill=borde_color, width=1, tags="decoracion")

        # Rueda central
        self.boton_middle = self.canvas.create_polygon(
            self._puntos_rect_redondeado(108, 32, 130, 66, 8),
            fill=wheel_color, outline=borde_color, width=1, smooth=True, tags="middle"
        )
        self.canvas.create_line(119, 40, 119, 46, fill=wheel_notch, width=2, tags="decoracion")
        self.canvas.create_line(119, 50, 119, 56, fill=wheel_notch, width=2, tags="decoracion")

        # Botones laterales X1 (abajo) y X2 (arriba), asomando del costado
        # izquierdo del cuerpo
        self.boton_x2 = self.canvas.create_polygon(
            self._puntos_rect_redondeado(16, 60, 49, 92, 9),
            fill=lateral_color, outline=borde_color, width=1, smooth=True, tags="x2"
        )
        self.boton_x1 = self.canvas.create_polygon(
            self._puntos_rect_redondeado(16, 98, 49, 130, 9),
            fill=lateral_color, outline=borde_color, width=1, smooth=True, tags="x1"
        )

        # Las etiquetas quedan con su propio tag ("label_x1", etc.) y NO con
        # el tag del botón ("x1", etc.), porque ese tag lo usa itemconfig en
        # otros métodos para pintar el botón (fill=color) - si el texto
        # también lo tuviera, esos cambios de color le pintarían el número
        # encima y se dejaría de ver.
        etiquetas = [
            (81, 49, "L", "label_left"),
            (157, 49, "R", "label_right"),
            (32, 76, "2", "label_x2"),
            (32, 114, "1", "label_x1"),
        ]

        for x, y, texto, tag_label in etiquetas:
            self.canvas.create_text(x, y, text=texto, fill="white",
                                     font=("Segoe UI", 9, "bold"), tags=tag_label)

        # Puntos de estado ON/OFF junto a cada botón lateral (en vez de texto
        # "● OFF" que no entraba en el margen sin superponerse al botón)
        self.estado_x1_canvas = self.canvas.create_oval(4, 110, 12, 118, fill="#E74C3C",
                                                       outline="white", width=1, tags="estado_x1")
        self.estado_x2_canvas = self.canvas.create_oval(4, 72, 12, 80, fill="#E74C3C",
                                                       outline="white", width=1, tags="estado_x2")

        # Cada botón se enlaza con su propio tag Y con el tag de su etiqueta
        # de texto, para que el click/hover se registre también si el mouse
        # queda justo arriba de la letra o el número (que antes "tapaban" el
        # click porque el texto no tenía ningún tag interactivo).
        tags_por_boton = {
            "left": ["left", "label_left"],
            "right": ["right", "label_right"],
            "middle": ["middle"],
            "x1": ["x1", "label_x1"],
            "x2": ["x2", "label_x2"],
        }
        for boton, tags_asociados in tags_por_boton.items():
            for tag in tags_asociados:
                self.canvas.tag_bind(tag, "<Button-1>", lambda e, b=boton: self.mostrar_configuracion(b))

        # Hover robusto: en vez de depender de los eventos Enter/Leave de cada
        # item (que se pierden cuando el item cambia de color/estado con el
        # cursor quieto, o al pasar entre el botón y su letra), se calcula
        # qué botón está debajo del cursor con el movimiento del mouse y con
        # un chequeo periódico de respaldo.
        self._tags_a_boton = {tag: boton for boton, tags in tags_por_boton.items() for tag in tags}
        self.canvas.bind("<Motion>", lambda e: self._actualizar_hover(e.x, e.y))
        self.canvas.bind("<Leave>", lambda e: self._actualizar_hover(None, None))
        self._chequeo_hover_periodico()

    def setup_controles_compactos(self, boton=None):
        """Configura los controles de configuración para un botón específico"""
        for widget in self.control_frame.winfo_children():
            widget.destroy()
        
        if boton is None:
            label = ttk.Label(self.control_frame,
                             text="Haz click en un botón\npara configurarlo",
                             justify=tk.CENTER, foreground="gray", font=("Segoe UI", 9))
            label.pack(expand=True)
            return
        
        config = self.configuraciones[boton]
        nombres = {"left": "Izquierdo", "right": "Derecho",
                  "middle": "Rueda", "x1": "Lateral 1", "x2": "Lateral 2"}
        
        title = ttk.Label(self.control_frame, text=f"Botón: {nombres[boton]}",
                         font=("Segoe UI", 10, "bold"))
        title.pack(pady=(0, 8))
        
        if boton in ["x1", "x2"]:
            self.setup_controles_laterales(boton, config)
        
        self.setup_controles_comunes(boton, config)
        self.setup_controles_adicionales(boton, config)

    def setup_controles_laterales(self, boton, config):
        """Configura controles específicos para botones laterales"""
        tipo_frame = ttk.Frame(self.control_frame)
        tipo_frame.pack(fill=tk.X, pady=2)
        
        ttk.Label(tipo_frame, text="Tipo:", font=("Segoe UI", 8)).pack(side=tk.LEFT)
        self.tipo_var = tk.StringVar(value=config["tipo"])
        tipo_combo = ttk.Combobox(tipo_frame, textvariable=self.tipo_var,
                                 values=["teclado", "mouse"], state="readonly",
                                 width=8, font=("Segoe UI", 8))
        tipo_combo.pack(side=tk.RIGHT)
        tipo_combo.bind('<<ComboboxSelected>>', lambda e: self.actualizar_tipo_accion(boton))
        
        tecla_frame = ttk.Frame(self.control_frame)
        tecla_frame.pack(fill=tk.X, pady=2)
        
        ttk.Label(tecla_frame, text="Tecla:", font=("Segoe UI", 8)).pack(side=tk.LEFT)
        self.tecla_var = tk.StringVar(value=config["tecla"])
        
        self.tecla_combo = ttk.Combobox(tecla_frame, textvariable=self.tecla_var,
                                       state="readonly", width=8, font=("Segoe UI", 8))
        self.tecla_combo.pack(side=tk.RIGHT)
        self.tecla_combo.bind('<<ComboboxSelected>>', lambda e: self.actualizar_configuracion(boton))
        
        self.actualizar_opciones_teclas(config["tipo"])
        
        congelar_frame = ttk.Frame(self.control_frame)
        congelar_frame.pack(fill=tk.X, pady=2)
        
        self.congelar_var = tk.BooleanVar(value=config.get("congelar_cursor", False))
        congelar_check = ttk.Checkbutton(congelar_frame, text="Congelar cursor",
                                        variable=self.congelar_var,
                                        command=lambda: self.actualizar_congelar_cursor(boton))
        congelar_check.pack(side=tk.LEFT)

    def setup_controles_comunes(self, boton, config):
        """Configura controles comunes para todos los botones"""
        modo_frame = ttk.Frame(self.control_frame)
        modo_frame.pack(fill=tk.X, pady=2)
        
        ttk.Label(modo_frame, text="Modo:", font=("Segoe UI", 8)).pack(side=tk.LEFT)
        self.modo_var = tk.StringVar(value=config["modo"])
        modo_combo = ttk.Combobox(modo_frame, textvariable=self.modo_var,
                                 values=["intervalo", "cps"], state="readonly",
                                 width=8, font=("Segoe UI", 8))
        modo_combo.pack(side=tk.RIGHT)
        modo_combo.bind('<<ComboboxSelected>>', lambda e: self.actualizar_modo_repeticion(boton))
        
        self.controles_dinamicos_frame = ttk.Frame(self.control_frame)
        self.controles_dinamicos_frame.pack(fill=tk.X, pady=2)
        self.actualizar_controles_dinamicos_compactos(boton)

    def setup_controles_adicionales(self, boton, config):
        """Configura controles adicionales e información"""
        duracion_label = ttk.Label(self.control_frame, text="Duración: 1ms (ultra-rápido)",
                                  foreground="blue", font=("Segoe UI", 8))
        duracion_label.pack(pady=2)
        
        max_cps_label = ttk.Label(self.control_frame, text=f"Máximo: {MAX_CPS} CPS (precisión alta)",
                                  foreground="green", font=("Segoe UI", 8))
        max_cps_label.pack(pady=2)
        
        if boton in ["x1", "x2"]:
            self.setup_estado_boton_lateral(boton)
        
        self.manual_btn = tk.Button(self.control_frame, text="Manual",
                                   command=lambda: self.toggle_modo_manual(boton))
        self.manual_btn.pack(pady=4)
        
        self.actualizar_estilo_boton_manual(boton, modo_manual=self.modo_manual_activo.get(boton, False))

    def setup_estado_boton_lateral(self, boton):
        """Configura la visualización del estado para botones laterales"""
        estado_frame = ttk.Frame(self.control_frame)
        estado_frame.pack(fill=tk.X, pady=4)
        
        estado_text = "ACTIVADO" if self.botones_activados[boton] else "DESACTIVADO"
        estado_color = "green" if self.botones_activados[boton] else "red"
        self.estado_label = ttk.Label(estado_frame, text=f"Estado: {estado_text}",
                                     foreground=estado_color, font=("Segoe UI", 9, "bold"))
        self.estado_label.pack()

    def actualizar_controles_dinamicos_compactos(self, boton):
        """Actualiza los controles dinámicos según el modo seleccionado"""
        for widget in self.controles_dinamicos_frame.winfo_children():
            widget.destroy()
        
        config = self.configuraciones[boton]
        modo = self.modo_var.get()
        
        if modo == "intervalo":
            ttk.Label(self.controles_dinamicos_frame, text="Segundos:", font=("Segoe UI", 8)).pack(side=tk.LEFT)
            self.intervalo_var = tk.IntVar(value=config["intervalo"])
            intervalo_spin = ttk.Spinbox(self.controles_dinamicos_frame, from_=1, to=60, increment=1,
                                        textvariable=self.intervalo_var, width=6, font=("Segoe UI", 8),
                                        command=lambda: self.actualizar_configuracion(boton))
            intervalo_spin.pack(side=tk.RIGHT)
        else:
            ttk.Label(self.controles_dinamicos_frame, text="CPS:", font=("Segoe UI", 8)).pack(side=tk.LEFT)
            self.cps_var = tk.IntVar(value=config["cps"])
            cps_spin = ttk.Spinbox(self.controles_dinamicos_frame, from_=1, to=MAX_CPS, increment=1,
                                  textvariable=self.cps_var, width=6, font=("Segoe UI", 8),
                                  command=lambda: self.actualizar_configuracion(boton))
            cps_spin.pack(side=tk.RIGHT)
            
            cps = self.cps_var.get()
            intervalo_calculado = self.calcular_intervalo_desde_cps(cps)
            info_label = ttk.Label(self.controles_dinamicos_frame,
                                  text=f"≈ {intervalo_calculado*1000:.1f}ms/ciclo",
                                  foreground="green", font=("Segoe UI", 7))
            info_label.pack(side=tk.BOTTOM)

    # =====================================================
    #   FUNCIONES DE ACTUALIZACIÓN DE INTERFAZ
    # =====================================================

    def _desactivado(self, boton):
        return (boton == "x1" and self.boton_x1_desactivado) or (boton == "x2" and self.boton_x2_desactivado)

    def _color_base(self, boton):
        """Color normal de un botón según su estado actual (sin hover)"""
        if self._desactivado(boton):
            return "#7F8C8D"
        if self.botones_presionados[boton]:
            return "#E74C3C"
        if boton in ("x1", "x2") and self.botones_activados.get(boton):
            return "#27AE60"
        if boton == "middle":
            return "#7F8C8D"
        if boton in ("x1", "x2"):
            return "#E74C3C"
        return "#34495E"

    def _color_hover(self, boton):
        """Color al pasar el mouse: siempre claramente distinto al color base"""
        fijos = {"left": "#3498DB", "right": "#3498DB", "middle": "#E74C3C"}
        if boton in fijos:
            return fijos[boton]
        base = self._color_base(boton).lstrip("#")
        r, g, b = (int(base[i:i + 2], 16) for i in (0, 2, 4))
        r, g, b = (int(c + (255 - c) * 0.45) for c in (r, g, b))
        return f"#{r:02X}{g:02X}{b:02X}"

    def _reaplicar_hover(self):
        """Si el mouse sigue encima de un botón, vuelve a pintarle el hover
        (otros repintados del estado lo habían pisado)"""
        boton = getattr(self, "boton_hover", None)
        if boton and not self.botones_presionados[boton] and not self._desactivado(boton):
            try:
                self.canvas.itemconfig(boton, fill=self._color_hover(boton))
            except Exception:
                pass

    def _boton_bajo_cursor(self, x, y):
        """Devuelve el botón ('left', 'x1', ...) que está bajo (x, y) del canvas, o None"""
        if x is None:
            return None
        for item_id in reversed(self.canvas.find_overlapping(x, y, x, y)):
            for tag in self.canvas.gettags(item_id):
                boton = self._tags_a_boton.get(tag)
                if boton:
                    return boton
        return None

    def _actualizar_hover(self, x, y):
        """Aplica/quita el resaltado según el botón que haya bajo el cursor"""
        if not self.ejecutandose:
            return
        boton = self._boton_bajo_cursor(x, y)
        if boton and self._desactivado(boton):
            boton = None
        if boton == self.boton_hover:
            self._reaplicar_hover()
            return
        if boton is None:
            self.quitar_resaltado_compacto()
        else:
            self.resaltar_boton_compacto(boton)

    def _chequeo_hover_periodico(self):
        """Respaldo: cada 100 ms revisa dónde está el cursor y corrige el resaltado"""
        if not self.ejecutandose:
            return
        try:
            x = self.canvas.winfo_pointerx() - self.canvas.winfo_rootx()
            y = self.canvas.winfo_pointery() - self.canvas.winfo_rooty()
            dentro = (0 <= x < self.canvas.winfo_width() and 0 <= y < self.canvas.winfo_height()
                      and self.root.state() != "withdrawn"
                      and self.root.winfo_containing(self.canvas.winfo_pointerx(),
                                                     self.canvas.winfo_pointery()) is self.canvas)
            self._actualizar_hover(x if dentro else None, y if dentro else None)
        except Exception:
            pass
        self.root.after(100, self._chequeo_hover_periodico)

    def resaltar_boton_compacto(self, boton):
        """Resalta un botón al pasar el mouse por encima"""
        if self._desactivado(boton):
            return
        self.quitar_resaltado_compacto()
        self.boton_hover = boton
        if not self.botones_presionados[boton]:
            self.canvas.itemconfig(boton, fill=self._color_hover(boton))

    def quitar_resaltado_compacto(self):
        """Quita el resaltado de todos los botones"""
        self.boton_hover = None
        for boton in ("left", "right", "middle", "x1", "x2"):
            if not self.botones_presionados[boton]:
                self.canvas.itemconfig(boton, fill=self._color_base(boton))

    def actualizar_indicadores_estado(self):
        """Actualiza los indicadores de estado en la interfaz"""
        if not self.ejecutandose:
            return
            
        if self.botones_activados["x1"] and not self.boton_x1_desactivado:
            self.canvas.itemconfig(self.estado_x1_canvas, fill="#27AE60")
            self.estado_x1_var.set("X1: ON")
            if not self.botones_presionados["x1"]:
                self.canvas.itemconfig("x1", fill="#27AE60")
        else:
            self.canvas.itemconfig(self.estado_x1_canvas, fill="#E74C3C")
            self.estado_x1_var.set("X1: OFF")
            if not self.botones_presionados["x1"] and not self.boton_x1_desactivado:
                self.canvas.itemconfig("x1", fill="#E74C3C")
            elif self.boton_x1_desactivado:
                self.canvas.itemconfig("x1", fill="#7F8C8D")

        if self.botones_activados["x2"] and not self.boton_x2_desactivado:
            self.canvas.itemconfig(self.estado_x2_canvas, fill="#27AE60")
            self.estado_x2_var.set("X2: ON")
            if not self.botones_presionados["x2"]:
                self.canvas.itemconfig("x2", fill="#27AE60")
        else:
            self.canvas.itemconfig(self.estado_x2_canvas, fill="#E74C3C")
            self.estado_x2_var.set("X2: OFF")
            if not self.botones_presionados["x2"] and not self.boton_x2_desactivado:
                self.canvas.itemconfig("x2", fill="#E74C3C")
            elif self.boton_x2_desactivado:
                self.canvas.itemconfig("x2", fill="#7F8C8D")
        
        self._reaplicar_hover()
        self.actualizar_estado_global()

    def mostrar_configuracion(self, boton):
        """Muestra la configuración para un botón específico"""
        if (boton == "x1" and self.boton_x1_desactivado) or (boton == "x2" and self.boton_x2_desactivado):
            self.status_var.set(f"❌ Botón {boton.upper()} desactivado - Actívalo primero")
            return
            
        self.boton_actual = boton
        
        nombres = {"left": "Izquierdo", "right": "Derecho",
                  "middle": "Rueda", "x1": "Lateral 1", "x2": "Lateral 2"}
        self.status_var.set(f"Configurando: {nombres[boton]}")
        
        self.setup_controles_compactos(boton)
        
        self.quitar_resaltado_compacto()
        if not self.botones_presionados[boton]:
            self.canvas.itemconfig(boton, fill="#2ECC71")

    def actualizar_color_boton(self, boton, presionado):
        """Actualiza el color de un botón según su estado"""
        if not self.ejecutandose:
            return
            
        if (boton == "x1" and self.boton_x1_desactivado) or (boton == "x2" and self.boton_x2_desactivado):
            color = "#7F8C8D"
        elif presionado:
            color = "#E74C3C"
        elif boton in ["x1", "x2"] and self.botones_activados[boton]:
            color = "#27AE60"
        else:
            if boton == "middle":
                color = "#7F8C8D"
            elif boton in ["x1", "x2"]:
                color = "#E74C3C"
            else:
                color = "#34495E"
        
        self.canvas.itemconfig(boton, fill=color)
        self._reaplicar_hover()

    # =====================================================
    #   GESTIÓN DE BOTONES INDIVIDUALES
    # =====================================================

    def configurar_estilos_botones(self):
        pass

    def actualizar_estilo_botones_desactivacion(self):
        """Actualiza el estilo de los botones de desactivación individual"""
        if self.boton_x1_desactivado:
            self.desactivar_x1_btn.config(
                text="🔓 X1", 
                bg="#F44336",
                fg="white",
                activebackground="#D32F2F",
                activeforeground="white"
            )
        else:
            self.desactivar_x1_btn.config(
                text="🔒 X1", 
                bg="#4CAF50",
                fg="white",
                activebackground="#45A049",
                activeforeground="white"
            )
        
        if self.boton_x2_desactivado:
            self.desactivar_x2_btn.config(
                text="🔓 X2", 
                bg="#F44336",
                fg="white",
                activebackground="#D32F2F",
                activeforeground="white"
            )
        else:
            self.desactivar_x2_btn.config(
                text="🔒 X2", 
                bg="#4CAF50",
                fg="white",
                activebackground="#45A049",
                activeforeground="white"
            )

    def actualizar_estilo_boton_manual(self, boton, modo_manual=False):
        """Actualiza el estilo del botón Manual según el estado"""
        config = self.configuraciones.get(boton, {})
        congelar_activo = config.get("congelar_cursor", False)
        
        if congelar_activo:
            self.manual_btn.config(
                state=tk.DISABLED,
                bg="#CCCCCC",
                fg="#666666",
                activebackground="#CCCCCC",
                activeforeground="#666666"
            )
        else:
            if modo_manual:
                self.manual_btn.config(
                    state=tk.NORMAL,
                    text="Manual ✓",
                    bg="#4CAF50",
                    fg="white",
                    activebackground="#45A049",
                    activeforeground="white"
                )
            else:
                self.manual_btn.config(
                    state=tk.NORMAL,
                    text="Manual",
                    bg="SystemButtonFace",
                    fg="SystemButtonText",
                    activebackground="SystemButtonFace",
                    activeforeground="SystemButtonText"
                )

    def toggle_desactivar_x1(self):
        """Activa o desactiva el botón X1 individualmente"""
        self.boton_x1_desactivado = not self.boton_x1_desactivado
        
        if self.boton_x1_desactivado:
            self.status_var.set("🔒 Botón X1 desactivado")
            self.botones_activados["x1"] = False
            if self.modo_manual_activo["x1"]:
                self.detener_modo_manual("x1")
            if self.configuraciones["x1"].get("congelar_cursor", False):
                self.detener_congelamiento()
        else:
            self.status_var.set("✅ Botón X1 activado")
        
        self.actualizar_estilo_botones_desactivacion()
        self.quitar_resaltado_compacto()
        self.actualizar_indicadores_estado()
        self.actualizar_estado_global()
        
        if self.boton_actual == "x1":
            self.actualizar_estilo_boton_manual("x1", modo_manual=self.modo_manual_activo["x1"])

    def toggle_desactivar_x2(self):
        """Activa o desactiva el botón X2 individualmente"""
        self.boton_x2_desactivado = not self.boton_x2_desactivado
        
        if self.boton_x2_desactivado:
            self.status_var.set("🔒 Botón X2 desactivado")
            self.botones_activados["x2"] = False
            if self.modo_manual_activo["x2"]:
                self.detener_modo_manual("x2")
            if self.configuraciones["x2"].get("congelar_cursor", False):
                self.detener_congelamiento()
        else:
            self.status_var.set("✅ Botón X2 activado")
        
        self.actualizar_estilo_botones_desactivacion()
        self.quitar_resaltado_compacto()
        self.actualizar_indicadores_estado()
        self.actualizar_estado_global()
        
        if self.boton_actual == "x2":
            self.actualizar_estilo_boton_manual("x2", modo_manual=self.modo_manual_activo["x2"])

    # =====================================================
    #   SISTEMA TRAY (BANDEJA DEL SISTEMA)
    # =====================================================

    def crear_icono_tray(self):
        """Crea el icono para la bandeja del sistema"""
        if not SYSTEM_TRAY_DISPONIBLE:
            return
            
        try:
            self.actualizar_estado_global()
            self.crear_imagen_tray()
            
            menu = (
                item('Abrir', self.mostrar_aplicacion),
                item('Cerrar', self.cerrar_aplicacion_desde_tray)
            )
            
            self.icono_tray = pystray.Icon("mouse_griffin", self.imagen_tray, 
                                          "Mouse Griffin M607W", menu)
            
            thread = threading.Thread(target=self.iniciar_icono_tray, daemon=True)
            thread.start()
            
        except Exception:
            pass

    def crear_imagen_tray(self):
        """Crea la imagen del icono según el estado actual"""
        try:
            image = Image.new('RGB', (16, 16), color='#2C3E50')
            draw = ImageDraw.Draw(image)
            
            if self.estado_global == "activado" and not (self.boton_x1_desactivado and self.boton_x2_desactivado):
                draw.rectangle([4, 4, 12, 12], fill='#00FF00', outline='#FFFFFF')
                draw.rectangle([6, 6, 10, 10], fill='#00CC00')
            elif self.boton_x1_desactivado and self.boton_x2_desactivado:
                draw.rectangle([4, 4, 12, 12], fill='#7F8C8D', outline='#FFFFFF')
                draw.rectangle([6, 6, 10, 10], fill='#95A5A6')
            else:
                draw.rectangle([4, 4, 12, 12], fill='#FF0000', outline='#FFFFFF')
                draw.rectangle([6, 6, 10, 10], fill='#CC0000')
            
            self.imagen_tray = image
            return image
            
        except Exception:
            image = Image.new('RGB', (16, 16), color='#2C3E50')
            draw = ImageDraw.Draw(image)
            draw.rectangle([4, 4, 12, 12], fill='#FF0000', outline='#FFFFFF')
            return image

    def actualizar_icono_tray(self):
        """Actualiza el icono en la bandeja del sistema"""
        if not SYSTEM_TRAY_DISPONIBLE or not self.icono_tray:
            return
            
        try:
            nueva_imagen = self.crear_imagen_tray()
            self.icono_tray.icon = nueva_imagen
            
            if self.boton_x1_desactivado and self.boton_x2_desactivado:
                self.icono_tray.title = "Mouse Griffin M607W - DESACTIVADO"
            elif self.estado_global == "activado":
                self.icono_tray.title = "Mouse Griffin M607W - ACTIVADO"
            else:
                self.icono_tray.title = "Mouse Griffin M607W - Desactivado"
                
        except Exception:
            pass

    def actualizar_estado_global(self):
        """Actualiza el estado global de la aplicación"""
        estado_anterior = self.estado_global
        
        if self.boton_x1_desactivado and self.boton_x2_desactivado:
            self.estado_global = "desactivado"
        else:
            x1_activo = self.botones_activados["x1"] and not self.boton_x1_desactivado
            x2_activo = self.botones_activados["x2"] and not self.boton_x2_desactivado
            
            if x1_activo or x2_activo:
                self.estado_global = "activado"
            else:
                self.estado_global = "desactivado"
        
        if estado_anterior != self.estado_global and SYSTEM_TRAY_DISPONIBLE:
            self.actualizar_icono_tray()
            
        return self.estado_global

    def iniciar_monitoreo_estado_tray(self):
        """Inicia el monitoreo del estado para el system tray"""
        def monitoreo_estado():
            while self.ejecutandose:
                try:
                    self.actualizar_estado_global()
                    time.sleep(1)
                except Exception:
                    time.sleep(5)
        
        thread = threading.Thread(target=monitoreo_estado, daemon=True)
        thread.start()

    def iniciar_icono_tray(self):
        """Inicia el icono del system tray"""
        try:
            if self.icono_tray:
                self.icono_tray.run()
        except Exception:
            pass

    def minimizar_a_tray(self):
        """Minimiza la aplicación a la bandeja del sistema"""
        if not SYSTEM_TRAY_DISPONIBLE:
            self.cerrar_aplicacion()
            return
            
        try:
            self.root.withdraw()
            self.minimizado_tray = True
            self.status_var.set("Minimizado al tray")
        except Exception:
            self.cerrar_aplicacion()

    def mostrar_aplicacion(self, icon=None, item=None):
        """Muestra la aplicación desde la bandeja del sistema"""
        self.root.after(0, self.mostrar_ventana)

    def mostrar_ventana(self):
        """Muestra la ventana principal"""
        if not SYSTEM_TRAY_DISPONIBLE:
            return
            
        try:
            self.root.deiconify()
            self.root.lift()
            self.root.focus_force()
            self.root.attributes('-topmost', True)
            self.root.attributes('-topmost', False)
            
            self.minimizado_tray = False
            self.status_var.set("Aplicación restaurada")
        except Exception:
            pass

    # =====================================================
    #   GESTIÓN DE CONFIGURACIÓN
    # =====================================================

    def actualizar_modo_repeticion(self, boton):
        """Actualiza la interfaz cuando cambia el modo de repetición"""
        self.actualizar_controles_dinamicos_compactos(boton)
        self.actualizar_configuracion(boton)

    def actualizar_tipo_accion(self, boton):
        """Actualiza las opciones cuando cambia el tipo de acción"""
        tipo_seleccionado = self.tipo_var.get()
        self.actualizar_opciones_teclas(tipo_seleccionado)
        self.actualizar_configuracion(boton)

    def actualizar_opciones_teclas(self, tipo):
        """Actualiza las opciones disponibles de teclas"""
        if tipo == "teclado":
            teclas_comunes = ["a", "b", "c", "d", "e", "f", "g", "h", "i", "j", "k", "l", "m", 
                             "n", "o", "p", "q", "r", "s", "t", "u", "v", "w", "x", "y", "z",
                             "space", "enter", "tab", "shift", "ctrl", "alt", "esc", "f1", "f2",
                             "f3", "f4", "f5", "f6", "f7", "f8", "f9", "f10", "f11", "f12"]
            self.tecla_combo['values'] = teclas_comunes
        else:
            botones_mouse = ["left", "right", "middle"]
            self.tecla_combo['values'] = botones_mouse

    def actualizar_configuracion(self, boton):
        """Actualiza la configuración con los valores actuales"""
        if boton in ["x1", "x2"]:
            nueva_config = {
                "tipo": self.tipo_var.get(),
                "tecla": self.tecla_var.get(),
                "modo": self.modo_var.get()
            }
        else:
            nueva_config = {"modo": self.modo_var.get()}
        
        if self.modo_var.get() == "intervalo":
            nueva_config["intervalo"] = int(self.intervalo_var.get())
            nueva_config["cps"] = self.calcular_cps_desde_intervalo(self.intervalo_var.get())
        else:
            nueva_config["cps"] = int(self.cps_var.get())
            nueva_config["intervalo"] = self.calcular_intervalo_desde_cps(self.cps_var.get())
        
        self.configuraciones[boton].update(nueva_config)
        
        if hasattr(self, 'controles_dinamicos_frame'):
            self.actualizar_controles_dinamicos_compactos(boton)
        
        if boton in ["x1", "x2"]:
            self.actualizar_estilo_boton_manual(boton, modo_manual=self.modo_manual_activo.get(boton, False))

    def actualizar_congelar_cursor(self, boton):
        """Actualiza la configuración de congelar cursor"""
        self.configuraciones[boton]["congelar_cursor"] = self.congelar_var.get()
        
        if not self.congelar_var.get() and self.cursor_congelado:
            self.detener_congelamiento()
        
        self.actualizar_estilo_boton_manual(boton, modo_manual=self.modo_manual_activo.get(boton, False))
        
        if self.congelar_var.get():
            self.status_var.set(f"❄️ Congelar cursor activado para {boton.upper()}")
        else:
            self.status_var.set(f"✅ Congelar cursor desactivado para {boton.upper()}")

    def calcular_intervalo_desde_cps(self, cps):
        """Duración del ciclo completo (pulsar + esperar) para lograr los CPS pedidos.

        El ciclo YA incluye el tiempo de la pulsación, por eso es exactamente
        1/cps (antes se le restaba 1ms de más y salían más CPS de los pedidos).
        """
        if cps <= 0:
            return 60.0
        return max(1.0 / cps, 0.001)

    def calcular_cps_desde_intervalo(self, intervalo):
        """Calcula los CPS a partir de la duración del ciclo completo"""
        if intervalo <= 0:
            return float(MAX_CPS)
        return int(min(1.0 / intervalo, MAX_CPS))

    def _pulsar(self, tipo, tecla):
        """Una pulsación completa (abajo, 1ms, arriba) de teclado o mouse"""
        if tipo == "teclado":
            pydirectinput.keyDown(tecla)
        else:
            pydirectinput.mouseDown(button=tecla)
        inicio = time.perf_counter()
        while (time.perf_counter() - inicio) < self.TIEMPO_PULSACION:
            pass
        if tipo == "teclado":
            pydirectinput.keyUp(tecla)
        else:
            pydirectinput.mouseUp(button=tecla)

    def _bucle_preciso(self, periodo, accion, continuar):
        """Ejecuta accion() una vez cada `periodo` segundos mientras continuar() sea True.

        Usa un horario ABSOLUTO (cada ciclo arranca en inicio + n*periodo), así
        la duración de la pulsación y de pydirectinput no acumulan deriva y el
        ritmo real coincide con los CPS configurados.
        """
        proximo = time.perf_counter()
        while continuar():
            accion()
            proximo += periodo
            ahora = time.perf_counter()
            if proximo < ahora:
                proximo = ahora  # si el sistema se atrasó, no dispara ráfagas para recuperar
            while True:
                restante = proximo - time.perf_counter()
                if restante <= 0:
                    break
                if not continuar():
                    return
                if restante > 0.01:
                    # sleep largo pero cortado a 50ms para poder detenerse rápido
                    time.sleep(min(restante - 0.005, 0.05))
                else:
                    time.sleep(0.00001)

    # =====================================================
    #   MODO MANUAL - CON BUCLE DE PRECISIÓN
    # =====================================================

    def toggle_modo_manual(self, boton):
        """Activa/desactiva el modo Manual con periodo de gracia"""
        if (boton == "x1" and self.boton_x1_desactivado) or (boton == "x2" and self.boton_x2_desactivado):
            self.status_var.set(f"❌ Botón {boton.upper()} desactivado - Actívalo primero")
            return
        
        config = self.configuraciones[boton]
        
        if self.congelar_var.get():
            self.status_var.set(f"❌ Modo Manual no disponible con 'Congelar cursor' activado")
            return
        
        tiempo_actual = time_module.time()
        tiempo_activado = self.tiempo_activacion_manual[boton]
        
        if (self.modo_manual_activo[boton] and 
            tiempo_actual - tiempo_activado < self.periodo_gracia):
            tiempo_restante = self.periodo_gracia - (tiempo_actual - tiempo_activado)
            self.status_var.set(f"⏳ Espere {tiempo_restante:.1f}s para desactivar")
            return
        
        nuevo_estado = not self.modo_manual_activo[boton]
        self.modo_manual_activo[boton] = nuevo_estado
        
        if nuevo_estado:
            self.tiempo_activacion_manual[boton] = tiempo_actual
        
        if self.hilos_manual[boton] and self.hilos_manual[boton].is_alive():
            self.detener_manual[boton] = True
            time.sleep(0.05)
        
        self.actualizar_estilo_boton_manual(boton, modo_manual=nuevo_estado)
        
        if nuevo_estado:
            self.status_var.set(f"✅ Modo Manual ACTIVADO para {boton.upper()}")
            self.detener_manual[boton] = False
            
            self.hilos_manual[boton] = threading.Thread(
                target=self.ejecutar_modo_manual_preciso, 
                args=(boton, config),
                daemon=True
            )
            self.hilos_manual[boton].start()
        else:
            self.status_var.set(f"⏹️ Modo Manual DESACTIVADO para {boton.upper()}")
            self.detener_manual[boton] = True

    def ejecutar_modo_manual_preciso(self, boton, config):
        """Ejecuta el modo manual con un bucle de precisión (CPS reales)"""
        if config["modo"] == "intervalo":
            periodo = config["intervalo"]
        else:
            periodo = self.calcular_intervalo_desde_cps(config["cps"])

        tipo_accion = config["tipo"]
        tecla = config['tecla']

        try:
            self._bucle_preciso(
                periodo,
                lambda: self._pulsar(tipo_accion, tecla),
                lambda: self.modo_manual_activo[boton] and not self.detener_manual[boton] and self.ejecutandose,
            )
        except Exception as e:
            msg_error = str(e)[:30]
            self.root.after(0, lambda m=msg_error: self.status_var.set(f"❌ Error: {m}"))

        # Cuando termina el bucle
        self.root.after(0, lambda: self.actualizar_estilo_boton_manual(boton, modo_manual=False))

    def detener_modo_manual(self, boton):
        """Detiene el modo manual para un botón específico"""
        if boton in self.modo_manual_activo:
            self.modo_manual_activo[boton] = False
            self.detener_manual[boton] = True
        
        if self.boton_actual == boton:
            self.actualizar_estilo_boton_manual(boton, modo_manual=False)

    # =====================================================
    #   SISTEMA DE EJECUCIÓN Y AUTOMATIZACIÓN DE PRECISIÓN
    # =====================================================

    def programar_accion_automatica(self, boton):
        """Programa acciones automáticas con bucle de precisión"""
        if (boton == "x1" and self.boton_x1_desactivado) or (boton == "x2" and self.boton_x2_desactivado):
            return

        # Evita lanzar un hilo duplicado si ya hay uno corriendo para este botón
        # (puede pasar si el botón se activa/desactiva muy rápido, por ejemplo
        # por rebote del switch): el hilo existente ya va a ver el nuevo estado.
        if self.hilos_auto.get(boton) and self.hilos_auto[boton].is_alive():
            return

        def accion_thread_precisa():
            config = self.configuraciones[boton]
            
            if config.get("congelar_cursor", False) and not self.cursor_congelado:
                self.congelar_cursor(boton)
            
            # Calcular intervalo
            if config["modo"] == "intervalo":
                tiempo_espera = config["intervalo"]
            else:
                tiempo_espera = self.calcular_intervalo_desde_cps(config["cps"])
            
            tipo_accion = config["tipo"]
            tecla = config['tecla']

            try:
                self._bucle_preciso(
                    tiempo_espera,
                    lambda: self._pulsar(tipo_accion, tecla),
                    lambda: (self.botones_activados[boton] and self.ejecutandose and
                             not (boton == "x1" and self.boton_x1_desactivado) and
                             not (boton == "x2" and self.boton_x2_desactivado)),
                )
            except Exception:
                pass

            if config.get("congelar_cursor", False) and self.cursor_congelado:
                self.detener_congelamiento()
        
        thread = threading.Thread(target=accion_thread_precisa, daemon=True)
        self.hilos_auto[boton] = thread
        thread.start()

    def programar_auto_click(self, boton):
        """Programa clicks automáticos para botones normales"""
        # Evita lanzar un hilo duplicado si ya hay uno corriendo para este botón
        if self.hilos_auto.get(boton) and self.hilos_auto[boton].is_alive():
            return

        def auto_click_thread():
            config = self.configuraciones[boton]
            if config["activo"] and self.ejecutandose:
                if config["modo"] == "intervalo":
                    periodo = config["intervalo"]
                else:
                    periodo = self.calcular_intervalo_desde_cps(config["cps"])

                self._bucle_preciso(
                    periodo,
                    lambda: self._pulsar("mouse", boton),
                    lambda: self.configuraciones[boton]["activo"] and self.ejecutandose,
                )

        thread = threading.Thread(target=auto_click_thread, daemon=True)
        self.hilos_auto[boton] = thread
        thread.start()

    # =====================================================
    #   SISTEMA DE CONGELAMIENTO DEL CURSOR
    # =====================================================

    def congelar_cursor(self, boton):
        """Congela el cursor en su posición actual"""
        if not self.ejecutandose:
            return
            
        try:
            if DETECCION_MEJORADA_DISPONIBLE:
                import win32api
                self.posicion_congelada = win32api.GetCursorPos()
            else:
                # Fallback: usar pynput para obtener la posición
                from pynput.mouse import Controller
                mouse = Controller()
                self.posicion_congelada = mouse.position
            
            self.cursor_congelado = True
            
            self.detener_congelar = False
            self.congelar_thread = threading.Thread(target=self.mantener_cursor_congelado, daemon=True)
            self.congelar_thread.start()
            
            self.root.after(0, lambda: self.status_var.set("❄️ Cursor congelado"))
            
        except Exception as e:
            msg_error = str(e)
            self.root.after(0, lambda m=msg_error: self.status_var.set(f"❌ Error al congelar: {m}"))

    def mantener_cursor_congelado(self):
        """Mantiene el cursor en la posición congelada"""
        try:
            if DETECCION_MEJORADA_DISPONIBLE:
                import win32api
                
                while self.cursor_congelado and not self.detener_congelar and self.ejecutandose:
                    boton_activo_con_congelar = False
                    for boton in ["x1", "x2"]:
                        if (self.botones_activados[boton] and 
                            not (boton == "x1" and self.boton_x1_desactivado) and 
                            not (boton == "x2" and self.boton_x2_desactivado) and
                            self.configuraciones[boton].get("congelar_cursor", False)):
                            boton_activo_con_congelar = True
                            break
                    
                    if not boton_activo_con_congelar:
                        self.detener_congelamiento()
                        break
                    
                    if self.posicion_congelada:
                        win32api.SetCursorPos(self.posicion_congelada)
                    
                    time.sleep(0.005)
            else:
                # Fallback: usar pydirectinput para mover el cursor
                from pynput.mouse import Controller
                mouse = Controller()
                
                while self.cursor_congelado and not self.detener_congelar and self.ejecutandose:
                    boton_activo_con_congelar = False
                    for boton in ["x1", "x2"]:
                        if (self.botones_activados[boton] and 
                            not (boton == "x1" and self.boton_x1_desactivado) and 
                            not (boton == "x2" and self.boton_x2_desactivado) and
                            self.configuraciones[boton].get("congelar_cursor", False)):
                            boton_activo_con_congelar = True
                            break
                    
                    if not boton_activo_con_congelar:
                        self.detener_congelamiento()
                        break
                    
                    if self.posicion_congelada:
                        mouse.position = self.posicion_congelada
                    
                    time.sleep(0.005)
                    
        except Exception:
            self.detener_congelamiento()

    def detener_congelamiento(self):
        """Detiene el congelamiento del cursor"""
        self.cursor_congelado = False
        self.detener_congelar = True
        self.posicion_congelada = None
        
        if self.ejecutandose:
            self.root.after(0, lambda: self.status_var.set("✅ Cursor liberado"))

    # =====================================================
    #   DETECCIÓN USB Y MONITOREO
    # =====================================================

    def detectar_mouse_usb(self):
        """Detección básica de dispositivos USB"""
        return self.detectar_mouse_usb_basico()

    def detectar_mouse_usb_basico(self):
        """Método básico de detección USB"""
        mouses_detectados = []
        try:
            info = {
                'nombre': 'Griffin M607W',
                'punto_montaje': 'USB',
                'tipo': 'HID',
                'descripcion': 'Mouse gaming Griffin M607W',
                'estado': 'Conectado',
                'tipo_deteccion': 'Detección automática',
                'es_griffin': True
            }
            mouses_detectados.append(info)
        except Exception:
            pass
        
        return mouses_detectados

    def iniciar_deteccion_usb(self):
        """Inicia la detección de dispositivos USB en segundo plano"""
        def deteccion_thread():
            ultimo_estado = None
            while self.ejecutandose:
                try:
                    dispositivos = self.detectar_mouse_usb()
                    mouse_griffin = None
                    
                    for dispositivo in dispositivos:
                        if dispositivo.get('es_griffin', False):
                            mouse_griffin = dispositivo
                            break
                    
                    estado_actual = "conectado" if mouse_griffin else "desconectado"
                    
                    if estado_actual != ultimo_estado and self.ejecutandose:
                        if mouse_griffin:
                            self.usb_status_var.set("✅ Conectado")
                        else:
                            self.usb_status_var.set("❌ Desconectado")
                        
                        ultimo_estado = estado_actual
                    
                except Exception:
                    if self.ejecutandose:
                        self.usb_status_var.set("⚠️ Error USB")
                
                time_module.sleep(3)
        
        self.deteccion_thread = threading.Thread(target=deteccion_thread, daemon=True)
        self.deteccion_thread.start()

    def iniciar_monitoreo(self):
        """Inicia el monitoreo de botones del mouse"""
        def monitor_thread():
            def on_click(x, y, button, pressed):
                if not self.ejecutandose:
                    return
                    
                boton_map = {
                    Button.left: "left",
                    Button.right: "right", 
                    Button.middle: "middle",
                    Button.x1: "x1",
                    Button.x2: "x2"
                }
                
                boton_nombre = boton_map.get(button)
                if boton_nombre and self.ejecutandose:
                    if (boton_nombre == "x1" and self.boton_x1_desactivado) or (boton_nombre == "x2" and self.boton_x2_desactivado):
                        return
                    
                    self.botones_presionados[boton_nombre] = pressed
                    self.ultima_accion_time = time_module.time()
                    
                    if self.ejecutandose:
                        self.root.after(0, lambda: self.actualizar_color_boton(boton_nombre, pressed))
                    
                    if boton_nombre in ["x1", "x2"] and pressed:
                        self.botones_activados[boton_nombre] = not self.botones_activados[boton_nombre]
                        
                        if self.ejecutandose:
                            self.root.after(0, self.actualizar_indicadores_estado)
                        
                        estado = "ACTIVADO" if self.botones_activados[boton_nombre] else "DESACTIVADO"
                        
                        config = self.configuraciones[boton_nombre]
                        congelar_info = " + CONGELADO" if config.get("congelar_cursor", False) and self.botones_activados[boton_nombre] else ""
                        
                        self.root.after(0, lambda: self.status_var.set(f"Botón {boton_nombre} {estado}{congelar_info}"))
                        
                        if self.botones_activados[boton_nombre]:
                            self.programar_accion_automatica(boton_nombre)
                        else:
                            if config.get("congelar_cursor", False) and self.cursor_congelado:
                                self.detener_congelamiento()
                    
                    elif pressed and boton_nombre not in ["x1", "x2"] and self.configuraciones[boton_nombre]["activo"] and self.ejecutandose:
                        self.programar_auto_click(boton_nombre)
            
            self.listener = Listener(on_click=on_click)
            self.listener.start()
            self.listener.join()
        
        self.monitor_thread = threading.Thread(target=monitor_thread, daemon=True)
        self.monitor_thread.start()

    def iniciar_animacion_botones(self):
        """Inicia animaciones para mostrar actividad"""
        def animar():
            while self.ejecutandose:
                tiempo_transcurrido = time_module.time() - self.ultima_accion_time
                
                if tiempo_transcurrido > 2.0 and self.ejecutandose:
                    for boton in self.botones_presionados:
                        if not self.botones_presionados[boton] and self.ejecutandose:
                            self.root.after(0, lambda b=boton: self.quitar_resaltado_animacion(b))
                
                time_module.sleep(0.1)
        
        self.animacion_thread = threading.Thread(target=animar, daemon=True)
        self.animacion_thread.start()

    def quitar_resaltado_animacion(self, boton):
        """Quita el resaltado de un botón para animaciones"""
        if not self.ejecutandose:
            return
            
        if not self.botones_presionados[boton] and hasattr(self, 'boton_actual') and boton != self.boton_actual:
            if (boton == "x1" and self.boton_x1_desactivado) or (boton == "x2" and self.boton_x2_desactivado):
                color = "#7F8C8D"
            else:
                colores = {"left": "#34495E", "right": "#34495E", "middle": "#7F8C8D", 
                          "x1": "#E74C3C", "x2": "#E74C3C"}
                color = colores[boton]
                
            self.canvas.itemconfig(boton, fill=color)
            self._reaplicar_hover()

    # =====================================================
    #   GESTIÓN DE CIERRE DE LA APLICACIÓN
    # =====================================================

    def cerrar_aplicacion_desde_tray(self, icon=None, item=None):
        """Cierra la aplicación desde el system tray"""
        self.root.after(0, self.cerrar_aplicacion_completa)

    def cerrar_aplicacion_completa(self):
        """Cierra completamente la aplicación"""
        self.ejecutandose = False
        
        for boton in ["x1", "x2"]:
            if self.modo_manual_activo.get(boton, False):
                self.detener_modo_manual(boton)
        
        if self.cursor_congelado:
            self.detener_congelamiento()
        
        if self.icono_tray:
            try:
                self.icono_tray.stop()
            except:
                pass
        
        if hasattr(self, 'listener') and self.listener:
            try:
                self.listener.stop()
            except:
                pass
        
        self.guardar_configuracion_silenciosa()
        
        time.sleep(0.5)
        
        try:
            self.root.quit()
            self.root.destroy()
        except:
            pass
        
        os._exit(0)

    def guardar_configuracion(self):
        """Guarda la configuración en archivo"""
        try:
            directorio_actual = os.path.dirname(os.path.abspath(__file__))
            archivo_config = os.path.join(directorio_actual, "config.txt")
            
            with open(archivo_config, 'w') as f:
                f.write("# Configuración del Mouse Griffin M607W\n")
                f.write(f"# Duración: 1ms | Máximo {MAX_CPS} CPS\n\n")
                
                for boton, config in self.configuraciones.items():
                    if boton in ["x1", "x2"]:
                        activo = int(self.botones_activados[boton])
                        congelar = int(config.get("congelar_cursor", False))
                        desactivado = int(self.boton_x1_desactivado if boton == "x1" else self.boton_x2_desactivado)
                        manual = int(self.modo_manual_activo.get(boton, False))
                        linea = f"{boton}={config['tipo']},{config['tecla']},{config['modo']},{config['intervalo']},{config['cps']},{activo},{congelar},{desactivado},{manual}\n"
                    else:
                        linea = f"{boton}=mouse,{config['tecla']},{config['modo']},{config['intervalo']},{config['cps']},0,0,0,0\n"
                    f.write(linea)
            
            self.status_var.set("✅ Configuración guardada")
            
        except Exception as e:
            self.status_var.set(f"❌ Error al guardar: {e}")

    def guardar_configuracion_silenciosa(self):
        """Guarda la configuración silenciosamente (para cierre)"""
        try:
            directorio_actual = os.path.dirname(os.path.abspath(__file__))
            archivo_config = os.path.join(directorio_actual, "config.txt")
            
            with open(archivo_config, 'w') as f:
                f.write("# Configuración del Mouse Griffin M607W\n")
                f.write(f"# Duración: 1ms | Máximo {MAX_CPS} CPS\n\n")
                
                for boton, config in self.configuraciones.items():
                    if boton in ["x1", "x2"]:
                        activo = int(self.botones_activados[boton])
                        congelar = int(config.get("congelar_cursor", False))
                        desactivado = int(self.boton_x1_desactivado if boton == "x1" else self.boton_x2_desactivado)
                        manual = int(self.modo_manual_activo.get(boton, False))
                        linea = f"{boton}={config['tipo']},{config['tecla']},{config['modo']},{config['intervalo']},{config['cps']},{activo},{congelar},{desactivado},{manual}\n"
                    else:
                        linea = f"{boton}=mouse,{config['tecla']},{config['modo']},{config['intervalo']},{config['cps']},0,0,0,0\n"
                    f.write(linea)
            
        except Exception:
            pass

    def cargar_configuracion(self):
        """Carga la configuración desde archivo"""
        try:
            directorio_actual = os.path.dirname(os.path.abspath(__file__))
            archivo_config = os.path.join(directorio_actual, "config.txt")
            
            if not os.path.exists(archivo_config):
                self.status_var.set("ℹ️ No se encontró config.txt")
                return
            
            with open(archivo_config, 'r') as f:
                lineas = f.readlines()
            
            for linea in lineas:
                linea = linea.strip()
                if not linea or linea.startswith('#'):
                    continue
                
                if '=' in linea:
                    partes = linea.split('=')
                    if len(partes) == 2:
                        boton = partes[0].strip()
                        valores = partes[1].split(',')
                        
                        if len(valores) >= 5 and boton in self.configuraciones:
                            try:
                                if boton in ["x1", "x2"]:
                                    tipo = valores[0]
                                    tecla = valores[1]
                                    modo = valores[2]
                                    
                                    try:
                                        intervalo = int(float(valores[3]))
                                    except (ValueError, IndexError):
                                        intervalo = 5
                                    
                                    try:
                                        cps = int(float(valores[4]))
                                    except (ValueError, IndexError):
                                        cps = 5
                                    
                                    activo = bool(int(valores[5])) if len(valores) > 5 else False
                                    congelar = bool(int(valores[6])) if len(valores) > 6 else False
                                    desactivado = bool(int(valores[7])) if len(valores) > 7 else False
                                    manual = bool(int(valores[8])) if len(valores) > 8 else False
                                    
                                    cps = min(cps, MAX_CPS)
                                    
                                    self.configuraciones[boton].update({
                                        "tipo": tipo, "tecla": tecla, "modo": modo,
                                        "intervalo": intervalo, "cps": cps,
                                        "congelar_cursor": congelar
                                    })
                                    self.botones_activados[boton] = activo
                                    self.modo_manual_activo[boton] = manual
                                    
                                    if boton == "x1":
                                        self.boton_x1_desactivado = desactivado
                                    else:
                                        self.boton_x2_desactivado = desactivado
                                        
                                else:
                                    modo = valores[2]
                                    
                                    try:
                                        intervalo = int(float(valores[3]))
                                    except (ValueError, IndexError):
                                        intervalo = 5
                                    
                                    try:
                                        cps = int(float(valores[4]))
                                    except (ValueError, IndexError):
                                        cps = 5
                                    
                                    cps = min(cps, MAX_CPS)
                                    
                                    self.configuraciones[boton].update({
                                        "modo": modo, "intervalo": intervalo, "cps": cps
                                    })
                                    
                            except Exception:
                                continue
            
            if hasattr(self, 'boton_actual') and self.boton_actual in self.configuraciones:
                self.root.after(0, lambda: self.setup_controles_compactos(self.boton_actual))
            
            self.root.after(0, self.actualizar_estilo_botones_desactivacion)
            self.root.after(0, self.actualizar_indicadores_estado)
            
            for boton in ["x1", "x2"]:
                if self.modo_manual_activo.get(boton, False):
                    self.root.after(100, lambda b=boton: self.iniciar_modo_manual_desde_carga(b))
                elif (self.botones_activados.get(boton, False) and
                      not (boton == "x1" and self.boton_x1_desactivado) and
                      not (boton == "x2" and self.boton_x2_desactivado)):
                    # El indicador quedaba en ON al cargar, pero el auto-click real
                    # nunca se volvía a iniciar hasta el próximo clic físico. Lo
                    # restauramos acá para que el estado guardado sea real.
                    self.root.after(100, lambda b=boton: self.programar_accion_automatica(b))

            self.status_var.set("✅ Configuración cargada")
            
        except Exception as e:
            self.status_var.set(f"❌ Error al cargar: {e}")

    def iniciar_modo_manual_desde_carga(self, boton):
        """Inicia el modo manual desde la configuración cargada"""
        if self.modo_manual_activo.get(boton, False):
            config = self.configuraciones[boton]
            if self.boton_actual == boton:
                self.actualizar_estilo_boton_manual(boton, modo_manual=True)
            
            self.detener_manual[boton] = False
            self.hilos_manual[boton] = threading.Thread(
                target=self.ejecutar_modo_manual_preciso, 
                args=(boton, config),
                daemon=True
            )
            self.hilos_manual[boton].start()
            
            self.status_var.set(f"🔄 Modo Manual restaurado para {boton.upper()}")

    def cerrar_aplicacion(self):
        """Cierra la aplicación normalmente"""
        self.ejecutandose = False
        
        for boton in ["x1", "x2"]:
            if self.modo_manual_activo.get(boton, False):
                self.detener_modo_manual(boton)
        
        if self.cursor_congelado:
            self.detener_congelamiento()
        
        if self.icono_tray:
            try:
                self.icono_tray.stop()
            except:
                pass
        
        if hasattr(self, 'listener') and self.listener:
            try:
                self.listener.stop()
            except:
                pass
        
        self.guardar_configuracion_silenciosa()
        
        try:
            self.root.quit()
            self.root.destroy()
        except:
            pass
        
        os._exit(0)

# =====================================================
#   FUNCIÓN PRINCIPAL
# =====================================================

def iniciar_app_principal():
    """Se llama al cerrar la ventana de verificación (botón 'Iniciar aplicación')"""
    modulos_criticos_ok = cargar_modulos_post_verificacion()

    if not modulos_criticos_ok:
        root_error = tk.Tk()
        root_error.withdraw()
        messagebox.showerror(
            "Error de dependencias",
            "No se pudieron instalar módulos necesarios (pydirectinput, pynput o psutil).\n"
            "Revisá tu conexión a internet y volvé a intentarlo."
        )
        root_error.destroy()
        sys.exit(1)

    try:
        root = tk.Tk()
        app = MouseConfigApp(root)
        root.mainloop()
    except Exception as e:
        print(f"Error en la aplicación: {e}")
        input("Presiona Enter para salir...")


def main():
    """Función principal: primero verifica/instala dependencias, después abre la app"""
    root_verificacion = tk.Tk()
    VentanaVerificacion(root_verificacion, DEPENDENCIAS_APP, iniciar_app_principal)
    root_verificacion.mainloop()


if __name__ == "__main__":
    main()
