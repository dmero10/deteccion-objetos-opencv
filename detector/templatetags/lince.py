from django import template

register = template.Library()


@register.filter
def porcentaje(valor):
    """0.913 -> '91%'"""
    try:
        return f"{float(valor) * 100:.0f}%"
    except (TypeError, ValueError):
        return ""


@register.filter
def entero_pct(valor):
    """0.913 -> 91 (para atributos style/width)"""
    try:
        return round(float(valor) * 100)
    except (TypeError, ValueError):
        return 0
