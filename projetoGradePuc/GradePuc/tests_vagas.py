"""Optativas que ocupam as vagas de grupo do currículo (INF1026 -> INF0307).

Históricos inventados. Nas linhas em andamento (EA) o SAU deixa Tipo e Grupo vazios,
então os testes usam tipo '' nessas linhas, como no espelho de verdade.
"""
from unittest.mock import patch

from django.test import TestCase

from .historico import SEM_VAGA, codigos_bloqueados, ocupacao_das_vagas, salvar_espelho
from .models import Curriculo, LigacaoHabilitacao
from .tests_espelho import SemCurriculosCarregados, criar_aluno, criar_curriculo, dados_espelho, disciplina_espelho
from .views import CHAVE_LEITURA_OCR


def linha(codigo, situacao, periodo='20262', tipo='', grupo=''):
	d = disciplina_espelho(codigo, situacao, periodo=periodo, grupo=grupo)
	d['tipo'] = tipo
	return d


class VagasDeOptativaTests(SemCurriculosCarregados, TestCase):
	def setUp(self):
		self.aluno = criar_aluno('9300001')
		# 4º caractere 0 = vaga de grupo (criar_curriculo marca eh_grupo assim)
		self.curriculo = criar_curriculo('Curso Inventado', [
			('ABC1001', 1), ('CRE1200', 1), ('INF0307', 2), ('CRE0712', 3), ('ENG0561', 3), ('ENG0562', 4),
		])
		LigacaoHabilitacao.objects.create(
			curso_sigla='CEG', habilitacao_sigla='XYZ', enfase_sigla='', curriculo=self.curriculo, origem='pre_cadastro',
		)

	def salvar(self, *linhas):
		salvar_espelho(self.aluno, dados_espelho(list(linhas), curso='CEG', habilitacao='XYZ', enfase=''))

	def pendentes(self):
		return [item.codigo for item in ocupacao_das_vagas(self.aluno)[0]]

	def conta_como(self):
		ocupadas = ocupacao_das_vagas(self.aluno)[1]
		return {self.aluno.historico.get(id=i).codigo: vaga for i, vaga in ocupadas.items()}

	def test_optativa_em_andamento_sem_tipo_fecha_a_vaga_do_mesmo_prefixo(self):
		self.salvar(linha('ABC1001', 'AP', '20261', tipo='OB'), linha('INF1026', 'EA'))
		self.assertNotIn('INF0307', self.pendentes())
		self.assertNotIn('ABC1001', self.pendentes())
		self.assertEqual(self.conta_como(), {'INF1026': 'INF0307'})

	def test_duas_optativas_e_uma_vaga_so_fecham_uma(self):
		self.salvar(linha('INF1026', 'EA'), linha('INF1037', 'AP', '20261'))
		self.assertEqual(len(self.conta_como()), 1)
		self.assertNotIn('INF0307', self.pendentes())

	def test_duas_optativas_e_duas_vagas_fecham_as_duas(self):
		Curriculo.objects.all().delete()
		curriculo = criar_curriculo('Curso Inventado 2', [('INF0307', 2), ('INF0307', 5)])
		LigacaoHabilitacao.objects.filter(curso_sigla='CEG').update(curriculo=curriculo)
		self.salvar(linha('INF1026', 'EA'), linha('INF1037', 'AP', '20261'))
		self.assertEqual(self.conta_como(), {'INF1026': 'INF0307', 'INF1037': 'INF0307'})
		self.assertEqual(self.pendentes(), [])

	def test_item_do_curriculo_nunca_fecha_vaga(self):
		# CRE1200 é disciplina do currículo: não conta como CRE0712 (Optativas de Cristianismo)
		self.salvar(linha('CRE1200', 'EA'))
		self.assertIn('CRE0712', self.pendentes())
		self.assertNotIn('CRE1200', self.pendentes())
		self.assertEqual(self.conta_como(), {})

	def test_tipo_ob_ou_oc_nao_fecha_vaga(self):
		self.salvar(linha('INF1099', 'AP', '20261', tipo='OB'), linha('INF1098', 'AP', '20261', tipo='OC'))
		self.assertIn('INF0307', self.pendentes())

	def test_prefixo_com_mais_de_um_grupo_fica_pendente(self):
		self.salvar(linha('ENG1234', 'EA'))
		self.assertIn('ENG0561', self.pendentes())
		self.assertIn('ENG0562', self.pendentes())
		self.assertEqual(self.conta_como(), {})

	def test_reprovada_nao_fecha_vaga(self):
		self.salvar(linha('INF1026', 'RM', '20261'))
		self.assertIn('INF0307', self.pendentes())

	def test_nada_aparece_feito_e_pendente_ao_mesmo_tempo(self):
		self.salvar(linha('ABC1001', 'AP', '20261', tipo='OB'), linha('INF1026', 'EA'), linha('CRE1200', 'EA'))
		self.assertFalse(set(self.pendentes()) & codigos_bloqueados(self.aluno))


