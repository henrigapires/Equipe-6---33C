"""Lê no site da PUC as disciplinas de cada grupo de optativas dos currículos.

Os grupos são os itens com eh_grupo=True dos currículos (curriculos.json). Para cada um,
baixa ementa.aspx?cd=<grupo> e grava a lista em GradePuc/dados/grupos.json (vai junto
com o projeto; a migration 0009 carrega ele) e no banco.

Use --so-arquivo para só gerar o arquivo, sem mexer no banco.
"""
import json
import time
from pathlib import Path

import requests
from django.core.management.base import BaseCommand
from django.db import transaction

from ...curriculos import decodificar_html
from ...grupos import ARQUIVO, URL_EMENTA, carregar_arquivo, interpretar_ementa_do_grupo
from ...models import DisciplinaCurriculo

CABECALHOS = {"User-Agent": "GradePuc (projeto academico ENG4021 PUC-Rio)"}
PAUSA = 0.3  # segundos entre uma página e outra, para não sobrecarregar o site


def em_uma_linha(valor):
    return json.dumps(valor, ensure_ascii=False)


class Command(BaseCommand):
    help = "Importa do site da PUC as disciplinas de cada grupo de optativas dos currículos."

    def add_arguments(self, parser):
        parser.add_argument("--so-arquivo", action="store_true", help="Só gera dados/grupos.json, sem gravar no banco.")
        parser.add_argument("--cache", help="Pasta para salvar e reaproveitar o HTML baixado.")

    def baixar(self, grupo):
        arquivo = self.cache / f"{grupo}.html" if self.cache else None
        if arquivo and arquivo.exists():
            return decodificar_html(arquivo.read_bytes())

        resposta = requests.get(URL_EMENTA.format(grupo), headers=CABECALHOS, timeout=30)
        resposta.raise_for_status()
        if arquivo:
            arquivo.write_bytes(resposta.content)
        time.sleep(PAUSA)
        return decodificar_html(resposta.content)

    def handle(self, *args, **options):
        self.cache = Path(options["cache"]) if options["cache"] else None
        if self.cache:
            self.cache.mkdir(parents=True, exist_ok=True)

        codigos = sorted(set(DisciplinaCurriculo.objects.filter(eh_grupo=True).values_list("codigo", flat=True)))
        self.stdout.write(f"Lendo {len(codigos)} grupos...")

        grupos = {}
        sem_lista = []
        avisos = []
        total = 0
        for grupo in codigos:
            try:
                disciplinas = interpretar_ementa_do_grupo(self.baixar(grupo))
            except requests.RequestException as erro:
                avisos.append(f"{grupo}: não foi possível baixar ({erro})")
                continue
            if disciplinas:
                grupos[grupo] = disciplinas
                total += len(disciplinas)
            else:
                sem_lista.append(grupo)

        if avisos:
            # Arquivo incompleto não substitui o anterior.
            self.stdout.write(self.style.ERROR(f"\n{len(avisos)} grupos não foram baixados; nada foi gravado:"))
            for aviso in avisos:
                self.stdout.write(f"  - {aviso}")
            return

        self.salvar_arquivo(grupos)
        if not options["so_arquivo"]:
            with transaction.atomic():
                carregar_arquivo()

        self.stdout.write(self.style.SUCCESS(
            f"\nIMPORTAÇÃO CONCLUÍDA!\n"
            f"Grupos com lista: {len(grupos)}\n"
            f"Disciplinas (grupo, disciplina): {total}\n"
            f"Banco: {'não alterado (--so-arquivo)' if options['so_arquivo'] else 'atualizado'}"
        ))
        if sem_lista:
            self.stdout.write(f"Grupos sem lista na PUC ({len(sem_lista)}): {', '.join(sem_lista)}")

    def salvar_arquivo(self, grupos):
        # Um grupo por linha: dá para revisar no diff.
        linhas = [
            "{",
            '  "sobre": ' + em_uma_linha(
                "Disciplinas de cada grupo de optativas dos currículos, lidas da ementa do grupo no site "
                "da PUC com importar_grupos. Carregadas pela migration 0009 quando o banco não tem nenhuma."
            ) + ",",
            '  "grupos": {',
        ]
        for n, (grupo, disciplinas) in enumerate(grupos.items()):
            virgula = "," if n + 1 < len(grupos) else ""
            linhas.append(f"    {em_uma_linha(grupo)}: {em_uma_linha(disciplinas)}{virgula}")
        linhas += ["  }", "}"]

        texto = "\n".join(linhas) + "\n"
        json.loads(texto)   # garante que saiu um JSON válido
        ARQUIVO.write_text(texto, encoding="utf-8")
