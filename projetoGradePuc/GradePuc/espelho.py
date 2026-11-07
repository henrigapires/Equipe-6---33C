"""Leitura do 'Espelho do Histórico' do SAU (PDF com texto selecionável).

Duas camadas, para dar para testar sem PDF:
- extrair_palavras(arquivo): abre o PDF e devolve as palavras de cada página.
- interpretar_paginas(paginas): transforma essas palavras no dicionário final.
"""
import io
import re
import unicodedata

import pdfplumber


# Situações do SAU (legenda do espelho)
SITUACOES_CURSADAS = {"AP", "CP", "CC", "CT", "DS"}
SITUACOES_EM_ANDAMENTO = {"EA"}
# Qualquer outra (RM, RF, NC, NI, CA, CD, CJ, CL, AT, DT, LT, IN...) pode ser sugerida de novo.

CODIGO = re.compile(r"^[A-Z]{3}\d{4}$")
CODIGO_E_NOME = re.compile(r"^([A-Z]{3}\d{4})\s*-\s*(.*)$")
MATRICULA = re.compile(r"\((\d{7})\)")


class EspelhoInvalido(Exception):
    pass


class EspelhoSemTexto(Exception):
    pass


def classificar_situacao(situacao):
    if situacao in SITUACOES_CURSADAS:
        return "cursada"
    if situacao in SITUACOES_EM_ANDAMENTO:
        return "em_andamento"
    return "pode_cursar"


def sem_acento(texto):
    texto = unicodedata.normalize("NFD", texto)
    return "".join(c for c in texto if unicodedata.category(c) != "Mn").lower()


def extrair_palavras(arquivo):
    """Aceita um caminho ou um arquivo enviado pelo Django."""
    if hasattr(arquivo, "read"):
        if hasattr(arquivo, "seek"):
            arquivo.seek(0)
        arquivo = io.BytesIO(arquivo.read())

    paginas = []
    try:
        with pdfplumber.open(arquivo) as pdf:
            for pagina in pdf.pages:
                paginas.append({
                    "palavras": pagina.extract_words(keep_blank_chars=False, use_text_flow=False),
                    "texto": pagina.extract_text() or "",
                    "altura": pagina.height,
                })
    except Exception:
        raise EspelhoInvalido("Não foi possível abrir este arquivo como PDF.")
    return paginas


def mesma_linha(palavras, referencia, tolerancia=3):
    return [w for w in palavras if abs(w["top"] - referencia["top"]) <= tolerancia]


def ler_cabecalho_do_curso(palavras):
    """Linha 'Curso | Habilitação | Ênfase | Ano currículo | Código currículo | CR acumulado'
    com os valores logo abaixo. Cada valor vai para o rótulo mais próximo na horizontal."""
    for curso in [w for w in palavras if sem_acento(w["text"]) == "curso"]:
        linha = sorted(mesma_linha(palavras, curso), key=lambda w: w["x0"])
        textos = [sem_acento(w["text"]) for w in linha]
        if "habilitacao" not in textos:
            continue

        inicios = {"curso": "curso", "habilitacao": "habilitacao", "enfase": "enfase",
                   "ano": "ano_curriculo", "codigo": "codigo_curriculo", "cr": "cr"}
        rotulos = []
        for i, w in enumerate(linha):
            chave = inicios.get(sem_acento(w["text"]))
            if not chave:
                continue
            fim = w
            for seguinte in linha[i + 1:]:
                if sem_acento(seguinte["text"]) in inicios:
                    break
                fim = seguinte
            rotulos.append((chave, (w["x0"] + fim["x1"]) / 2))

        topo = max(w["bottom"] for w in linha)
        valores = [w for w in palavras if topo + 1 < w["top"] < topo + 40]
        if not valores:
            return {}
        primeira_linha = min(w["top"] for w in valores)
        valores = sorted([w for w in valores if w["top"] - primeira_linha <= 3], key=lambda w: w["x0"])

        resultado = {}
        for valor in valores:
            centro = (valor["x0"] + valor["x1"]) / 2
            chave = min(rotulos, key=lambda r: abs(r[1] - centro))[0]
            resultado[chave] = (resultado.get(chave, "") + " " + valor["text"]).strip()
        return resultado
    return {}


def numero_inteiro(texto):
    try:
        return int(float(texto.replace(",", ".")))
    except (ValueError, AttributeError):
        return 0


