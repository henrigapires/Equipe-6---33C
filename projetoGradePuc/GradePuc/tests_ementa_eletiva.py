"""Página /eletivas/<código>/ (ementa lida do site da PUC), com o urlopen simulado.

Códigos e textos inventados (TST...), no formato das páginas de ementa da PUC.
"""
from unittest.mock import patch
from urllib.error import URLError

from django.test import TestCase

from .models import Requisito
from .tests_espelho import criar_aluno

CABECALHO = """<html><body><form><div id="global"><div id="cod_ttl_discp"><span id="hCodigo">{codigo}</span> |
<span id="hTitulo">{titulo}</span></div><div id="hCreditos">{creditos} créditos</div></div>"""

PAGINA_SEM_EMENTA = CABECALHO + """<div id="conteudo"><div id="divContent">
<span class="erro">Disciplina sem ementa cadastrada.</span></div></div></form></body></html>"""

PAGINA_COMPLETA = CABECALHO + """<div id="conteudo">
<p id="pEmenta">Limites, derivadas e integrais de teste.</p>
<div id="bibliografia"><h4>Bibliografia</h4><p>AUTOR, A. Livro de Teste;
                       Editora Teste, 2020.</p></div>
<div id="bibliografiaComplementar"><h4>Bibliografia Complementar</h4><p>OUTRO, B. Apostila.</p></div>
<div id="prerequisito"><h4>Pré-requisitos</h4><p>{pre}</p></div>
<div id="corequisito"><h4>Co-requisitos</h4><p>{co}</p></div>
<p id="pUltimaAtualizacao">Última atualização da ementa: 01/02/2024</p>
</div></form></body></html>"""


class RespostaFalsa:
    def __init__(self, html):
        self.html = html

    def read(self):
        return self.html.encode("cp1252")


class PaginaDaEmentaTests(TestCase):
    def setUp(self):
        self.client.force_login(criar_aluno("9700001").usuario)

    def abrir(self, codigo, html=None, erro=None):
        with patch("GradePuc.views.urlopen") as urlopen:
            if erro:
                urlopen.side_effect = erro
            else:
                urlopen.return_value = RespostaFalsa(html)
            resposta = self.client.get(f"/eletivas/{codigo}/")
        self.assertEqual(resposta.status_code, 200)
        return resposta.content.decode()

    def test_sem_ementa_mostra_o_aviso_e_mantem_titulo_codigo_e_creditos(self):
        html = self.abrir("TST9418", PAGINA_SEM_EMENTA.format(codigo="TST9418", titulo="ELETRONICA DE TESTE", creditos=2))
        self.assertIn('<div class="aviso">', html)
        self.assertIn("Sem ementa disponibilizada no SAU.", html)
        self.assertIn("ELETRONICA DE TESTE", html)
        self.assertIn("TST9418", html)
        self.assertIn("2 créditos", html)
        # seções vazias não aparecem
        for titulo in ("<h3>Ementa</h3>", "<h3>Bibliografia</h3>", "<h3>Bibliografia complementar</h3>",
                       "<h3>Última atualização</h3>"):
            self.assertNotIn(titulo, html)
        self.assertIn("Sem informação de requisitos.", html)

    def test_sem_ementa_mas_com_requisito_na_tabela(self):
        Requisito.objects.create(disciplina="TST9418", tipo="pre", alternativa=0, codigo="TST1001")
        html = self.abrir("TST9418", PAGINA_SEM_EMENTA.format(codigo="TST9418", titulo="ELETRONICA DE TESTE", creditos=2))
        self.assertIn("Sem ementa disponibilizada no SAU.", html)
        self.assertIn("<p>TST1001</p>", html)
        self.assertIn("<p>Nenhum co-requisito</p>", html)
        self.assertNotIn("Sem informação de requisitos.", html)

    def test_pagina_completa_com_requisitos_da_tabela(self):
        Requisito.objects.create(disciplina="TST9162", tipo="pre", alternativa=0, codigo="TST1158",
                                 observacao="MATEMÁTICA (nivel 3)")
        Requisito.objects.create(disciplina="TST9162", tipo="pre", alternativa=1, codigo="TST1161")
        pagina = PAGINA_COMPLETA.format(
            codigo="TST9162", titulo="CALCULO DE TESTE", creditos=4,
            pre="TST1158 e MATEMÁTICA (nivel 3) ou TST1161",
            co="Nenhum co-requisito encontrado para TST9162")
        html = self.abrir("TST9162", pagina)
        self.assertNotIn("Sem ementa disponibilizada no SAU.", html)
        self.assertIn("Limites, derivadas e integrais de teste.", html)
        self.assertIn("<p>AUTOR, A. Livro de Teste; Editora Teste, 2020.</p>", html)    # sem o rótulo repetido
        self.assertIn("<p>OUTRO, B. Apostila.</p>", html)
        self.assertIn("<p>TST1158 e MATEMÁTICA (nivel 3) ou TST1161</p>", html)
        self.assertIn("<p>Nenhum co-requisito</p>", html)
        self.assertNotIn("encontrado para", html)
        self.assertIn("<p>01/02/2024</p>", html)

    def test_sem_requisito_na_tabela_arruma_o_texto_da_pagina(self):
        pagina = PAGINA_COMPLETA.format(
            codigo="TST9100", titulo="INTRODUCAO DE TESTE", creditos=4,
            pre="Nenhum pre-requisito encontrado para TST9100",
            co="Nenhum co-requisito encontrado para TST9100")
        html = self.abrir("TST9100", pagina)
        self.assertIn("<p>Nenhum pré-requisito</p>", html)
        self.assertIn("<p>Nenhum co-requisito</p>", html)
        self.assertNotIn("encontrado para", html)

    def test_erro_de_rede_mantem_a_mensagem(self):
        html = self.abrir("TST9162", erro=URLError("sem rede"))
        self.assertIn("Não foi possível acessar a página de ementas da PUC.", html)
