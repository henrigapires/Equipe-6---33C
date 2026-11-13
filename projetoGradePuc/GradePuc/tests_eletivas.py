"""Banco de eletivas (grupos de optativas) e sugestão de eletivas para as grades sugeridas.

Os códigos de grupo são os reais de Engenharia de Produção 2023 (ENG0561, FIL0300...);
as disciplinas, turmas e horários são inventados.
"""
import importlib
import json

from django.apps import apps
from django.test import TestCase

from .eletivas import horarios_da_turma, sugerir_eletivas, sugerir_para_grades, turmas_candidatas
from .grupos import eletivas_do_curriculo, interpretar_ementa_do_grupo
from .models import (
	Curriculo, Disciplina, DisciplinaCurriculo, DisciplinaDoGrupo, HistoricoDisciplina,
	LigacaoHabilitacao, Professor, Requisito, RotinaPreferencias, Turma,
)
from .tests import criar_preferencias_completas
from .tests_espelho import criar_aluno

migracao = importlib.import_module('GradePuc.migrations.0009_carregar_grupos')

EMENTA_DO_GRUPO = """
<div id="cod_ttl_discp"><span id="hCodigo">ENG0561</span> | <span id="hTitulo">OPTATIVAS DE ADMINISTRAÇÃO</span></div>
<fieldset id="grupoDisciplina">
	<legend>Grupo de Disciplinas</legend>
	<span class="links">
		<p><a href='ementa.aspx?cd=ENG1021'>ENG1021</a><span>ADMINISTRACAO P/ENGENHEIROS</span></p>
		<p><a href='ementa.aspx?cd=ENG4500'>ENG4500</a><span>ADM E ECON PARA ENGENHEIROS</span></p>
		<p><a href='ementa.aspx?cd=ENG4500'>ENG4500</a><span>ADM E ECON PARA ENGENHEIROS</span></p>
	</span>
</fieldset>
"""

EMENTA_SEM_GRUPO = """
<div id="cod_ttl_discp"><span id="hCodigo">ELL0900</span> | <span id="hTitulo">ELETIVAS LIVRES</span></div>
<div id="divContent"><span class="erro">Disciplina sem ementa cadastrada.</span></div>
"""


class LeituraDaEmentaTests(TestCase):
	def test_le_as_disciplinas_do_grupo_sem_repetir(self):
		self.assertEqual(interpretar_ementa_do_grupo(EMENTA_DO_GRUPO), [
			('ENG1021', 'ADMINISTRACAO P/ENGENHEIROS'),
			('ENG4500', 'ADM E ECON PARA ENGENHEIROS'),
		])

	def test_eletivas_livres_nao_tem_lista(self):
		self.assertEqual(interpretar_ementa_do_grupo(EMENTA_SEM_GRUPO), [])


class MigrationDosGruposTests(TestCase):
	def test_banco_vazio_recebe_os_grupos_do_arquivo(self):
		DisciplinaDoGrupo.objects.all().delete()
		migracao.carregar_grupos(apps, None)
		arquivo = json.loads(migracao.ARQUIVO.read_text(encoding='utf-8'))
		total = 0
		for disciplinas in arquivo['grupos'].values():
			total += len(disciplinas)
		self.assertEqual(DisciplinaDoGrupo.objects.count(), total)
		self.assertTrue(DisciplinaDoGrupo.objects.filter(grupo='ENG0561', codigo='ENG4500').exists())


class LeituraDoHorarioTests(TestCase):
	def turma(self, dias_horarios, sala='L100'):
		return Turma(dias_horarios=dias_horarios, sala=sala)

	def test_formato_normal(self):
		self.assertEqual(horarios_da_turma(self.turma('TER 13-15; QUI 13-15')), [(1, 780, 900), (3, 780, 900)])

	def test_sabado_com_acento(self):
		self.assertEqual(horarios_da_turma(self.turma('SÁB 08-12')), [(5, 480, 720)])

	def test_hora_que_foi_parar_na_sala(self):
		# Linha do Excel "SEG 13-16" sem sala: o import guardou "SEG" e sala "13-16".
		self.assertEqual(horarios_da_turma(self.turma('SEG; QUA', sala='13-16')), [(0, 780, 960), (2, 780, 960)])

	def test_sem_horario(self):
		self.assertIsNone(horarios_da_turma(self.turma('')))
		self.assertIsNone(horarios_da_turma(self.turma('SEG', sala='L100')))


