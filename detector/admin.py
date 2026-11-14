from django.contrib import admin
from django.utils.html import format_html

from .models import Avistamiento


@admin.register(Avistamiento)
class AvistamientoAdmin(admin.ModelAdmin):
    list_display = ("miniatura", "nombre", "confianza_pct", "cantidad", "fecha")
    list_filter = ("nombre", "fecha")
    search_fields = ("nombre",)
    date_hierarchy = "fecha"
    readonly_fields = ("miniatura_grande",)
    exclude = ("imagen",)

    @admin.display(description="Imagen")
    def miniatura(self, obj):
        return format_html('<img src="/avistamientos/{}/imagen/" style="height:40px;border-radius:4px">', obj.pk)

    @admin.display(description="Recorte")
    def miniatura_grande(self, obj):
        return format_html('<img src="/avistamientos/{}/imagen/" style="max-height:240px">', obj.pk)

    @admin.display(description="Confianza", ordering="confianza")
    def confianza_pct(self, obj):
        return f"{obj.confianza:.0%}"
