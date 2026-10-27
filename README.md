# Mouse Griffin M607W

Programa de escritorio (Python/Tkinter) para configurar los botones del mouse Griffin M607W
(izquierdo, derecho, rueda y los dos laterales X1/X2) con clics automáticos por intervalo o por CPS
(máximo 25 CPS), modo manual, congelado de cursor y bandeja del sistema.

## Uso
1. Instalar Python 3.13 (32/64 bits).
2. Ejecutar `mouse.py`. Al iniciar verifica e instala solas las dependencias
   (pydirectinput, pynput, psutil, pystray, Pillow, pywin32) y abre la aplicación.
3. La X cierra el programa; el botón 📌 lo manda a la bandeja del sistema.

`Desinst_Depen_Mouse.py` desinstala las dependencias. La configuración se guarda en `config.txt`.
