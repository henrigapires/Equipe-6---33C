"""Prints do espelho que se sobrepõem, que começam no meio do semestre, e o OCR ausente.

Caixas de OCR inventadas (códigos XYZ..., notas e nomes falsos), com a geometria dos prints reais.
"""
import sys
from unittest.mock import patch

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase

from . import ocr
from .espelho import interpretar_paginas, semestre_anterior
from .tests_espelho import criar_aluno
from .tests_ocr import caixa_em, pagina_de_print, png_em_memoria, print_do_cabecalho


def linha_a(y, texto, situacao, periodo=None, creditos='4', horas='60'):
	"""Linha do print A (tem o cabeçalho da tabela: colunas nas posições dos rótulos)."""
	caixas = [caixa_em(texto, 228, y, 520, y + 28), caixa_em('33A', 560, y, 610, y + 28),
	          caixa_em(situacao, 785, y, 820, y + 28), caixa_em(creditos, 1188, y, 1200, y + 28),
	          caixa_em(horas, 1278, y, 1312, y + 28)]
	if periodo:
		caixas.append(caixa_em(periodo, 110, y + 10, 185, y + 38))
	return caixas


def print_a(numero=0):
	"""Quadro do curso + cabeçalho da tabela + as primeiras linhas (como o print A)."""
	caixas = list(print_do_cabecalho(numero)['palavras'])
	caixas += linha_a(520, 'XYZ9101-PRIMEIRA', 'AP', periodo='20251')
	caixas += linha_a(580, 'XYZ9102-SEGUNDA', 'AP', creditos='6', horas='90')
	caixas += linha_a(640, 'XYZ9103-TERCEIRA', 'AP')
	caixas += linha_a(700, 'XYZ9201-QUARTA', 'EA', periodo='20252', creditos='2', horas='30')
	return pagina_de_print(caixas, numero, altura=800)


def linha_b(y, texto, situacao, periodo=None, creditos='4', horas='60'):
	"""Linha do print B (sem cabeçalho, outro recorte: as colunas ficam em outras posições)."""
	caixas = [caixa_em(texto, 186, y, 470, y + 30), caixa_em('33A', 569, y, 625, y + 30),
	          caixa_em(situacao, 828, y, 868, y + 30), caixa_em('OB' if situacao == 'AP' else '', 988, y, 1033, y + 30),
	          caixa_em(creditos, 1292, y, 1313, y + 30), caixa_em(horas, 1374, y, 1414, y + 30)]
	if periodo:
		caixas.append(caixa_em(periodo, 52, y + 10, 132, y + 40))
	return [c for c in caixas if c['text']]


def print_b(numero=1):
	"""Só a tabela, começando no meio de 20251: a primeira linha está cortada (só se vê a
	situação), as seguintes não têm rótulo de período e repetem linhas do print A."""
	caixas = [caixa_em('AP', 828, 5, 868, 30), caixa_em('4', 1292, 5, 1313, 30)]    # linha cortada no topo
	caixas += linha_b(61, 'XYZ9102-SEGUNDA', 'AP', creditos='6', horas='90')
	caixas += linha_b(160, 'XYZ9103-TERCEIRA', 'AP')
	caixas += linha_b(260, 'XYZ9201-QUARTA', 'EA', periodo='20252', creditos='2', horas='30')
	caixas += linha_b(360, 'XYZ9202-QUINTA', 'EA')
	caixas += linha_b(460, 'XYZ9203-SEXTA', 'EA')
	return pagina_de_print(caixas, numero, altura=600)


ESPERADO = [
	('20251', 'XYZ9101', 'AP'), ('20251', 'XYZ9102', 'AP'), ('20251', 'XYZ9103', 'AP'),
	('20252', 'XYZ9201', 'EA'), ('20252', 'XYZ9202', 'EA'), ('20252', 'XYZ9203', 'EA'),
]


def linhas(dados):
	return [(d['periodo'], d['codigo'], d['situacao']) for d in dados['disciplinas']]


