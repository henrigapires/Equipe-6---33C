"""Tags dos templates do espelho do histórico."""
from django import template

from .. import ocr

register = template.Library()


@register.simple_tag
def ocr_instalado():
    """Uso: {% ocr_instalado as tem_ocr %}. False quando a leitura de prints não está
    instalada neste computador (Python 3.13+ ou requirements não instalados)."""
    return ocr.ocr_instalado()
