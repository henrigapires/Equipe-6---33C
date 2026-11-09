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
from .espelho import creditos_conferidos, interpretar_paginas, ler_cabecalho_ocr, normalizar_decimal, parece_espelho
from .models import Aluno, LigacaoHabilitacao
from .tests_espelho import criar_aluno, criar_curriculo, dados_espelho, disciplina_espelho, pagina_espelho
from .historico import salvar_espelho
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
	def rodar(imagem, **parametros):
		return [[[[x0, y0], [x1, y0], [x1, y1], [x0, y1]], texto, 0.99] for texto, x0, y0, x1, y1 in caixas], 0.1
	return rodar


class ExtrairPalavrasOcrTests(TestCase):
	def test_imagem_vira_paginas_no_formato_de_palavras(self):
		with patch('GradePuc.ocr.motor_ocr', return_value=motor_falso([('CTC4001 -', 10, 20, 80, 35)])):
			paginas = ocr.extrair_palavras_ocr(png_em_memoria())
		self.assertEqual(len(paginas), 1)
		pagina = paginas[0]
		self.assertTrue(pagina['ocr'])
		self.assertEqual((pagina['largura'], pagina['altura']), (1800, 1200))  # print pequeno é ampliado
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

	def test_cadastro_com_pdf_sem_texto_vai_direto_para_a_conferencia(self):
		self.client.logout()
		dados = {'nome': 'Teste', 'matricula': '9100003', 'email': '', 'password': 'Senha!123',
		         'confirmar_senha': 'Senha!123', 'espelho': pdf_enviado()}
		with patch('GradePuc.views.ler_espelho_por_ocr', return_value=leitura_ocr()):
			resposta = self.client.post('/cadastro/', dados, follow=True)
		self.assertContains(resposta, 'Lemos o seu arquivo por OCR')
		self.assertEqual(resposta.redirect_chain[-1][0], '/perfil/')
		self.assertTrue(resposta.context['user'].is_authenticated)
		self.assertContains(resposta, self.AVISO_OCR)
		self.assertContains(resposta, 'Confirmar e salvar')
		# e confirmar salva no aluno novo
		self.client.post('/perfil/', {'acao': 'confirmar_ocr'})
		self.assertEqual(Aluno.objects.get(matricula='9100003').historico.count(), 2)


def dois_prints():
	"""O espelho de pagina_ocr() cortado em dois prints: o segundo rolou a página, não mostra
	mais o cabeçalho da tabela e repete a última disciplina do primeiro (sobreposição)."""
	completa = pagina_ocr()
	primeiro = [c for c in completa['palavras'] if c['top'] < 1000]
	deslocamento = 800
	segundo = [
		{**c, 'top': c['top'] - deslocamento, 'bottom': c['bottom'] - deslocamento}
		for c in completa['palavras'] if c['top'] >= 862
	]
	def pagina(caixas, numero):
		return {'palavras': caixas, 'texto': '\n'.join(c['text'] for c in caixas),
		        'altura': 1980, 'largura': 1530, 'ocr': True, 'arquivo': numero}
	return pagina(primeiro, 0), pagina(segundo, 1)


class VariosPrintsTests(TestCase):
	def test_segundo_print_sem_cabecalho_descobre_as_colunas_sozinho(self):
		primeiro, segundo = dois_prints()
		dados = interpretar_paginas([primeiro, segundo])
		self.assertEqual([d['codigo'] for d in dados['disciplinas']], ['CTC9001', 'CTC9002', 'INF9009', 'MAT9002'])
		self.assertEqual([d['periodo'] for d in dados['disciplinas']], ['20261', '20261', '20262', '20262'])
		self.assertEqual([d['situacao'] for d in dados['disciplinas']], ['AP', 'AP', 'EA', 'EA'])
		self.assertEqual(dados['disciplinas'][1]['grupo'], 'MAT9161')
		self.assertEqual(dados['curso'], 'CEG')

	def test_disciplina_repetida_entre_prints_conta_uma_vez(self):
		primeiro, segundo = dois_prints()
		dados = interpretar_paginas([primeiro, segundo])
		self.assertEqual([d['codigo'] for d in dados['disciplinas']].count('CTC9002'), 1)

	def test_repetida_dentro_do_mesmo_arquivo_nao_e_descartada(self):
		primeiro, segundo = dois_prints()
		segundo['arquivo'] = 0
		dados = interpretar_paginas([primeiro, segundo])
		self.assertEqual([d['codigo'] for d in dados['disciplinas']].count('CTC9002'), 2)

	def test_so_o_print_da_tabela_sem_cabecalho_tambem_e_lido(self):
		_, segundo = dois_prints()
		dados = interpretar_paginas([segundo])
		self.assertEqual([d['codigo'] for d in dados['disciplinas']], ['CTC9002', 'INF9009', 'MAT9002'])
		self.assertEqual([d['situacao'] for d in dados['disciplinas']], ['AP', 'EA', 'EA'])

	def test_prints_de_tamanhos_diferentes(self):
		primeiro, segundo = dois_prints()
		# o segundo print foi tirado com metade da largura: tudo na metade da escala
		segundo['palavras'] = [
			{**c, 'x0': c['x0'] / 2, 'x1': c['x1'] / 2, 'top': c['top'] / 2, 'bottom': c['bottom'] / 2}
			for c in segundo['palavras']
		]
		segundo['largura'] = 765
		dados = interpretar_paginas([primeiro, segundo])
		self.assertEqual([d['codigo'] for d in dados['disciplinas']], ['CTC9001', 'CTC9002', 'INF9009', 'MAT9002'])

	def test_ler_espelho_por_ocr_junta_os_arquivos_em_ordem(self):
		primeiro, segundo = dois_prints()
		respostas = iter([primeiro['palavras'], segundo['palavras']])

		def motor(imagem, **parametros):
			return [[[[c['x0'], c['top']], [c['x1'], c['top']], [c['x1'], c['bottom']], [c['x0'], c['bottom']]], c['text'], 0.99]
			        for c in next(respostas)], 0.1

		arquivos = [png_em_memoria(1530, 1980), png_em_memoria(1530, 1980)]
		with patch('GradePuc.ocr.motor_ocr', return_value=motor):
			dados = ocr.ler_espelho_por_ocr(arquivos)
		self.assertEqual([d['codigo'] for d in dados['disciplinas']], ['CTC9001', 'CTC9002', 'INF9009', 'MAT9002'])