class EscolhaManualDaVagaTests(SemCurriculosCarregados, TestCase):
	def setUp(self):
		self.aluno = criar_aluno('9300002')
		self.client.force_login(self.aluno.usuario)
		curriculo = criar_curriculo('Curso Inventado', [('INF0307', 2), ('ENG0561', 3), ('ENG0562', 4)])
		LigacaoHabilitacao.objects.create(
			curso_sigla='CEG', habilitacao_sigla='XYZ', enfase_sigla='', curriculo=curriculo, origem='pre_cadastro',
		)
		salvar_espelho(self.aluno, dados_espelho(
			[linha('INF1026', 'EA'), linha('ENG1234', 'EA')], curso='CEG', habilitacao='XYZ', enfase='',
		))

	def id_de(self, codigo):
		return self.aluno.historico.get(codigo=codigo).id

	def pendentes(self):
		return [item.codigo for item in ocupacao_das_vagas(self.aluno)[0]]

	def test_tela_mostra_a_etiqueta_e_o_seletor(self):
		resposta = self.client.get('/perfil/')
		self.assertContains(resposta, 'conta como INF0307')
		self.assertContains(resposta, 'value="conta_como"', count=2)       # INF1026 e ENG1234
		self.assertContains(resposta, 'INF0307 – Disciplina INF0307')

	def test_escolha_manual_grava_o_grupo_e_a_vaga_some(self):
		resposta = self.client.post('/perfil/', {'acao': 'conta_como', 'linha': self.id_de('ENG1234'), 'grupo': 'ENG0562'}, follow=True)
		self.assertContains(resposta, 'ENG1234 agora conta como ENG0562.')
		self.assertEqual(self.aluno.historico.get(codigo='ENG1234').grupo, 'ENG0562')
		self.assertNotIn('ENG0562', self.pendentes())
		self.assertIn('ENG0561', self.pendentes())
		self.assertContains(resposta, 'conta como ENG0562')

	def test_nenhum_desfaz_e_a_regra_automatica_nao_volta(self):
		resposta = self.client.post('/perfil/', {'acao': 'conta_como', 'linha': self.id_de('INF1026'), 'grupo': ''}, follow=True)
		self.assertContains(resposta, 'INF1026 não ocupa vaga de optativa.')
		self.assertEqual(self.aluno.historico.get(codigo='INF1026').grupo, SEM_VAGA)
		self.assertIn('INF0307', self.pendentes())
		self.assertNotContains(resposta, 'conta como INF0307')
		self.assertNotIn(SEM_VAGA, codigos_bloqueados(self.aluno))

	def test_vaga_que_nao_e_do_curriculo_da_erro(self):
		resposta = self.client.post('/perfil/', {'acao': 'conta_como', 'linha': self.id_de('ENG1234'), 'grupo': 'XYZ0999'}, follow=True)
		self.assertContains(resposta, 'Escolha uma vaga de optativa do seu currículo.')
		self.assertEqual(self.aluno.historico.get(codigo='ENG1234').grupo, '')

	def test_na_conferencia_do_ocr_muda_so_a_sessao(self):
		dados = dados_espelho([linha('INF1026', 'EA'), linha('ENG1234', 'EA')], curso='CEG', habilitacao='XYZ', enfase='')
		dados['ocr'] = {'codigos': 2, 'situacoes': 2}
		with patch('GradePuc.views.ler_espelho_por_ocr', return_value=dados):
			self.client.post('/perfil/', {'acao': 'enviar_espelho', 'espelho': _pdf()})
		resposta = self.client.post('/perfil/', {'acao': 'conta_como', 'linha': '1', 'grupo': 'ENG0561'}, follow=True)
		self.assertContains(resposta, 'ENG1234 agora conta como ENG0561.')
		self.assertEqual(self.client.session[CHAVE_LEITURA_OCR]['dados']['disciplinas'][1]['grupo'], 'ENG0561')
		self.assertEqual(self.aluno.historico.get(codigo='ENG1234').grupo, '')     # banco não mudou
		self.assertContains(resposta, 'conta como ENG0561')