class PrintsQueSeSobrepoemTests(TestCase):
	def test_a_depois_b(self):
		dados = interpretar_paginas([print_a(0), print_b(1)])
		self.assertEqual(linhas(dados), ESPERADO)
		# a linha cortada no topo de B é a sobreposição com A: não vira aviso de "pode ter faltado"
		self.assertEqual(dados['ocr']['codigos'], dados['ocr']['situacoes'])

	def test_b_depois_a(self):
		self.assertEqual(linhas(interpretar_paginas([print_b(0), print_a(1)])), ESPERADO)

	def test_a_b_e_um_print_inteiro(self):
		inteiro = pagina_de_print(print_a(2)['palavras'] + [
			c for y, t in ((760, 'XYZ9202-QUINTA'), (820, 'XYZ9203-SEXTA')) for c in linha_a(y, t, 'EA')
		], 2, altura=900)
		self.assertEqual(linhas(interpretar_paginas([print_a(0), print_b(1), inteiro])), ESPERADO)

	def test_nenhum_periodo_vazio_nem_repetida(self):
		dados = interpretar_paginas([print_b(0), print_a(1)])
		self.assertTrue(all(d['periodo'] for d in dados['disciplinas']))
		codigos = [d['codigo'] for d in dados['disciplinas']]
		self.assertEqual(len(codigos), len(set(codigos)))

	def test_print_que_comeca_no_meio_do_semestre_sozinho(self):
		dados = interpretar_paginas([print_b(0)])
		# as linhas antes do primeiro rótulo (20252) são do semestre anterior, marcadas para conferir
		self.assertEqual(linhas(dados), ESPERADO[1:])
		self.assertEqual([d['codigo'] for d in dados['disciplinas'] if d.get('confira_periodo')], ['XYZ9102', 'XYZ9103'])
		# a linha cortada no topo não foi coberta por outro print: continua contando como faltando
		self.assertEqual((dados['ocr']['codigos'], dados['ocr']['situacoes']), (5, 6))

	def test_concluida_nao_herda_periodo_em_andamento_de_outro_print(self):
		# B sem os rótulos, depois de um print que termina em 20252 (em andamento), sem sobreposição
		so_ea = pagina_de_print(linha_b(61, 'XYZ9301-OUTRA', 'EA', periodo='20252'), 0, altura=200)
		concluida = pagina_de_print(
			linha_b(61, 'XYZ9302-MAIS', 'AP') + linha_b(160, 'XYZ9401-NOVA', 'EA', periodo='20252'), 1, altura=300,
		)
		dados = interpretar_paginas([so_ea, concluida])
		periodos = {d['codigo']: d['periodo'] for d in dados['disciplinas']}
		self.assertEqual(periodos['XYZ9302'], '20251')         # semestre anterior, não 20252

	def test_mesma_disciplina_em_semestres_diferentes_nao_e_repetida(self):
		# reprovou e cursou de novo: duas linhas de verdade, no mesmo arquivo
		pagina = pagina_de_print(
			linha_b(61, 'XYZ9101-PRIMEIRA', 'RM', periodo='20242') + linha_b(160, 'XYZ9101-PRIMEIRA', 'RM', periodo='20251'),
			0, altura=300,
		)
		self.assertEqual(linhas(interpretar_paginas([pagina])), [('20242', 'XYZ9101', 'RM'), ('20251', 'XYZ9101', 'RM')])

	def test_semestre_anterior(self):
		self.assertEqual(semestre_anterior('20262'), '20261')
		self.assertEqual(semestre_anterior('20261'), '20252')


class OcrAusenteTests(TestCase):
	def setUp(self):
		self.aluno = criar_aluno('9400001')
		self.client.force_login(self.aluno.usuario)
		ocr._motor = None

	def tearDown(self):
		ocr._motor = None

	def enviar_print(self):
		imagem = SimpleUploadedFile('print.png', png_em_memoria().read(), content_type='image/png')
		return self.client.post('/perfil/', {'acao': 'enviar_espelho', 'espelho': imagem}, follow=True)

	def test_sem_rapidocr_a_mensagem_manda_enviar_o_pdf(self):
		with patch.dict(sys.modules, {'rapidocr_onnxruntime': None}), self.assertLogs('GradePuc.espelho', 'WARNING') as logs:
			resposta = self.enviar_print()
		self.assertContains(resposta, 'A leitura de prints não está instalada neste computador.')
		self.assertContains(resposta, 'Python 3.12 ou anterior')
		self.assertNotContains(resposta, 'Não conseguimos ler')
		self.assertIn('rapidocr_onnxruntime', ' '.join(logs.output))

	def test_aviso_ao_lado_do_campo_quando_o_ocr_nao_esta_instalado(self):
		with patch('GradePuc.ocr.ocr_instalado', return_value=False):
			self.assertContains(self.client.get('/perfil/'), 'perfil__aviso-sem-ocr')
			self.client.logout()
			self.assertContains(self.client.get('/cadastro/'), 'A leitura de prints não está instalada neste computador')

	def test_sem_aviso_quando_o_ocr_esta_instalado(self):
		with patch('GradePuc.ocr.ocr_instalado', return_value=True):
			self.assertNotContains(self.client.get('/perfil/'), 'perfil__aviso-sem-ocr')
			self.client.logout()
			self.assertNotContains(self.client.get('/cadastro/'), 'A leitura de prints não está instalada')

	def test_ocr_instalado_procura_o_pacote(self):
		with patch('importlib.util.find_spec', return_value=None):
			self.assertFalse(ocr.ocr_instalado())


class LeituraQueFalhouTests(TestCase):
	def test_mensagem_diz_o_que_fazer_e_o_log_nao_tem_dado_do_aluno(self):
		# OCR "funciona", mas o print não tem a tabela (só uma saudação com a matrícula falsa)
		caixas = [('Boa noite Fulano (1234567)', 10, 10, 300, 40)]

		def motor(imagem, **parametros):
			return [[[[x0, y0], [x1, y0], [x1, y1], [x0, y1]], t, 0.9] for t, x0, y0, x1, y1 in caixas], 0.1

		aluno = criar_aluno('9400002')
		self.client.force_login(aluno.usuario)
		imagem = SimpleUploadedFile('print.png', png_em_memoria().read(), content_type='image/png')
		with patch('GradePuc.ocr.motor_ocr', return_value=motor), self.assertLogs('GradePuc.espelho', 'WARNING') as logs:
			resposta = self.client.post('/perfil/', {'acao': 'enviar_espelho', 'espelho': imagem}, follow=True)
		self.assertContains(resposta, 'colunas Período, Disciplina e Situação')
		self.assertContains(resposta, 'selecione todos os prints de uma vez')
		texto = ' '.join(logs.output)
		self.assertIn('1 caixas', texto)
		self.assertNotIn('1234567', texto)
		self.assertNotIn('Fulano', texto)