class EnvioDeVariosArquivosTests(TestCase):
	def setUp(self):
		self.aluno = criar_aluno('9100010')
		self.client.force_login(self.aluno.usuario)

	def imagens(self, quantidade):
		return [SimpleUploadedFile(f'print{n}.png', b'x', content_type='image/png') for n in range(quantidade)]

	def test_varios_prints_chegam_juntos_ao_ocr(self):
		with patch('GradePuc.views.ler_espelho_por_ocr', return_value=leitura_ocr()) as leitura:
			resposta = self.client.post('/perfil/', {'acao': 'enviar_espelho', 'espelho': self.imagens(3)}, follow=True)
		self.assertEqual([a.name for a in leitura.call_args.args[0]], ['print0.png', 'print1.png', 'print2.png'])
		self.assertContains(resposta, 'Lido por OCR: confira antes de salvar.')

	def test_pagina_de_envio_aceita_varios_arquivos(self):
		self.assertContains(self.client.get('/perfil/'), 'name="espelho" id="espelho" multiple')
		self.client.logout()
		self.assertContains(self.client.get('/cadastro/'), 'name="espelho" id="espelho" multiple')

	def test_limite_de_arquivos(self):
		with patch('GradePuc.views.ler_espelho_por_ocr') as leitura:
			resposta = self.client.post('/perfil/', {'acao': 'enviar_espelho', 'espelho': self.imagens(7)}, follow=True)
		leitura.assert_not_called()
		self.assertContains(resposta, 'Envie no máximo 6 arquivos de uma vez.')

	def test_pdf_nao_se_mistura_com_outros_arquivos(self):
		arquivos = self.imagens(1) + [pdf_enviado()]
		with patch('GradePuc.views.ler_espelho_por_ocr') as leitura:
			resposta = self.client.post('/perfil/', {'acao': 'enviar_espelho', 'espelho': arquivos}, follow=True)
		leitura.assert_not_called()
		self.assertContains(resposta, 'Para enviar vários arquivos, use só prints')

	def test_um_arquivo_com_formato_errado_barra_o_envio_todo(self):
		arquivos = self.imagens(1) + [SimpleUploadedFile('print.gif', b'GIF89a', content_type='image/gif')]
		with patch('GradePuc.views.ler_espelho_por_ocr') as leitura:
			resposta = self.client.post('/perfil/', {'acao': 'enviar_espelho', 'espelho': arquivos}, follow=True)
		leitura.assert_not_called()
		self.assertContains(resposta, 'Envie o espelho em PDF, PNG ou JPG.')

	def test_cadastro_com_varios_prints(self):
		self.client.logout()
		dados = {'nome': 'Teste', 'matricula': '9100011', 'email': '', 'password': 'Senha!123',
		         'confirmar_senha': 'Senha!123', 'espelho': self.imagens(2)}
		with patch('GradePuc.views.ler_espelho_por_ocr', return_value=leitura_ocr()) as leitura:
			resposta = self.client.post('/cadastro/', dados, follow=True)
		self.assertEqual(len(leitura.call_args.args[0]), 2)
		self.assertContains(resposta, 'Lemos o seu arquivo por OCR')


