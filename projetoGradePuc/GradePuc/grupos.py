"""Grupos de optativas dos currículos (ENG0561, INF0307...) e as eletivas de cada curso.

O currículo só traz o código do grupo; quais disciplinas contam para ele está na ementa
do grupo no site da PUC (ementa.aspx?cd=ENG0561, quadro "Grupo de Disciplinas").
Baixar as páginas fica no command importar_grupos: aqui só se interpreta o HTML.

Eletivas Livres (ELL0900) não têm lista (vale qualquer disciplina), então não entram.
"""
import json
from pathlib import Path

from bs4 import BeautifulSoup

from .curriculos import CODIGO, limpar
from .models import Disciplina, DisciplinaDoGrupo

URL_EMENTA = "https://www.puc-rio.br/ferramentas/ementas/ementa.aspx?cd={}"
ARQUIVO = Path(__file__).resolve().parent / "dados" / "grupos.json"


def interpretar_ementa_do_grupo(html):
    """[(codigo, nome)] das disciplinas do quadro "Grupo de Disciplinas".
    Lista vazia se a página não tem o quadro (disciplina comum ou ELL0900)."""
    quadro = BeautifulSoup(html, "html.parser").find(id="grupoDisciplina")
    if quadro is None:
        return []

    disciplinas = []
    vistos = []
    for linha in quadro.find_all("p"):
        link = linha.find("a")
        if link is None:
            continue
        codigo = CODIGO.match(limpar(link.get_text()))
        if codigo is None or codigo.group(1) in vistos:
            continue
        vistos.append(codigo.group(1))

        nome = linha.find("span")
        if nome is None:
            disciplinas.append((codigo.group(1), ""))
        else:
            disciplinas.append((codigo.group(1), limpar(nome.get_text())))
    return disciplinas


def carregar_arquivo():
    """Grava no banco os grupos de dados/grupos.json (troca o que havia)."""
    dados = json.loads(ARQUIVO.read_text(encoding="utf-8"))
    novas = []
    for grupo, disciplinas in dados["grupos"].items():
        for codigo, nome in disciplinas:
            novas.append(DisciplinaDoGrupo(grupo=grupo, codigo=codigo, nome=nome[:200]))
    DisciplinaDoGrupo.objects.all().delete()
    DisciplinaDoGrupo.objects.bulk_create(novas)


def grupos_do_curriculo(curriculo):
    """{código do grupo: nome no currículo}, na ordem do currículo."""
    grupos = {}
    for item in curriculo.itens.filter(eh_grupo=True).order_by("ordem"):
        grupos.setdefault(item.codigo, item.nome)
    return grupos


def eletivas_do_curriculo(curriculo, grupos=None):
    """Disciplinas do micro-horário que contam para algum grupo de optativas do currículo.

    Uma disciplina que já é item obrigatório do currículo não entra (ela não ocupa vaga
    de optativa: veja historico.ocupacao_das_vagas). Devolve {Disciplina: [códigos dos grupos]}."""
    grupos = grupos_do_curriculo(curriculo) if grupos is None else grupos
    obrigatorias = set(curriculo.itens.filter(eh_grupo=False).values_list("codigo", flat=True))

    grupos_por_codigo = {}
    for grupo, codigo in DisciplinaDoGrupo.objects.filter(grupo__in=grupos).values_list("grupo", "codigo"):
        if codigo not in obrigatorias:
            grupos_por_codigo.setdefault(codigo, []).append(grupo)

    # Só as que têm turma: algumas Disciplina do banco não vieram do micro-horário.
    no_micro_horario = Disciplina.objects.filter(codigo__in=grupos_por_codigo, turma__isnull=False).distinct()
    eletivas = {}
    for disciplina in no_micro_horario.order_by("codigo"):
        eletivas[disciplina] = grupos_por_codigo[disciplina.codigo]
    return eletivas
