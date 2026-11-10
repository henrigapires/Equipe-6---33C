from pathlib import Path
from urllib.parse import urljoin

import requests
from django.core.management.base import BaseCommand
from django.db import transaction
from django.db.models import F

from ...curriculos import (
    decodificar_html, escolher_mais_recentes, interpretar_pagina_curso, links_de_subpaginas,
)
from ...models import Curriculo, DisciplinaCurriculo, LigacaoHabilitacao

URL_CURSOS = "https://www.puc-rio.br/ensinopesq/ccg/cursos.html"
CABECALHOS = {"User-Agent": "GradePuc (projeto academico ENG4021 PUC-Rio)"}
MAXIMO_DE_PAGINAS = 150


class Command(BaseCommand):
    help = "Importa os currículos (periodização) dos cursos de graduação do site da PUC-Rio."

    def add_arguments(self, parser):
        parser.add_argument("--url", help="Importa só esta página de curso (para testar).")
        parser.add_argument("--cache", help="Pasta para salvar e reaproveitar o HTML baixado.")

    def baixar(self, url):
        arquivo = None
        if self.cache:
            arquivo = self.cache / url.rstrip("/").split("/")[-1]
            if arquivo.exists():
                return decodificar_html(arquivo.read_bytes())

        resposta = requests.get(url, headers=CABECALHOS, timeout=30)
        resposta.raise_for_status()
        if arquivo:
            arquivo.write_bytes(resposta.content)
        return decodificar_html(resposta.content)

    def handle(self, *args, **options):
        self.cache = Path(options["cache"]) if options["cache"] else None
        if self.cache:
            self.cache.mkdir(parents=True, exist_ok=True)

        if options["url"]:
            pendentes = [options["url"]]
        else:
            self.stdout.write("Lendo a lista de cursos...")
            pendentes = [urljoin(URL_CURSOS, link) for link in links_de_subpaginas(self.baixar(URL_CURSOS))]

        visitadas = set()
        avisos = []
        escolhidas = []
        while pendentes and len(visitadas) < MAXIMO_DE_PAGINAS:
            url = pendentes.pop(0)
            if url in visitadas:
                continue
            visitadas.add(url)

            try:
                html = self.baixar(url)
            except requests.RequestException as erro:
                avisos.append(f"{url}: não foi possível baixar ({erro})")
                continue

            secoes, avisos_da_pagina = interpretar_pagina_curso(html, url)
            avisos += avisos_da_pagina
            if secoes:
                escolhidas += escolher_mais_recentes(secoes)
                continue

            # páginas como Comunicação e Letras só têm links para as subpáginas de cada curso
            novas = [urljoin(url, link) for link in links_de_subpaginas(html)]
            novas = [link for link in novas if link not in visitadas]
            if novas:
                pendentes = novas + pendentes
            else:
                avisos.append(f"{url}: nenhuma periodização encontrada")

        with transaction.atomic():
            for secao in escolhidas:
                self.salvar_curriculo(secao)
            avisos += self.garantir_pre_cadastro()

        self.imprimir_resumo(visitadas, escolhidas, avisos)

    def salvar_curriculo(self, secao):
        curriculo, _ = Curriculo.objects.update_or_create(
            curso_nome=secao["curso_nome"][:200],
            ano=secao["ano"],
            enfase=secao["enfase"][:200],
            defaults={"titulo": secao["titulo"][:300], "url_pagina": secao["url"][:300]},
        )
        curriculo.itens.all().delete()
        DisciplinaCurriculo.objects.bulk_create([
            DisciplinaCurriculo(
                curriculo=curriculo,
                periodo=item["periodo"],
                codigo=item["codigo"],
                nome=item["nome"][:200],
                creditos=item["creditos"],
                ch_extensao=item["ch_extensao"][:20],
                eh_grupo=item["eh_grupo"],
                ordem=item["ordem"],
            )
            for item in secao["itens"]
        ])

    def garantir_pre_cadastro(self):
        """CEG/BCO (qualquer ênfase) = Engenharia de Computação, confirmado com um espelho real."""
        computacao = (
            Curriculo.objects.filter(curso_nome="Engenharia de Computação")
            .order_by(F("ano").desc(nulls_last=True)).first()
        )
        if computacao is None:
            return ["Pré-cadastro CEG/BCO não criado: currículo de Engenharia de Computação não encontrado."]

        ligacao, criada = LigacaoHabilitacao.objects.get_or_create(
            curso_sigla="CEG", habilitacao_sigla="BCO", enfase_sigla="",
            defaults={"curriculo": computacao, "origem": "pre_cadastro"},
        )
        if not criada and ligacao.origem == "pre_cadastro" and ligacao.curriculo != computacao:
            ligacao.curriculo = computacao
            ligacao.save()
        return []

    def imprimir_resumo(self, visitadas, escolhidas, avisos):
        por_curso = {}
        for secao in escolhidas:
            por_curso.setdefault(secao["curso_nome"], []).append(secao)

        self.stdout.write(self.style.SUCCESS(
            f"\nIMPORTAÇÃO CONCLUÍDA!\n"
            f"Páginas lidas: {len(visitadas)}\n"
            f"Cursos: {len(por_curso)}\n"
            f"Currículos: {len(escolhidas)}\n"
            f"Disciplinas nos currículos: {sum(len(s['itens']) for s in escolhidas)}"
        ))
        for curso, secoes in sorted(por_curso.items()):
            ano = secoes[0]["ano"] or "sem ano"
            enfases = [s["enfase"] for s in secoes if s["enfase"]]
            extra = f" - {len(secoes)} variantes: {', '.join(enfases)}" if len(secoes) > 1 else ""
            self.stdout.write(f"  {curso} ({ano}){extra}")

        if avisos:
            self.stdout.write(self.style.WARNING(f"\nAvisos ({len(avisos)}):"))
            for aviso in avisos:
                self.stdout.write(f"  - {aviso}")
