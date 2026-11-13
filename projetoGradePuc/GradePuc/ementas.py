"""Pré-requisitos e co-requisitos das disciplinas, lidos da ementa no site da PUC.

Página: https://www.puc-rio.br/ferramentas/ementas/ementa.aspx?cd=<CÓDIGO> (iso-8859-1).
Nos quadros fieldset#prerequisito e fieldset#corequisito, cada span
"rptPreRequisito_ctlNN_spanPreRequisito" é uma alternativa (entre elas, "ou"); dentro
dela, os códigos ligados por "e" são todos exigidos. Um texto como "e MATEMÁTICA
(nivel 3)" é nivelamento, não disciplina: vira observação e não bloqueia.

Aqui só se interpreta o HTML e se lê/grava o arquivo dados/requisitos.json.
Baixar as páginas fica no command importar_requisitos.
"""
import json
import re
from pathlib import Path

from bs4 import BeautifulSoup

from .curriculos import limpar
from .models import EmentaLida, Requisito

URL_EMENTA = "https://www.puc-rio.br/ferramentas/ementas/ementa.aspx?cd={}"
ARQUIVO = Path(__file__).resolve().parent / "dados" / "requisitos.json"
CODIGO = re.compile(r"^[A-Z]{3}\d{4}$")
QUADROS = {"pre": "prerequisito", "co": "corequisito"}


def interpretar_alternativa(span):
    """([códigos], observação) de um span de alternativa."""
    codigos = []
    for link in span.find_all("a"):
        codigo = limpar(link.get_text()).upper()
        if CODIGO.match(codigo) and codigo not in codigos:
            codigos.append(codigo)
    textos = []
    for parte in span.find_all("span"):
        texto = limpar(parte.get_text())
        texto = re.sub(r"^(e|ou)\b\s*", "", texto, flags=re.IGNORECASE).strip()
        if texto:
            textos.append(texto)
    return codigos, "; ".join(textos)


def interpretar_ementa(html):
    """Requisitos de uma ementa:
    {'pre': [[códigos de uma alternativa], ...], 'co': [...],
     'observacoes': {'pre': [obs de cada alternativa], 'co': [...]}, 'encontrada': bool}
    'encontrada' é False quando a página não tem os quadros (código sem ementa na PUC)."""
    sopa = BeautifulSoup(html, "html.parser")
    resultado = {"pre": [], "co": [], "observacoes": {"pre": [], "co": []}, "encontrada": False}
    for tipo, quadro_id in QUADROS.items():
        quadro = sopa.find("fieldset", id=quadro_id)
        if quadro is None:
            continue
        resultado["encontrada"] = True
        for span in quadro.find_all("span", id=re.compile(r"^rpt\w+Requisito_ctl\d+_span\w+Requisito$")):
            codigos, observacao = interpretar_alternativa(span)
            if not codigos and not observacao:
                continue
            resultado[tipo].append(codigos)
            resultado["observacoes"][tipo].append(observacao)
    return resultado


def gravar_requisitos(codigo, lidos):
    """Troca no banco os requisitos de uma disciplina pelos lidos da ementa."""
    Requisito.objects.filter(disciplina=codigo).delete()
    novos = []
    for tipo in QUADROS:
        for alternativa, (codigos, observacao) in enumerate(zip(lidos[tipo], lidos["observacoes"][tipo])):
            if not codigos:   # alternativa só com nivelamento: não exige disciplina
                novos.append(Requisito(disciplina=codigo, tipo=tipo, alternativa=alternativa,
                                       codigo="", observacao=observacao[:200]))
            for exigido in codigos:
                novos.append(Requisito(disciplina=codigo, tipo=tipo, alternativa=alternativa,
                                       codigo=exigido, observacao=observacao[:200]))
    Requisito.objects.bulk_create(novos)
    EmentaLida.objects.update_or_create(codigo=codigo, defaults={"encontrada": lidos["encontrada"]})


