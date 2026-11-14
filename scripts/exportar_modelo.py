"""Genera detector/modelos/<modelo>.onnx a partir de los pesos oficiales de Ultralytics.

NO hace falta ejecutarlo para usar la aplicación: yolo11n.onnx ya viene en el
repositorio. Este script solo documenta cómo se obtuvo, por si se quiere regenerar
o probar otro modelo (yolo11n, yolo11s, yolov8n, yolov8s...). Para usar otro,
cambia DETECTOR_MODELO en el .env.

Necesita Ultralytics (y PyTorch), que NO forman parte de la aplicación. Conviene
instalarlos en un entorno aparte:

    python -m venv venv-export
    venv-export\\Scripts\\pip install torch --index-url https://download.pytorch.org/whl/cpu
    venv-export\\Scripts\\pip install ultralytics onnx onnxslim
    venv-export\\Scripts\\python scripts/exportar_modelo.py yolo11n

La aplicación luego ejecuta el .onnx solo con OpenCV (cv2.dnn.readNetFromONNX).
"""
import shutil
import sys
from pathlib import Path

DESTINO = Path(__file__).resolve().parent.parent / "detector" / "modelos"


def main():
    nombre = sys.argv[1] if len(sys.argv) > 1 else "yolo11n"
    from ultralytics import YOLO  # import aquí: solo existe en el entorno de exportación

    modelo = YOLO(f"{nombre}.pt")  # descarga los pesos oficiales si no existen
    ruta_onnx = Path(modelo.export(format="onnx", imgsz=640, opset=12, simplify=True, dynamic=False))
    DESTINO.mkdir(parents=True, exist_ok=True)
    final = DESTINO / f"{nombre}.onnx"
    shutil.copyfile(ruta_onnx, final)
    print(f"Modelo exportado: {final} ({final.stat().st_size / 1e6:.1f} MB)")


if __name__ == "__main__":
    main()
