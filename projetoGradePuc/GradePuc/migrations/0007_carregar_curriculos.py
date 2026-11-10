"""Carrega os currículos que vêm junto com o projeto (GradePuc/dados/curriculos.json).

O db.sqlite3 não vai para o GitHub, então quem clona o projeto e roda `migrate` ficava
sem nenhum currículo (o "Escolha seu curso" do perfil vinha vazio). Agora os currículos
já vêm no `migrate`, sem internet. `importar_curriculos` continua servindo para atualizar
a partir do site da PUC (e `exportar_curriculos` para atualizar o arquivo).

Só grava se a tabela de currículos estiver vazia: quem já importou não é mexido.
O caminho de volta não apaga nada (os currículos podem ter sido atualizados depois).
"""
import json
from pathlib import Path

from django.db import migrations

ARQUIVO = Path(__file__).resolve().parents[1] / "dados" / "curriculos.json"


def carregar_curriculos(apps, schema_editor):
    Curriculo = apps.get_model("GradePuc", "Curriculo")
    DisciplinaCurriculo = apps.get_model("GradePuc", "DisciplinaCurriculo")
    LigacaoHabilitacao = apps.get_model("GradePuc", "LigacaoHabilitacao")
    if Curriculo.objects.exists() or not ARQUIVO.exists():
        return

    dados = json.loads(ARQUIVO.read_text(encoding="utf-8"))
    por_titulo = {}
    for c in dados["curriculos"]:
        curriculo = Curriculo.objects.create(
            titulo=c["titulo"], curso_nome=c["curso_nome"], ano=c["ano"],
            enfase=c["enfase"], url_pagina=c["url_pagina"],
        )
        por_titulo[curriculo.titulo] = curriculo
        DisciplinaCurriculo.objects.bulk_create([
            DisciplinaCurriculo(
                curriculo=curriculo, periodo=periodo, codigo=codigo, nome=nome,
                creditos=creditos, ch_extensao=ch_extensao, eh_grupo=eh_grupo, ordem=ordem,
            )
            for ordem, (periodo, codigo, nome, creditos, ch_extensao, eh_grupo) in enumerate(c["itens"])
        ])

    for ligacao in dados.get("ligacoes_pre_cadastradas", []):
        curriculo = por_titulo.get(ligacao["curriculo"])
        if curriculo is None:
            continue
        LigacaoHabilitacao.objects.get_or_create(
            curso_sigla=ligacao["curso_sigla"],
            habilitacao_sigla=ligacao["habilitacao_sigla"],
            enfase_sigla=ligacao["enfase_sigla"],
            defaults={"curriculo": curriculo, "origem": "pre_cadastro"},
        )


class Migration(migrations.Migration):

    dependencies = [
        ("GradePuc", "0006_espelho_e_curriculos"),
    ]

    operations = [
        migrations.RunPython(carregar_curriculos, migrations.RunPython.noop),
    ]