def requisitos_do_banco():
    """{disciplina: {'pre': [[códigos]], 'co': [...], 'observacoes': {...}}} do banco, para exportar."""
    por_disciplina = {}
    for r in Requisito.objects.order_by("disciplina", "tipo", "alternativa", "id"):
        d = por_disciplina.setdefault(r.disciplina, {"pre": {}, "co": {}, "obs": {"pre": {}, "co": {}}})
        alternativa = d[r.tipo].setdefault(r.alternativa, [])
        if r.codigo:
            alternativa.append(r.codigo)
        d["obs"][r.tipo][r.alternativa] = r.observacao
    resultado = {}
    for disciplina, d in por_disciplina.items():
        resultado[disciplina] = {
            tipo: [d[tipo][n] for n in sorted(d[tipo])] for tipo in QUADROS
        }
        resultado[disciplina]["observacoes"] = {
            tipo: [d["obs"][tipo][n] for n in sorted(d[tipo])] for tipo in QUADROS
        }
    return resultado


def em_uma_linha(valor):
    return json.dumps(valor, ensure_ascii=False)


def exportar_arquivo(equivalencias=None):
    """Grava dados/requisitos.json com o que está no banco (só requisitos, nada de aluno).
    Uma disciplina por linha, para dar para revisar no diff."""
    requisitos = requisitos_do_banco()
    lidas = list(EmentaLida.objects.filter(encontrada=True).values_list("codigo", flat=True))
    sem_ementa = list(EmentaLida.objects.filter(encontrada=False).values_list("codigo", flat=True))
    linhas = [
        "{",
        '  "sobre": ' + em_uma_linha(
            "Pré-requisitos e co-requisitos das disciplinas, lidos da ementa no site da PUC com "
            "importar_requisitos. Cada lista dentro de 'pre'/'co' é uma alternativa (OU); os códigos "
            "dentro dela são todos exigidos (E). Carregados pela migration 0011 quando o banco não tem nenhum."
        ) + ",",
        '  "lidas": ' + em_uma_linha(lidas) + ",",
        '  "sem_ementa": ' + em_uma_linha(sem_ementa) + ",",
        '  "requisitos": {',
    ]
    for n, (disciplina, dados) in enumerate(sorted(requisitos.items())):
        virgula = "," if n + 1 < len(requisitos) else ""
        linhas.append(f"    {em_uma_linha(disciplina)}: {em_uma_linha(dados)}{virgula}")
    linhas.append("  },")
    linhas.append('  "equivalencias": [')
    classes = equivalencias or []
    for n, classe in enumerate(classes):
        linhas.append("    " + em_uma_linha(classe) + ("," if n + 1 < len(classes) else ""))
    linhas += ["  ]", "}"]
    texto = "\n".join(linhas) + "\n"
    json.loads(texto)   # garante que saiu um JSON válido
    ARQUIVO.write_text(texto, encoding="utf-8")
    return len(requisitos), len(lidas), len(sem_ementa)


def carregar_dados(dados, Requisito=Requisito, EmentaLida=EmentaLida):
    """Grava no banco o conteúdo de requisitos.json (os modelos podem ser os históricos da migration)."""
    novos = []
    for disciplina, d in dados["requisitos"].items():
        for tipo in QUADROS:
            observacoes = d.get("observacoes", {}).get(tipo, [])
            for alternativa, codigos in enumerate(d.get(tipo, [])):
                observacao = observacoes[alternativa] if alternativa < len(observacoes) else ""
                for exigido in codigos or [""]:
                    novos.append(Requisito(disciplina=disciplina, tipo=tipo, alternativa=alternativa,
                                           codigo=exigido, observacao=observacao[:200]))
    Requisito.objects.bulk_create(novos, batch_size=2000)
    EmentaLida.objects.bulk_create(
        [EmentaLida(codigo=c, encontrada=True) for c in dados.get("lidas", [])]
        + [EmentaLida(codigo=c, encontrada=False) for c in dados.get("sem_ementa", [])],
        batch_size=2000, ignore_conflicts=True,
    )

