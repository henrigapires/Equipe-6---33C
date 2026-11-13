"""buscar_ementa (ementa_online.py), o cache, o endpoint /api/ementas/<código>/ e o painel.

O urlopen é sempre simulado: nenhum teste acessa a internet. Códigos inventados (TST...).
"""
from unittest.mock import patch
from urllib.error import HTTPError, URLError

from django.core.cache import cache
from django.test import TestCase

from .ementa_online import (
    ERRO_CODIGO_INVALIDO, ERRO_DE_REDE, ERRO_NAO_ENCONTRADA, TEMPO_LIMITE, buscar_ementa,
)
from .models import Requisito
from .tests_ementa_eletiva import PAGINA_COMPLETA, PAGINA_SEM_EMENTA, RespostaFalsa
from .tests_espelho import criar_aluno

PAGINA_INEXISTENTE = "<html><body><form><div id='global'></div><p>Página não encontrada</p></form></body></html>"


def pagina_completa(codigo="TST9162", ementa="Limites, derivadas e integrais de teste."):
    return PAGINA_COMPLETA.format(codigo=codigo, titulo="CALCULO DE TESTE", creditos=4,
                                  pre="Nenhum pre-requisito encontrado para " + codigo,
                                  co="Nenhum co-requisito encontrado para " + codigo).replace(
        "Limites, derivadas e integrais de teste.", ementa)


class BuscarEmentaTests(TestCase):
    def setUp(self):
        cache.clear()

    def buscar(self, codigo, html=None, erro=None):
        with patch("GradePuc.ementa_online.urlopen") as urlopen:
            if erro:
                urlopen.side_effect = erro
            else:
                urlopen.return_value = RespostaFalsa(html)
            return buscar_ementa(codigo), urlopen

    def test_ementa_completa(self):
        Requisito.objects.create(disciplina="TST9162", tipo="pre", alternativa=0, codigo="TST1161")
        dados, urlopen = self.buscar("TST9162", pagina_completa())
        self.assertEqual(dados["erro"], "")
        self.assertFalse(dados["sem_ementa"])
        self.assertEqual(dados["ementa"], "Limites, derivadas e integrais de teste.")
        self.assertEqual(dados["bibliografia"], "AUTOR, A. Livro de Teste; Editora Teste, 2020.")
        self.assertEqual(dados["bibliografia_complementar"], "OUTRO, B. Apostila.")
        self.assertEqual(dados["atualizacao"], "01/02/2024")
        self.assertEqual((dados["pre_requisitos"], dados["co_requisitos"]), ("TST1161", "Nenhum co-requisito"))
        # endereço fixo da PUC, só com o código; timeout curto
        requisicao = urlopen.call_args.args[0]
        self.assertEqual(requisicao.full_url, "https://www.puc-rio.br/ferramentas/ementas/ementa.aspx?cd=TST9162")
        self.assertEqual(urlopen.call_args.kwargs["timeout"], TEMPO_LIMITE)
        self.assertEqual(TEMPO_LIMITE, 10)

    def test_sem_ementa_cadastrada(self):
        dados, _ = self.buscar("TST9418", PAGINA_SEM_EMENTA.format(codigo="TST9418", titulo="TESTE", creditos=2))
        self.assertTrue(dados["sem_ementa"])
        self.assertEqual(dados["erro"], "")
        self.assertEqual((dados["nome"], dados["creditos"]), ("TESTE", "2 créditos"))
        self.assertEqual(dados["ementa"], "")

    def test_pagina_inexistente(self):
        dados, _ = self.buscar("TST0001", PAGINA_INEXISTENTE)
        self.assertEqual(dados["erro"], ERRO_NAO_ENCONTRADA)
        self.assertFalse(dados["erro_de_rede"])

    def test_erro_de_rede(self):
        for erro in (URLError("sem rede"), TimeoutError(), HTTPError("u", 500, "erro", {}, None), ConnectionResetError()):
            cache.clear()
            dados, _ = self.buscar("TST9162", erro=erro)
            self.assertEqual(dados["erro"], ERRO_DE_REDE)
            self.assertTrue(dados["erro_de_rede"])

    def test_codigo_invalido_nem_monta_a_url(self):
        for codigo in ("", "abc", "INF100", "INF10070", "1NF1007", "INF1007&x=1", "../INF1007", "INF 1007"):
            dados, urlopen = self.buscar(codigo, pagina_completa())
            self.assertEqual(dados["erro"], ERRO_CODIGO_INVALIDO, codigo)
            urlopen.assert_not_called()
        dados, urlopen = self.buscar("tst9162", pagina_completa())      # minúsculas: vira TST9162
        self.assertEqual(dados["erro"], "")

    def test_cache_evita_a_segunda_requisicao(self):
        with patch("GradePuc.ementa_online.urlopen", return_value=RespostaFalsa(pagina_completa())) as urlopen:
            primeira = buscar_ementa("TST9162")
            segunda = buscar_ementa("TST9162")
        self.assertEqual(urlopen.call_count, 1)
        self.assertEqual(primeira, segunda)

    def test_erro_de_rede_nao_fica_no_cache(self):
        with patch("GradePuc.ementa_online.urlopen") as urlopen:
            urlopen.side_effect = [URLError("sem rede"), RespostaFalsa(pagina_completa())]
            self.assertTrue(buscar_ementa("TST9162")["erro_de_rede"])
            dados = buscar_ementa("TST9162")
        self.assertEqual(urlopen.call_count, 2)
        self.assertEqual(dados["ementa"], "Limites, derivadas e integrais de teste.")

    def test_requisitos_da_tabela_nao_ficam_presos_no_cache(self):
        with patch("GradePuc.ementa_online.urlopen", return_value=RespostaFalsa(pagina_completa())):
            self.assertEqual(buscar_ementa("TST9162")["pre_requisitos"], "Nenhum pré-requisito")
            Requisito.objects.create(disciplina="TST9162", tipo="pre", alternativa=0, codigo="TST1161")
            self.assertEqual(buscar_ementa("TST9162")["pre_requisitos"], "TST1161")


