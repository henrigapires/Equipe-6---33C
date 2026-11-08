"""Testes do OCR do espelho (plano B).

Sem arquivo real e sem rodar o OCR de verdade: as imagens e PDFs são gerados
em memória e o motor do RapidOCR é trocado por um falso que devolve caixas.
"""
import io
import sys
import types
from unittest.mock import patch

import pypdfium2 as pdfium
from django.test import TestCase
from PIL import Image

from . import ocr


def png_em_memoria(largura=300, altura=200):
	buffer = io.BytesIO()
	Image.new('RGB', (largura, altura), 'white').save(buffer, format='PNG')
	buffer.name = 'print.png'
	buffer.seek(0)
	return buffer


def pdf_em_branco(largura=200, altura=100):
	documento = pdfium.PdfDocument.new()
	documento.new_page(largura, altura)
	buffer = io.BytesIO()
	documento.save(buffer)
	buffer.name = 'escaneado.pdf'
	buffer.seek(0)
	return buffer


def motor_falso(caixas):
	"""Imita o RapidOCR: recebe a imagem e devolve ([caixa, texto, confiança], tempo)."""
	def rodar(imagem):
		return [[[[x0, y0], [x1, y0], [x1, y1], [x0, y1]], texto, 0.99] for texto, x0, y0, x1, y1 in caixas], 0.1
	return rodar


class ExtrairPalavrasOcrTests(TestCase):
	def test_imagem_vira_paginas_no_formato_de_palavras(self):
		with patch('GradePuc.ocr.motor_ocr', return_value=motor_falso([('CTC4001 -', 10, 20, 80, 35)])):
			paginas = ocr.extrair_palavras_ocr(png_em_memoria())
		self.assertEqual(len(paginas), 1)
		pagina = paginas[0]
		self.assertTrue(pagina['ocr'])
		self.assertEqual((pagina['largura'], pagina['altura']), (300, 200))
		palavra = pagina['palavras'][0]
		self.assertEqual((palavra['text'], palavra['x0'], palavra['x1'], palavra['top'], palavra['bottom']), ('CTC4001 -', 10, 80, 20, 35))
		self.assertIn('CTC4001', pagina['texto'])

	def test_pdf_sem_texto_e_renderizado_na_escala_do_ocr(self):
		with patch('GradePuc.ocr.motor_ocr', return_value=motor_falso([])):
			paginas = ocr.extrair_palavras_ocr(pdf_em_branco(200, 100))
		self.assertEqual(len(paginas), 1)
		self.assertEqual((paginas[0]['largura'], paginas[0]['altura']), (500, 250))

	def test_arquivo_que_nao_abre(self):
		arquivo = io.BytesIO(b'isto nao e imagem')
		arquivo.name = 'foto.png'
		with self.assertRaises(ocr.EspelhoInvalido):
			ocr.extrair_palavras_ocr(arquivo)


class MotorOcrTests(TestCase):
	def setUp(self):
		ocr._motor = None

	def tearDown(self):
		ocr._motor = None

	def test_sem_rapidocr_instalado(self):
		with patch.dict(sys.modules, {'rapidocr_onnxruntime': None}):
			with self.assertRaises(ocr.OcrIndisponivel):
				ocr.motor_ocr()

	def test_motor_e_carregado_uma_vez_so(self):
		criados = []

		class RapidOCRFalso:
			def __init__(self):
				criados.append(self)

		modulo = types.ModuleType('rapidocr_onnxruntime')
		modulo.RapidOCR = RapidOCRFalso
		with patch.dict(sys.modules, {'rapidocr_onnxruntime': modulo}):
			primeiro = ocr.motor_ocr()
			segundo = ocr.motor_ocr()
		self.assertIs(primeiro, segundo)
		self.assertEqual(len(criados), 1)
