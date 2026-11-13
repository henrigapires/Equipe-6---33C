"""Propõe classes de equivalência para revisão humana. NÃO ativa nada.

As equivalências usadas pelo site são só as confirmadas (requisitos.EQUIVALENCIAS_CONFIRMADAS)
e os pares do campo grupo dos espelhos. Este comando sugere outras, para alguém revisar e,
se concordar, copiar para a lista confirmada:

1. Regra estrita sobre os requisitos das ementas: dois códigos se ligam quando aparecem
   juntos, como alternativas de UM código só, em pelo menos 2 requisitos, quando o menos
   frequente aparece junto com o outro em pelo menos 60% das vezes, e quando têm o mesmo
   prefixo (departamento).
2. Só ficam as classes em que todos os códigos têm o mesmo título normalizado (sem acento,
   caixa alta, sem algarismo romano ou arábico no fim: "ÁLGEBRA LINEAR I" = "ALGEBRA LINEAR 1").
3. Nunca entram os códigos de requisitos.NUNCA_EQUIVALENTES nem classes já confirmadas.

Grava revisao/equivalencias_sugeridas.txt (fora do app; o site não lê esse arquivo).
Os títulos vêm do HTML guardado pelo importar_requisitos --cache.

  python manage.py sugerir_equivalencias --cache cache_ementas
"""
import re
import unicodedata
from itertools import combinations
from pathlib import Path

from django.core.management.base import BaseCommand

from ...curriculos import decodificar_html
from ...models import Requisito
from ...requisitos import EQUIVALENCIAS_CONFIRMADAS, NUNCA_EQUIVALENTES

ARQUIVO = Path(__file__).resolve().parents[3] / "revisao" / "equivalencias_sugeridas.txt"
CONTENCAO_MINIMA = 0.6
JUNTOS_MINIMO = 2
NUMERAL_NO_FIM = re.compile(r"(\s+([IVXLC]+|\d+))+$")


def titulo_normalizado(titulo):
    sem_acento = "".join(c for c in unicodedata.normalize("NFD", titulo) if unicodedata.category(c) != "Mn")
    texto = re.sub(r"\s+", " ", sem_acento.upper()).strip()
    return NUMERAL_NO_FIM.sub("", texto)


def classes_estritas():
    alternativas = {}
    for disciplina, tipo, alternativa, codigo in Requisito.objects.values_list("disciplina", "tipo", "alternativa", "codigo"):
        if codigo:
            alternativas.setdefault((disciplina, tipo, alternativa), set()).add(codigo)
    unicos = {}
    for (disciplina, tipo, _), codigos in alternativas.items():
        if len(codigos) == 1:
            unicos.setdefault((disciplina, tipo), set()).add(next(iter(codigos)))
    onde = {}
    pares = set()
    for requisito, codigos in unicos.items():
        if len(codigos) < 2:
            continue
        for codigo in codigos:
            onde.setdefault(codigo, set()).add(requisito)
        pares |= set(combinations(sorted(codigos), 2))

    pai = {}

    def raiz(codigo):
        pai.setdefault(codigo, codigo)
        while pai[codigo] != codigo:
            pai[codigo] = pai[pai[codigo]]
            codigo = pai[codigo]
        return codigo

    for a, b in pares:
        if a[:3] != b[:3] or a in NUNCA_EQUIVALENTES or b in NUNCA_EQUIVALENTES:
            continue
        juntos = len(onde[a] & onde[b])
        if juntos >= JUNTOS_MINIMO and juntos / min(len(onde[a]), len(onde[b])) >= CONTENCAO_MINIMA:
            ra, rb = raiz(a), raiz(b)
            if ra != rb:
                pai[max(ra, rb)] = min(ra, rb)
    classes = {}
    for codigo in list(pai):
        classes.setdefault(raiz(codigo), []).append(codigo)
    return [sorted(classe) for classe in classes.values() if len(classe) > 1]


class Command(BaseCommand):
    help = "Sugere classes de equivalência para revisão (não ativa nenhuma)."

    def add_arguments(self, parser):
        parser.add_argument("--cache", required=True, help="Pasta com o HTML das ementas (importar_requisitos --cache).")

    def handle(self, *args, **options):
        titulos = {}
        for arquivo in Path(options["cache"]).glob("*.html"):
            achou = re.search(r'id="hTitulo"[^>]*>([^<]*)<', decodificar_html(arquivo.read_bytes()))
            if achou and achou.group(1).strip():
                titulos[arquivo.stem] = achou.group(1).strip()

        confirmadas = [set(classe) for classe in EQUIVALENCIAS_CONFIRMADAS]
        sugeridas, descartadas = [], 0
        for classe in sorted(classes_estritas()):
            if any(set(classe) <= confirmada for confirmada in confirmadas):
                continue
            normalizados = {titulo_normalizado(titulos.get(codigo, "")) for codigo in classe}
            if len(normalizados) == 1 and "" not in normalizados:
                sugeridas.append(classe)
            else:
                descartadas += 1

        linhas = [
            "# Classes de equivalência SUGERIDAS para revisão. O site NÃO usa este arquivo.",
            "# Gerado por: python manage.py sugerir_equivalencias --cache cache_ementas",
            "# Para ativar uma classe, revise e copie para requisitos.EQUIVALENCIAS_CONFIRMADAS.",
            f"# {len(sugeridas)} classes (regra estrita + mesmo título normalizado); "
            f"{descartadas} classes estritas descartadas por título diferente.",
            "",
        ]
        for classe in sugeridas:
            linhas.append(" = ".join(f"{codigo} ({titulos[codigo]})" for codigo in classe))
        ARQUIVO.parent.mkdir(exist_ok=True)
        ARQUIVO.write_text("\n".join(linhas) + "\n", encoding="utf-8")
        self.stdout.write(f"{ARQUIVO.name}: {len(sugeridas)} classes sugeridas, {descartadas} descartadas por título.")
