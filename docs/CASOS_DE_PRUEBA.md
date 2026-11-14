# Casos de prueba — Lince, detector de objetos

El sistema se probó en tres niveles:

| Nivel | Qué prueba | Cómo se ejecuta | Resultado |
|---|---|---|---|
| 1. Automatizadas | Cada módulo por separado, con cámara y detector simulados (y el modelo real sobre una imagen de referencia) | `python manage.py test` | **68 / 68 pasan** |
| 2. Funcionales | El sistema completo en funcionamiento: servidor, cámara real, YOLO11n y PostgreSQL | `python scripts/prueba_funcional.py` | **15 / 15 pasan** ([detalle](resultado_pruebas.md)) |
| 3. Interfaz | Diseño, temas claro/oscuro y pantallas de celular | Revisión visual en el navegador | Ver tabla 3 |

Entorno de ejecución: Windows 11, Python 3.11, Django 5.2, OpenCV 4.14, PostgreSQL 17,
cámara web integrada (640×480), CPU sin GPU.

---

## 1. Pruebas automatizadas (`python manage.py test`)

Están en `detector/tests/`, un archivo por módulo. No necesitan cámara: usan una cámara
simulada (`CapturaFalsa`) y un detector simulado (`DetectorFalso`, que siempre "ve" una
persona y dos tazas). Las de `ModeloRealTests` sí ejecutan YOLO11n con OpenCV.

| Archivo | Pruebas | Qué cubre |
|---|---|---|
| `test_camara.py` | 14 | Captura, flujo MJPEG, apagado automático, hilo de detección, pausa/reanudación, error de cámara o de modelo |
| `test_yolo.py` | 16 | Decodificación de la salida de YOLO, letterbox, NMS por clase, dibujo de cajas, 80 clases y categorías, **modelo real sobre `bus.jpg`** |
| `test_registro.py` | 11 | Guardado en PostgreSQL con recorte JPEG, intervalo por clase, "nuevo hallazgo", errores de base de datos |
| `test_vistas.py` | 27 | Páginas, API, álbum, bitácora (filtros, paginación, CSV, vaciar), análisis de imágenes y validación de archivos |

Casos representativos:

| ID | Caso | Resultado esperado | Estado |
|---|---|---|---|
| CA-01 | Iniciar la cámara dos veces | No abre una segunda cámara; reutiliza el mismo hilo | ✔ Pasa |
| CA-02 | La cámara no abre (ocupada o índice inválido) | `iniciar()` devuelve `False` y el estado muestra un mensaje de error claro | ✔ Pasa |
| CA-03 | Nadie mira el video | La cámara se libera sola tras `CAMERA_APAGADO_INACTIVO` segundos | ✔ Pasa |
| CA-04 | Falta el archivo del modelo | El video sigue funcionando sin detección y se informa el error | ✔ Pasa |
| CA-05 | Se apaga la detección mientras YOLO procesa un frame | Ese frame no vuelve a publicar objetos "fantasma" | ✔ Pasa |
| CA-06 | Salida simulada de YOLO con una caja en (320, 320) | Se convierte a coordenadas del frame original descontando el relleno del letterbox | ✔ Pasa |
| CA-07 | Dos cajas casi iguales de la misma clase | NMS deja solo la de mayor confianza | ✔ Pasa |
| CA-08 | Persona y celular en la misma zona | Se conservan ambos (NMS separado por clase) | ✔ Pasa |
| CA-09 | YOLO11n real sobre `bus.jpg` | Detecta ≥ 3 personas y el bus, con cajas dentro de la imagen | ✔ Pasa |
| CA-10 | Imagen totalmente negra | Ningún objeto detectado | ✔ Pasa |
| CA-11 | Dos detecciones seguidas del mismo objeto | Solo se guarda un avistamiento por clase cada 15 s | ✔ Pasa |
| CA-12 | Dos tazas en el mismo frame | Un avistamiento con `cantidad = 2` y la caja más confiable | ✔ Pasa |
| CA-13 | Falla la base de datos al guardar | La detección sigue funcionando y se informa el error | ✔ Pasa |
| CA-14 | Álbum con varias fotos de "persona" | La lámina muestra la de mayor confianza | ✔ Pasa |
| CA-15 | Filtros de la bitácora con valores inválidos (`objeto=abc`) | Se ignoran sin error | ✔ Pasa |
| CA-16 | Subir un `.txt` en "Analizar imagen" | HTTP 400 con "no es una imagen válida" | ✔ Pasa |
| CA-17 | Subir una imagen mayor al límite | HTTP 400 con "pesa más de …" | ✔ Pasa |
| CA-18 | Analizar una imagen | No se guarda nada en la bitácora | ✔ Pasa |
| CA-19 | API de configuración con tipos incorrectos (`"activa": "si"`) | HTTP 400 | ✔ Pasa |
| CA-20 | Vaciar la bitácora con GET | HTTP 405 (solo se permite POST) | ✔ Pasa |

