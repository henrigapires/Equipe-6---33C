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

# OCR: "CTC4001 -", "CTC4002-MODELAGEME", "20261 CTC4001 - INSTRUMENTACAO" (texto já sem acento e em maiúsculas)
CODIGO_OCR = re.compile(r"^(?:(\d{5})\s*)?([A-Z0-9]{3})\s*([0-9OILSB]{4})(?![A-Z0-9])\s*-?\s*(.*)$")
CODIGO_OCR_SOLTO = re.compile(r"([A-Z0-9]{3})\s*([0-9OILSB]{4})(?![A-Z0-9])")
LETRAS_TROCADAS = str.maketrans("0158", "OISB")       # o OCR às vezes lê letra como número...
NUMEROS_TROCADOS = str.maketrans("OILSB", "01158")    # ...e número como letra
# Só o começo de cada rótulo: o OCR erra o fim ("Situaclio", "Discipli")
ROTULOS_DA_TABELA = [
    ("periodo", "perio"), ("disciplina", "discip"), ("turma", "turm"), ("grau", "grau"),
    ("situacao", "situa"), ("tipo", "tipo"), ("grupo", "grup"), ("creditos", "cred"),
    ("horas", "hora"), ("extensao", "ext"), ("oportunidades", "oport"),
]


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


def parece_espelho(texto):
    """Procura 'Espelho do Histórico' sem acento e sem espaços (o OCR às vezes junta as palavras)."""
    compacto = re.sub(r"[^a-z]", "", sem_acento(texto))
    return "espelhodohist" in compacto


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


def primeira_palavra(texto):
    partes = sem_acento(texto).split()
    return partes[0] if partes else ""


def ler_cabecalho_do_curso(palavras, tolerancia=3, distancia=40):
    """Linha 'Curso | Habilitação | Ênfase | Ano currículo | Código currículo | CR acumulado'
    com os valores logo abaixo. Cada valor vai para o rótulo mais próximo na horizontal.
    No OCR um rótulo pode vir inteiro numa caixa ("Ano curriculo") e as distâncias são em pixels."""
    for curso in [w for w in palavras if sem_acento(w["text"]) == "curso"]:
        linha = sorted(mesma_linha(palavras, curso, tolerancia), key=lambda w: w["x0"])
        textos = [primeira_palavra(w["text"]) for w in linha]
        if "habilitacao" not in textos:
            continue

        inicios = {"curso": "curso", "habilitacao": "habilitacao", "enfase": "enfase",
                   "ano": "ano_curriculo", "codigo": "codigo_curriculo", "cr": "cr"}
        rotulos = []
        for i, w in enumerate(linha):
            chave = inicios.get(primeira_palavra(w["text"]))
            if not chave:
                continue
            fim = w
            for seguinte in linha[i + 1:]:
                if primeira_palavra(seguinte["text"]) in inicios:
                    break
                fim = seguinte
            rotulos.append((chave, (w["x0"] + fim["x1"]) / 2))

        topo = max(w["bottom"] for w in linha)
        valores = [w for w in palavras if topo + 1 < w["top"] < topo + distancia]
        if not valores:
            return {}
        primeira_linha = min(w["top"] for w in valores)
        valores = sorted([w for w in valores if w["top"] - primeira_linha <= tolerancia], key=lambda w: w["x0"])

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


# ---------- Leitura das caixas do OCR ----------