class EletivasTestCase(TestCase):
	"""Currículo pequeno de Produção: duas obrigatórias e três grupos de optativa.

	ENG0561 (3º período): ENG9500, ENG9501
	FIL0300 (6º período): FIL9001 (pré-requisito FIL9000), FIL9002
	CRE0712 (3º período): MAT9161, que também é obrigatória, então não conta como eletiva
	"""

	@classmethod
	def setUpTestData(cls):
		# O migrate já carrega currículos e grupos de verdade: aqui começamos do zero.
		LigacaoHabilitacao.objects.all().delete()
		DisciplinaCurriculo.objects.all().delete()
		Curriculo.objects.all().delete()
		DisciplinaDoGrupo.objects.all().delete()
		# Os requisitos de verdade (migration 0011) também saem: códigos daqui, como ENG9500,
		# existem na PUC e têm pré-requisito. Cada teste cria os requisitos de que precisa.
		Requisito.objects.all().delete()

	def setUp(self):
		self.curriculo = Curriculo.objects.create(
			curso_nome='Engenharia de Produção', ano=2023, enfase='Sistemas Produtivos (SPR)',
			titulo='Periodização - Engenharia de Produção', url_pagina='https://www.puc-rio.br',
		)
		itens = [
			(1, 'MAT9161', False), (1, 'ENG9001', False),
			(3, 'ENG0561', True), (3, 'CRE0712', True), (6, 'FIL0300', True),
		]
		ordem = 0
		for periodo, codigo, eh_grupo in itens:
			DisciplinaCurriculo.objects.create(
				curriculo=self.curriculo, periodo=periodo, codigo=codigo, nome='Item ' + codigo,
				eh_grupo=eh_grupo, ordem=ordem,
			)
			ordem += 1
		LigacaoHabilitacao.objects.create(
			curso_sigla='CTC', habilitacao_sigla='BPR', enfase_sigla='SPR',
			curriculo=self.curriculo, origem='admin',
		)
		grupos = [
			('ENG0561', 'ENG9500'), ('ENG0561', 'ENG9501'),
			('FIL0300', 'FIL9001'), ('FIL0300', 'FIL9002'),
			('CRE0712', 'MAT9161'),
		]
		for grupo, codigo in grupos:
			DisciplinaDoGrupo.objects.create(grupo=grupo, codigo=codigo, nome='Disciplina ' + codigo)

		self.professor = Professor.objects.create(nome='Professor Teste')
		self.aluno = criar_aluno('3333333')
		self.aluno.curso_sigla = 'CTC'
		self.aluno.habilitacao_sigla = 'BPR'
		self.aluno.enfase_sigla = 'SPR'
		self.aluno.save()

	def criar_turma(self, codigo, horario, creditos=4, vagas=30, sala='L100', codigo_turma='3VA', destino=''):
		disciplina = Disciplina.objects.filter(codigo=codigo).first()
		if disciplina is None:
			disciplina = Disciplina.objects.create(codigo=codigo, nome='Disciplina ' + codigo, creditos=creditos)
		return Turma.objects.create(
			disciplina=disciplina, professor=self.professor, codigo_turma=codigo_turma,
			dias_horarios=horario, vagas=vagas, sala=sala, destino=destino,
		)

	def preferencias(self, turno='sem_preferencia', modalidade='hibrido', distribuicao='tanto_faz',
	                 janelas='tanto_faz', carga='media'):
		return RotinaPreferencias(
			aluno=self.aluno, turno=turno, modalidade=modalidade, distribuicao_aulas=distribuicao,
			janelas=janelas, carga_disciplinas=carga,
		)

	def grade(self, *turmas):
		"""Uma grade no mesmo formato que gerar_grades devolve."""
		return {'turmas': list(turmas), 'pontuacao': 0}

	def codigos(self, sugestoes):
		codigos = []
		for sugestao in sugestoes:
			codigos.append(sugestao['turma'].disciplina.codigo)
		return codigos


class BancoDeEletivasTests(EletivasTestCase):
	def test_so_disciplinas_dos_grupos_do_curriculo_com_turma(self):
		self.criar_turma('ENG9500', 'SEG 07-09')
		self.criar_turma('MAT9161', 'TER 07-09')     # está num grupo, mas é obrigatória
		self.criar_turma('INF9037', 'QUA 07-09')     # não está em grupo nenhum
		DisciplinaDoGrupo.objects.create(grupo='INF0307', codigo='INF9037', nome='De outro curso')
		Disciplina.objects.create(codigo='ENG9501', nome='Sem turma')

		resultado = {}
		for disciplina, grupos in eletivas_do_curriculo(self.curriculo).items():
			resultado[disciplina.codigo] = grupos
		self.assertEqual(resultado, {'ENG9500': ['ENG0561']})