class PrintRecortadoTests(TestCase):
	def sem(self, pagina, *textos):
		pagina['palavras'] = [c for c in pagina['palavras'] if c['text'] not in textos]
		pagina['texto'] = '\n'.join(c['text'] for c in pagina['palavras'])
		return pagina

	def test_print_sem_o_titulo_mas_com_a_tabela_e_aceito(self):
		pagina = self.sem(pagina_ocr(), 'PUC-Rio-SAU-EspelhodoHistorico', 'Boa noiteFulano(1234567)')
		dados = interpretar_paginas([pagina])
		self.assertEqual(len(dados['disciplinas']), 4)
		self.assertEqual(dados['curso'], 'CEG')

	def test_imagem_sem_titulo_e_sem_tabela_continua_recusada(self):
		pagina = {'palavras': [caixa('Boleto', 10, 10)], 'texto': 'Boleto', 'altura': 100, 'largura': 100, 'ocr': True}
		with self.assertRaises(ocr.EspelhoInvalido):
			interpretar_paginas([pagina])

	def test_tipo_da_disciplina_mal_lido_usa_a_linha_de_baixo(self):
		pagina = pagina_ocr()
		for c in pagina['palavras']:
			if c['text'] == 'Tipo da':
				c['text'] = 'ep od!'
		dados = interpretar_paginas([pagina])
		self.assertEqual([d['tipo'] for d in dados['disciplinas']], ['OB', 'OC', '', ''])

	def test_zero_no_meio_do_nome_vira_letra_o(self):
		pagina = pagina_ocr()
		for c in pagina['palavras']:
			if c['text'] == 'MODELAGEM E':
				c['text'] = 'M0DELAGEM E'
		dados = interpretar_paginas([pagina])
		self.assertEqual(dados['disciplinas'][1]['nome'], 'MODELAGEM E PROGRAMACAO')

	def test_print_pequeno_e_ampliado_antes_do_ocr(self):
		with patch('GradePuc.ocr.motor_ocr', return_value=motor_falso([])):
			paginas = ocr.extrair_palavras_ocr(png_em_memoria(900, 600))
		self.assertEqual((paginas[0]['largura'], paginas[0]['altura']), (1800, 1200))


class ConferenciaComCaraDePerfilTests(TestCase):
	"""A leitura por OCR aparece no mesmo layout do perfil (curso, próximas, histórico), sem salvar nada."""

	def setUp(self):
		self.aluno = criar_aluno('9100020')
		self.client.force_login(self.aluno.usuario)
		curriculo = criar_curriculo('Engenharia de Computação', [('CTC9001', 1), ('INF9009', 1), ('INF9037', 2)])
		LigacaoHabilitacao.objects.create(
			curso_sigla='CEG', habilitacao_sigla='BCO', enfase_sigla='CCB', curriculo=curriculo, origem='pre_cadastro',
		)

	def ver_previa(self, dados=None):
		with patch('GradePuc.views.ler_espelho_por_ocr', return_value=dados or leitura_ocr()):
			return self.client.post('/perfil/', {'acao': 'enviar_espelho', 'espelho': pdf_enviado()}, follow=True)

	def test_previa_mostra_curso_proximas_e_historico(self):
		resposta = self.ver_previa()
		self.assertContains(resposta, 'Lido por OCR: confira antes de salvar.')
		self.assertContains(resposta, 'Curso reconhecido: <strong>Engenharia de Computação')
		self.assertContains(resposta, 'Próximas do seu currículo')
		self.assertContains(resposta, 'INF9037')
		self.assertContains(resposta, 'Meu histórico')
		self.assertContains(resposta, '2026.1')
		self.assertContains(resposta, '2026.2')
		self.assertContains(resposta, 'value="confirmar_ocr"', count=2)   # botões em cima e embaixo
		self.assertNotContains(resposta, 'name="espelho"')
		self.assertNotContains(resposta, 'Remover meu histórico')

	def test_previa_nao_grava_nada(self):
		self.ver_previa()
		self.client.get('/perfil/')
		self.aluno.refresh_from_db()
		self.assertEqual(self.aluno.historico.count(), 0)
		self.assertIsNone(self.aluno.espelho_importado_em)
		self.assertFalse(Disciplina_existe('CTC9001'))

	def test_previa_nao_mexe_no_historico_ja_salvo(self):
		salvar_espelho(self.aluno, dados_espelho([disciplina_espelho('MAT9161', 'AP')]))
		resposta = self.ver_previa()
		self.assertNotContains(resposta, 'MAT9161')
		self.assertEqual(list(self.aluno.historico.values_list('codigo', flat=True)), ['MAT9161'])

	def test_situacao_nao_lida_aparece_marcada(self):
		dados = leitura_ocr()
		dados['disciplinas'][1]['situacao'] = ''
		resposta = self.ver_previa(dados)
		self.assertContains(resposta, 'perfil__situacao--nao-lida')
		self.assertContains(resposta, 'pode ter faltado alguma disciplina')

	def test_curso_desconhecido_espera_salvar_para_confirmar(self):
		resposta = self.ver_previa(dados_espelho([disciplina_espelho('CTC9001', 'AP')], curso='XYZ'))
		self.assertContains(resposta, 'depois de salvar, você confirma aqui')
		self.assertNotContains(resposta, 'name="curriculo"')
		self.assertFalse(LigacaoHabilitacao.objects.filter(curso_sigla='XYZ').exists())


def Disciplina_existe(codigo):
	from .models import Disciplina
	return Disciplina.objects.filter(codigo=codigo).exists()


