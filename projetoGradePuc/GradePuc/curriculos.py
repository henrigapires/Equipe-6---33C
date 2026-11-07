"""Leitura das páginas de curso da PUC (periodização dos currículos).

Só interpreta HTML; baixar as páginas e gravar no banco fica no command
importar_curriculos. Assim dá para testar com um HTML pequeno.
"""
import re

from bs4 import BeautifulSoup

CODIGO = re.compile(r"^([A-Z]{3}\d{4})")
ANO = re.compile(r"(19|20)\d{2}")
# "(Currículo 2023)", "(currículo 0 - anterior a 2023)", "– currículo 2021", "(Currículo2021)"
TRECHO_CURRICULO = re.compile(r"\(?\s*curr[ií]culo\s*([^)]*)\)?", re.IGNORECASE)
TRECHO_ENTRADA = re.compile(r"\(\s*entrada de alunos[^)]*\)", re.IGNORECASE)
# títulos sem a palavra "currículo": "Bacharelado em Filosofia - 2023", "(anterior a 2023)"
TRECHO_ANTERIOR = re.compile(r"\(?\s*anterior a\s*(?:19|20)\d{2}\s*\)?", re.IGNORECASE)
TRECHO_ANO_NO_FIM = re.compile(r"\s*[-–(]\s*(?:19|20)\d{2}\s*\)?\s*$")
VARIANTE = re.compile(r"^\s*(\d)\s*[-–]")
ENFASE = re.compile(r"\s*[-–]?\s*(?:com\s+)?[ÊE]nfase(?:\s+em)?\s+(.*)$", re.IGNORECASE)


def decodificar_html(conteudo):
    """As páginas dizem ser UTF-8; se não forem, cai para Windows-1252."""
    try:
        return conteudo.decode("utf-8")
    except UnicodeDecodeError:
        return conteudo.decode("cp1252", errors="replace")


def limpar(texto):
    return re.sub(r"\s+", " ", texto.replace("\xa0", " ")).strip()


def interpretar_titulo(titulo):
    """'Periodização - Engenharia de Produção (Currículo 2023) - Ênfase em Sistemas Produtivos (SPR)'
    -> curso_nome, ano, enfase, anterior_a (ano citado em 'anterior a AAAA', ou None)."""
    texto = re.sub(r"^Periodiza[çc][ãa]o\s*[-–:]?\s*", "", limpar(titulo), flags=re.IGNORECASE)

    ano = None
    anterior_a = None
    variante = ""
    m = (TRECHO_CURRICULO.search(texto) or TRECHO_ENTRADA.search(texto)
         or TRECHO_ANTERIOR.search(texto) or TRECHO_ANO_NO_FIM.search(texto))
    if m:
        dentro = m.group(0)
        anos = [int(a.group(0)) for a in ANO.finditer(dentro)]
        if re.search(r"anterior", dentro, re.IGNORECASE):
            anterior_a = anos[0] if anos else None
        elif re.search(r"entrada de alunos", dentro, re.IGNORECASE):
            pass
        elif anos:
            ano = anos[0]
        if m.re is TRECHO_CURRICULO:
            v = VARIANTE.match(m.group(1))
            if v:
                variante = "Currículo " + v.group(1)
        antes, depois = texto[:m.start()], texto[m.end():]
    else:
        antes, depois = texto, ""

    curso = antes.strip(" -–")
    enfase = ""
    e = ENFASE.search(curso)
    if e:
        enfase = e.group(1).strip(" -–")
        curso = curso[:e.start()].strip(" -–")
    e = ENFASE.search(depois)
    if e:
        enfase = e.group(1).strip(" -–")

    if variante:
        enfase = (enfase + " - " + variante) if enfase else variante
    return {"curso_nome": curso, "ano": ano, "enfase": enfase, "anterior_a": anterior_a}


def numero_do_periodo(texto):
    """'1º PERÍODO' -> 1, 'PERÍODO LETIVO INDETERMINADO' -> None. Devolve False se não for linha de período."""
    maiusculo = limpar(texto).upper()
    if "PER" not in maiusculo and "CICLO" not in maiusculo:
        return False
    if "INDETERMINADO" in maiusculo:
        return None
    m = re.search(r"\d+", maiusculo)
    return int(m.group(0)) if m else False


