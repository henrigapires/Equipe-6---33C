"""Testes do OCR do espelho (plano B).

Sem arquivo real e sem rodar o OCR de verdade: as imagens e PDFs são gerados
em memória e o motor do RapidOCR é trocado por um falso que devolve caixas.
"""
import io
import random
import sys
import types
from unittest.mock import patch

import pypdfium2 as pdfium
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase
from PIL import Image

from . import ocr
from .espelho import interpretar_paginas, parece_espelho
from .tests_espelho import criar_aluno, dados_espelho, disciplina_espelho, pagina_espelho
from .views import CHAVE_LEITURA_OCR


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


def caixa(texto, x0, top, x1=None, altura=25):
	return {'text': texto, 'x0': x0, 'x1': x1 or x0 + 12 * len(texto), 'top': top, 'bottom': top + altura}


def pagina_ocr(sem_rotulo_disciplina=False, sem_situacao_na_ultima=False):
	"""Caixas como o RapidOCR devolve (pixels, sem acento, código e nome juntos ou não)."""
	caixas = [
		caixa('PUC-Rio-SAU-EspelhodoHistorico', 710, 35), caixa('Boa noiteFulano(1234567)', 680, 145),
		caixa('Curso', 115, 463), caixa('Habilitacao', 274, 464), caixa('Enfase', 491, 458),
		caixa('Ano curriculo', 670, 464), caixa('Codigo curriculo', 942, 464), caixa('CR acumulado', 1246, 464),
		caixa('CEG', 124, 524), caixa('BCO', 310, 523), caixa('CCB', 508, 525), caixa('2023', 714, 523),
		caixa('0', 1018, 525), caixa('7,5', 1301, 524),
		# cabeçalho da tabela: "Situaclio" é como o OCR leu "Situação" numa imagem borrada
		caixa('Periodo', 92, 656, 173), caixa('Turma', 495, 655, 567), caixa('Grau', 597, 655, 657),
		caixa('Situaclio', 683, 655, 775), caixa('Tipo da', 817, 639, 901), caixa('disciplina', 806, 665, 911),
		caixa('Grupo', 953, 655, 1020), caixa('No', 1071, 638, 1107), caixa('créd.', 1061, 666, 1121),
		caixa('Horas', 1148, 655, 1216), caixa('Horas', 1244, 639, 1313), caixa('Ext.', 1254, 670, 1304),
		caixa('No oport.', 1342, 624, 1444),
		# período colado no código e no nome
		caixa('20261 CTC9001 - INSTRUMENTACAO E', 92, 745, 461), caixa('MEDICAO', 203, 802, 298),
		caixa('33A', 507, 774, 556), caixa('8,5', 604, 774, 645), caixa('AP', 713, 774, 747), caixa('OB', 842, 774, 877),
		caixa('4', 1084, 780, 1097), caixa('60', 1148, 774, 1180), caixa('0', 1271, 778, 1287), caixa('1', 1388, 781, 1400),
		# código sozinho, nome nas linhas de baixo, tipo em minúscula e grupo de equivalência
		caixa('CTC9002 -', 203, 862, 309), caixa('MODELAGEM E', 203, 889, 356), caixa('PROGRAMACAO', 203, 915, 356),
		caixa('33A', 506, 875, 556), caixa('AP', 712, 875, 748), caixa('oC', 841, 875, 878),
		caixa('MAT9161', 940, 875, 1030), caixa('6', 1083, 878, 1100),
		# período numa caixa separada e código em minúsculas
		caixa('20262', 97, 1398, 164), caixa('inf9009-logica para', 205, 1385, 435), caixa('COMPUTACAO', 205, 1415, 340),
		caixa('3WA', 506, 1399, 556), caixa('EA', 714, 1399, 746), caixa('4', 1082, 1401, 1099),
		# zeros lidos como a letra O
		caixa('MAT9OO2 - CALCULO', 204, 1475, 400), caixa('33C', 508, 1487, 554), caixa('2', 1083, 1489, 1099),
		caixa('*Sera desligado compulsoriamente da Universidade', 85, 1600, 1398),
	]
	if not sem_situacao_na_ultima:
		caixas.append(caixa('EA', 714, 1487, 745))
	if not sem_rotulo_disciplina:
		caixas.append(caixa('Disciplina', 204, 653, 309))
	random.Random(7).shuffle(caixas)   # o OCR não devolve na ordem de leitura
	texto = '\n'.join(c['text'] for c in caixas)
	return {'palavras': caixas, 'texto': texto, 'altura': 1980, 'largura': 1530, 'ocr': True}