class AvisoDeLeituraTests(TestCase):
	def test_perfil_tem_aviso_escondido_e_script_do_botao(self):
		aluno = criar_aluno('9100030')
		self.client.force_login(aluno.usuario)
		resposta = self.client.get('/perfil/')
		self.assertContains(resposta, 'id="aviso-lendo"')
		self.assertContains(resposta, 'Lendo o arquivo...')
		self.assertContains(resposta, "botao.textContent = 'Lendo...'")

	def test_cadastro_trava_o_botao_so_quando_ha_arquivo(self):
		resposta = self.client.get('/cadastro/')
		self.assertContains(resposta, 'arquivo.files.length')

	def test_previa_do_ocr_nao_mostra_o_aviso_de_envio(self):
		aluno = criar_aluno('9100031')
		self.client.force_login(aluno.usuario)
		with patch('GradePuc.views.ler_espelho_por_ocr', return_value=leitura_ocr()):
			resposta = self.client.post('/perfil/', {'acao': 'enviar_espelho', 'espelho': pdf_enviado()}, follow=True)
		self.assertNotContains(resposta, 'id="aviso-lendo"')


# ---------- Parte A: dois prints recortados (quadro do curso + tabela sem cabeçalho) ----------
# Geometria copiada dos prints de verdade (depois de ampliados para 1800 px), mas com
# siglas, códigos, nomes e notas inventados.

def pagina_de_print(caixas, numero, largura=1800, altura=1700):
	return {'palavras': caixas, 'texto': '\n'.join(c['text'] for c in caixas),
	        'altura': altura, 'largura': largura, 'ocr': True, 'arquivo': numero}


def caixa_em(texto, x0, top, x1, bottom):
	return {'text': texto, 'x0': x0, 'x1': x1, 'top': top, 'bottom': bottom}


def print_do_cabecalho(numero=0, sem_codigo_do_curriculo=True, siglas_coladas=True):
	"""Quadro do curso com os rótulos colados ("Anocurriculo"), o "Enfase" mais alto
	(por causa do acento), duas siglas numa caixa só e o CR lido de cabeça para baixo ("6'8")."""
	caixas = [
		caixa_em('ESPELHODOHISTORICO', 119, 26, 407, 53),
		caixa_em('Enfase', 541, 204, 625, 240), caixa_em('Curso', 129, 210, 200, 237),
		caixa_em('Habilitacao', 305, 211, 434, 236), caixa_em('Anocurriculo', 738, 211, 889, 234),
		caixa_em('Codigocurriculo', 1034, 210, 1218, 236), caixa_em('CRacumulado', 1367, 211, 1529, 235),
		caixa_em('XEG', 140, 277, 189, 302),
		caixa_em('2021', 786, 277, 842, 301), caixa_em("6'8", 1427, 275, 1468, 304),
		# cabeçalho da tabela, sem nenhuma disciplina embaixo
		caixa_em('No oport.', 1471, 386, 1579, 414), caixa_em('Tipo da', 896, 401, 986, 432),
		caixa_em('ND', 1176, 404, 1211, 428), caixa_em('Horas', 1363, 404, 1437, 429),
		caixa_em('Periodo', 103, 419, 193, 442), caixa_em('Disciplina', 228, 417, 341, 444),
		caixa_em('Turma', 543, 419, 622, 445), caixa_em('Grau', 656, 420, 717, 444),
		caixa_em('Situacao', 750, 419, 851, 445), caixa_em('Grupo', 1043, 417, 1118, 447),
		caixa_em('Horas', 1258, 418, 1332, 445), caixa_em('disciplina', 1469, 416, 1582, 446),
		caixa_em('disciplina', 885, 433, 997, 462), caixa_em('cred.', 1163, 433, 1225, 459),
		caixa_em('Ext.', 1374, 434, 1424, 460), caixa_em('(*)', 1504, 449, 1549, 480),
	]
	if siglas_coladas:
		caixas.append(caixa_em('YCO ZCB', 346, 277, 607, 302))
	else:
		caixas += [caixa_em('YCO', 346, 277, 394, 302), caixa_em('ZCB', 559, 277, 607, 302)]
	if not sem_codigo_do_curriculo:
		caixas.append(caixa_em('0', 1115, 277, 1130, 302))
	return pagina_de_print(caixas, numero, altura=500)