class SugestaoDeEletivasTests(EletivasTestCase):
	def test_conflito_de_horario(self):
		obrigatoria = self.criar_turma('ENG9001', 'SEG 07-09')
		self.criar_turma('ENG9500', 'SEG 08-10')     # bate com a obrigatória
		self.criar_turma('ENG9501', 'TER 07-09')

		sugestoes = sugerir_eletivas(self.aluno, self.preferencias(), self.grade(obrigatoria))
		self.assertEqual(self.codigos(sugestoes), ['ENG9501'])

	def test_grades_diferentes_recebem_eletivas_diferentes(self):
		segunda = self.criar_turma('ENG9001', 'SEG 07-09')
		terca = self.criar_turma('MAT9161', 'TER 07-09')
		self.criar_turma('ENG9500', 'SEG 07-09')
		self.criar_turma('ENG9501', 'TER 07-09')

		por_grade = sugerir_para_grades(
			self.aluno, self.preferencias(), [self.grade(segunda), self.grade(terca)]
		)
		self.assertEqual(self.codigos(por_grade[0]), ['ENG9501'])
		self.assertEqual(self.codigos(por_grade[1]), ['ENG9500'])

	def test_turnos_diferentes(self):
		obrigatoria = self.criar_turma('ENG9001', 'SEX 07-09')
		self.criar_turma('ENG9500', 'SEG 09-11')     # manhã
		self.criar_turma('ENG9501', 'TER 14-16')     # tarde
		self.criar_turma('FIL9002', 'QUA 19-21')     # noite
		grade = self.grade(obrigatoria)

		self.assertEqual(self.codigos(sugerir_eletivas(self.aluno, self.preferencias(turno='manha'), grade)), ['ENG9500'])
		self.assertEqual(self.codigos(sugerir_eletivas(self.aluno, self.preferencias(turno='tarde'), grade)), ['ENG9501'])
		self.assertEqual(self.codigos(sugerir_eletivas(self.aluno, self.preferencias(turno='noite'), grade)), ['FIL9002'])
		todas = sugerir_eletivas(self.aluno, self.preferencias(turno='sem_preferencia'), grade)
		self.assertEqual(sorted(self.codigos(todas)), ['ENG9500', 'ENG9501', 'FIL9002'])

	def test_turma_que_passa_de_um_turno_para_outro_nao_entra(self):
		obrigatoria = self.criar_turma('ENG9001', 'SEX 07-09')
		self.criar_turma('ENG9500', 'SEG 09-11; QUA 13-15')
		sugestoes = sugerir_eletivas(self.aluno, self.preferencias(turno='manha'), self.grade(obrigatoria))
		self.assertEqual(sugestoes, [])

	def test_disciplina_ja_cursada(self):
		obrigatoria = self.criar_turma('ENG9001', 'SEG 07-09')
		eletiva = self.criar_turma('ENG9500', 'TER 07-09')
		self.criar_turma('ENG9501', 'QUA 07-09')
		self.aluno.disciplinas_cursadas.add(eletiva.disciplina)

		sugestoes = sugerir_eletivas(self.aluno, self.preferencias(), self.grade(obrigatoria))
		self.assertEqual(self.codigos(sugestoes), ['ENG9501'])

	def test_pre_requisito_nao_cumprido(self):
		obrigatoria = self.criar_turma('ENG9001', 'SEG 07-09')
		eletiva = self.criar_turma('FIL9001', 'TER 07-09')
		requisito = Disciplina.objects.create(codigo='FIL9000', nome='Requisito')
		eletiva.disciplina.pre_requisitos.add(requisito)
		grade = self.grade(obrigatoria)

		self.assertEqual(sugerir_eletivas(self.aluno, self.preferencias(), grade), [])

		self.aluno.disciplinas_cursadas.add(requisito)
		self.assertEqual(self.codigos(sugerir_eletivas(self.aluno, self.preferencias(), grade)), ['FIL9001'])

	def test_vaga_do_grupo_ja_preenchida(self):
		obrigatoria = self.criar_turma('ENG9001', 'SEG 07-09')
		self.criar_turma('ENG9501', 'TER 07-09')
		self.criar_turma('FIL9002', 'QUA 07-09')
		# Já fez ENG9500, que ocupa a única vaga de ENG0561.
		HistoricoDisciplina.objects.create(
			aluno=self.aluno, periodo='20261', codigo='ENG9500', nome='Disciplina ENG9500',
			situacao='AP', grupo='ENG0561', creditos=4,
		)
		sugestoes = sugerir_eletivas(self.aluno, self.preferencias(), self.grade(obrigatoria))
		self.assertEqual(self.codigos(sugestoes), ['FIL9002'])

	def test_limite_de_creditos_da_carga(self):
		# Grade de 16 créditos: na carga leve (até 19) só cabe a eletiva de 2 créditos.
		grade = self.grade(
			self.criar_turma('ENG9001', 'SEG 07-09', creditos=8),
			self.criar_turma('MAT9161', 'TER 07-09', creditos=8),
		)
		self.criar_turma('ENG9500', 'QUA 07-09', creditos=4)
		self.criar_turma('FIL9002', 'QUI 07-09', creditos=2)

		leve = sugerir_eletivas(self.aluno, self.preferencias(carga='leve'), grade)
		self.assertEqual(self.codigos(leve), ['FIL9002'])
		media = sugerir_eletivas(self.aluno, self.preferencias(carga='media'), grade)
		self.assertEqual(sorted(self.codigos(media)), ['ENG9500', 'FIL9002'])

	def test_modalidade(self):
		obrigatoria = self.criar_turma('ENG9001', 'SEG 07-09')
		self.criar_turma('ENG9500', 'TER 07-09', sala='VIRTUAL')
		self.criar_turma('ENG9501', 'QUA 07-09', sala='L100')
		grade = self.grade(obrigatoria)

		self.assertEqual(self.codigos(sugerir_eletivas(self.aluno, self.preferencias(modalidade='online'), grade)), ['ENG9500'])
		self.assertEqual(self.codigos(sugerir_eletivas(self.aluno, self.preferencias(modalidade='presencial'), grade)), ['ENG9501'])

	def test_ordem_pelo_encaixe_com_as_preferencias(self):
		obrigatoria = self.criar_turma('ENG9001', 'SEG 07-09')
		self.criar_turma('ENG9500', 'TER 09-11')     # ocupa mais um dia da semana
		self.criar_turma('ENG9501', 'SEG 09-11')     # no mesmo dia da obrigatória
		grade = self.grade(obrigatoria)

		# Quem quer um dia livre prefere a eletiva no dia que já tem aula.
		dia_livre = sugerir_eletivas(self.aluno, self.preferencias(distribuicao='dia_livre'), grade)
		self.assertEqual(self.codigos(dia_livre), ['ENG9501', 'ENG9500'])
		# Quem quer a semana equilibrada prefere espalhar.
		equilibrado = sugerir_eletivas(self.aluno, self.preferencias(distribuicao='equilibrado'), grade)
		self.assertEqual(self.codigos(equilibrado), ['ENG9500', 'ENG9501'])

	def test_mesma_turma_em_varios_destinos_aparece_uma_vez(self):
		obrigatoria = self.criar_turma('ENG9001', 'SEG 07-09')
		self.criar_turma('ENG9500', 'TER 07-09', vagas=2, destino='CCI')
		self.criar_turma('ENG9500', 'TER 07-09', vagas=12, destino='QQC')

		sugestoes = sugerir_eletivas(self.aluno, self.preferencias(), self.grade(obrigatoria))
		self.assertEqual(len(sugestoes), 1)
		self.assertEqual(sugestoes[0]['turma'].vagas, 12)

	def test_nenhuma_eletiva_possivel(self):
		obrigatoria = self.criar_turma('ENG9001', 'SEG 07-09; TER 07-09')
		self.criar_turma('ENG9500', 'SEG 07-09')
		self.criar_turma('ENG9501', 'TER 08-10')
		self.criar_turma('FIL9002', 'QUA 07-09', vagas=0)
		self.criar_turma('FIL9001', '')               # sem horário no micro-horário

		sugestoes = sugerir_eletivas(self.aluno, self.preferencias(), self.grade(obrigatoria))
		self.assertEqual(sugestoes, [])

	def test_aluno_sem_curriculo(self):
		self.aluno.curso_sigla = ''
		self.aluno.save()
		self.criar_turma('ENG9500', 'TER 07-09')
		self.assertEqual(turmas_candidatas(self.aluno, self.preferencias()), [])


