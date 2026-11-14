from django.db import models

from .clases import CLASES, categoria_de


class Avistamiento(models.Model):
    """Un objeto detectado en el video, guardado en PostgreSQL con su recorte en JPEG.

    No se guarda cada frame: el registrador (registro.py) guarda como máximo un
    avistamiento por clase cada DETECTOR_INTERVALO_REGISTRO segundos.
    """

    clase = models.PositiveSmallIntegerField(db_index=True, help_text="Índice COCO (0-79)")
    nombre = models.CharField(max_length=40)
    confianza = models.FloatField(help_text="Confianza de la mejor caja (0-1)")
    cantidad = models.PositiveSmallIntegerField(default=1, help_text="Objetos de esta clase en el frame")
    x = models.PositiveIntegerField(default=0)
    y = models.PositiveIntegerField(default=0)
    ancho = models.PositiveIntegerField(default=0)
    alto = models.PositiveIntegerField(default=0)
    imagen = models.BinaryField(help_text="Recorte del objeto en JPEG", editable=False)
    fecha = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        ordering = ["-fecha", "-id"]
        verbose_name = "avistamiento"
        verbose_name_plural = "avistamientos"
        indexes = [models.Index(fields=["clase", "-confianza"], name="avist_clase_conf_idx")]

    def __str__(self):
        return f"{self.nombre} ({self.confianza:.0%}) · {self.fecha:%Y-%m-%d %H:%M:%S}"

    @property
    def categoria(self):
        return categoria_de(self.clase)

    @property
    def nombre_ingles(self):
        return CLASES[self.clase][0] if 0 <= self.clase < len(CLASES) else ""