def print_da_tabela(numero=1):
	"""Tabela sem o cabeçalho, em outra escala (as colunas não batem com as do outro print)."""
	caixas = [
		# créditos perdidos pelo OCR: vêm das horas (60 = 4 x 15)
		caixa_em('XYZ9101-', 186, 61, 314, 91), caixa_em('20251', 52, 101, 132, 129),
		caixa_em('PRIMEIRA DISCIPLINA', 185, 97, 434, 130), caixa_em('33A', 569, 100, 625, 129),
		caixa_em('7,4', 691, 100, 738, 132), caixa_em('AP', 828, 100, 868, 130), caixa_em('OB', 988, 99, 1033, 130),
		caixa_em('60', 1375, 100, 1413, 129), caixa_em('0', 1532, 105, 1548, 126),
		# nota de cabeça para baixo (9,9 lido "6'6") e tipo em minúscula
		caixa_em('XYZ9102-SEGUNDAE', 188, 211, 495, 237), caixa_em('COISA', 185, 245, 374, 278),
		caixa_em('33A', 569, 226, 625, 256), caixa_em("6'6", 689, 225, 740, 260), caixa_em('AP', 826, 225, 869, 257),
		caixa_em('oc', 988, 226, 1033, 257), caixa_em('6', 1292, 229, 1313, 255), caixa_em('90', 1374, 225, 1414, 257),
		# grupo de equivalência e horas lidas errado ("06" no lugar de 90): vale o crédito
		caixa_em('XYZ9103-TERCEIRA', 184, 320, 456, 355), caixa_em('33A', 569, 336, 625, 366),
		caixa_em('9,0', 688, 334, 740, 369), caixa_em('AP', 826, 334, 868, 367), caixa_em('OB', 988, 335, 1033, 367),
		caixa_em('XYZ9100', 1114, 335, 1226, 364), caixa_em('6', 1290, 335, 1314, 366), caixa_em('06', 1374, 334, 1414, 367),
		caixa_em('1', 1679, 342, 1691, 356),
		# segundo período
		caixa_em('XYZ9201-QUARTA', 186, 430, 471, 462), caixa_em('20252', 52, 450, 133, 478),
		caixa_em('83B', 568, 450, 624, 480), caixa_em('EA', 827, 448, 869, 480),
		caixa_em('2', 1292, 451, 1313, 479), caixa_em('30', 1374, 448, 1414, 481),
		# código com uma letra perdida ("QM" no lugar de "QUM")
		caixa_em('QM9501-QUIMICAX', 185, 540, 412, 572), caixa_em('EA', 827, 542, 869, 574),
		caixa_em('5', 1289, 543, 1315, 574), caixa_em('75', 1374, 541, 1415, 575),
		# ext. e nº de oportunidades lidos
		caixa_em('XYZ9202-SEXTA', 187, 640, 474, 665), caixa_em('3WA', 566, 654, 629, 686),
		caixa_em('EA', 828, 656, 868, 684), caixa_em('4', 1291, 659, 1312, 682), caixa_em('60', 1374, 654, 1414, 686),
		caixa_em('0', 1532, 659, 1548, 680), caixa_em('1', 1677, 663, 1691, 679),
		# código escondido no meio de lixo: só se percebe pela segunda situação no bloco
		caixa_em('R XYZ9203 SETIMA', 187, 750, 506, 775), caixa_em('EA', 827, 766, 868, 798),
		caixa_em('2', 1290, 767, 1314, 797), caixa_em('30', 1374, 766, 1414, 798),
	]
	return pagina_de_print(caixas, numero)


class DoisPrintsRecortadosTests(TestCase):
	CODIGOS = ['XYZ9101', 'XYZ9102', 'XYZ9103', 'XYZ9201', 'QM9501', 'XYZ9202', 'XYZ9203']

	def conferir(self, dados):
		self.assertEqual(
			(dados['curso'], dados['habilitacao'], dados['enfase'], dados['ano_curriculo'], dados['cr']),
			('XEG', 'YCO', 'ZCB', '2021', '8,9'),
		)
		linhas = dados['disciplinas']
		self.assertEqual([d['codigo'] for d in linhas], self.CODIGOS)
		self.assertEqual([d['periodo'] for d in linhas], ['20251'] * 3 + ['20252'] * 4)
		self.assertEqual([d['situacao'] for d in linhas], ['AP', 'AP', 'AP', 'EA', 'EA', 'EA', 'EA'])
		self.assertEqual([d['creditos'] for d in linhas], [4, 6, 6, 2, 5, 4, 2])
		self.assertEqual([d['grau'] for d in linhas[:3]], ['7,4', '9,9', '9,0'])
		self.assertEqual([d['tipo'] for d in linhas[:3]], ['OB', 'OC', 'OB'])
		self.assertEqual(linhas[2]['grupo'], 'XYZ9100')
		self.assertEqual([d['codigo'] for d in linhas if d.get('confira')], ['QM9501', 'XYZ9203'])
		self.assertEqual(dados['ocr'], {'codigos': 7, 'situacoes': 7})

	def test_cabecalho_e_depois_tabela(self):
		self.conferir(interpretar_paginas([print_do_cabecalho(0), print_da_tabela(1)]))

	def test_ordem_invertida_da_o_mesmo_resultado(self):
		self.conferir(interpretar_paginas([print_da_tabela(0), print_do_cabecalho(1)]))

	def test_valor_do_codigo_do_curriculo(self):
		dados = interpretar_paginas([print_do_cabecalho(0, sem_codigo_do_curriculo=False), print_da_tabela(1)])
		self.assertEqual(dados['codigo_curriculo'], '0')

	def test_print_so_do_cabecalho_le_o_curso_mas_nenhuma_disciplina(self):
		dados = interpretar_paginas([print_do_cabecalho(0)])
		self.assertEqual((dados['curso'], dados['disciplinas']), ('XEG', []))

	def test_nunca_cola_duas_situacoes(self):
		dados = interpretar_paginas([print_do_cabecalho(0), print_da_tabela(1)])
		self.assertTrue(all(len(d['situacao']) == 2 for d in dados['disciplinas']))


