import tkinter as tk
from tkinter import ttk, messagebox, scrolledtext
import subprocess
import sys
import os
import threading
import importlib.util

class DependenciesUninstaller:
    def __init__(self, root):
        self.root = root
        self.root.title("Desinstalador de Dependencias - Mouse Griffin M607W")
        self.root.geometry("700x650")
        self.root.resizable(True, True)
        
        # Centrar ventana
        self.centrar_ventana()
        
        # Lista de dependencias que pueden ser desinstaladas
        self.dependencies = [
            {"nombre": "pydirectinput", "modulo": "pydirectinput",
             "descripcion": "Control de mouse/teclado", "tamano": "50KB"},
            
            {"nombre": "pynput", "modulo": "pynput",
             "descripcion": "Eventos teclado/mouse", "tamano": "100KB"},
            
            {"nombre": "psutil", "modulo": "psutil",
             "descripcion": "Información del sistema", "tamano": "500KB"},
            
            {"nombre": "pywin32", "modulo": "win32api",
             "descripcion": "APIs de Windows", "solo_windows": True, "tamano": "10MB"},
            
            {"nombre": "pystray", "modulo": "pystray",
             "descripcion": "Icono en bandeja", "tamano": "200KB"},
            
            {"nombre": "Pillow", "modulo": "PIL",
             "descripcion": "Procesamiento imágenes", "tamano": "2MB"},
            
            {"nombre": "keyboard", "modulo": "keyboard",
             "descripcion": "Alternativa a pynput", "tamano": "150KB"},
            
            {"nombre": "mouse", "modulo": "mouse",
             "descripcion": "Alternativa a pydirectinput", "tamano": "80KB"},
            
            {"nombre": "numpy", "modulo": "numpy",
             "descripcion": "Cálculos numéricos", "tamano": "15MB"},
            
            {"nombre": "pandas", "modulo": "pandas",
             "descripcion": "Análisis de datos", "tamano": "30MB"},
            
            {"nombre": "matplotlib", "modulo": "matplotlib",
             "descripcion": "Gráficos", "tamano": "8MB"},
        ]
        
        # Variables de estado
        self.desinstalando = False
        self.proceso_activo = False
        self.dependencias_instaladas = []
        self.dependencias_seleccionadas = []
        
        # Variables para checkboxes
        self.checkbox_vars = {}
        
        # Configurar la interfaz
        self.setup_ui()
        
        # Verificar dependencias instaladas al iniciar
        self.verificar_dependencias_instaladas()
        
        # Crear menú
        self.crear_menu()

    def centrar_ventana(self):
        """Centra la ventana en la pantalla"""
        self.root.update_idletasks()
        ancho_pantalla = self.root.winfo_screenwidth()
        alto_pantalla = self.root.winfo_screenheight()
        ancho_ventana = 700
        alto_ventana = 650
        x = (ancho_pantalla // 2) - (ancho_ventana // 2)
        y = (alto_pantalla // 2) - (alto_ventana // 2)
        self.root.geometry(f'{ancho_ventana}x{alto_ventana}+{x}+{y}')

    def crear_menu(self):
        """Crea un menú en la ventana principal"""
        menubar = tk.Menu(self.root)
        self.root.config(menu=menubar)
        
        # Menú Archivo
        file_menu = tk.Menu(menubar, tearoff=0)
        menubar.add_cascade(label="Archivo", menu=file_menu)
        file_menu.add_command(label="Refrescar", command=self.verificar_dependencias_instaladas)
        file_menu.add_separator()
        file_menu.add_command(label="Salir", command=self.root.quit)
        
        # Menú Acciones
        action_menu = tk.Menu(menubar, tearoff=0)
        menubar.add_cascade(label="Acciones", menu=action_menu)
        action_menu.add_command(label="Seleccionar Todas", command=self.seleccionar_todas)
        action_menu.add_command(label="Deseleccionar Todas", command=self.deseleccionar_todas)
        action_menu.add_separator()
        action_menu.add_command(label="Desinstalar Seleccionadas", command=self.desinstalar_seleccionadas)

    def setup_ui(self):
        """Configura la interfaz de usuario del desinstalador"""
        main_frame = ttk.Frame(self.root, padding="10")
        main_frame.pack(fill=tk.BOTH, expand=True)
        
        # Título
        title_frame = ttk.Frame(main_frame)
        title_frame.pack(fill=tk.X, pady=(0, 10))
        
        title_label = ttk.Label(title_frame, 
                               text="🔄 Desinstalador de Dependencias", 
                               font=("Arial", 14, "bold"))
        title_label.pack(side=tk.LEFT)
        
        # Botón para refrescar
        refresh_btn = ttk.Button(title_frame, 
                                text="🔄 Refrescar", 
                                command=self.verificar_dependencias_instaladas,
                                width=12)
        refresh_btn.pack(side=tk.RIGHT, padx=(5, 0))
        
        # Información del sistema
        info_frame = ttk.LabelFrame(main_frame, text="Información del Sistema", padding="8")
        info_frame.pack(fill=tk.X, pady=(0, 10))
        
        info_grid = ttk.Frame(info_frame)
        info_grid.pack(fill=tk.X)
        
        ttk.Label(info_grid, text="Sistema Operativo:", font=("Arial", 9, "bold")).grid(row=0, column=0, sticky=tk.W, padx=(0, 5))
        ttk.Label(info_grid, text=f"{sys.platform}", font=("Arial", 9)).grid(row=0, column=1, sticky=tk.W, padx=(0, 20))
        
        ttk.Label(info_grid, text="Python:", font=("Arial", 9, "bold")).grid(row=0, column=2, sticky=tk.W, padx=(0, 5))
        ttk.Label(info_grid, text=f"{sys.version.split()[0]}", font=("Arial", 9)).grid(row=0, column=3, sticky=tk.W, padx=(0, 20))
        
        ttk.Label(info_grid, text="Dependencias instaladas:", font=("Arial", 9, "bold")).grid(row=0, column=4, sticky=tk.W, padx=(0, 5))
        self.instaladas_count_var = tk.StringVar(value="0")
        ttk.Label(info_grid, textvariable=self.instaladas_count_var, font=("Arial", 9, "bold"), 
                 foreground="green").grid(row=0, column=5, sticky=tk.W)
        
        # Frame para lista de dependencias con checkboxes
        deps_frame = ttk.LabelFrame(main_frame, text="Dependencias Instaladas", padding="10")
        deps_frame.pack(fill=tk.BOTH, expand=True, pady=(0, 10))
        
        # Canvas y Scrollbar para lista de dependencias
        canvas_frame = ttk.Frame(deps_frame)
        canvas_frame.pack(fill=tk.BOTH, expand=True)
        
        canvas = tk.Canvas(canvas_frame)
        scrollbar = ttk.Scrollbar(canvas_frame, orient="vertical", command=canvas.yview)
        self.scrollable_frame = ttk.Frame(canvas)
        
        self.scrollable_frame.bind(
            "<Configure>",
            lambda e: canvas.configure(scrollregion=canvas.bbox("all"))
        )
        
        canvas.create_window((0, 0), window=self.scrollable_frame, anchor="nw")
        canvas.configure(yscrollcommand=scrollbar.set)
        
        canvas.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")
        
        # Frame para checkboxes (se llenará dinámicamente)
        self.checkboxes_frame = ttk.Frame(self.scrollable_frame)
        self.checkboxes_frame.pack(fill=tk.BOTH, expand=True)
        
        # Consola de salida
        console_frame = ttk.LabelFrame(main_frame, text="Consola de Desinstalación", padding="5")
        console_frame.pack(fill=tk.BOTH, expand=True, pady=(0, 10))
        
        self.console_text = scrolledtext.ScrolledText(console_frame, 
                                                     height=8,
                                                     font=("Consolas", 9),
                                                     bg="black",
                                                     fg="white",
                                                     insertbackground="white")
        self.console_text.pack(fill=tk.BOTH, expand=True)
        self.console_text.config(state=tk.DISABLED)
        
        # Barra de progreso y botones
        bottom_frame = ttk.Frame(main_frame)
        bottom_frame.pack(fill=tk.X, pady=(0, 5))
        
        # Barra de progreso
        self.progress_bar = ttk.Progressbar(bottom_frame, mode='determinate', length=200)
        self.progress_bar.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 10))
        
        # Botón para desinstalar seleccionadas
        self.desinstalar_btn = ttk.Button(bottom_frame, 
                                         text="🗑️ Desinstalar Seleccionadas", 
                                         command=self.desinstalar_seleccionadas,
                                         state=tk.DISABLED)
        self.desinstalar_btn.pack(side=tk.RIGHT, padx=(5, 0))
        
        # Botón para limpiar consola
        self.limpiar_btn = ttk.Button(bottom_frame, 
                                     text="🧹 Limpiar Consola", 
                                     command=self.limpiar_consola)
        self.limpiar_btn.pack(side=tk.RIGHT, padx=(5, 0))
        
        # Botón para seleccionar todas
        self.select_all_btn = ttk.Button(bottom_frame, 
                                        text="✅ Seleccionar Todas", 
                                        command=self.seleccionar_todas)
        self.select_all_btn.pack(side=tk.RIGHT, padx=(5, 0))

    def verificar_dependencias_instaladas(self):
        """Verifica qué dependencias están instaladas"""
        self.escribir_consola("🔍 Buscando dependencias instaladas...\n")
        
        # Limpiar checkboxes anteriores
        for widget in self.checkboxes_frame.winfo_children():
            widget.destroy()
        
        self.dependencias_instaladas = []
        self.checkbox_vars = {}
        
        row = 0
        for dep in self.dependencies:
            # Verificar si es solo para Windows
            if dep.get("solo_windows", False) and sys.platform != "win32":
                continue
            
            # Verificar si está instalada
            instalada = self.verificar_dependencia(dep["modulo"])
            
            if instalada:
                self.dependencias_instaladas.append(dep)
                
                # Crear frame para cada dependencia
                dep_frame = ttk.Frame(self.checkboxes_frame)
                dep_frame.pack(fill=tk.X, pady=2)
                
                # Checkbox
                var = tk.BooleanVar(value=False)
                self.checkbox_vars[dep["nombre"]] = var
                
                checkbox = ttk.Checkbutton(dep_frame, 
                                          text=f"{dep['nombre']} - {dep['descripcion']} ({dep['tamano']})",
                                          variable=var)
                checkbox.pack(side=tk.LEFT, anchor=tk.W)
                
                # Etiqueta de estado
                estado_label = ttk.Label(dep_frame, text="✅ INSTALADA", 
                                        foreground="green", font=("Arial", 8, "bold"))
                estado_label.pack(side=tk.RIGHT, padx=(10, 0))
                
                row += 1
        
        # Actualizar contador
        self.instaladas_count_var.set(str(len(self.dependencias_instaladas)))
        
        if self.dependencias_instaladas:
            self.escribir_consola(f"✅ Encontradas {len(self.dependencias_instaladas)} dependencia(s) instalada(s)\n")
            self.desinstalar_btn.config(state=tk.NORMAL)
        else:
            self.escribir_consola("ℹ️ No se encontraron dependencias instaladas\n")
            self.desinstalar_btn.config(state=tk.DISABLED)

    def verificar_dependencia(self, nombre_modulo):
        """Verifica si un módulo está instalado"""
        try:
            if nombre_modulo == "PIL":
                # Caso especial para Pillow
                spec = importlib.util.find_spec("PIL")
                return spec is not None
            else:
                spec = importlib.util.find_spec(nombre_modulo)
                return spec is not None
        except Exception:
            return False

    def seleccionar_todas(self):
        """Selecciona todas las dependencias"""
        for var in self.checkbox_vars.values():
            var.set(True)
        
        if self.checkbox_vars:
            self.escribir_consola("✅ Todas las dependencias seleccionadas\n")
        else:
            self.escribir_consola("ℹ️ No hay dependencias para seleccionar\n")

    def deseleccionar_todas(self):
        """Deselecciona todas las dependencias"""
        for var in self.checkbox_vars.values():
            var.set(False)
        
        if self.checkbox_vars:
            self.escribir_consola("✅ Todas las dependencias deseleccionadas\n")
        else:
            self.escribir_consola("ℹ️ No hay dependencias para deseleccionar\n")

    def obtener_dependencias_seleccionadas(self):
        """Obtiene la lista de dependencias seleccionadas"""
        seleccionadas = []
        for dep in self.dependencias_instaladas:
            if self.checkbox_vars.get(dep["nombre"], tk.BooleanVar(value=False)).get():
                seleccionadas.append(dep)
        return seleccionadas

    def desinstalar_seleccionadas(self):
        """Desinstala las dependencias seleccionadas"""
        seleccionadas = self.obtener_dependencias_seleccionadas()
        
        if not seleccionadas:
            messagebox.showwarning("Advertencia", "No hay dependencias seleccionadas para desinstalar.")
            return
        
        # Confirmar desinstalación
        deps_nombres = ", ".join([d["nombre"] for d in seleccionadas[:3]])
        if len(seleccionadas) > 3:
            deps_nombres += f" y {len(seleccionadas)-3} más"
        
        confirmacion = messagebox.askyesno(
            "Confirmar Desinstalación", 
            f"¿Está seguro de desinstalar {len(seleccionadas)} dependencia(s)?\n\n"
            f"{deps_nombres}\n\n"
            f"⚠️ Esta acción no se puede deshacer."
        )
        
        if not confirmacion:
            return
        
        # Iniciar desinstalación
        self.iniciar_desinstalacion(seleccionadas)

    def iniciar_desinstalacion(self, lista_deps):
        """Inicia el proceso de desinstalación"""
        if self.desinstalando:
            messagebox.showwarning("Advertencia", "Ya hay una desinstalación en curso.")
            return
        
        self.desinstalando = True
        self.proceso_activo = True
        self.progress_bar["value"] = 0
        self.progress_bar["maximum"] = len(lista_deps)
        
        # Deshabilitar botones durante la desinstalación
        self.desinstalar_btn.config(state=tk.DISABLED)
        self.select_all_btn.config(state=tk.DISABLED)
        self.limpiar_btn.config(state=tk.DISABLED)
        
        # Limpiar consola
        self.limpiar_consola()
        
        # Iniciar desinstalación en hilo separado
        thread = threading.Thread(target=self.ejecutar_desinstalacion, args=(lista_deps,))
        thread.daemon = True
        thread.start()

    def ejecutar_desinstalacion(self, lista_deps):
        """Ejecuta la desinstalación de dependencias"""
        try:
            self.escribir_consola("🚀 INICIANDO DESINSTALACIÓN\n")
            self.escribir_consola("=" * 50 + "\n")
            self.escribir_consola(f"Total a desinstalar: {len(lista_deps)}\n")
            self.escribir_consola("=" * 50 + "\n\n")
            
            total = len(lista_deps)
            exitosas = 0
            fallidas = 0
            
            for i, dep in enumerate(lista_deps, 1):
                if not self.proceso_activo:
                    break
                
                # Actualizar progreso
                self.root.after(0, lambda v=i: self.progress_bar.config(value=v))
                self.root.update()
                
                self.escribir_consola(f"🗑️ [{i}/{total}] Desinstalando {dep['nombre']}...\n")
                
                # Ejecutar comando de desinstalación
                resultado = self.ejecutar_comando_desinstalacion(dep)
                
                if resultado:
                    exitosas += 1
                    self.escribir_consola(f"   ✅ {dep['nombre']} desinstalado correctamente\n\n")
                else:
                    fallidas += 1
                    self.escribir_consola(f"   ❌ Error desinstalando {dep['nombre']}\n\n")
            
            # Completar barra de progreso
            self.progress_bar["value"] = total
            
            # Mostrar resumen
            self.escribir_consola("=" * 50 + "\n")
            self.escribir_consola("📊 RESUMEN DE DESINSTALACIÓN:\n")
            self.escribir_consola(f"   ✅ Exitosa(s): {exitosas}\n")
            self.escribir_consola(f"   ❌ Fallida(s): {fallidas}\n")
            self.escribir_consola(f"   📦 Total: {total}\n\n")
            
            if fallidas == 0:
                self.escribir_consola("✨ ¡Desinstalación completada con éxito!\n")
            else:
                self.escribir_consola("⚠️ Algunas dependencias no se pudieron desinstalar\n")
            
            # Actualizar lista de dependencias instaladas
            self.root.after(1000, self.verificar_dependencias_instaladas)
            
        except Exception as e:
            self.escribir_consola(f"❌ ERROR CRÍTICO: {str(e)}\n")
        
        finally:
            # Restaurar estado
            self.desinstalando = False
            self.proceso_activo = False
            
            # Habilitar botones
            self.root.after(100, self.habilitar_botones)

    def ejecutar_comando_desinstalacion(self, dep):
        """Ejecuta el comando de desinstalación de una dependencia"""
        try:
            # Comando para desinstalar
            if sys.platform == "win32":
                comando = [sys.executable, "-m", "pip", "uninstall", dep["nombre"], "-y"]
            else:
                comando = ["pip", "uninstall", dep["nombre"], "-y"]
            
            self.escribir_consola(f"   Comando: {' '.join(comando)}\n")
            
            # Ejecutar comando
            resultado = subprocess.run(
                comando,
                capture_output=True,
                text=True,
                timeout=120  # 2 minutos timeout
            )
            
            # Mostrar output
            if resultado.stdout:
                lines = resultado.stdout.split('\n')
                for line in lines[:5]:  # Mostrar solo primeras 5 líneas
                    if line.strip():
                        self.escribir_consola(f"   {line}\n")
            
            if resultado.stderr and "error" in resultado.stderr.lower():
                self.escribir_consola(f"   Error: {resultado.stderr[:200]}...\n")
            
            return resultado.returncode == 0
            
        except subprocess.TimeoutExpired:
            self.escribir_consola("   ⏰ Timeout: El proceso tardó demasiado\n")
            return False
        except Exception as e:
            self.escribir_consola(f"   ❌ Excepción: {str(e)}\n")
            return False

    def habilitar_botones(self):
        """Habilita todos los botones"""
        self.desinstalar_btn.config(state=tk.NORMAL if self.dependencias_instaladas else tk.DISABLED)
        self.select_all_btn.config(state=tk.NORMAL)
        self.limpiar_btn.config(state=tk.NORMAL)

    def escribir_consola(self, texto):
        """Escribe texto en la consola"""
        self.root.after(0, self._escribir_consola_thread, texto)

    def _escribir_consola_thread(self, texto):
        """Escribe en la consola desde el hilo principal"""
        self.console_text.config(state=tk.NORMAL)
        self.console_text.insert(tk.END, texto)
        self.console_text.see(tk.END)
        self.console_text.config(state=tk.DISABLED)

    def limpiar_consola(self):
        """Limpia la consola de texto"""
        self.console_text.config(state=tk.NORMAL)
        self.console_text.delete(1.0, tk.END)
        self.console_text.config(state=tk.DISABLED)

    def limpiar_cache_pip(self):
        """Limpia el cache de pip"""
        self.escribir_consola("🧹 Limpiando cache de pip...\n")
        
        try:
            comando = [sys.executable, "-m", "pip", "cache", "purge"]
            resultado = subprocess.run(comando, capture_output=True, text=True)
            
            if resultado.returncode == 0:
                self.escribir_consola("✅ Cache limpiado correctamente\n")
            else:
                self.escribir_consola("⚠️ No se pudo limpiar el cache completamente\n")
                
        except Exception as e:
            self.escribir_consola(f"❌ Error: {str(e)}\n")

    def mostrar_info_pip(self):
        """Muestra información de pip"""
        self.escribir_consola("📊 Información de pip:\n")
        
        try:
            comando = [sys.executable, "-m", "pip", "--version"]
            resultado = subprocess.run(comando, capture_output=True, text=True)
            
            if resultado.returncode == 0:
                self.escribir_consola(f"   {resultado.stdout}\n")
            else:
                self.escribir_consola("❌ Error obteniendo información de pip\n")
                
        except Exception as e:
            self.escribir_consola(f"❌ Error: {str(e)}\n")

def main():
    """Función principal del desinstalador"""
    # Configurar para Windows
    if sys.platform == "win32":
        import ctypes
        # Intentar ocultar consola
        try:
            whnd = ctypes.windll.kernel32.GetConsoleWindow()
            if whnd != 0:
                ctypes.windll.user32.ShowWindow(whnd, 0)
        except:
            pass
    
    root = tk.Tk()
    app = DependenciesUninstaller(root)
    
    # Manejar cierre de ventana
    def on_closing():
        if app.desinstalando:
            if messagebox.askyesno("Salir", 
                                  "Hay una desinstalación en curso. ¿Desea salir de todos modos?"):
                app.proceso_activo = False
                root.destroy()
        else:
            root.destroy()
    
    root.protocol("WM_DELETE_WINDOW", on_closing)
    root.mainloop()

if __name__ == "__main__":
    main()