def ler_tabela(palavras, altura):
    """Lê as disciplinas de uma página. Devolve [] se a página não tiver a tabela."""
    ancora = None
    for w in palavras:
        if sem_acento(w["text"]) == "periodo":
            textos = {sem_acento(x["text"]) for x in mesma_linha(palavras, w, 5)}
            if "disciplina" in textos and "turma" in textos:
                ancora = w
                break
    if ancora is None:
        return None

    # o cabeçalho pode ter duas linhas ("N°" / "créd.")
    cabecalho = [w for w in palavras if -8 <= w["top"] - ancora["top"] <= 20]
    fim_cabecalho = max(w["bottom"] for w in cabecalho)

    def x_de(*textos):
        achados = [w["x0"] for w in cabecalho if sem_acento(w["text"]) in textos]
        if not achados:
            raise EspelhoInvalido("Não reconhecemos as colunas da tabela do espelho.")
        return min(achados)

    # posições das colunas pelo cabeçalho da tabela (deslocamentos validados no espelho real)
    x_periodo, x_disc = x_de("periodo"), x_de("disciplina")
    x_turma, x_grau, x_sit = x_de("turma"), x_de("grau"), x_de("situacao")
    x_grupo = x_de("grupo")
    x_tipo = x_sit + (x_grupo - x_sit) * 0.45      # "Tipo da disciplina" fica entre Situação e Grupo
    x_cred = x_de("cred.") - 15
    x_horas = x_de("horas") - 5

    corpo = [w for w in palavras if w["top"] > fim_cabecalho]
    rodape = [w["top"] for w in corpo if w["text"].startswith("*") or w["text"] == "TODOS"]
    fim_tabela = min(rodape) if rodape else altura

    inicios = sorted(
        [w for w in corpo if CODIGO.match(w["text"]) and abs(w["x0"] - x_disc) < 15 and w["top"] < fim_tabela],
        key=lambda w: w["top"],
    )

    disciplinas = []
    for i, inicio in enumerate(inicios):
        # período e grau ficam na linha central do bloco da disciplina
        y0 = inicio["top"] - 12
        y1 = inicios[i + 1]["top"] - 12 if i + 1 < len(inicios) else fim_tabela
        bloco = [w for w in corpo if y0 <= w["top"] < y1]

        def coluna(xa, xb):
            ordenadas = sorted(bloco, key=lambda w: (round(w["top"]), w["x0"]))
            return " ".join(w["text"] for w in ordenadas if xa <= w["x0"] < xb)

        m = CODIGO_E_NOME.match(coluna(x_disc, x_turma - 5))
        if not m:
            continue
        disciplinas.append({
            "periodo": coluna(x_periodo - 5, x_disc - 5),
            "codigo": m.group(1),
            "nome": m.group(2).strip(),
            "turma": coluna(x_turma - 5, x_grau - 8),
            "grau": coluna(x_grau - 8, x_sit - 12),
            "situacao": coluna(x_sit - 12, x_tipo),
            "tipo": coluna(x_tipo, x_grupo - 5),
            "grupo": coluna(x_grupo - 5, x_cred),
            "creditos": numero_inteiro(coluna(x_cred, x_horas)),
        })
    return disciplinas


def interpretar_paginas(paginas):
    texto = "\n".join(p["texto"] for p in paginas)
    if not any(p["palavras"] for p in paginas):
        raise EspelhoSemTexto(
            "Este PDF não tem texto selecionável (parece escaneado ou foto). "
            "Envie o PDF original baixado do SAU."
        )
    if "Espelho do Hist" not in texto:
        raise EspelhoInvalido("Este PDF não parece ser o Espelho do Histórico do SAU.")

    m = MATRICULA.search(texto)
    dados = {
        "matricula": m.group(1) if m else "",
        "curso": "", "habilitacao": "", "enfase": "",
        "ano_curriculo": "", "codigo_curriculo": "", "cr": "",
        "disciplinas": [],
    }

    achou_tabela = False
    for n, pagina in enumerate(paginas):
        if n == 0 or not dados["curso"]:
            dados.update(ler_cabecalho_do_curso(pagina["palavras"]))
        linhas = ler_tabela(pagina["palavras"], pagina.get("altura", 10000))
        if linhas is not None:
            achou_tabela = True
            dados["disciplinas"].extend(linhas)

    if not achou_tabela:
        raise EspelhoInvalido("Não encontramos a tabela de disciplinas neste espelho.")

    # o período só aparece na primeira disciplina do semestre; as seguintes herdam
    atual = ""
    for d in dados["disciplinas"]:
        if d["periodo"]:
            atual = d["periodo"]
        else:
            d["periodo"] = atual
    return dados


def ler_espelho(arquivo):
    return interpretar_paginas(extrair_palavras(arquivo))