class InterpretacaoDoOcrTests(TestCase):
	def test_le_disciplinas_das_caixas_do_ocr(self):
		dados = interpretar_paginas([pagina_ocr()])
		self.assertEqual((dados['curso'], dados['habilitacao'], dados['enfase'], dados['ano_curriculo']), ('CEG', 'BCO', 'CCB', '2023'))
		self.assertEqual(dados['matricula'], '1234567')
		linhas = dados['disciplinas']
		self.assertEqual([d['codigo'] for d in linhas], ['CTC9001', 'CTC9002', 'INF9009', 'MAT9002'])
		self.assertEqual([d['periodo'] for d in linhas], ['20261', '20261', '20262', '20262'])
		self.assertEqual([d['situacao'] for d in linhas], ['AP', 'AP', 'EA', 'EA'])
		self.assertEqual([d['nome'] for d in linhas], ['INSTRUMENTACAO E MEDICAO', 'MODELAGEM E PROGRAMACAO', 'LOGICA PARA COMPUTACAO', 'CALCULO'])
		self.assertEqual([d['tipo'] for d in linhas], ['OB', 'OC', '', ''])
		self.assertEqual([d['grupo'] for d in linhas], ['', 'MAT9161', '', ''])
		self.assertEqual([d['creditos'] for d in linhas], [4, 6, 4, 2])
		self.assertEqual(linhas[0]['turma'], '33A')
		self.assertEqual(dados['ocr'], {'codigos': 4, 'situacoes': 4})

	def test_sem_o_rotulo_disciplina_estima_a_coluna(self):
		dados = interpretar_paginas([pagina_ocr(sem_rotulo_disciplina=True)])
		self.assertEqual([d['codigo'] for d in dados['disciplinas']], ['CTC9001', 'CTC9002', 'INF9009', 'MAT9002'])

	def test_contagem_mostra_quando_falta_uma_situacao(self):
		dados = interpretar_paginas([pagina_ocr(sem_situacao_na_ultima=True)])
		self.assertEqual(dados['ocr'], {'codigos': 4, 'situacoes': 3})
		self.assertEqual(dados['disciplinas'][-1]['situacao'], '')

	def test_titulo_sem_espacos_e_sem_acento(self):
		self.assertTrue(parece_espelho('PUC-Rio-SAU-EspelhodoHistorico'))
		self.assertTrue(parece_espelho('Espelho do Histórico'))
		self.assertFalse(parece_espelho('Boleto bancário'))

	def test_leitura_direta_continua_igual_e_sem_contagem_de_ocr(self):
		dados = interpretar_paginas([pagina_espelho()])
		self.assertNotIn('ocr', dados)
		self.assertEqual([d['codigo'] for d in dados['disciplinas']], ['MAT9161', 'MAT9181', 'INF9009', 'ENG9000'])


def leitura_ocr(codigos=2, situacoes=2):
	dados = dados_espelho([disciplina_espelho('CTC9001', 'AP'), disciplina_espelho('INF9009', 'EA', periodo='20262')])
	dados['ocr'] = {'codigos': codigos, 'situacoes': situacoes}
	return dados


def pdf_enviado():
	return SimpleUploadedFile('escaneado.pdf', pdf_em_branco().read(), content_type='application/pdf')