class ValoresDoOcrTests(TestCase):
	def test_decimal_lido_pelo_ocr(self):
		self.assertEqual(normalizar_decimal('8.9'), '8,9')
		self.assertEqual(normalizar_decimal('9,0'), '9,0')
		self.assertEqual(normalizar_decimal("6'8"), '8,9')     # lido de cabeça para baixo
		self.assertEqual(normalizar_decimal("6'6"), '9,9')
		self.assertEqual(normalizar_decimal("7'4"), '')        # não dá para desvirar com certeza
		self.assertEqual(normalizar_decimal('AP'), '')

	def test_creditos_conferidos_com_as_horas(self):
		self.assertEqual(creditos_conferidos('', '60'), 4)
		self.assertEqual(creditos_conferidos('6', '06'), 6)
		self.assertEqual(creditos_conferidos('4161', '90'), 6)
		self.assertEqual(creditos_conferidos('4', ''), 4)
		self.assertEqual(creditos_conferidos('', ''), 0)

	def test_rotulos_colados_e_enfase_mais_alto(self):
		dados = ler_cabecalho_ocr(print_do_cabecalho()['palavras'])
		self.assertEqual(dados, {'curso': 'XEG', 'habilitacao': 'YCO', 'enfase': 'ZCB', 'ano_curriculo': '2021', 'cr': '8,9'})


class OcrDeNovoNoRecorteTests(TestCase):
	def test_valor_que_faltou_e_lido_de_novo_no_recorte_ampliado(self):
		pagina = print_do_cabecalho(siglas_coladas=False)    # só o código do currículo está sem valor
		cabecalho = [(c['text'], c['x0'], c['top'], c['x1'], c['bottom']) for c in pagina['palavras']]
		chamadas = []

		def motor(imagem, **parametros):
			chamadas.append((imagem.shape, parametros))
			if len(chamadas) == 1:
				return motor_falso(cabecalho)(imagem)
			# o recorte ampliado do "Código currículo": um "0" no meio
			altura, largura = imagem.shape[:2]
			return [[[[largura / 2 - 15, altura / 2 - 20], [largura / 2 + 15, altura / 2 - 20],
			          [largura / 2 + 15, altura / 2 + 20], [largura / 2 - 15, altura / 2 + 20]], '0', 0.9]], 0.1

		with patch('GradePuc.ocr.motor_ocr', return_value=motor):
			paginas = ocr.extrair_palavras_ocr(png_em_memoria(1800, 500))
		self.assertTrue(all(p.get('use_cls') is False for _, p in chamadas))
		self.assertEqual(len(chamadas), 2)            # a página inteira + o recorte do código
		dados = ler_cabecalho_ocr(paginas[0]['palavras'])
		self.assertEqual(dados['codigo_curriculo'], '0')


class ConferenciaComOBancoTests(TestCase):
	def leitura(self):
		return interpretar_paginas([print_do_cabecalho(0), print_da_tabela(1)])

	def test_codigo_com_letra_perdida_e_consertado(self):
		criar_curriculo('Curso Inventado', [('QUM9501', 1), ('XYZ9101', 1)])
		dados = ocr.conferir_com_o_banco(self.leitura())
		linhas = {d['codigo']: d for d in dados['disciplinas']}
		self.assertIn('QUM9501', linhas)
		self.assertNotIn('confira', linhas['QUM9501'])
		self.assertTrue(linhas['XYZ9203'].get('confira'))      # não existe no banco: continua para conferir

	def test_dois_candidatos_nao_conserta(self):
		criar_curriculo('Curso Inventado', [('QUM9501', 1), ('QMA9501', 1)])
		dados = ocr.conferir_com_o_banco(self.leitura())
		linhas = {d['codigo']: d for d in dados['disciplinas']}
		self.assertTrue(linhas['QM9501'].get('confira'))

	def test_nome_e_creditos_oficiais_do_banco(self):
		criar_curriculo('Curso Inventado', [('XYZ9102', 1)])   # o helper cria com 4 créditos
		dados = ocr.conferir_com_o_banco(self.leitura())
		linha = [d for d in dados['disciplinas'] if d['codigo'] == 'XYZ9102'][0]
		self.assertEqual((linha['nome'], linha['creditos']), ('Disciplina XYZ9102', 4))
		desconhecida = [d for d in dados['disciplinas'] if d['codigo'] == 'XYZ9101'][0]
		self.assertEqual((desconhecida['nome'], desconhecida['creditos']), ('PRIMEIRA DISCIPLINA', 4))


