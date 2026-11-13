"""Ementa de uma disciplina lida na página oficial da PUC, para a tela /eletivas/<código>/
e para o painel "Detalhes" do fluxograma de pré-requisitos.

O endereço é fixo; o usuário só escolhe o código, que é validado antes. A página quase
nunca muda, então o que vem dela fica 12 horas no cache do Django (erro de rede não).
Os pré/co-requisitos vêm da tabela Requisito, que é lida a cada vez (não entram no cache).
"""
import re
from html.parser import HTMLParser
from http.client import HTTPException
from urllib.request import Request, urlopen

from django.core.cache import cache

from .models import Requisito

CODIGO_VALIDO = re.compile(r"^[A-Z]{3}\d{4}$")
URL_DA_EMENTA = "https://www.puc-rio.br/ferramentas/ementas/ementa.aspx?cd={codigo}"
TEMPO_LIMITE = 10                   # segundos
TEMPO_NO_CACHE = 12 * 60 * 60       # 12 horas

ERRO_CODIGO_INVALIDO = "Código de disciplina inválido."
ERRO_DE_REDE = "Não foi possível acessar a página de ementas da PUC."
ERRO_NAO_ENCONTRADA = "Não encontramos a ementa dessa disciplina na PUC."

SEM_EMENTA_NO_SAU = "Disciplina sem ementa cadastrada"
# rótulo que a página repete no começo de cada campo
ROTULOS_DA_EMENTA = {
    "bibliografia": "Bibliografia",
    "bibliografia_complementar": "Bibliografia Complementar",
    "pre_requisitos": "Pré-requisitos",
    "co_requisitos": "Co-requisitos",
    "atualizacao": "Última atualização da ementa:",
}
CAMPOS_DA_PAGINA = ("codigo", "nome", "creditos", "ementa", "bibliografia", "bibliografia_complementar",
                    "pre_requisitos", "co_requisitos", "atualizacao")


class ExtratorEmenta(HTMLParser):

    def __init__(self):
        super().__init__()
        self.dados = {}
        self.campos = {
            "hCodigo": "codigo",
            "hTitulo": "nome",
            "hCreditos": "creditos",
            "pEmenta": "ementa",
            "bibliografia": "bibliografia",
            "bibliografiaComplementar": "bibliografia_complementar",
            "prerequisito": "pre_requisitos",
            "corequisito": "co_requisitos",
            "pUltimaAtualizacao": "atualizacao",
        }
        self.campo_atual = None
        self.tag_atual = None
        self.profundidade = 0
        self.texto_atual = []

    def handle_starttag(self, tag, attrs):
        atributos = dict(attrs)
        identificador = atributos.get("id", "")

        if self.campo_atual is None and identificador in self.campos:
            self.campo_atual = self.campos[identificador]
            self.tag_atual = tag
            self.profundidade = 1

        elif self.campo_atual is not None:
            self.profundidade += 1

    def handle_data(self, dado):
        if self.campo_atual and dado.strip():
            self.texto_atual.append(dado.strip())

    def handle_endtag(self, tag):
        if self.campo_atual is None:
            return

        self.profundidade -= 1

        if self.profundidade == 0:
            self.dados[self.campo_atual] = " ".join(self.texto_atual)
            self.campo_atual = None
            self.tag_atual = None
            self.texto_atual = []


def requisitos_em_texto(codigo, tipo):
    """"MAT1158 e MATEMÁTICA (nivel 3) ou MAT1181", da tabela Requisito; None se não há linha."""
    alternativas = {}
    for numero, exigido, observacao in Requisito.objects.filter(disciplina=codigo, tipo=tipo).order_by(
            "alternativa", "id").values_list("alternativa", "codigo", "observacao"):
        partes = alternativas.setdefault(numero, [])
        for parte in (exigido, observacao):
            if parte and parte not in partes:
                partes.append(parte)
    if not alternativas:
        return None
    return " ou ".join(" e ".join(partes) for partes in alternativas.values() if partes)


def arrumar_dados_da_ementa(dados, codigo):
    """Tira o rótulo repetido dos campos e põe os requisitos da tabela Requisito."""
    for campo, rotulo in ROTULOS_DA_EMENTA.items():
        texto = " ".join(dados.get(campo, "").split())
        if texto.startswith(rotulo):
            texto = texto[len(rotulo):].strip()
        dados[campo] = texto
    tem_requisito = Requisito.objects.filter(disciplina=codigo).exists()
    for campo, tipo, nenhum in (("pre_requisitos", "pre", "Nenhum pré-requisito"),
                                ("co_requisitos", "co", "Nenhum co-requisito")):
        da_tabela = requisitos_em_texto(codigo, tipo)
        if da_tabela:
            dados[campo] = da_tabela
        elif tem_requisito or dados[campo].lower().startswith(("nenhum pre", "nenhum pré", "nenhum co")):
            # "Nenhum pre-requisito encontrado para INF1007" -> "Nenhum pré-requisito"
            dados[campo] = nenhum
    dados["sem_informacao_de_requisitos"] = not dados["pre_requisitos"] and not dados["co_requisitos"]
    return dados


def ler_pagina_da_puc(codigo):
    """Os campos da página da PUC (sem requisitos da tabela). Levanta OSError/HTTPException
    se a rede falhar."""
    requisicao = Request(URL_DA_EMENTA.format(codigo=codigo), headers={"User-Agent": "Mozilla/5.0"})
    html = urlopen(requisicao, timeout=TEMPO_LIMITE).read().decode("cp1252", errors="replace")
    extrator = ExtratorEmenta()
    extrator.feed(html)
    dados = {campo: extrator.dados.get(campo, "") for campo in CAMPOS_DA_PAGINA}
    # Página sem ementa ("Disciplina sem ementa cadastrada."): mantém título, código e créditos
    dados["sem_ementa"] = SEM_EMENTA_NO_SAU in html
    dados["erro"] = "" if dados["codigo"] else ERRO_NAO_ENCONTRADA
    return dados


def buscar_ementa(codigo):
    """{codigo, nome, creditos, ementa, bibliografia, bibliografia_complementar, atualizacao,
    pre_requisitos, co_requisitos, sem_ementa, sem_informacao_de_requisitos, erro, erro_de_rede}.
    `erro` vazio quando deu certo."""
    codigo = (codigo or "").strip().upper()
    if not CODIGO_VALIDO.match(codigo):
        return {"codigo": codigo, "erro": ERRO_CODIGO_INVALIDO, "erro_de_rede": False}

    chave = f"ementa_online:{codigo}"
    dados = cache.get(chave)
    if dados is None:
        try:
            dados = ler_pagina_da_puc(codigo)
        except (OSError, HTTPException):     # URLError, HTTPError e timeout são OSError
            return {"codigo": codigo, "erro": ERRO_DE_REDE, "erro_de_rede": True}
        cache.set(chave, dados, TEMPO_NO_CACHE)

    dados = dict(dados, erro_de_rede=False)
    if not dados["erro"]:
        arrumar_dados_da_ementa(dados, codigo)
    return dados
