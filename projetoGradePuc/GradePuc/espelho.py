"""Leitura do 'Espelho do Histórico' do SAU (PDF com texto selecionável).

Duas camadas, para dar para testar sem PDF:
- extrair_palavras(arquivo): abre o PDF e devolve as palavras de cada página.
- interpretar_paginas(paginas): transforma essas palavras no dicionário final.
"""
import io
import logging
import re
import unicodedata

import pdfplumber

# Só números e sim/não no log (quantas caixas, se achou o cabeçalho, quantas linhas):
# nada do aluno (nome, matrícula, notas, disciplinas).
log = logging.getLogger("GradePuc.espelho")


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

    # "Tipo da" é fácil de o OCR errar; a linha de baixo ("disciplina") fica entre Situação e Grupo
    if "tipo" not in centros and "grupo" in centros:
        abaixo = [
            centro_do_trecho(w, "discip") for w in cabecalho
            if "discip" in sem_acento(w["text"]) and centros["situacao"] < centro_do_trecho(w, "discip") < centros["grupo"]
        ]
        if abaixo:
            centros["tipo"] = abaixo[0]
    return centros,max(w["bottom"] for w in cabecalho)


# ---------- Print/scan lido pelo OCR: cabeçalho do curso ----------

# Começo de cada rótulo do quadro do curso, comparado sem acento e sem espaços
# (o OCR cola as palavras: "Anocurriculo", "CRacumulado").
ROTULOS_DO_CURSO = [
    ("curso", "curso"), ("habilitacao", "habilit"), ("enfase", "enfas"),
    ("ano_curriculo", "anocurr"), ("codigo_curriculo", "codigocurr"), ("cr", "cracum"),
]
DECIMAL = re.compile(r"^(\d{1,2})\s*([,.'´`‘’])\s*(\d{1,2})$")
GIRADO_180 = str.maketrans("69", "96")


def compacto(texto):
    return re.sub(r"[^a-z]", "", sem_acento(texto))


def rotulo_do_curso(w):
    texto = compacto(w["text"])
    for chave, inicio in ROTULOS_DO_CURSO:
        if texto.startswith(inicio):
            return chave
    return None


def rotulos_do_curso_ocr(palavras):
    """Rótulos do quadro do curso numa página do OCR: {chave: caixa}.
    O 'Ênfase' (com acento) sai um pouco mais alto que os outros, por isso a tolerância
    vertical é de ~1,2 vez a altura das letras."""
    h = altura_tipica(palavras)
    for ancora in palavras:
        if rotulo_do_curso(ancora) != "curso":
            continue
        rotulos = {}
        for w in palavras:
            chave = rotulo_do_curso(w)
            if chave and chave not in rotulos and abs(centro_y(w) - centro_y(ancora)) <= 1.2 * h:
                rotulos[chave] = w
        if "habilitacao" in rotulos:
            return rotulos
    return {}


def faixa_dos_valores_do_curso(palavras, rotulos):
    """Altura (topo, fim) da linha de valores logo abaixo dos rótulos do curso."""
    h = altura_tipica(palavras)
    base = max(w["bottom"] for w in rotulos.values())
    return base - 0.3 * h, base + 3 * h


def normalizar_decimal(texto):
    """Nota ou CR lidos pelo OCR: '8.9' vira '8,9'. Um apóstrofo no lugar da vírgula ("6'8")
    é sinal de caixa lida de cabeça para baixo (o 8,9 girado): desvira quando só tem dígitos
    que continuam dígitos girados (0, 1, 6, 8, 9). Se não dá para ter certeza, devolve vazio
    em vez de um valor errado."""
    m = DECIMAL.match(texto.strip())
    if not m:
        return ""
    inteiro, separador, fracao = m.groups()
    if separador in ",.":
        return f"{inteiro},{fracao}"
    if set(inteiro + fracao) - set("01689"):
        return ""
    desvirado = (inteiro + fracao)[::-1].translate(GIRADO_180)
    return desvirado[:len(fracao)] + "," + desvirado[len(fracao):]