class CadastroComPrintsTests(TestCase):
	def test_dois_prints_em_ordem_invertida_terminam_na_conferencia_logado(self):
		def caixas(pagina):
			return [[[[c['x0'], c['top']], [c['x1'], c['top']], [c['x1'], c['bottom']], [c['x0'], c['bottom']]], c['text'], 0.9]
			        for c in pagina['palavras']]
		# o navegador mandou a tabela antes do cabeçalho; depois vêm os recortes relidos (vazios)
		respostas = iter([caixas(print_da_tabela()), caixas(print_do_cabecalho())])

		def motor(imagem, **parametros):
			return next(respostas, []), 0.1

		arquivos = [
			SimpleUploadedFile('tabela.png', png_em_memoria(1800, 1700).read(), content_type='image/png'),
			SimpleUploadedFile('cabecalho.png', png_em_memoria(1800, 500).read(), content_type='image/png'),
		]
		dados = {'nome': 'Teste', 'matricula': '9100040', 'email': '', 'password': 'Senha!123',
		         'confirmar_senha': 'Senha!123', 'espelho': arquivos}
		with patch('GradePuc.ocr.motor_ocr', return_value=motor):
			resposta = self.client.post('/cadastro/', dados, follow=True)
		self.assertEqual(resposta.redirect_chain[-1][0], '/perfil/')
		self.assertTrue(resposta.context['user'].is_authenticated)
		self.assertContains(resposta, 'Lido por OCR: confira antes de salvar.')
		for codigo in DoisPrintsRecortadosTests.CODIGOS:
			self.assertContains(resposta, codigo)
		self.assertContains(resposta, 'XEG')
		self.assertEqual(Aluno.objects.get(matricula='9100040').historico.count(), 0)   # ainda não salvou


# ---------- Parte C: correções à mão ----------

class CorrecaoNaConferenciaTests(TestCase):
	"""Na conferência do OCR as correções mexem só na leitura da sessão."""

	def setUp(self):
		self.aluno = criar_aluno('9100050')
		self.client.force_login(self.aluno.usuario)
		criar_curriculo('Curso Inventado', [('CTC9001', 1), ('INF9009', 1), ('MAT9161', 1)])
		with patch('GradePuc.views.ler_espelho_por_ocr', return_value=leitura_ocr(codigos=2, situacoes=3)):
			self.client.post('/perfil/', {'acao': 'enviar_espelho', 'espelho': pdf_enviado()})

	def linhas_da_sessao(self):
		return self.client.session[CHAVE_LEITURA_OCR]['dados']['disciplinas']

	def corrigir(self, **campos):
		return self.client.post('/perfil/', campos, follow=True)

	def test_aviso_aponta_para_adicionar(self):
		resposta = self.client.get('/perfil/')
		self.assertContains(resposta, 'Faltou alguma? Adicione abaixo.')
		self.assertContains(resposta, 'id="adicionar"')
		self.assertContains(resposta, 'name="periodo" value="20262"')     # sugere o último período

	def test_adicionar_disciplina(self):
		resposta = self.corrigir(acao='adicionar_disciplina', codigo='mat 9161', situacao='EA', periodo='2026.2')
		self.assertContains(resposta, 'MAT9161 adicionada.')
		self.assertContains(resposta, 'Disciplina MAT9161')        # nome do banco
		self.assertContains(resposta, 'Lido por OCR: confira antes de salvar.')
		self.assertEqual(self.linhas_da_sessao()[-1]['codigo'], 'MAT9161')
		self.assertEqual(self.linhas_da_sessao()[-1]['periodo'], '20262')
		self.assertEqual(self.aluno.historico.count(), 0)          # nada no banco ainda
		self.assertNotContains(resposta, 'pode ter faltado')        # já corrigiu à mão

	def test_codigo_inexistente(self):
		resposta = self.corrigir(acao='adicionar_disciplina', codigo='ZZZ9999', situacao='AP', periodo='20261')
		self.assertContains(resposta, 'Não encontramos a disciplina ZZZ9999. Confira o código no SAU.')
		self.assertEqual(len(self.linhas_da_sessao()), 2)

	def test_codigo_mal_digitado_e_repetido(self):
		resposta = self.corrigir(acao='adicionar_disciplina', codigo='MAT91', situacao='AP', periodo='20261')
		self.assertContains(resposta, 'Digite o código da disciplina com 3 letras e 4 números')
		resposta = self.corrigir(acao='adicionar_disciplina', codigo='CTC9001', situacao='AP', periodo='20261')
		self.assertContains(resposta, 'CTC9001 já está na lista em 20261.')

	def test_remover_linha(self):
		resposta = self.corrigir(acao='remover_disciplina', linha='0')
		self.assertContains(resposta, 'CTC9001 removida.')
		self.assertEqual([d['codigo'] for d in self.linhas_da_sessao()], ['INF9009'])

	def test_trocar_situacao(self):
		resposta = self.corrigir(acao='trocar_situacao', linha='1', situacao='AP')
		self.assertContains(resposta, 'Situação de INF9009 trocada.')
		self.assertEqual(self.linhas_da_sessao()[1]['situacao'], 'AP')
		resposta = self.corrigir(acao='trocar_situacao', linha='1', situacao='XX')
		self.assertContains(resposta, 'Escolha uma situação da lista.')

	def test_linha_que_nao_existe(self):
		resposta = self.corrigir(acao='remover_disciplina', linha='7')
		self.assertContains(resposta, 'Não encontramos essa disciplina na lista.')

	def test_confirmar_salva_o_que_foi_corrigido(self):
		self.corrigir(acao='remover_disciplina', linha='0')
		self.corrigir(acao='adicionar_disciplina', codigo='MAT9161', situacao='AP', periodo='20261')
		self.client.post('/perfil/', {'acao': 'confirmar_ocr'})
		self.assertEqual(
			sorted(self.aluno.historico.values_list('codigo', 'situacao')), [('INF9009', 'EA'), ('MAT9161', 'AP')]
		)

	def test_codigo_incerto_aparece_marcado(self):
		dados = leitura_ocr()
		dados['disciplinas'][0]['confira'] = True
		with patch('GradePuc.views.ler_espelho_por_ocr', return_value=dados):
			resposta = self.client.post('/perfil/', {'acao': 'enviar_espelho', 'espelho': pdf_enviado()}, follow=True)
		self.assertContains(resposta, 'confira o código', count=1)