def altura_tipica(palavras):
    """Altura mediana das caixas: no OCR as distâncias são em pixels e mudam com a imagem."""
    alturas = sorted(w["bottom"] - w["top"] for w in palavras)
    return alturas[len(alturas) // 2] if alturas else 10


def centro_y(w):
    return (w["top"] + w["bottom"]) / 2


def centro_do_trecho(w, trecho):
    """Centro horizontal de um rótulo dentro da caixa (o OCR pode juntar dois rótulos numa caixa)."""
    texto = sem_acento(w["text"])
    inicio = texto.find(trecho)
    if inicio < 0 or not texto:
        return (w["x0"] + w["x1"]) / 2
    meio = (inicio + len(trecho) / 2) / len(texto)
    return w["x0"] + (w["x1"] - w["x0"]) * meio


def corrigir_codigo(letras, numeros):
    return letras.translate(LETRAS_TROCADAS) + numeros.translate(NUMEROS_TROCADOS)


def codigo_valido(letras, numeros):
    """Evita confundir pedaços de nomes com códigos: o número precisa ter dígitos de verdade."""
    corrigido = corrigir_codigo(letras, numeros)
    return CODIGO.match(corrigido) and sum(c.isdigit() for c in numeros) >= 2


def achar_colunas_ocr(palavras):
    """Posição (centro x) de cada coluna da tabela e onde o cabeçalho termina.
    Devolve None se a página não tiver o cabeçalho da tabela."""
    h = altura_tipica(palavras)
    ancora = None
    for w in palavras:
        if "perio" in sem_acento(w["text"]):
            linha = [sem_acento(x["text"]) for x in palavras if abs(centro_y(x) - centro_y(w)) <= h]
            if any("discip" in t for t in linha) and any("turm" in t for t in linha):
                ancora = w
                break
    if ancora is None:
        return None

    cabecalho = [w for w in palavras if ancora["top"] - 3 * h <= centro_y(w) <= ancora["bottom"] + 2 * h]
    centros = {}
    for coluna, trecho in ROTULOS_DA_TABELA:
        candidatos = [w for w in cabecalho if trecho in sem_acento(w["text"])]
        if candidatos:
            primeiro = min(candidatos, key=lambda w: w["x0"])
            centros[coluna] = centro_do_trecho(primeiro, trecho)
    if not all(c in centros for c in ("periodo", "turma", "situacao")):
        return None

    # "Disciplina" fica entre Período e Turma (o outro "disciplina" é o de "Tipo da disciplina").
    # Se o OCR não leu esse rótulo, estima a posição como no espelho original.
    entre = [
        centro_do_trecho(w, "discip") for w in cabecalho
        if "discip" in sem_acento(w["text"]) and centros["periodo"] < centro_do_trecho(w, "discip") < centros["turma"]
    ]
    if entre:
        centros["disciplina"] = min(entre)
    else:
        centros["disciplina"] = centros["periodo"] + (centros["turma"] - centros["periodo"]) * 0.31
    return centros, max(w["bottom"] for w in cabecalho)


def ler_tabela_ocr(palavras, largura=None, colunas_de_antes=None):
    """Lê as disciplinas de uma página do OCR. Devolve (disciplinas, códigos lidos,
    situações lidas), ou None se a página não tiver a tabela.

    colunas_de_antes = (centros, largura) de um print anterior: serve para ler um
    print que continua a tabela e não mostra mais o cabeçalho (rolou a página)."""
    h = altura_tipica(palavras)
    largura = largura or max((w["x1"] for w in palavras), default=0)
    achou = achar_colunas_ocr(palavras)
    if achou:
        centros, fim_cabecalho = achou
    elif colunas_de_antes and colunas_de_antes[1]:
        escala = largura / colunas_de_antes[1]
        centros = {c: x * escala for c, x in colunas_de_antes[0].items()}
        fim_cabecalho = float("-inf")
    else:
        return None

    def coluna_de(w):
        meio = (w["x0"] + w["x1"]) / 2
        return min(centros, key=lambda c: abs(centros[c] - meio))

    corpo = [w for w in palavras if centro_y(w) > fim_cabecalho]
    rodape = [
        w["top"] for w in corpo
        if w["text"].startswith("*") or sem_acento(w["text"]).startswith("http") or w["x1"] - w["x0"] > 0.6 * largura
    ]
    fim_tabela = min(rodape) if rodape else float("inf")
    tabela = [w for w in corpo if w["top"] < fim_tabela]

    inicios = []
    for w in tabela:
        if coluna_de(w) not in ("periodo", "disciplina"):
            continue
        m = CODIGO_OCR.match(sem_acento(w["text"]).upper().strip())
        if m and codigo_valido(m.group(2), m.group(3)):
            inicios.append((w, m))
    inicios.sort(key=lambda par: par[0]["top"])

    situacoes_lidas = sum(
        1 for w in tabela
        if coluna_de(w) == "situacao" and len(re.sub(r"[^A-Z]", "", sem_acento(w["text"]).upper())) == 2
    )

    disciplinas = []
    for i, (inicio, m) in enumerate(inicios):
        y0 = inicio["top"] - h / 2
        y1 = inicios[i + 1][0]["top"] - h / 2 if i + 1 < len(inicios) else fim_tabela
        bloco = [w for w in tabela if w is not inicio and y0 <= centro_y(w) < y1]

        def coluna(nome):
            caixas = sorted([w for w in bloco if coluna_de(w) == nome], key=lambda w: (w["top"], w["x0"]))
            return " ".join(sem_acento(w["text"]).upper().strip() for w in caixas)

        periodo = m.group(1) or ""
        if not periodo:
            achou = re.search(r"\d{5}", coluna("periodo"))
            periodo = achou.group(0) if achou else ""

        nome = (m.group(4) + " " + coluna("disciplina")).strip(" -")
        grupo = CODIGO_OCR_SOLTO.search(coluna("grupo")) if "grupo" in centros else None
        creditos = re.search(r"\d+", coluna("creditos")) if "creditos" in centros else None

        disciplinas.append({
            "periodo": periodo,
            "codigo": corrigir_codigo(m.group(2), m.group(3)),
            "nome": re.sub(r"\s+", " ", nome),
            "turma": coluna("turma"),
            "grau": coluna("grau"),
            "situacao": re.sub(r"[^A-Z]", "", coluna("situacao")),
            "tipo": re.sub(r"[^A-Z]", "", coluna("tipo").translate(LETRAS_TROCADAS)) if "tipo" in centros else "",
            "grupo": corrigir_codigo(grupo.group(1), grupo.group(2)) if grupo else "",
            "creditos": int(creditos.group(0)) if creditos else 0,
        })
    return disciplinas, len(inicios), situacoes_lidas


def interpretar_paginas(paginas):
    texto = "\n".join(p["texto"] for p in paginas)
    if not any(p["palavras"] for p in paginas):
        raise EspelhoSemTexto(
            "Este PDF não tem texto selecionável (parece escaneado ou foto). "
            "Envie o PDF original baixado do SAU."
        )
    if not parece_espelho(texto):
        raise EspelhoInvalido("Este PDF não parece ser o Espelho do Histórico do SAU.")

    m = MATRICULA.search(texto)
    dados = {
        "matricula": m.group(1) if m else "",
        "curso": "", "habilitacao": "", "enfase": "",
        "ano_curriculo": "", "codigo_curriculo": "", "cr": "",
        "disciplinas": [],
    }

    achou_tabela = False
    contagem_ocr = {"codigos": 0, "situacoes": 0}
    colunas_de_antes = None     # colunas do último print com cabeçalho (prints seguintes não têm)
    origens = []                # de qual arquivo veio cada disciplina
    for n, pagina in enumerate(paginas):
        palavras = pagina["palavras"]
        por_ocr = pagina.get("ocr", False)
        if n == 0 or not dados["curso"]:
            if por_ocr:
                h = altura_tipica(palavras)
                dados.update(ler_cabecalho_do_curso(palavras, tolerancia=0.6 * h, distancia=3 * h))
            else:
                dados.update(ler_cabecalho_do_curso(palavras))

        if por_ocr:
            largura = pagina.get("largura")
            resultado = ler_tabela_ocr(palavras, largura, colunas_de_antes)
            achou = achar_colunas_ocr(palavras)
            if achou:
                colunas_de_antes = (achou[0], largura or max((w["x1"] for w in palavras), default=0))
            linhas = None
            if resultado is not None:
                linhas, codigos, situacoes = resultado
                contagem_ocr["codigos"] += codigos
                contagem_ocr["situacoes"] += situacoes
        else:
            linhas = ler_tabela(palavras, pagina.get("altura", 10000))
        if linhas is not None:
            achou_tabela = True
            dados["disciplinas"].extend(linhas)
            origens.extend([pagina.get("arquivo", 0)] * len(linhas))

    if any(p.get("ocr") for p in paginas):
        dados["ocr"] = contagem_ocr

    if not achou_tabela:
        raise EspelhoInvalido("Não encontramos a tabela de disciplinas neste espelho.")

    # o período só aparece na primeira disciplina do semestre; as seguintes herdam
    atual = ""
    for d in dados["disciplinas"]:
        if d["periodo"]:
            atual = d["periodo"]
        else:
            d["periodo"] = atual

    # prints que se sobrepõem repetem disciplinas: vale a primeira vez que apareceu
    # (só entre arquivos diferentes, dentro de um arquivo nada é descartado)
    vistas = {}
    sem_repetidas = []
    for d, origem in zip(dados["disciplinas"], origens):
        chave = (d["periodo"], d["codigo"])
        if vistas.setdefault(chave, origem) == origem:
            sem_repetidas.append(d)
    dados["disciplinas"] = sem_repetidas
    return dados


def ler_espelho(arquivo):
    return interpretar_paginas(extrair_palavras(arquivo))