class FluxoDeConferenciaTests(TestCase):
	AVISO_OCR = 'Lido por OCR: confira antes de salvar.'

	def setUp(self):
		self.aluno = criar_aluno('9100001')
		self.client.force_login(self.aluno.usuario)
		ocr._motor = None

	def tearDown(self):
		ocr._motor = None

	def enviar_lido_por_ocr(self, dados):
		with patch('GradePuc.views.ler_espelho_por_ocr', return_value=dados):
			return self.client.post('/perfil/', {'acao': 'enviar_espelho', 'espelho': pdf_enviado()}, follow=True)

	def test_pdf_sem_texto_vai_para_a_conferencia_sem_salvar(self):
		resposta = self.enviar_lido_por_ocr(leitura_ocr())
		self.assertContains(resposta, self.AVISO_OCR)
		self.assertContains(resposta, 'CTC9001')
		self.assertContains(resposta, 'Confirmar e salvar')
		self.assertContains(resposta, 'Enviar outro arquivo')
		self.assertNotContains(resposta, 'pode ter faltado')
		self.assertEqual(self.aluno.historico.count(), 0)
		self.assertIn(CHAVE_LEITURA_OCR, self.client.session)

	def test_confirmar_salva_o_historico(self):
		self.enviar_lido_por_ocr(leitura_ocr())
		resposta = self.client.post('/perfil/', {'acao': 'confirmar_ocr'}, follow=True)
		self.assertContains(resposta, 'Histórico importado: 2 disciplinas.')
		self.assertContains(resposta, 'Ver grades sugeridas')
		self.assertNotContains(resposta, self.AVISO_OCR)
		self.assertEqual(self.aluno.historico.count(), 2)
		self.assertNotIn(CHAVE_LEITURA_OCR, self.client.session)

	def test_enviar_outro_arquivo_descarta_a_leitura(self):
		self.enviar_lido_por_ocr(leitura_ocr())
		resposta = self.client.post('/perfil/', {'acao': 'descartar_ocr'}, follow=True)
		self.assertContains(resposta, 'Leitura descartada. Envie outro arquivo.')
		self.assertContains(resposta, 'name="espelho"')
		self.assertEqual(self.aluno.historico.count(), 0)

	def test_aviso_quando_codigos_e_situacoes_nao_batem(self):
		resposta = self.enviar_lido_por_ocr(leitura_ocr(codigos=3, situacoes=2))
		self.assertContains(resposta, 'pode ter faltado alguma disciplina')

	def test_pdf_sem_texto_e_sem_ocr_instalado(self):
		with patch.dict(sys.modules, {'rapidocr_onnxruntime': None}):
			resposta = self.client.post('/perfil/', {'acao': 'enviar_espelho', 'espelho': pdf_enviado()}, follow=True)
		self.assertEqual(resposta.status_code, 200)
		self.assertContains(resposta, ocr.MENSAGEM_NAO_LEU)
		self.assertNotContains(resposta, self.AVISO_OCR)
		self.assertNotIn(CHAVE_LEITURA_OCR, self.client.session)

	def test_ocr_que_nao_acha_nada(self):
		with patch('GradePuc.ocr.motor_ocr', return_value=motor_falso([])):
			resposta = self.client.post('/perfil/', {'acao': 'enviar_espelho', 'espelho': pdf_enviado()}, follow=True)
		self.assertContains(resposta, ocr.MENSAGEM_NAO_LEU)
		self.assertEqual(self.aluno.historico.count(), 0)

	def test_leitura_de_outro_aluno_e_ignorada(self):
		outro = criar_aluno('9100002')
		sessao = self.client.session
		sessao[CHAVE_LEITURA_OCR] = {'aluno': outro.id, 'dados': leitura_ocr()}
		sessao.save()
		resposta = self.client.get('/perfil/')
		self.assertNotContains(resposta, self.AVISO_OCR)
		self.assertNotIn(CHAVE_LEITURA_OCR, self.client.session)

	def test_print_da_tela_passa_pelo_ocr_de_ponta_a_ponta(self):
		# imagem gerada em memória + motor falso que devolve as caixas de pagina_ocr()
		caixas = [(c['text'], c['x0'], c['top'], c['x1'], c['bottom']) for c in pagina_ocr()['palavras']]
		imagem = SimpleUploadedFile('print.png', png_em_memoria(1530, 1980).read(), content_type='image/png')
		with patch('GradePuc.views.ler_espelho') as leitura_direta, patch('GradePuc.ocr.motor_ocr', return_value=motor_falso(caixas)):
			resposta = self.client.post('/perfil/', {'acao': 'enviar_espelho', 'espelho': imagem}, follow=True)
		leitura_direta.assert_not_called()
		self.assertContains(resposta, self.AVISO_OCR)
		for codigo in ['CTC9001', 'CTC9002', 'INF9009', 'MAT9002']:
			self.assertContains(resposta, codigo)
		self.assertNotContains(resposta, 'pode ter faltado')
		self.assertEqual(self.aluno.historico.count(), 0)

	def test_jpg_tambem_e_aceito(self):
		imagem = SimpleUploadedFile('print.JPG', b'qualquer', content_type='image/jpeg')
		resposta = self.enviar_lido_por_ocr_com_arquivo(imagem)
		self.assertContains(resposta, self.AVISO_OCR)

	def enviar_lido_por_ocr_com_arquivo(self, arquivo):
		with patch('GradePuc.views.ler_espelho_por_ocr', return_value=leitura_ocr()):
			return self.client.post('/perfil/', {'acao': 'enviar_espelho', 'espelho': arquivo}, follow=True)

	def test_limites_de_tamanho_e_formatos(self):
		grande = SimpleUploadedFile('print.png', b'0' * (8 * 1024 * 1024 + 1), content_type='image/png')
		self.assertContains(self.enviar_lido_por_ocr_com_arquivo(grande), 'A imagem tem mais de 8 MB.')
		pdf_grande = SimpleUploadedFile('espelho.pdf', b'0' * (5 * 1024 * 1024 + 1), content_type='application/pdf')
		self.assertContains(self.enviar_lido_por_ocr_com_arquivo(pdf_grande), 'O arquivo tem mais de 5 MB.')
		gif = SimpleUploadedFile('print.gif', b'GIF89a', content_type='image/gif')
		self.assertContains(self.enviar_lido_por_ocr_com_arquivo(gif), 'Envie o espelho em PDF, PNG ou JPG.')
		self.assertNotIn(CHAVE_LEITURA_OCR, self.client.session)

	def test_imagem_que_nao_abre(self):
		quebrada = SimpleUploadedFile('print.png', b'nao sou png', content_type='image/png')
		resposta = self.client.post('/perfil/', {'acao': 'enviar_espelho', 'espelho': quebrada}, follow=True)
		self.assertContains(resposta, ocr.MENSAGEM_NAO_LEU)

	def test_formularios_aceitam_imagens(self):
		self.assertContains(self.client.get('/perfil/'), 'accept=".pdf,.png,.jpg,.jpeg,')
		self.client.logout()
		self.assertContains(self.client.get('/cadastro/'), 'accept=".pdf,.png,.jpg,.jpeg,')

	def test_cadastro_com_pdf_sem_texto_deixa_a_conferencia_para_o_perfil(self):
		self.client.logout()
		dados = {'nome': 'Teste', 'matricula': '9100003', 'email': '', 'password': 'Senha!123',
		         'confirmar_senha': 'Senha!123', 'espelho': pdf_enviado()}
		with patch('GradePuc.views.ler_espelho_por_ocr', return_value=leitura_ocr()):
			resposta = self.client.post('/cadastro/', dados, follow=True)
		self.assertContains(resposta, 'Lemos o seu arquivo por OCR')
		self.assertTrue(self.client.login(username='9100003', password='Senha!123'))
		self.assertContains(self.client.get('/perfil/'), self.AVISO_OCR)
