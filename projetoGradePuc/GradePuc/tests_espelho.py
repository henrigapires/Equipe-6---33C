"""Testes do espelho do histórico e dos currículos.

Sem internet e sem PDF real: o espelho é simulado com palavras falsas
(texto + posição), no mesmo formato que o pdfplumber devolve.
"""
from django.test import TestCase

from .espelho import (
	EspelhoInvalido, EspelhoSemTexto, classificar_situacao, interpretar_paginas,
)


def palavra(texto, x0, top):
	return {"text": texto, "x0": x0, "x1": x0 + 6 * len(texto), "top": top, "bottom": top + 8}


def cabecalho_da_tabela(top):
	return [
		palavra("Período", 40, top), palavra("Disciplina", 90, top), palavra("Turma", 300, top),
		palavra("Grau", 340, top), palavra("Situação", 380, top), palavra("Tipo", 430, top),
		palavra("da", 456, top), palavra("disciplina", 470, top), palavra("Grupo", 520, top),
		palavra("N°", 570, top), palavra("créd.", 570, top + 9), palavra("Horas", 610, top),
		palavra("Horas", 650, top), palavra("Ext.", 650, top + 9),
		palavra("N°", 690, top), palavra("oport.", 690, top + 9),
	]


def linha_disciplina(top, codigo, nome, situacao, periodo="", turma="3VA", grau="", tipo="Obrigatória",
                     grupo="", creditos="4", nome_segunda_linha=""):
	palavras = [palavra(codigo, 90, top), palavra("-", 140, top)]
	x = 150
	for parte in nome.split():
		palavras.append(palavra(parte, x, top))
		x += 6 * len(parte) + 5
	if nome_segunda_linha:
		x = 150
		for parte in nome_segunda_linha.split():
			palavras.append(palavra(parte, x, top + 10))
			x += 6 * len(parte) + 5
	if periodo:
		palavras.append(palavra(periodo, 40, top))
	palavras.append(palavra(turma, 300, top))
	if grau:
		palavras.append(palavra(grau, 340, top))
	palavras.append(palavra(situacao, 380, top))
	palavras.append(palavra(tipo, 450, top))
	if grupo:
		palavras.append(palavra(grupo, 520, top))
	palavras.append(palavra(creditos, 575, top))
	return palavras


def pagina_espelho(com_enfase=True):
	palavras = [
		palavra("Espelho", 40, 20), palavra("do", 90, 20), palavra("Histórico", 110, 20),
		palavra("Boa", 40, 40), palavra("noite", 65, 40), palavra("Fulano", 100, 40), palavra("(1234567)", 145, 40),
		palavra("Curso", 50, 100), palavra("Habilitação", 120, 100), palavra("Ênfase", 200, 100),
		palavra("Ano", 260, 100), palavra("currículo", 282, 100), palavra("Código", 345, 100),
		palavra("currículo", 385, 100), palavra("CR", 450, 100), palavra("acumulado", 468, 100),
		palavra("CEG", 52, 115), palavra("BCO", 125, 115), palavra("2023", 275, 115),
		palavra("X99", 370, 115), palavra("7,25", 465, 115),
	]
	if com_enfase:
		palavras.append(palavra("CCB", 205, 115))
	palavras += cabecalho_da_tabela(200)
	palavras += linha_disciplina(230, "MAT9161", "CÁLCULO TESTE I", "AP", periodo="20261", grau="8,5")
	palavras += linha_disciplina(260, "MAT9181", "CÁLCULO TESTE II", "AP", grau="7,0", grupo="MAT9161")
	palavras += linha_disciplina(290, "INF9009", "ÁLGEBRA", "EA", periodo="20262", nome_segunda_linha="LINEAR TESTE")
	palavras += linha_disciplina(330, "ENG9000", "MATÉRIA REPROVADA", "RF", grau="2,0", creditos="2")
	palavras += [palavra("*", 40, 400), palavra("Legenda", 50, 400)]
	texto = "Espelho do Histórico\nBoa noite Fulano (1234567)\n..."
	return {"palavras": palavras, "texto": texto, "altura": 800}


