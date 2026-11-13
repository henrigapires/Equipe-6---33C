"""Carrega os pré/co-requisitos que vêm junto com o projeto (GradePuc/dados/requisitos.json).

Igual à 0007 (currículos) e à 0009 (grupos): quem clona o projeto e roda `migrate` já fica
com os requisitos, sem internet. `importar_requisitos` atualiza a partir do site da PUC.

Só grava se as tabelas estiverem vazias. O caminho de volta não apaga nada.
"""
import json
from pathlib import Path

from django.db import migrations

ARQUIVO = Path(__file__).resolve().parents[1] / "dados" / "requisitos.json"


def carregar_requisitos(apps, schema_editor):
    Requisito = apps.get_model("GradePuc", "Requisito")
    EmentaLida = apps.get_model("GradePuc", "EmentaLida")
    if Requisito.objects.exists() or EmentaLida.objects.exists() or not ARQUIVO.exists():
        return
    from GradePuc.ementas import carregar_dados
    carregar_dados(json.loads(ARQUIVO.read_text(encoding="utf-8")), Requisito=Requisito, EmentaLida=EmentaLida)


class Migration(migrations.Migration):

    dependencies = [
        ("GradePuc", "0010_requisitos"),
    ]

    operations = [
        migrations.RunPython(carregar_requisitos, migrations.RunPython.noop),
    ]