class TelaDeEletivasTests(EletivasTestCase):
	def test_mostra_as_eletivas_de_cada_grade_sugerida(self):
		# Carga leve: o gerador monta grades de 3 obrigatórias.
		RotinaPreferencias.objects.create(
			aluno=self.aluno, turno='manha', modalidade='hibrido',
			distribuicao_aulas='tanto_faz', janelas='tanto_faz', carga_disciplinas='leve',
		)
		DisciplinaCurriculo.objects.create(curriculo=self.curriculo, periodo=2, codigo='ENG9002', nome='Item', ordem=9)
		self.criar_turma('ENG9001', 'SEG 07-09')
		self.criar_turma('MAT9161', 'TER 07-09')
		self.criar_turma('ENG9002', 'QUA 07-09')
		self.criar_turma('ENG9500', 'QUI 07-09')
		self.criar_turma('ENG9501', 'SEG 07-09')     # bate com ENG9001
		self.criar_turma('FIL9002', 'QUI 14-16')     # tarde

		self.client.force_login(self.aluno.usuario)
		html = self.client.get('/eletivas/').content.decode()
		self.assertIn('Para a Grade sugerida 1', html)
		self.assertIn('ENG9500', html)
		self.assertIn('Item ENG0561', html)     # "Conta como": nome do grupo no currículo
		self.assertNotIn('ENG9501', html)
		self.assertNotIn('FIL9002', html)

	def test_sem_questionario_vai_para_o_questionario(self):
		self.client.force_login(self.aluno.usuario)
		resposta = self.client.get('/eletivas/')
		self.assertRedirects(resposta, '/questionario/', fetch_redirect_response=False)

	def test_sem_curriculo_mostra_aviso(self):
		self.aluno.curso_sigla = ''
		self.aluno.save()
		criar_preferencias_completas(self.aluno)
		self.client.force_login(self.aluno.usuario)
		self.assertContains(self.client.get('/eletivas/'), 'Nenhuma eletiva encontrada.')


