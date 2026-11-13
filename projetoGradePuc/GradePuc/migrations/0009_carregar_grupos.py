"""Carrega os grupos de optativas que vêm junto com o projeto (GradePuc/dados/grupos.json).

Igual à 0007: quem clona o projeto e roda `migrate` já fica com as disciplinas de cada
grupo (ENG0561 -> ENG1021, ENG4500...), sem internet. `importar_grupos` atualiza a
partir do site da PUC.

Só grava se a tabela estiver vazia. O caminho de volta não apaga nada.
"""
import json
from pathlib import Path

from django.db import migrations

ARQUIVO = Path(__file__).resolve().parents[1] / "dados" / "grupos.json"


def carregar_grupos(apps, schema_editor):
    DisciplinaDoGrupo = apps.get_model("GradePuc", "DisciplinaDoGrupo")
    if DisciplinaDoGrupo.objects.exists() or not ARQUIVO.exists():
        return

    dados = json.loads(ARQUIVO.read_text(encoding="utf-8"))
    novas = []
    for grupo, disciplinas in dados["grupos"].items():
        for codigo, nome in disciplinas:
            novas.append(DisciplinaDoGrupo(grupo=grupo, codigo=codigo, nome=nome[:200]))
    DisciplinaDoGrupo.objects.bulk_create(novas)


class Migration(migrations.Migration):

    dependencies = [
        ("GradePuc", "0008_disciplinadogrupo"),
    ]

    operations = [
        migrations.RunPython(carregar_grupos, migrations.RunPython.noop),
    ]
