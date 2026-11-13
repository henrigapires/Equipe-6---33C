"""Lê no site da PUC os pré-requisitos e co-requisitos das disciplinas (ementa.aspx?cd=<código>).

Começa pelos códigos de Disciplina, DisciplinaCurriculo e das listas de optativas
(DisciplinaDoGrupo) e segue a rede: todo código que aparece como requisito também é lido,
até fechar. Cada código lido vai para o banco na hora (Requisito + EmentaLida), então dá
para interromper e rodar de novo: por padrão (--so-faltantes) só baixa o que ainda não foi
lido. --refazer baixa tudo de novo. No fim grava GradePuc/dados/requisitos.json, que vai
junto com o projeto (a migration 0011 carrega ele).

Educado com o servidor da PUC: no máximo ~3 páginas por segundo, timeout, até 3 tentativas
com espera. Código com erro não derruba o comando: aparece no relatório do fim.
"""
import re
import time
from collections import deque
from pathlib import Path

import requests
from django.core.management.base import BaseCommand
from django.db import transaction

from ...curriculos import decodificar_html
from ...ementas import URL_EMENTA, exportar_arquivo, gravar_requisitos, interpretar_ementa
from ...models import Disciplina, DisciplinaCurriculo, DisciplinaDoGrupo, EmentaLida, Requisito

CABECALHOS = {"User-Agent": "GradePuc (projeto academico ENG4021 PUC-Rio)"}
INTERVALO = 0.34       # segundos entre requisições (~3 por segundo)
TENTATIVAS = 3
TIMEOUT = 30
CODIGO = re.compile(r"^[A-Z]{3}\d{4}$")


def codigos_iniciais():
    codigos = set(Disciplina.objects.values_list("codigo", flat=True))
    codigos |= set(DisciplinaCurriculo.objects.filter(eh_grupo=False).values_list("codigo", flat=True))
    codigos |= set(DisciplinaDoGrupo.objects.values_list("codigo", flat=True))
    return sorted(c for c in codigos if CODIGO.match(c))


class Command(BaseCommand):
    help = "Importa do site da PUC os pré-requisitos e co-requisitos das disciplinas."

    def add_arguments(self, parser):
        modo = parser.add_mutually_exclusive_group()
        modo.add_argument("--so-faltantes", action="store_true",
                          help="Padrão: só baixa os códigos que ainda não foram lidos.")
        modo.add_argument("--refazer", action="store_true", help="Baixa todos os códigos de novo.")
        parser.add_argument("--codigos", nargs="+", help="Começa só por estes códigos (para testar).")
        parser.add_argument("--cache", help="Pasta para salvar e reaproveitar o HTML baixado.")
        parser.add_argument("--so-exportar", action="store_true",
                            help="Não baixa nada: só regrava dados/requisitos.json com o que está no banco.")

    def handle(self, *args, **options):
        if options["so_exportar"]:
            self.exportar()
            return

        self.cache = Path(options["cache"]) if options["cache"] else None
        if self.cache:
            self.cache.mkdir(parents=True, exist_ok=True)
        self.refazer = options["refazer"]
        self.ultima_requisicao = 0.0

        fila = deque(c.upper() for c in (options["codigos"] or codigos_iniciais()))
        vistos = set(fila)
        ja_lidos = set() if self.refazer else set(EmentaLida.objects.values_list("codigo", flat=True))
        erros = []
        baixados = 0
        inicio = time.time()
        self.stdout.write(f"{len(fila)} códigos para começar ({len(ja_lidos)} já lidos antes).")

        while fila:
            codigo = fila.popleft()
            if codigo in ja_lidos:
                exigidos = Requisito.objects.filter(disciplina=codigo).exclude(codigo="").values_list("codigo", flat=True)
            else:
                try:
                    lidos = interpretar_ementa(self.baixar(codigo))
                except requests.RequestException as erro:
                    erros.append(f"{codigo}: {type(erro).__name__}")
                    continue
                with transaction.atomic():
                    gravar_requisitos(codigo, lidos)
                baixados += 1
                exigidos = [c for tipo in ("pre", "co") for alternativa in lidos[tipo] for c in alternativa]
                if baixados % 50 == 0:
                    minutos = (time.time() - inicio) / 60
                    self.stdout.write(f"  {baixados} baixados, {len(fila)} na fila, {len(erros)} erros ({minutos:.1f} min)")

            for exigido in exigidos:
                if exigido not in vistos and CODIGO.match(exigido):
                    vistos.add(exigido)
                    fila.append(exigido)

        self.exportar()
        sem_ementa = list(EmentaLida.objects.filter(encontrada=False).values_list("codigo", flat=True))
        self.stdout.write(self.style.SUCCESS(f"\nIMPORTAÇÃO CONCLUÍDA: {baixados} páginas baixadas agora."))
        if sem_ementa:
            self.stdout.write(f"Códigos sem ementa na PUC ({len(sem_ementa)}): {', '.join(sem_ementa)}")
        if erros:
            self.stdout.write(self.style.WARNING(
                f"Códigos com erro ({len(erros)}), rode de novo para tentar só eles:\n  " + "\n  ".join(erros)
            ))

    def baixar(self, codigo):
        arquivo = self.cache / f"{codigo}.html" if self.cache else None
        if arquivo and arquivo.exists() and not self.refazer:
            return decodificar_html(arquivo.read_bytes())

        for tentativa in range(1, TENTATIVAS + 1):
            espera = INTERVALO - (time.time() - self.ultima_requisicao)
            if espera > 0:
                time.sleep(espera)
            self.ultima_requisicao = time.time()
            try:
                resposta = requests.get(URL_EMENTA.format(codigo), headers=CABECALHOS, timeout=TIMEOUT)
                resposta.raise_for_status()
                break
            except requests.RequestException:
                if tentativa == TENTATIVAS:
                    raise
                time.sleep(2 * tentativa)     # espera mais a cada tentativa
        if arquivo:
            arquivo.write_bytes(resposta.content)
        return decodificar_html(resposta.content)

    def exportar(self):
        disciplinas, lidas, sem_ementa = exportar_arquivo()
        self.stdout.write(
            f"requisitos.json: {lidas} ementas lidas, {disciplinas} disciplinas com requisito, {sem_ementa} sem ementa."
        )