def segunda_pagina():
	palavras = [palavra("Espelho", 40, 20), palavra("do", 90, 20), palavra("Histórico", 110, 20)]
	palavras += cabecalho_da_tabela(100)
	palavras += linha_disciplina(130, "FIS9001", "FÍSICA TESTE", "EA")
	palavras += [palavra("*", 40, 300)]
	return {"palavras": palavras, "texto": "Espelho do Histórico", "altura": 800}


class LeituraDoEspelhoTests(TestCase):
	def test_cabecalho_do_curso(self):
		dados = interpretar_paginas([pagina_espelho()])
		self.assertEqual(dados["matricula"], "1234567")
		self.assertEqual(dados["curso"], "CEG")
		self.assertEqual(dados["habilitacao"], "BCO")
		self.assertEqual(dados["enfase"], "CCB")
		self.assertEqual(dados["ano_curriculo"], "2023")
		self.assertEqual(dados["codigo_curriculo"], "X99")
		self.assertEqual(dados["cr"], "7,25")

	def test_sem_enfase_nao_desloca_as_outras_colunas(self):
		dados = interpretar_paginas([pagina_espelho(com_enfase=False)])
		self.assertEqual(dados["enfase"], "")
		self.assertEqual(dados["ano_curriculo"], "2023")
		self.assertEqual(dados["cr"], "7,25")

	def test_disciplinas_periodo_herdado_e_nome_em_duas_linhas(self):
		dados = interpretar_paginas([pagina_espelho()])
		codigos = [d["codigo"] for d in dados["disciplinas"]]
		self.assertEqual(codigos, ["MAT9161", "MAT9181", "INF9009", "ENG9000"])

		por_codigo = {d["codigo"]: d for d in dados["disciplinas"]}
		self.assertEqual(por_codigo["MAT9181"]["periodo"], "20261")
		self.assertEqual(por_codigo["ENG9000"]["periodo"], "20262")
		self.assertEqual(por_codigo["INF9009"]["nome"], "ÁLGEBRA LINEAR TESTE")
		self.assertEqual(por_codigo["MAT9161"]["grau"], "8,5")
		self.assertEqual(por_codigo["MAT9181"]["grupo"], "MAT9161")
		self.assertEqual(por_codigo["ENG9000"]["creditos"], 2)
		self.assertEqual(por_codigo["MAT9161"]["tipo"], "Obrigatória")

	def test_em_andamento_tem_grau_vazio(self):
		dados = interpretar_paginas([pagina_espelho()])
		inf = [d for d in dados["disciplinas"] if d["codigo"] == "INF9009"][0]
		self.assertEqual(inf["situacao"], "EA")
		self.assertEqual(inf["grau"], "")

	def test_segunda_pagina_herda_o_periodo(self):
		dados = interpretar_paginas([pagina_espelho(), segunda_pagina()])
		fis = dados["disciplinas"][-1]
		self.assertEqual(fis["codigo"], "FIS9001")
		self.assertEqual(fis["periodo"], "20262")

	def test_classificacao_das_situacoes(self):
		for situacao in ["AP", "CP", "CC", "CT", "DS"]:
			self.assertEqual(classificar_situacao(situacao), "cursada")
		self.assertEqual(classificar_situacao("EA"), "em_andamento")
		for situacao in ["RM", "RF", "NC", "CA", "TR"]:
			self.assertEqual(classificar_situacao(situacao), "pode_cursar")

	def test_pdf_que_nao_e_espelho(self):
		pagina = {"palavras": [palavra("Boleto", 40, 20)], "texto": "Boleto bancário", "altura": 800}
		with self.assertRaises(EspelhoInvalido):
			interpretar_paginas([pagina])

	def test_pdf_sem_texto(self):
		with self.assertRaises(EspelhoSemTexto):
			interpretar_paginas([{"palavras": [], "texto": "", "altura": 800}])

	def test_espelho_sem_tabela(self):
		pagina = {"palavras": [palavra("Espelho", 40, 20)], "texto": "Espelho do Histórico", "altura": 800}
		with self.assertRaises(EspelhoInvalido):
			interpretar_paginas([pagina])