class ApiDaEmentaTests(TestCase):
    def setUp(self):
        cache.clear()
        self.client.force_login(criar_aluno("9700002").usuario)

    def test_exige_login(self):
        self.client.logout()
        with patch("GradePuc.ementa_online.urlopen") as urlopen:
            self.assertEqual(self.client.get("/api/ementas/TST9162/").status_code, 302)
        urlopen.assert_not_called()

    def test_devolve_os_campos(self):
        with patch("GradePuc.ementa_online.urlopen", return_value=RespostaFalsa(pagina_completa())):
            dados = self.client.get("/api/ementas/TST9162/").json()
        for campo in ("ementa", "bibliografia", "bibliografia_complementar", "atualizacao", "sem_ementa", "erro"):
            self.assertIn(campo, dados)
        self.assertEqual(dados["ementa"], "Limites, derivadas e integrais de teste.")

    def test_erro_de_rede_e_codigo_invalido(self):
        with patch("GradePuc.ementa_online.urlopen", side_effect=URLError("sem rede")):
            resposta = self.client.get("/api/ementas/TST9162/")
        self.assertEqual(resposta.status_code, 200)
        self.assertTrue(resposta.json()["erro_de_rede"])
        with patch("GradePuc.ementa_online.urlopen") as urlopen:
            resposta = self.client.get("/api/ementas/XYZ/")
        self.assertEqual(resposta.status_code, 400)
        self.assertEqual(resposta.json()["erro"], ERRO_CODIGO_INVALIDO)
        urlopen.assert_not_called()

    def test_detalhes_do_painel_nao_dependem_da_ementa(self):
        # os detalhes (requisitos, status...) não buscam a ementa: funcionam com a PUC fora do ar
        with patch("GradePuc.ementa_online.urlopen", side_effect=URLError("sem rede")) as urlopen:
            resposta = self.client.get("/api/disciplinas/codigo/TST9162/")
        self.assertEqual(resposta.status_code, 200)
        self.assertEqual(resposta.json()["ementa_url"], "/eletivas/TST9162/")
        urlopen.assert_not_called()

    def test_tela_aponta_para_o_endpoint_da_ementa(self):
        resposta = self.client.get("/pre-requisitos/")
        self.assertContains(resposta, 'data-api-ementa="/api/ementas/XXX0000/"')
        self.assertContains(resposta, "Ver página completa")

    def test_busca_tem_painel_de_detalhes_proprio(self):
        # "Detalhes" de um resultado da busca abre dentro do bloco da busca, não no lateral
        resposta = self.client.get("/pre-requisitos/")
        html = resposta.content.decode()
        bloco = html[html.index('class="dica busca-disciplinas"'):html.index('Voltar para minha grade')]
        self.assertIn('class="detalhes-busca" tabindex="-1"', bloco)
        self.assertIn('class="botao-detalhes fechar-detalhes">Fechar</button>', bloco)
        self.assertIn('class="detalhes-disciplina"', bloco)
        self.assertLess(bloco.index('busca-resultados'), bloco.index('detalhes-busca'))
        self.assertContains(resposta, "mostrarDetalhes(codigo, detalheDaBusca)")