class EletivasComRequisitosDasEmentasTests(EletivasTestCase):
	"""Mesma regra do gerador (requisitos.py): pré-requisito das ementas e co-requisito
	cumprido por já ter cursado ou pela própria grade."""

	def requisito(self, disciplina, tipo, *alternativas):
		Requisito.objects.filter(disciplina=disciplina, tipo=tipo).delete()
		for numero, codigos in enumerate(alternativas):
			for codigo in codigos:
				Requisito.objects.create(disciplina=disciplina, tipo=tipo, alternativa=numero, codigo=codigo)

	def test_pre_requisito_nao_cumprido_nunca_e_sugerido(self):
		obrigatoria = self.criar_turma('ENG9001', 'SEG 07-09')
		self.criar_turma('FIL9001', 'TER 07-09')
		self.requisito('FIL9001', 'pre', ['ABC9000'], ['ABC8000'])   # outro prefixo: não ocupa vaga de FIL0300
		grade = self.grade(obrigatoria)
		self.assertEqual(sugerir_eletivas(self.aluno, self.preferencias(), grade), [])
		HistoricoDisciplina.objects.create(aluno=self.aluno, periodo='20251', codigo='ABC8000', nome='X', situacao='AP')
		self.assertEqual(self.codigos(sugerir_eletivas(self.aluno, self.preferencias(), grade)), ['FIL9001'])

	def test_co_requisito_cumprido_pela_propria_grade(self):
		sem_o_par = self.criar_turma('ENG9001', 'SEG 07-09')
		self.criar_turma('FIL9001', 'TER 07-09')
		self.requisito('FIL9001', 'co', ['ENG9001'])
		self.assertEqual(self.codigos(sugerir_eletivas(self.aluno, self.preferencias(), self.grade(sem_o_par))), ['FIL9001'])
		outra = self.criar_turma('MAT9161', 'QUA 07-09')
		self.assertEqual(sugerir_eletivas(self.aluno, self.preferencias(), self.grade(outra)), [])

	def test_co_requisito_cumprido_por_ja_ter_cursado(self):
		grade = self.grade(self.criar_turma('MAT9161', 'QUA 07-09'))
		self.criar_turma('FIL9001', 'TER 07-09')
		self.requisito('FIL9001', 'co', ['ENG9001'])
		HistoricoDisciplina.objects.create(aluno=self.aluno, periodo='20251', codigo='ENG9001', nome='X', situacao='AP')
		self.assertEqual(self.codigos(sugerir_eletivas(self.aluno, self.preferencias(), grade)), ['FIL9001'])