---

## 2. Pruebas funcionales del sistema en funcionamiento

Ejecutadas con `scripts/prueba_funcional.py` contra el servidor real, con la cámara
encendida y una persona frente a ella. El informe generado automáticamente está en
[resultado_pruebas.md](resultado_pruebas.md).

| ID | Caso | Pasos | Resultado esperado | Resultado obtenido | Estado |
|---|---|---|---|---|---|
| CF-01 | Página principal | Abrir `/` | HTTP 200 con el Observatorio | HTTP 200 | ✔ |
| CF-02 | Demás páginas | Abrir Álbum, Bitácora, Analizar, Admin | HTTP 200 en todas | HTTP 200 en todas | ✔ |
| CF-03 | API de estado | `GET /api/estado/` | JSON con cámara, detección y registro | Modelo `yolo11n` informado | ✔ |
| CF-04 | Encender cámara | Botón *Encender cámara* | La cámara abre | Cámara 0 a 640×480 | ✔ |
| CF-05 | Video en vivo | Ver el flujo `/video/` 3 s | ≥ 10 frames JPEG | 55 frames (~18 fps) | ✔ |
| CF-06 | Detección en vivo | Ponerse frente a la cámara | Se detecta y se mide la inferencia | persona 92 % · 134 ms · 7,9 detecciones/s | ✔ |
| CF-07 | Cambiar confianza | Mover la regla a 80 % y volver a 45 % | Se aplica sin reiniciar el video | Aplicado | ✔ |
| CF-08 | Pausar detección | Apagar *Detectar objetos* | El video sigue, sin cajas ni objetos | 0 objetos con video activo | ✔ |
| CF-09 | Capturar foto | Botón *Capturar foto* | Descarga un JPEG | JPEG de 30 KB | ✔ |
| CF-10 | Guardado en bitácora | Esperar con un objeto a la vista | Avistamiento en PostgreSQL con recorte | #2 persona 92 % con recorte JPEG | ✔ |
| CF-11 | Analizar imagen | Subir `bus.jpg` | ≥ 3 personas y 1 bus | 3 personas y 1 bus | ✔ |
| CF-12 | Archivo inválido | Subir un `.txt` | Rechazo con mensaje | HTTP 400 + mensaje | ✔ |
| CF-13 | Exportar CSV | *Exportar CSV* en la bitácora | Archivo CSV | CSV con los avistamientos | ✔ |
| CF-14 | Seguridad de acciones | GET a una acción y POST sin token | Rechazados | GET → 405, POST sin CSRF → 403 | ✔ |
| CF-15 | Apagar cámara | Botón *Apagar cámara* | La cámara se libera | Liberada | ✔ |

---

## 3. Pruebas de interfaz

| ID | Caso | Resultado esperado | Estado |
|---|---|---|---|
| CI-01 | Tema claro ("papel") | Contraste legible, acento bermellón | ✔ Verificado con captura |
| CI-02 | Tema oscuro ("cuarto oscuro"), según la preferencia del sistema | Mismos elementos legibles sobre fondo oscuro | ✔ Verificado con captura |
| CI-03 | Celular (390 px de ancho) | Una columna, sin desplazamiento horizontal, menú desplazable | ✔ Verificado con captura |
| CI-04 | Primera vez que aparece un objeto | Sello animado "¡Nuevo hallazgo!" y la lámina del álbum se completa | Verificar en la demostración |
| CI-05 | Atajos de teclado | `Espacio` cámara, `D` detección, `G` guardar, `F` foto | Verificar en la demostración |
| CI-06 | Dos pestañas abiertas | Ambas ven el video; "espectadores" = 2; una sola cámara abierta | Verificar en la demostración |
| CI-07 | Arrastrar una foto a "Analizar imagen" | Vista previa y análisis | Verificar en la demostración |

---

## Defectos encontrados durante las pruebas

| # | Defecto | Cómo se detectó | Corrección |
|---|---|---|---|
| 1 | Al desactivar la detección quedaba un objeto "fantasma" en el panel | Prueba manual de la Sesión 2 | El hilo descarta el resultado si la detección se apagó durante la inferencia (prueba CA-05) |
| 2 | YOLOv4-tiny confundía y omitía objetos | Revisión del usuario | Cambio a YOLO11n (ver la comparativa en el README) |
| 3 | La prueba esperaba 4 personas en `bus.jpg`; el modelo encuentra 3 (la cuarta está cortada en el borde) | `manage.py test` | Se ajustó la expectativa al comportamiento real del modelo |
| 4 | Álbum y bitácora devolvían error 500 en el servidor que ya estaba corriendo | Prueba funcional CF-02 | Django registra las librerías de plantillas al iniciar: hay que reiniciar el servidor tras crear `templatetags/`. Con el servidor reiniciado, CF-02 pasa |
| 5 | En celular el contenido se salía de la pantalla | Captura a 390 px | Columnas de la grilla con `minmax(0, 1fr)` |
