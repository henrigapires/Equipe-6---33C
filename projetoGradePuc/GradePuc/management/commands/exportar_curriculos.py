"""Gera GradePuc/dados/curriculos.json a partir dos currículos do banco.

Esse arquivo vai junto com o projeto: a migration 0007 carrega os currículos dele
quando o banco ainda não tem nenhum (quem clona o projeto e roda `migrate` já fica
com os cursos, sem internet). Rode depois de `importar_curriculos` para atualizar.

Só entram Curriculo, DisciplinaCurriculo e as ligações de pré-cadastro
(nada de aluno, histórico ou ligação confirmada por aluno).
"""
import json
from pathlib import Path

from django.core.management.base import BaseCommand

from ...models import Curriculo, LigacaoHabilitacao

ARQUIVO = Path(__file__).resolve().parents[2] / "dados" / "curriculos.json"


def em_uma_linha(valor):
    return json.dumps(valor, ensure_ascii=False)


class Command(BaseCommand):
    help = "Exporta os currículos do banco para GradePuc/dados/curriculos.json (vai junto com o projeto)."

    def handle(self, *args, **options):
        # Uma disciplina por linha: o arquivo fica compacto e dá para revisar no diff.
        linhas = [
            "{",
            '  "sobre": ' + em_uma_linha(
                "Currículos da graduação PUC-Rio, importados do site da PUC com importar_curriculos "
                "e exportados com exportar_curriculos. Carregados pela migration 0007 quando o banco não tem currículo."
            ) + ",",
            '  "colunas_dos_itens": ' + em_uma_linha(
                ["periodo", "codigo", "nome", "creditos", "ch_extensao", "eh_grupo"]
            ) + ",",
            '  "curriculos": [',
        ]
        curriculos = list(Curriculo.objects.order_by("curso_nome", "ano", "enfase"))
        for n, curriculo in enumerate(curriculos):
            cabecalho = {
                "titulo": curriculo.titulo, "curso_nome": curriculo.curso_nome, "ano": curriculo.ano,
                "enfase": curriculo.enfase, "url_pagina": curriculo.url_pagina,
            }
            linhas.append("    {")
            for chave, valor in cabecalho.items():
                linhas.append(f'      "{chave}": {em_uma_linha(valor)},')
            linhas.append('      "itens": [')
            itens = list(curriculo.itens.order_by("ordem").values_list(
                "periodo", "codigo", "nome", "creditos", "ch_extensao", "eh_grupo"
            ))
            for i, item in enumerate(itens):
                linhas.append("        " + em_uma_linha(list(item)) + ("," if i + 1 < len(itens) else ""))
            linhas.append("      ]")
            linhas.append("    }" + ("," if n + 1 < len(curriculos) else ""))
        linhas.append("  ],")

        ligacoes = [
            {"curso_sigla": l.curso_sigla, "habilitacao_sigla": l.habilitacao_sigla,
             "enfase_sigla": l.enfase_sigla, "curriculo": l.curriculo.titulo}
            for l in LigacaoHabilitacao.objects.filter(
                origem="pre_cadastro", confirmado_por__isnull=True, curriculo__isnull=False
            ).select_related("curriculo").order_by("curso_sigla", "habilitacao_sigla", "enfase_sigla")
        ]
        linhas.append('  "ligacoes_pre_cadastradas": [')
        for i, ligacao in enumerate(ligacoes):
            linhas.append("    " + em_uma_linha(ligacao) + ("," if i + 1 < len(ligacoes) else ""))
        linhas.append("  ]")
        linhas.append("}")

        texto = "\n".join(linhas) + "\n"
        json.loads(texto)   # garante que saiu um JSON válido
        ARQUIVO.parent.mkdir(exist_ok=True)
        ARQUIVO.write_text(texto, encoding="utf-8")
        itens = sum(c.itens.count() for c in curriculos)
        self.stdout.write(self.style.SUCCESS(
            f"{ARQUIVO.name}: {len(curriculos)} currículos, {itens} disciplinas, {len(ligacoes)} ligações de pré-cadastro."
        ))