def ler_cabecalho_ocr(palavras):
    """Curso, habilitação, ênfase, ano e código do currículo e CR numa página do OCR.
    Os valores são reconhecidos pelo padrão (siglas = 3 letras, ano = 4 dígitos,
    código = número curto, CR = decimal); a posição só decide entre as siglas."""
    rotulos = rotulos_do_curso_ocr(palavras)
    if not rotulos:
        return {}
    centros = {c: (w["x0"] + w["x1"]) / 2 for c, w in rotulos.items()}
    topo, fim = faixa_dos_valores_do_curso(palavras, rotulos)
    caixas_dos_rotulos = [id(w) for w in rotulos.values()]

    pedacos = []   # (texto, centro x): "BCO CCB" numa caixa só vira dois pedaços
    for w in palavras:
        if id(w) in caixas_dos_rotulos or not (topo < centro_y(w) < fim):
            continue
        inicio = 0
        for parte in w["text"].split():
            pos = w["text"].find(parte, inicio)
            inicio = pos + len(parte)
            meio = (pos + len(parte) / 2) / len(w["text"])
            pedacos.append((parte, w["x0"] + (w["x1"] - w["x0"]) * meio))

    def mais_perto(x, chaves):
        presentes = [c for c in chaves if c in centros]
        return min(presentes, key=lambda c: abs(centros[c] - x)) if presentes else None

    resultado = {}
    siglas = []
    for texto, x in sorted(pedacos, key=lambda p: p[1]):
        t = sem_acento(texto).upper().strip(".;:")
        if re.fullmatch(r"[A-Z]{3}", t):
            siglas.append((t, x))
        elif re.fullmatch(r"(19|20)\d{2}", t):
            resultado.setdefault("ano_curriculo", t)
        elif DECIMAL.match(t):
            resultado.setdefault("cr", normalizar_decimal(t))
        elif re.fullmatch(r"\d{1,3}", t) and mais_perto(x, ["codigo_curriculo", "cr"]) != "cr":
            resultado.setdefault("codigo_curriculo", t)

    # siglas: cada uma vai para o rótulo mais perto; se duas caírem no mesmo, vale a ordem
    chaves = ["curso", "habilitacao", "enfase"]
    pela_posicao = [mais_perto(x, chaves) for _, x in siglas]
    if None not in pela_posicao and len(set(pela_posicao)) == len(pela_posicao):
        for (t, _), chave in zip(siglas, pela_posicao):
            resultado[chave] = t
    else:
        for (t, _), chave in zip(siglas, chaves):
            resultado[chave] = t
    return resultado


# ---------- Print/scan lido pelo OCR: tabela de disciplinas ----------

# Para reconhecer a coluna Situação num print sem cabeçalho
SITUACOES_CONHECIDAS = SITUACOES_CURSADAS | SITUACOES_EM_ANDAMENTO | {
    "RM", "RF", "NC", "NI", "CA", "CD", "CJ", "CL", "AT", "DT", "LT", "IN", "TR",
}
# Código com uma letra perdida ("FS4001-FISICA I"): só vale com o hífen logo depois
CODIGO_OCR_CURTO = re.compile(r"^(?:(\d{5})\s*)?([A-Z]{2})\s*([0-9OILSB]{4})\s*-\s*(.*)$")


def inicio_de_disciplina(texto):
    """Caixa que abre uma disciplina: 'CTC4001 -', 'CTC4002-MODELAGEM', '20261 CTC4001 - ...'.
    Com uma letra perdida ('FS4001-FISICA') também vale, marcada como incerta."""
    t = sem_acento(texto).upper().strip()
    m = CODIGO_OCR.match(t)
    if m and codigo_valido(m.group(2), m.group(3)):
        incerto = False
    else:
        m = CODIGO_OCR_CURTO.match(t)
        if not m or sum(c.isdigit() for c in m.group(3)) < 2:
            return None
        incerto = True
    return {"periodo": m.group(1) or "", "letras": m.group(2), "numeros": m.group(3),
            "resto": m.group(4), "incerto": incerto}


def texto_limpo(w):
    return sem_acento(w["text"]).upper().strip()