class CorrecaoNoPerfilSalvoTests(TestCase):
	"""No perfil já salvo as correções mexem no banco e nas disciplinas cursadas."""

	def setUp(self):
		self.aluno = criar_aluno('9100060')
		self.client.force_login(self.aluno.usuario)
		criar_curriculo('Curso Inventado', [('CTC9001', 1), ('INF9009', 1), ('MAT9161', 1)])
		salvar_espelho(self.aluno, dados_espelho([
			disciplina_espelho('CTC9001', 'AP'), disciplina_espelho('INF9009', 'EA', periodo='20262'),
		]))

	def cursadas(self):
		return sorted(self.aluno.disciplinas_cursadas.values_list('codigo', flat=True))

	def linha(self, codigo):
		return self.aluno.historico.get(codigo=codigo)

	def test_adicionar_entra_no_historico_e_nas_cursadas(self):
		resposta = self.client.post('/perfil/', {
			'acao': 'adicionar_disciplina', 'codigo': 'MAT9161', 'situacao': 'AP', 'periodo': '20261',
		}, follow=True)
		self.assertContains(resposta, 'MAT9161 adicionada.')
		self.assertEqual(resposta.redirect_chain[-1][0], '/perfil/#historico')
		self.assertEqual(self.linha('MAT9161').nome, 'Disciplina MAT9161')
		self.assertIn('MAT9161', self.cursadas())

	def test_adicionar_repetida_ou_inexistente(self):
		resposta = self.client.post('/perfil/', {
			'acao': 'adicionar_disciplina', 'codigo': 'CTC9001', 'situacao': 'AP', 'periodo': '20261',
		}, follow=True)
		self.assertContains(resposta, 'CTC9001 já está no seu histórico em 20261.')
		resposta = self.client.post('/perfil/', {
			'acao': 'adicionar_disciplina', 'codigo': 'ZZZ9999', 'situacao': 'AP', 'periodo': '20261',
		}, follow=True)
		self.assertContains(resposta, 'Não encontramos a disciplina ZZZ9999.')
		self.assertEqual(self.aluno.historico.count(), 2)

	def test_remover_tira_das_cursadas(self):
		resposta = self.client.post('/perfil/', {'acao': 'remover_disciplina', 'linha': self.linha('CTC9001').id}, follow=True)
		self.assertContains(resposta, 'CTC9001 removida.')
		self.assertFalse(self.aluno.historico.filter(codigo='CTC9001').exists())
		self.assertEqual(self.cursadas(), ['INF9009'])

	def test_trocar_para_reprovada_volta_a_ser_sugerida(self):
		self.client.post('/perfil/', {'acao': 'trocar_situacao', 'linha': self.linha('CTC9001').id, 'situacao': 'RM'})
		self.assertEqual(self.linha('CTC9001').situacao, 'RM')
		self.assertEqual(self.cursadas(), ['INF9009'])

	def test_linha_de_outro_aluno_nao_e_mexida(self):
		outro = criar_aluno('9100061')
		salvar_espelho(outro, dados_espelho([disciplina_espelho('MAT9161', 'AP')]))
		linha_do_outro = outro.historico.get()
		resposta = self.client.post('/perfil/', {'acao': 'remover_disciplina', 'linha': linha_do_outro.id}, follow=True)
		self.assertContains(resposta, 'Não encontramos essa disciplina no seu histórico.')
		self.assertTrue(outro.historico.exists())

	def test_tela_tem_os_botoes_de_correcao(self):
		resposta = self.client.get('/perfil/')
		self.assertContains(resposta, 'value="trocar_situacao"', count=2)
		self.assertContains(resposta, 'value="remover_disciplina"', count=2)
		self.assertContains(resposta, 'Adicionar disciplina')