def ler_tabela(tabela):
    itens = []
    periodo = None
    for tr in tabela.find_all("tr"):
        celulas = [limpar(td.get_text(" ")) for td in tr.find_all(["td", "th"])]
        if not celulas or not any(celulas):
            continue
        primeira = celulas[0]

        if primeira.lower().startswith("total de cr"):
            break  # depois do total vêm só observações

        codigo = CODIGO.match(primeira)
        if codigo and len(celulas) >= 2:
            numero = re.match(r"\d+", celulas[2]) if len(celulas) > 2 else None
            itens.append({
                "periodo": periodo,
                "codigo": codigo.group(1),
                "nome": celulas[1],
                "creditos": int(numero.group(0)) if numero else 0,
                "ch_extensao": celulas[3] if len(celulas) > 3 else "",
                "eh_grupo": codigo.group(1)[3] == "0",  # ex. ENG0561, ELL0900: grupo de optativas
                "ordem": len(itens),
            })
            continue

        if len(celulas) == 1 or tr.find(attrs={"colspan": True}):
            novo = numero_do_periodo(primeira)
            if novo is not False:
                periodo = novo
    return itens


def interpretar_pagina_curso(html, url):
    """Devolve (secoes, avisos). Cada seção é um currículo encontrado na página,
    ainda sem escolher o mais recente."""
    sopa = BeautifulSoup(html, "html.parser")
    secoes = []
    avisos = []
    titulos_usados = set()

    for tabela in sopa.find_all("table", class_="ccg_tabela_periodizacao"):
        titulo_tag = tabela.find_previous(["h2", "h3", "h4", "h5"])
        titulo = limpar(titulo_tag.get_text(" ")) if titulo_tag else ""
        if not re.match(r"Periodiza[çc][ãa]o", titulo, re.IGNORECASE):
            continue
        if id(titulo_tag) in titulos_usados:
            avisos.append(f"{url}: mais de uma tabela para '{titulo}' (usada só a primeira)")
            continue
        titulos_usados.add(id(titulo_tag))

        itens = ler_tabela(tabela)
        if not itens:
            avisos.append(f"{url}: tabela sem disciplinas em '{titulo}'")
            continue
        secao = interpretar_titulo(titulo)
        secao.update({"titulo": titulo, "url": url, "itens": itens})
        secoes.append(secao)
    return secoes, avisos


def curso_base(nome):
    """'Bacharelado em Direito - diurno Contencioso' -> 'Bacharelado em Direito'."""
    return re.split(r"\s+[-–]\s+", nome)[0].strip().lower()


def escolher_mais_recentes(secoes):
    """Fica só com o currículo mais recente de cada curso da página (todas as ênfases
    desse ano). Se o curso não tem nenhum currículo com ano, fica com o primeiro listado.
    Um currículo 'anterior a AAAA' sai se a página tem algum currículo de AAAA ou depois."""
    anos_da_pagina = [s["ano"] for s in secoes if s["ano"]]
    secoes = [
        s for s in secoes
        if not (s["anterior_a"] and any(ano >= s["anterior_a"] for ano in anos_da_pagina))
    ]

    por_curso = {}
    for secao in secoes:
        por_curso.setdefault((secao["url"], curso_base(secao["curso_nome"])), []).append(secao)

    escolhidas = []
    for grupo in por_curso.values():
        anos = [s["ano"] for s in grupo if s["ano"]]
        if anos:
            escolhidas += [s for s in grupo if s["ano"] == max(anos)]
        else:
            escolhidas.append(grupo[0])
    return escolhidas


def links_de_subpaginas(html):
    """Links .html da área principal da página (ex.: Comunicação -> Cinema, Jornalismo...)."""
    sopa = BeautifulSoup(html, "html.parser")
    area = sopa.find(class_=re.compile("puc_layout_area-inicial_esquerda")) or sopa
    links = []
    for a in area.find_all("a"):
        href = (a.get("href") or "").strip()
        if href.endswith(".html") and "/" not in href and ":" not in href and href not in links:
            links.append(href)
    return links
