# Resultado de las pruebas funcionales

Ejecutado el 2026-11-13 23:42 contra `http://127.0.0.1:8000` (con cámara).

| ID | Caso | Resultado | Detalle | Tiempo |
|---|---|---|---|---|
| CF-01 | La página principal carga | **PASA** | HTTP 200 · página del Observatorio | 0.0 s |
| CF-02 | Las demás páginas cargan | **PASA** | Álbum, Bitácora, Analizar y Admin: HTTP 200 | 0.3 s |
| CF-03 | La API de estado responde JSON válido | **PASA** | modelo yolo11n · álbum 1/80 | 0.0 s |
| CF-04 | Encender la cámara | **PASA** | cámara 0 abierta a 640x480 | 1.2 s |
| CF-05 | El video en vivo llega al navegador (MJPEG) | **PASA** | 55 frames JPEG en 3 s (~18 fps) | 3.0 s |
| CF-06 | YOLO11n detecta en vivo sobre el video | **PASA** | 134 ms por inferencia · 7.9 detecciones/s · objetos: persona 92% | 0.0 s |
| CF-07 | Cambiar la confianza mínima en vivo | **PASA** | 0.45 → 0.80 → 0.45 aplicado sin reiniciar el video | 0.0 s |
| CF-08 | Pausar y reanudar la detección | **PASA** | con la detección apagada el video sigue y no hay objetos | 0.5 s |
| CF-09 | Capturar una foto del video | **PASA** | JPEG de 30 KB | 0.0 s |
| CF-10 | Los avistamientos se guardan en la bitácora | **PASA** | #2 persona 92% guardado con recorte en PostgreSQL | 0.1 s |
| CF-11 | Analizar una imagen subida (bus.jpg) | **PASA** | 3 personas y 1 bus en la imagen de referencia | 0.2 s |
| CF-12 | Rechazar un archivo que no es imagen | **PASA** | rechazado con HTTP 400 y mensaje claro | 0.0 s |
| CF-13 | Exportar la bitácora a CSV | **PASA** | CSV con 2 avistamiento(s) | 0.1 s |
| CF-14 | Las acciones exigen POST con token CSRF | **PASA** | GET → 405 y POST sin token CSRF → 403 | 0.0 s |
| CF-15 | Apagar la cámara | **PASA** | cámara liberada | 0.4 s |

**15 pasan · 0 fallan · 0 omitidos**