def _pdf():
	from .tests_ocr import pdf_enviado     # PDF sem texto: vai para o OCR (que o teste troca)
	return pdf_enviado()


class CasoEngenhariaDeProducaoTests(TestCase):
	"""Regressão: CEG / BPD / CCB, Engenharia de Produção 2023 (FAR), com o currículo real que
	a migration carrega e um histórico inventado parecido com o de quem testou."""

	def setUp(self):
		self.aluno = criar_aluno('9300003')
		self.client.force_login(self.aluno.usuario)
		far = Curriculo.objects.get(curso_nome='Engenharia de Produção', enfase__contains='FAR')
		LigacaoHabilitacao.objects.create(
			curso_sigla='CEG', habilitacao_sigla='BPD', enfase_sigla='CCB', curriculo=far, origem='aluno',
		)
		concluidas = [linha(c, 'AP', '20261', tipo='OB') for c in ('CTC4001', 'CTC4002', 'CTC4003', 'ENG4010')]
		concluidas += [linha('EMP1310', 'AP', '20261', tipo='OC'), linha('ENG4025', 'AP', '20261', tipo='OC'),
		               linha('MAT4181', 'AP', '20261', tipo='OB', grupo='MAT4161')]
		em_andamento = [linha(c, 'EA') for c in (
			'CRE1200', 'EMP1320', 'ENG4015', 'ENG4020', 'ENG4021', 'FIS4001', 'INF1026', 'MAT4162',
		)]
		salvar_espelho(self.aluno, dados_espelho(concluidas + em_andamento, curso='CEG', habilitacao='BPD', enfase='CCB'))

	def test_inf1026_fecha_inf0307_e_cre1200_nao_fecha_cre0712(self):
		pendentes, conta_como = ocupacao_das_vagas(self.aluno)
		codigos = [item.codigo for item in pendentes]
		self.assertNotIn('INF0307', codigos)
		self.assertIn('CRE0712', codigos)
		self.assertNotIn('MAT4161', codigos)            # equivalência do SAU (MAT4181)
		self.assertEqual(list(conta_como.values()), ['INF0307'])
		self.assertFalse(set(codigos) & codigos_bloqueados(self.aluno))

	def test_tela_mostra_conta_como_e_proximas_sem_repetir(self):
		resposta = self.client.get('/perfil/')
		self.assertContains(resposta, 'conta como INF0307')
		proximas = [item.codigo for item in resposta.context['pendentes']]
		self.assertNotIn('INF0307', proximas)
		self.assertNotIn('INF1026', proximas)
		self.assertNotIn('CRE1200', proximas)