def mediana(valores):
    valores = sorted(valores)
    return valores[len(valores) // 2]


def inferir_colunas_ocr(palavras, largura):
    """Print da tabela sem o cabeçalho (o aluno rolou a página): descobre as colunas pelo
    próprio print, sem usar posições de outro print (cada print é um recorte diferente).
    Caixas alinhadas formam uma coluna, e o conteúdo diz qual é: situação (AP, EA...),
    nota (decimal), tipo (2 letras), grupo (código), créditos/horas/extensão/oportunidades
    (números, nessa ordem). Devolve {coluna: centro x} ou None."""
    h = altura_tipica(palavras)
    codigos = [w for w in palavras if w["x0"] < 0.45 * largura and inicio_de_disciplina(w["text"])]
    if not codigos:
        return None
    x_nome = mediana(w["x0"] for w in codigos)

    def na_coluna_do_nome(w):
        return abs(w["x0"] - x_nome) <= 2 * h

    nomes = [w for w in palavras if na_coluna_do_nome(w)]
    periodos = [w for w in palavras if w["x1"] < x_nome and re.fullmatch(r"\d{5}", w["text"].strip())]
    valores = [
        w for w in palavras
        if w["x0"] > x_nome + 2 * h and not na_coluna_do_nome(w)
        and w["x1"] - w["x0"] <= 0.6 * largura and not w["text"].startswith("*")
    ]

    # caixas com o centro perto umas das outras = mesma coluna
    grupos = []
    for w in sorted(valores, key=lambda w: (w["x0"] + w["x1"]) / 2):
        meio = (w["x0"] + w["x1"]) / 2
        if grupos and meio - grupos[-1]["ultimo"] <= 1.5 * h:
            grupos[-1]["caixas"].append(w)
        else:
            grupos.append({"caixas": [w]})
        grupos[-1]["ultimo"] = meio
    for g in grupos:
        g["centro"] = mediana((w["x0"] + w["x1"]) / 2 for w in g["caixas"])
        g["textos"] = [texto_limpo(w) for w in g["caixas"]]

    def parte(g, teste):
        return sum(1 for t in g["textos"] if teste(t)) / len(g["textos"])

    def eh_situacao(t):
        return t in SITUACOES_CONHECIDAS

    def eh_duas_letras(t):
        return bool(re.fullmatch(r"[A-Z]{2}", t.translate(LETRAS_TROCADAS)))

    def eh_codigo(t):
        return bool(CODIGO_OCR_SOLTO.fullmatch(t.replace(" ", "")))

    situacao = max(grupos, key=lambda g: parte(g, eh_situacao), default=None)
    if situacao is None or parte(situacao, eh_situacao) < 0.5:
        return None

    centros = {
        "periodo": mediana(w["x0"] + w["x1"] for w in periodos) / 2 if periodos else x_nome - 3 * h,
        "disciplina": mediana((w["x0"] + w["x1"]) / 2 for w in nomes),
        "situacao": situacao["centro"],
    }
    antes = [g for g in grupos if g["centro"] < situacao["centro"]]
    depois = [g for g in grupos if g["centro"] > situacao["centro"]]

    graus = [g for g in antes if parte(g, lambda t: bool(DECIMAL.match(t))) >= 0.5]
    if graus:
        centros["grau"] = graus[-1]["centro"]
    turmas = [g for g in antes if g not in graus]
    if turmas:
        centros["turma"] = turmas[0]["centro"]

    numeros = []
    for g in depois:
        if "tipo" not in centros and not numeros and parte(g, eh_duas_letras) >= 0.5:
            centros["tipo"] = g["centro"]
        elif "grupo" not in centros and parte(g, eh_codigo) >= 0.5:
            centros["grupo"] = g["centro"]
        elif parte(g, str.isdigit) >= 0.5:
            numeros.append(g)

    # créditos (1 a 12), horas (15 x créditos), horas de extensão, nº de oportunidades
    def valor_tipico(g):
        return mediana(int(t) for t in g["textos"] if t.isdigit())

    sobra = list(numeros)
    if sobra and valor_tipico(sobra[0]) < 15:
        centros["creditos"] = sobra.pop(0)["centro"]
    if sobra:
        centros["horas"] = sobra.pop(0)["centro"]
    if len(sobra) >= 2:
        centros["extensao"], centros["oportunidades"] = sobra[0]["centro"], sobra[1]["centro"]
    elif sobra:
        so_multiplos_de_15 = all(int(t) % 15 == 0 for t in sobra[0]["textos"] if t.isdigit())
        centros["extensao" if so_multiplos_de_15 else "oportunidades"] = sobra[0]["centro"]
    return centros


def creditos_conferidos(texto_creditos, texto_horas):
    """Créditos da linha, conferidos com as horas (horas = 15 x créditos).
    O OCR às vezes perde o dígito dos créditos ou um zero das horas."""
    achou = re.search(r"\d+", texto_creditos)
    creditos = int(achou.group(0)) if achou else None
    achou = re.search(r"\d+", texto_horas)
    horas = int(achou.group(0)) if achou else None
    valido = creditos is not None and 1 <= creditos <= 12
    if valido and (horas is None or horas == 15 * creditos):
        return creditos
    if horas and horas % 15 == 0 and 1 <= horas // 15 <= 12:
        return horas // 15
    if valido:
        return creditos
    return creditos or 0


def ler_tabela_ocr(palavras, largura=None):
    """Lê as disciplinas de uma página do OCR. Devolve (disciplinas, códigos lidos,
    situações lidas), ou None se a página não tiver a tabela.
    Com o cabeçalho da tabela no print, as colunas vêm da posição dos rótulos;
    sem ele (o aluno rolou a página), são descobertas pelo próprio print."""
    h = altura_tipica(palavras)
    largura = largura or max((w["x1"] for w in palavras), default=0)
    achou = achar_colunas_ocr(palavras)
    if achou:
        centros, fim_cabecalho = achou
    else:
        centros = inferir_colunas_ocr(palavras, largura)
        if centros is None:
            return None
        fim_cabecalho = float("-inf")

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

    na_esquerda = [w for w in tabela if coluna_de(w) in ("periodo", "disciplina")]
    inicios = []
    for w in na_esquerda:
        inicio = inicio_de_disciplina(w["text"])
        if inicio:
            inicios.append((w, inicio))
    inicios.sort(key=lambda par: par[0]["top"])

    situacoes = [
        w for w in tabela
        if coluna_de(w) == "situacao" and len(re.sub(r"[^A-Z]", "", sem_acento(w["text"]).upper())) == 2
    ]

    # Duas situações no mesmo bloco = duas disciplinas: o OCR não reconheceu o código da
    # segunda. Procura um código na caixa da esquerda que está na altura da segunda situação.
    def fim_do_bloco(lista, i):
        return lista[i + 1][0]["top"] - h / 2 if i + 1 < len(lista) else fim_tabela

    extras = []
    for i, (inicio, _) in enumerate(inicios):
        no_bloco = sorted(
            [w for w in situacoes if inicio["top"] - h / 2 <= centro_y(w) < fim_do_bloco(inicios, i)],
            key=centro_y,
        )
        for anterior, seguinte in zip(no_bloco, no_bloco[1:]):
            if centro_y(seguinte) - centro_y(anterior) <= h:
                continue
            perto = [w for w in na_esquerda if abs(centro_y(w) - centro_y(seguinte)) <= 1.5 * h]
            for w in sorted(perto, key=lambda w: abs(centro_y(w) - centro_y(seguinte))):
                m = CODIGO_OCR_SOLTO.search(texto_limpo(w))
                if m and w is not inicio:
                    extras.append((w, {"periodo": "", "letras": m.group(1), "numeros": m.group(2),
                                       "resto": texto_limpo(w)[m.end():], "incerto": True}))
                    break
    inicios = sorted(inicios + extras, key=lambda par: par[0]["top"])

    disciplinas = []
    for i, (inicio, cod) in enumerate(inicios):
        y0 = inicio["top"] - h / 2
        y1 = fim_do_bloco(inicios, i)
        bloco = [w for w in tabela if w is not inicio and y0 <= centro_y(w) < y1]

        def coluna(nome):
            caixas = sorted([w for w in bloco if coluna_de(w) == nome], key=lambda w: (w["top"], w["x0"]))
            return " ".join(texto_limpo(w) for w in caixas)

        periodo = cod["periodo"]
        if not periodo:
            achou = re.search(r"\d{5}", coluna("periodo"))
            periodo = achou.group(0) if achou else ""

        nome = (cod["resto"] + " " + coluna("disciplina")).strip(" -")
        grupo = CODIGO_OCR_SOLTO.search(coluna("grupo")) if "grupo" in centros else None
        # só a primeira situação do bloco (nunca "EAEA")
        situacao = re.findall(r"[A-Z]{2}", re.sub(r"[^A-Z ]", "", coluna("situacao")))

        disciplina = {
            "periodo": periodo,
            "codigo": corrigir_codigo(cod["letras"], cod["numeros"]),
            # o OCR troca a letra O pelo zero no meio das palavras (M0DELAGEM)
            "nome": re.sub(r"(?<=[A-Z])0|0(?=[A-Z])", "O", re.sub(r"\s+", " ", nome)),
            "turma": coluna("turma"),
            "grau": normalizar_decimal(coluna("grau")),
            "situacao": situacao[0] if situacao else "",
            "tipo": re.sub(r"[^A-Z]", "", coluna("tipo").translate(LETRAS_TROCADAS)) if "tipo" in centros else "",
            "grupo": corrigir_codigo(grupo.group(1), grupo.group(2)) if grupo else "",
            "creditos": creditos_conferidos(coluna("creditos"), coluna("horas")),
        }
        if cod["incerto"]:
            disciplina["confira"] = True
        disciplinas.append(disciplina)

    # situações acima do primeiro código: linha cortada no topo do print (o código ficou fora)
    topo = inicios[0][0]["top"] - h / 2 if inicios else float("inf")
    cortadas_no_topo = sum(1 for w in situacoes if centro_y(w) < topo)
    return disciplinas, len(inicios), len(situacoes), cortadas_no_topo


def pagina_com_cabecalho_ocr(pagina):
    """Print que mostra o quadro do curso ou o cabeçalho da tabela."""
    palavras = pagina["palavras"]
    return bool(rotulos_do_curso_ocr(palavras) or achar_colunas_ocr(palavras))


def interpretar_paginas(paginas):
    texto = "\n".join(p["texto"] for p in paginas)
    if not any(p["palavras"] for p in paginas):
        raise EspelhoSemTexto(
            "Este PDF não tem texto selecionável (parece escaneado ou foto). "
            "Envie o PDF original baixado do SAU."
        )
    # um print recortado pode não mostrar o título; aí vale ter o cabeçalho do curso ou da
    # tabela, ou uma tabela de disciplinas reconhecível
    tem_espelho_ocr = any(
        p.get("ocr") and p["palavras"] and (
            pagina_com_cabecalho_ocr(p) or inferir_colunas_ocr(p["palavras"], p.get("largura") or 1)
        )
        for p in paginas
    )
    if not parece_espelho(texto) and not tem_espelho_ocr:
        raise EspelhoInvalido("Este PDF não parece ser o Espelho do Histórico do SAU.")

    # Prints podem chegar em qualquer ordem (o seletor de arquivos nem sempre respeita a
    # ordem dos cliques): o print com cabeçalho vem primeiro; entre os outros, vale a ordem enviada.
    paginas = sorted(paginas, key=lambda p: 0 if not p.get("ocr") or pagina_com_cabecalho_ocr(p) else 1)

    m = MATRICULA.search(texto)
    dados = {
        "matricula": m.group(1) if m else "",
        "curso": "", "habilitacao": "", "enfase": "",
        "ano_curriculo": "", "codigo_curriculo": "", "cr": "",
        "disciplinas": [],
    }

    achou_tabela = False
    contagem_ocr = {"codigos": 0, "situacoes": 0}
    por_pagina = []             # (arquivo, linhas da página, situações cortadas no topo)
    for n, pagina in enumerate(paginas):
        palavras = pagina["palavras"]
        por_ocr = pagina.get("ocr", False)
        if n == 0 or not dados["curso"]:
            if por_ocr:
                dados.update(ler_cabecalho_ocr(palavras))
            else:
                dados.update(ler_cabecalho_do_curso(palavras))

        cortadas = 0
        if por_ocr:
            resultado = ler_tabela_ocr(palavras, pagina.get("largura")) if palavras else None
            linhas = None
            if resultado is not None:
                linhas, codigos, situacoes, cortadas = resultado
                contagem_ocr["codigos"] += codigos
                contagem_ocr["situacoes"] += situacoes
            log.info(
                "espelho por OCR, arquivo %s: %d caixas de texto, cabeçalho da tabela: %s, quadro do curso: %s, "
                "tabela reconhecida: %s, %d linha(s)",
                pagina.get("arquivo", 0), len(palavras), bool(achar_colunas_ocr(palavras)),
                bool(rotulos_do_curso_ocr(palavras)), linhas is not None, len(linhas or []),
            )
        else:
            linhas = ler_tabela(palavras, pagina.get("altura", 10000))
        if linhas is not None:
            achou_tabela = True
            por_pagina.append((pagina.get("arquivo", 0), linhas, cortadas))

    if not achou_tabela:
        raise EspelhoInvalido("Não encontramos a tabela de disciplinas neste espelho.")

    dados["disciplinas"], cortadas_cobertas = juntar_paginas(por_pagina)
    if any(p.get("ocr") for p in paginas):
        # linha cortada no topo de um print que repete o anterior não é disciplina perdida
        contagem_ocr["situacoes"] -= cortadas_cobertas
        dados["ocr"] = contagem_ocr
    return dados


def semestre_anterior(periodo):
    """'20262' -> '20261'; '20261' -> '20252'."""
    ano, semestre = int(periodo[:4]), periodo[4]
    return f"{ano}1" if semestre == "2" else f"{ano - 1}2"


def em_andamento(situacao):
    return situacao in SITUACOES_EM_ANDAMENTO


def mesma_disciplina(a, b):
    """Mesmo código e mesma situação (ou uma das situações não foi lida)."""
    return a["codigo"] == b["codigo"] and (a["situacao"] == b["situacao"] or not a["situacao"] or not b["situacao"])


def juntar_paginas(por_pagina):
    """Junta as linhas das páginas/prints, resolvendo o período e as repetidas.

    No SAU o período só aparece na primeira disciplina do semestre; as seguintes herdam.
    Um print que começa no meio do semestre tem linhas sem período no começo:
    - se vierem do mesmo arquivo (página seguinte do mesmo PDF), herdam o último período;
    - se vierem de outro print e a mesma disciplina (código e situação) já apareceu,
      é a sobreposição entre prints: pegam aquele período e não entram de novo;
    - senão, pegam o último período lido, só se a situação combina (uma disciplina
      concluída não herda um período em andamento, e vice-versa);
    - senão, o semestre anterior ao primeiro período que aparece no print (marcado para conferir).
    Prints que se sobrepõem repetem disciplinas: entre arquivos diferentes, a mesma
    disciplina conta uma vez (dentro de um arquivo nada é descartado: dá para repetir uma
    disciplina em outro semestre).

    Devolve (disciplinas, situações cortadas no topo de prints que repetem o anterior)."""
    juntas = []                 # (disciplina, arquivo, período veio do próprio print)
    cortadas_cobertas = 0
    for arquivo, linhas, cortadas in por_pagina:
        atual = ""
        primeiro = next((d["periodo"] for d in linhas if d["periodo"]), "")
        sobreposicao = False
        for d in linhas:
            proprio = True
            if d["periodo"]:
                atual = d["periodo"]
            elif atual:
                d["periodo"] = atual
            else:
                proprio = False
                d["periodo"] = periodo_do_comeco_do_print(d, arquivo, juntas, primeiro)
                if any(a != arquivo and mesma_disciplina(x, d) for x, a, _ in juntas):
                    sobreposicao = True

            repetida = any(
                a != arquivo and mesma_disciplina(x, d) and (x["periodo"] == d["periodo"] or not proprio)
                for x, a, _ in juntas
            )
            if not repetida:
                juntas.append((d, arquivo, proprio))
        if sobreposicao:
            cortadas_cobertas += cortadas
    return [d for d, _, _ in juntas], cortadas_cobertas


def periodo_do_comeco_do_print(d, arquivo, juntas, primeiro_do_print):
    if juntas and juntas[-1][1] == arquivo:                      # página seguinte do mesmo PDF,
        if juntas[-1][0].get("confira_periodo"):                 # ou a linha de cima no mesmo print
            d["confira_periodo"] = True
        return juntas[-1][0]["periodo"]
    igual = next((x for x, a, _ in juntas if a != arquivo and mesma_disciplina(x, d)), None)
    if igual is not None:
        return igual["periodo"]                                  # sobreposição com o print anterior
    if juntas:
        ultimo = juntas[-1][0]["periodo"]
        andamento_do_ultimo = any(em_andamento(x["situacao"]) for x, _, _ in juntas if x["periodo"] == ultimo)
        if not d["situacao"] or em_andamento(d["situacao"]) == andamento_do_ultimo:
            return ultimo
    d["confira_periodo"] = True
    if primeiro_do_print:
        return semestre_anterior(primeiro_do_print)
    return juntas[-1][0]["periodo"] if juntas else ""


def ler_espelho(arquivo):
    return interpretar_paginas(extrair_palavras(arquivo))
