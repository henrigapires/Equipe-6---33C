"""Testes do espelho do histórico e dos currículos.

Sem internet e sem PDF real: o espelho é simulado com palavras falsas
(texto + posição), no mesmo formato que o pdfplumber devolve.
"""
from django.contrib.auth.models import User
from django.test import TestCase

from .espelho import (
	EspelhoInvalido, EspelhoSemTexto, classificar_situacao, interpretar_paginas,
)
from .gerador_grades import gerar_grades
from .historico import pendentes_do_curriculo, remover_historico, salvar_espelho
from .ligacao import confirmar_curso, deduzir_curriculos
from .models import (
	Aluno, Curriculo, Disciplina, DisciplinaCurriculo, HistoricoDisciplina, LigacaoHabilitacao,
	Professor, RotinaPreferencias, Turma,
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


def criar_aluno(matricula):
	usuario = User.objects.create_user(username=matricula, password='Senha!123', first_name='Teste')
	return Aluno.objects.create(usuario=usuario, matricula=matricula, senha='')


def disciplina_espelho(codigo, situacao, periodo='20261', grupo='', creditos=4):
	return {
		'periodo': periodo, 'codigo': codigo, 'nome': 'DISCIPLINA ' + codigo, 'turma': '3VA',
		'grau': '' if situacao == 'EA' else '8,0', 'situacao': situacao, 'tipo': 'Obrigatória',
		'grupo': grupo, 'creditos': creditos,
	}


def dados_espelho(disciplinas, curso='CEG', habilitacao='BCO', enfase='CCB'):
	return {
		'matricula': '1234567', 'curso': curso, 'habilitacao': habilitacao, 'enfase': enfase,
		'ano_curriculo': '2023', 'codigo_curriculo': 'X99', 'cr': '7,25', 'disciplinas': disciplinas,
	}


def criar_curriculo(nome, codigos, enfase='', ano=2023):
	curriculo = Curriculo.objects.create(
		curso_nome=nome, ano=ano, enfase=enfase, titulo=nome,
		url_pagina='https://exemplo.invalid/' + nome.replace(' ', '_'),
	)
	for ordem, (codigo, periodo) in enumerate(codigos):
		DisciplinaCurriculo.objects.create(
			curriculo=curriculo, codigo=codigo, nome='Disciplina ' + codigo, periodo=periodo,
			creditos=4, ordem=ordem, eh_grupo=codigo[3] == '0',
		)
	return curriculo


class SalvarEspelhoTests(TestCase):
	def setUp(self):
		self.aluno = criar_aluno('1111111')
		self.mat_a = Disciplina.objects.create(codigo='MAT9161', nome='Cálculo Teste I')
		self.mat_b = Disciplina.objects.create(codigo='MAT9161', nome='Cálculo Teste I (cópia)')
		self.reprovada = Disciplina.objects.create(codigo='ENG9000', nome='Reprovada')

	def salvar_padrao(self):
		return salvar_espelho(self.aluno, dados_espelho([
			disciplina_espelho('MAT9181', 'AP', grupo='MAT9161'),
			disciplina_espelho('INF9009', 'EA', periodo='20262'),
			disciplina_espelho('ENG9000', 'RF', periodo='20262'),
		]))

	def cursadas(self):
		return set(self.aluno.disciplinas_cursadas.values_list('codigo', flat=True))

	def test_cria_historico_e_preenche_o_curso(self):
		self.salvar_padrao()
		self.aluno.refresh_from_db()
		self.assertEqual(self.aluno.historico.count(), 3)
		self.assertEqual(
			(self.aluno.curso_sigla, self.aluno.habilitacao_sigla, self.aluno.enfase_sigla), ('CEG', 'BCO', 'CCB')
		)
		self.assertEqual(self.aluno.matricula_espelho, '1234567')
		self.assertIsNotNone(self.aluno.espelho_importado_em)

	def test_cria_disciplina_que_nao_existia(self):
		self.salvar_padrao()
		nova = Disciplina.objects.get(codigo='INF9009')
		self.assertEqual(nova.departamento, 'INF')
		self.assertEqual(nova.creditos, 4)
		self.assertEqual(HistoricoDisciplina.objects.get(codigo='INF9009').disciplina, nova)

	def test_cursadas_incluem_em_andamento_e_grupo(self):
		self.salvar_padrao()
		self.assertEqual(self.cursadas(), {'MAT9181', 'INF9009', 'MAT9161'})
		ids = set(self.aluno.disciplinas_cursadas.values_list('id', flat=True))
		self.assertIn(self.mat_a.id, ids)
		self.assertIn(self.mat_b.id, ids)
		self.assertNotIn(self.reprovada.id, ids)

	def test_reenvio_substitui_em_vez_de_duplicar(self):
		self.salvar_padrao()
		salvar_espelho(self.aluno, dados_espelho([disciplina_espelho('ENG9000', 'AP')]))
		self.assertEqual(self.aluno.historico.count(), 1)
		self.assertEqual(self.cursadas(), {'ENG9000'})

	def test_remover_historico_mantem_cursadas_manuais(self):
		manual = Disciplina.objects.create(codigo='HIS9001', nome='Marcada à mão')
		self.aluno.disciplinas_cursadas.add(manual)
		self.salvar_padrao()
		remover_historico(self.aluno)
		self.aluno.refresh_from_db()
		self.assertEqual(self.aluno.historico.count(), 0)
		self.assertEqual(self.aluno.curso_sigla, '')
		self.assertIsNone(self.aluno.espelho_importado_em)
		self.assertEqual(self.cursadas(), {'HIS9001'})


class GradesRespeitamHistoricoTests(TestCase):
	def test_nao_sugere_cursada_em_andamento_nem_equivalente(self):
		aluno = criar_aluno('2222222')
		professor = Professor.objects.create(nome='Professor Teste')
		horarios = ['SEG 07-09', 'TER 07-09', 'QUA 07-09', 'QUI 07-09', 'SEX 07-09', 'SEG 09-11', 'TER 09-11']
		codigos = ['MAT9161', 'INF9009', 'MAT9171', 'ADM9001', 'ECO9001', 'HIS9001', 'LET9001']
		for codigo, horario in zip(codigos, horarios):
			disciplina = Disciplina.objects.create(codigo=codigo, nome='Disciplina ' + codigo)
			Turma.objects.create(
				disciplina=disciplina, professor=professor, codigo_turma='3VA',
				dias_horarios=horario, vagas=30, sala='L100',
			)
		preferencias = RotinaPreferencias.objects.create(
			aluno=aluno, turno='sem_preferencia', modalidade='hibrido',
			distribuicao_aulas='tanto_faz', janelas='tanto_faz', carga_disciplinas='leve',
		)

		salvar_espelho(aluno, dados_espelho([
			disciplina_espelho('MAT9161', 'AP'),
			disciplina_espelho('INF9009', 'EA', periodo='20262'),
			disciplina_espelho('MAT9181', 'AP', grupo='MAT9171'),
		]))

		grades = gerar_grades(aluno, preferencias)
		self.assertTrue(grades)
		sugeridos = {turma.disciplina.codigo for grade in grades for turma in grade['turmas']}
		self.assertFalse(sugeridos & {'MAT9161', 'INF9009', 'MAT9171'})
		self.assertTrue(sugeridos <= {'ADM9001', 'ECO9001', 'HIS9001', 'LET9001'})


class LigacaoDeSiglasTests(TestCase):
	def setUp(self):
		self.computacao = criar_curriculo(
			'Engenharia de Computação', [('MAT9161', 1), ('INF9009', 1), ('INF9037', 2), ('ELL0900', None)]
		)
		self.producao = criar_curriculo(
			'Engenharia de Produção', [('MAT9161', 1), ('ENG9300', 2)], enfase='Sistemas Produtivos (SPR)'
		)
		LigacaoHabilitacao.objects.create(
			curso_sigla='CEG', habilitacao_sigla='BCO', enfase_sigla='',
			curriculo=self.computacao, origem='pre_cadastro',
		)

	def espelho_de_producao(self, codigo='MAT9161'):
		return dados_espelho([disciplina_espelho(codigo, 'AP')], curso='CTC', habilitacao='BPR', enfase='SPR')

	def ligacao_de_producao(self):
		return LigacaoHabilitacao.objects.get(curso_sigla='CTC', habilitacao_sigla='BPR', enfase_sigla='SPR')

	def test_pre_cadastro_vale_para_qualquer_enfase(self):
		for matricula, enfase in [('3000001', 'CCB'), ('3000002', 'XYZ')]:
			aluno = criar_aluno(matricula)
			reconhecido = salvar_espelho(aluno, dados_espelho([disciplina_espelho('MAT9161', 'AP')], enfase=enfase))
			self.assertTrue(reconhecido)
			self.assertFalse(aluno.precisa_confirmar_curso)

	def test_sigla_desconhecida_cria_pendencia(self):
		aluno = criar_aluno('3000003')
		self.assertFalse(salvar_espelho(aluno, self.espelho_de_producao()))
		self.assertTrue(aluno.precisa_confirmar_curso)
		self.assertIsNone(self.ligacao_de_producao().curriculo)

	def test_confirmar_curso_resolve_para_o_proximo_aluno(self):
		primeiro = criar_aluno('3000004')
		salvar_espelho(primeiro, self.espelho_de_producao('ENG9300'))
		self.assertTrue(confirmar_curso(primeiro, self.producao))
		self.assertFalse(primeiro.precisa_confirmar_curso)

		segundo = criar_aluno('3000005')
		self.assertTrue(salvar_espelho(segundo, self.espelho_de_producao()))
		ligacao = self.ligacao_de_producao()
		self.assertEqual((ligacao.curriculo, ligacao.origem, ligacao.confirmado_por), (self.producao, 'aluno', primeiro))

	def test_confirmar_nao_sobrescreve_ligacao_do_admin(self):
		LigacaoHabilitacao.objects.create(
			curso_sigla='CTC', habilitacao_sigla='BPR', enfase_sigla='SPR', curriculo=self.producao, origem='admin',
		)
		aluno = criar_aluno('3000006')
		salvar_espelho(aluno, self.espelho_de_producao())
		self.assertFalse(confirmar_curso(aluno, self.computacao))
		self.assertEqual(self.ligacao_de_producao().curriculo, self.producao)

	def test_pendentes_do_curriculo(self):
		aluno = criar_aluno('3000007')
		salvar_espelho(aluno, dados_espelho([disciplina_espelho('MAT9161', 'AP'), disciplina_espelho('INF9009', 'EA')]))
		self.assertEqual([i.codigo for i in pendentes_do_curriculo(aluno)], ['INF9037', 'ELL0900'])


class DeducaoDeCurriculoTests(TestCase):
	def test_codigos_raros_pesam_mais(self):
		comum = [('MAT9161', 1), ('MAT9162', 1), ('FIS9001', 1)]
		computacao = criar_curriculo('Engenharia de Computação', comum + [('INF9009', 2), ('INF9037', 2)])
		criar_curriculo('Engenharia de Produção', comum + [('ENG9300', 2)])
		criar_curriculo('Engenharia Civil', comum + [('CIV9001', 2)])

		aluno = criar_aluno('4000001')
		salvar_espelho(aluno, dados_espelho([
			disciplina_espelho('MAT9161', 'AP'), disciplina_espelho('MAT9162', 'AP'),
			disciplina_espelho('FIS9001', 'AP'), disciplina_espelho('INF9009', 'EA'),
		], curso='ZZZ', habilitacao='ZZZ', enfase=''))

		sugestoes = deduzir_curriculos(aluno)
		self.assertEqual(sugestoes[0]['curriculo'], computacao)
		self.assertTrue(sugestoes[0]['forte'])
		self.assertGreater(sugestoes[0]['pontos'], sugestoes[1]['pontos'])

	def test_sem_historico_nao_sugere_nada(self):
		self.assertEqual(deduzir_curriculos(criar_aluno('4000002')), [])
