"""Testes do espelho do histórico e dos currículos.

Sem internet e sem PDF real: o espelho é simulado com palavras falsas
(texto + posição), no mesmo formato que o pdfplumber devolve.
"""
import tempfile
from io import StringIO
from pathlib import Path
from unittest.mock import patch

from django.contrib.auth.models import User
from django.core.files.uploadedfile import SimpleUploadedFile
from django.core.management import call_command
from django.test import TestCase

from .curriculos import escolher_mais_recentes, interpretar_pagina_curso, interpretar_titulo
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


def tabela(linhas, com_extensao=True):
	cabecalho = '<tr><td>Código</td><td>Nome da Disciplina</td><td>Créditos</td>'
	cabecalho += '<td>CH Semestral de Extensão</td></tr>' if com_extensao else '</tr>'
	return '<table class="puc_tabela_padrao_TAG-TABLE ccg_tabela_periodizacao">' + cabecalho + linhas + '</table>'


def linha(codigo, nome, creditos, extensao='&nbsp;'):
	return f'<tr><td><a href="#">{codigo}</a></td><td>{nome}</td><td>{creditos}</td><td>{extensao}</td></tr>'


def periodo(texto):
	return f'<tr><td colspan="4">{texto}</td></tr>'


HTML_CURSO = (
	'<html><body>'
	'<h4><a name="a"></a> Periodização - Engenharia Teste (Currículo 2023) - <a href="#a">Ênfase em Alfa (ALF)</a></h4>'
	+ tabela(
		periodo('1º PERÍODO')
		+ linha('MAT9161', 'Cálculo Teste', 4) + linha('ENG9010', 'Projeto Teste', 4, '60h')
		+ periodo('2° PERÍODO') + linha('ENG0561', 'Optativas de Engenharia', 8)
		+ periodo('PERÍODO LETIVO INDETERMINADO') + linha('ACP0900', 'Atividades Complementares', 10)
		+ periodo('Total de créditos: 26') + linha('LET9801', 'Observação depois do total', 2)
	)
	+ '<h4>Periodização - Engenharia Teste (Currículo 2023) - <a href="#b">Ênfase em Beta (BET)</a></h4>'
	+ tabela(periodo('1º PERÍODO') + linha('MAT9161', 'Cálculo Teste', 4))
	+ '<h4>Periodização - Engenharia Teste (Currículo 0 - anterior a 2023)</h4>'
	+ tabela(periodo('1º PERÍODO') + linha('MAT9001', 'Cálculo Antigo', 4), com_extensao=False)
	+ '<h4>Periodização - Engenharia Teste (Currículo 2021)</h4>'
	+ tabela(periodo('1º PERÍODO') + linha('MAT9002', 'Cálculo 2021', 4))
	+ '<h4>Estrutura do Ciclo Básico</h4>'
	+ tabela(linha('MAT9003', 'Não é periodização', 4))
	+ '</body></html>'
)


class LeituraDasPaginasDeCursoTests(TestCase):
	def test_le_secoes_periodos_grupos_e_ignora_totais(self):
		secoes, avisos = interpretar_pagina_curso(HTML_CURSO, 'https://exemplo.invalid/eng_teste.html')
		self.assertEqual(len(secoes), 4)
		self.assertEqual(avisos, [])

		alfa = secoes[0]
		self.assertEqual((alfa['curso_nome'], alfa['ano'], alfa['enfase']), ('Engenharia Teste', 2023, 'Alfa (ALF)'))
		self.assertEqual([i['codigo'] for i in alfa['itens']], ['MAT9161', 'ENG9010', 'ENG0561', 'ACP0900'])
		self.assertEqual([i['periodo'] for i in alfa['itens']], [1, 1, 2, None])
		self.assertEqual([i['eh_grupo'] for i in alfa['itens']], [False, False, True, True])
		self.assertEqual(alfa['itens'][1]['ch_extensao'], '60h')
		self.assertEqual(alfa['itens'][2]['creditos'], 8)

	def test_fica_so_com_o_ano_mais_recente_e_todas_as_enfases(self):
		secoes, _ = interpretar_pagina_curso(HTML_CURSO, 'https://exemplo.invalid/eng_teste.html')
		escolhidas = escolher_mais_recentes(secoes)
		self.assertEqual([(s['ano'], s['enfase']) for s in escolhidas], [(2023, 'Alfa (ALF)'), (2023, 'Beta (BET)')])

	def test_formatos_de_titulo_do_site(self):
		casos = {
			'Periodização – Design – currículo 2023': ('Design', 2023, '', None),
			'Periodização - Bacharelado em Filosofia - 2023': ('Bacharelado em Filosofia', 2023, '', None),
			'Periodização - Bacharelado em Filosofia (anterior a 2023)': ('Bacharelado em Filosofia', None, '', 2023),
			'Periodização - Comunicação Social - Cinema (Entrada de alunos até 2020)': ('Comunicação Social - Cinema', None, '', None),
			'Periodização - Psicologia - Bacharelado (Currículo 0 - 2023)': ('Psicologia - Bacharelado', 2023, 'Currículo 0', None),
			'Periodização: Bacharelado em Artes Cênicas (Currículo 2023)': ('Bacharelado em Artes Cênicas', 2023, '', None),
			'Periodização - Bacharelado em Direito - Ênfase em Penal - diurno (Currículo 2018)': ('Bacharelado em Direito', 2018, 'Penal - diurno', None),
			'Periodização - Bacharelado em Estudos de Mídia Ênfase Cinema e Audiovisual (Currículo2021)': ('Bacharelado em Estudos de Mídia', 2021, 'Cinema e Audiovisual', None),
		}
		for titulo, (curso, ano, enfase, anterior_a) in casos.items():
			with self.subTest(titulo=titulo):
				r = interpretar_titulo(titulo)
				self.assertEqual((r['curso_nome'], r['ano'], r['enfase'], r['anterior_a']), (curso, ano, enfase, anterior_a))

	def test_curso_sem_ano_fica_com_o_primeiro_listado(self):
		secoes = [
			{'curso_nome': 'Comunicação Social - Cinema', 'ano': None, 'enfase': '', 'anterior_a': None, 'url': 'u', 'itens': [1]},
			{'curso_nome': 'Comunicação Social - Cinema', 'ano': None, 'enfase': '', 'anterior_a': None, 'url': 'u', 'itens': [2]},
		]
		self.assertEqual(escolher_mais_recentes(secoes), [secoes[0]])


class ImportarCurriculosCommandTests(TestCase):
	def test_importa_do_cache_sem_internet_e_e_idempotente(self):
		paginas = {
			'cursos.html': '<div class="puc_layout_area-inicial_esquerda"><a href="eng_computacao.html">Computação</a>'
			               '<a href="comunicacao.html">Comunicação</a></div>',
			'eng_computacao.html': '<h4>Periodização - Engenharia de Computação (Currículo 2023)</h4>'
			                       + tabela(periodo('1º PERÍODO') + linha('INF9009', 'Programação Teste', 4)),
			'comunicacao.html': '<div class="puc_layout_area-inicial_esquerda"><a href="comunicacao_cinema.html">Cinema</a></div>',
			'comunicacao_cinema.html': '<h4>Periodização - Comunicação Social - Cinema (Entrada de alunos até 2020)</h4>'
			                           + tabela(periodo('1º PERÍODO') + linha('COM9001', 'Cinema Teste', 4)),
		}
		with tempfile.TemporaryDirectory() as pasta:
			for nome, html in paginas.items():
				Path(pasta, nome).write_text(html, encoding='utf-8')
			for _ in range(2):
				call_command('importar_curriculos', cache=pasta, stdout=StringIO())

		self.assertEqual(Curriculo.objects.count(), 2)
		self.assertEqual(DisciplinaCurriculo.objects.count(), 2)
		computacao = Curriculo.objects.get(curso_nome='Engenharia de Computação')
		self.assertEqual(computacao.ano, 2023)
		ligacao = LigacaoHabilitacao.objects.get(curso_sigla='CEG', habilitacao_sigla='BCO', enfase_sigla='')
		self.assertEqual((ligacao.curriculo, ligacao.origem), (computacao, 'pre_cadastro'))


class PerfilViewTests(TestCase):
	def setUp(self):
		self.aluno = criar_aluno('5000001')
		self.client.force_login(self.aluno.usuario)
		self.computacao = criar_curriculo('Engenharia de Computação', [('MAT9161', 1), ('INF9037', 2)])

	def enviar(self, nome, conteudo):
		arquivo = SimpleUploadedFile(nome, conteudo, content_type='application/pdf')
		return self.client.post('/perfil/', {'acao': 'enviar_espelho', 'espelho': arquivo}, follow=True)

	def enviar_espelho_falso(self):
		dados = dados_espelho([disciplina_espelho('MAT9161', 'AP'), disciplina_espelho('INF9009', 'EA', periodo='20262')])
		with patch('GradePuc.views.ler_espelho', return_value=dados):
			return self.enviar('espelho.pdf', b'%PDF-1.4 falso')

	def test_perfil_exige_login(self):
		self.client.logout()
		resposta = self.client.get('/perfil/')
		self.assertEqual(resposta.status_code, 302)
		self.assertTrue(resposta['Location'].startswith('/login/'))

	def test_perfil_sem_espelho(self):
		resposta = self.client.get('/perfil/')
		self.assertEqual(resposta.status_code, 200)
		self.assertContains(resposta, 'Você ainda não enviou o espelho do histórico.')
		self.assertContains(resposta, '<span class="site-header__ola">Olá, Teste</span>')
		self.assertRegex(resposta.content.decode(), r'href="/perfil/"\s*class="btn-sair btn-perfil ativo"\s*aria-current="page"')
		self.assertNotContains(resposta, 'site-header__aviso')

	def test_arquivo_que_nao_e_pdf(self):
		resposta = self.enviar('notas.txt', b'nao sou pdf')
		self.assertContains(resposta, 'Envie o espelho em formato PDF.')
		self.assertEqual(self.aluno.historico.count(), 0)

	def test_pdf_que_nao_abre_mostra_erro_sem_quebrar(self):
		resposta = self.enviar('espelho.pdf', b'%PDF-1.4 isto nao e um pdf de verdade')
		self.assertEqual(resposta.status_code, 200)
		self.assertContains(resposta, 'site-mensagem--error')
		self.assertEqual(self.aluno.historico.count(), 0)

	def test_pdf_que_nao_e_espelho(self):
		with patch('GradePuc.views.ler_espelho', side_effect=EspelhoInvalido('Este PDF não parece ser o Espelho do Histórico do SAU.')):
			resposta = self.enviar('boleto.pdf', b'%PDF-1.4')
		self.assertContains(resposta, 'Este PDF não parece ser o Espelho do Histórico do SAU.')

	def test_envio_confirmacao_do_curso_e_indicador_no_header(self):
		resposta = self.enviar_espelho_falso()
		self.assertContains(resposta, 'Histórico importado: 2 disciplinas.')
		self.assertContains(resposta, 'Confirme seu curso')
		self.assertContains(resposta, '<span class="site-header__aviso"> •<span class="site-header__aviso-texto"> confirmar curso</span></span>')
		self.assertContains(resposta, 'Em andamento')
		self.assertEqual(self.aluno.historico.count(), 2)

		resposta = self.client.post('/perfil/', {'acao': 'confirmar_curso', 'curriculo': self.computacao.id}, follow=True)
		self.assertContains(resposta, 'Curso confirmado')
		self.assertContains(resposta, 'Curso reconhecido')
		self.assertNotContains(resposta, 'site-header__aviso')
		self.assertContains(resposta, 'INF9037')

	def test_remover_historico_exige_confirmacao(self):
		self.enviar_espelho_falso()
		resposta = self.client.post('/perfil/', {'acao': 'remover_historico'}, follow=True)
		self.assertContains(resposta, 'Marque a confirmação')
		self.assertEqual(self.aluno.historico.count(), 2)

		resposta = self.client.post('/perfil/', {'acao': 'remover_historico', 'confirmo': 'sim'}, follow=True)
		self.assertContains(resposta, 'Seu histórico foi removido.')
		self.aluno.refresh_from_db()
		self.assertEqual(self.aluno.historico.count(), 0)
		self.assertEqual(self.aluno.curso_sigla, '')
		self.assertEqual(self.aluno.disciplinas_cursadas.count(), 0)


class CadastroComEspelhoTests(TestCase):
	def cadastrar(self, arquivo=None):
		dados = {'nome': 'Teste Silva', 'matricula': '6000001', 'email': '', 'password': 'Senha!123', 'confirmar_senha': 'Senha!123'}
		if arquivo:
			dados['espelho'] = arquivo
		return self.client.post('/cadastro/', dados, follow=True)

	def test_formulario_aceita_arquivo(self):
		resposta = self.client.get('/cadastro/')
		self.assertContains(resposta, 'enctype="multipart/form-data"')
		self.assertContains(resposta, 'name="espelho"')

	def test_cadastro_sem_espelho_continua_igual(self):
		resposta = self.cadastrar()
		self.assertEqual(resposta.redirect_chain, [('/', 302)])
		aluno = Aluno.objects.get(matricula='6000001')
		self.assertEqual(aluno.usuario.first_name, 'Teste')
		self.assertEqual(aluno.historico.count(), 0)
		self.assertNotContains(resposta, 'site-mensagem')

	def test_cadastro_com_espelho(self):
		dados = dados_espelho([disciplina_espelho('MAT9161', 'AP')])
		with patch('GradePuc.views.ler_espelho', return_value=dados):
			resposta = self.cadastrar(SimpleUploadedFile('espelho.pdf', b'%PDF-1.4', content_type='application/pdf'))
		self.assertContains(resposta, 'Conta criada! Histórico importado: 1 disciplinas.')
		self.assertEqual(Aluno.objects.get(matricula='6000001').historico.count(), 1)

	def test_pdf_com_erro_nao_impede_o_cadastro(self):
		resposta = self.cadastrar(SimpleUploadedFile('espelho.pdf', b'%PDF-1.4 quebrado', content_type='application/pdf'))
		self.assertContains(resposta, 'Conta criada, mas o espelho não foi importado')
		self.assertTrue(User.objects.filter(username='6000001').exists())
		self.assertEqual(Aluno.objects.get(matricula='6000001').historico.count(), 0)


class AdminDoEspelhoTests(TestCase):
	def setUp(self):
		admin = User.objects.create_superuser('admin_teste', 'admin@exemplo.invalid', 'Senha!123')
		self.client.force_login(admin)
		self.aluno = criar_aluno('7000001')
		self.curriculo = criar_curriculo('Engenharia de Produção', [('MAT9161', 1)])
		salvar_espelho(self.aluno, dados_espelho([disciplina_espelho('MAT9161', 'AP')], curso='CTC', habilitacao='BPR', enfase='SPR'))
		self.pendencia = LigacaoHabilitacao.objects.get(curso_sigla='CTC')

	def test_paginas_do_admin_abrem(self):
		paginas = [
			'/admin/GradePuc/aluno/', f'/admin/GradePuc/aluno/{self.aluno.id}/change/',
			'/admin/GradePuc/historicodisciplina/', '/admin/GradePuc/historicodisciplina/?situacao=AP',
			'/admin/GradePuc/curriculo/', f'/admin/GradePuc/curriculo/{self.curriculo.id}/change/',
			'/admin/GradePuc/ligacaohabilitacao/',
		]
		for pagina in paginas:
			with self.subTest(pagina=pagina):
				self.assertEqual(self.client.get(pagina).status_code, 200)

		resposta = self.client.get(f'/admin/GradePuc/aluno/{self.aluno.id}/change/')
		self.assertContains(resposta, 'MAT9161')

	def test_filtro_sem_ligacao(self):
		resposta = self.client.get('/admin/GradePuc/ligacaohabilitacao/?ligacao=sem')
		self.assertContains(resposta, 'SPR')
		resposta = self.client.get('/admin/GradePuc/ligacaohabilitacao/?ligacao=com')
		self.assertNotContains(resposta, '>SPR<')

	def test_admin_resolve_a_sigla_pela_lista(self):
		resposta = self.client.post('/admin/GradePuc/ligacaohabilitacao/', {
			'form-TOTAL_FORMS': '1', 'form-INITIAL_FORMS': '1',
			'form-0-id': str(self.pendencia.id), 'form-0-curriculo': str(self.curriculo.id),
			'_save': 'Salvar',
		})
		self.assertEqual(resposta.status_code, 302)
		self.pendencia.refresh_from_db()
		self.assertEqual((self.pendencia.curriculo, self.pendencia.origem), (self.curriculo, 'admin'))
		self.assertFalse(Aluno.objects.get(id=self.aluno.id).precisa_confirmar_curso)


class AvisosDoPerfilTests(TestCase):
	AVISO_PRIVACIDADE = 'O PDF não é guardado: só lemos os dados e descartamos o arquivo.'

	def setUp(self):
		self.aluno = criar_aluno('8000001')
		self.client.force_login(self.aluno.usuario)

	def test_aviso_de_privacidade_no_perfil_e_no_cadastro(self):
		self.assertContains(self.client.get('/perfil/'), self.AVISO_PRIVACIDADE, count=1)
		self.client.logout()
		self.assertContains(self.client.get('/cadastro/'), self.AVISO_PRIVACIDADE, count=1)

	def test_aviso_de_substituir_so_quando_ja_tem_historico(self):
		self.assertNotContains(self.client.get('/perfil/'), 'substitui')
		salvar_espelho(self.aluno, dados_espelho([disciplina_espelho('MAT9161', 'AP')]))
		resposta = self.client.get('/perfil/')
		self.assertContains(resposta, 'Enviar um novo espelho <strong>substitui</strong> o histórico anterior.')
		self.assertContains(resposta, '<input type="checkbox" name="confirmo" value="sim" required>')

	def test_link_para_grades_so_logo_depois_de_importar(self):
		link = '<a href="/grades-sugeridas/" class="perfil__link-grades">Ver grades sugeridas</a>'
		dados = dados_espelho([disciplina_espelho('MAT9161', 'AP')])
		with patch('GradePuc.views.ler_espelho', return_value=dados):
			arquivo = SimpleUploadedFile('espelho.pdf', b'%PDF-1.4', content_type='application/pdf')
			resposta = self.client.post('/perfil/', {'acao': 'enviar_espelho', 'espelho': arquivo}, follow=True)
		self.assertContains(resposta, link)
		self.assertNotContains(self.client.get('/perfil/'), link)

	def test_sem_link_para_grades_quando_o_envio_falha(self):
		arquivo = SimpleUploadedFile('notas.txt', b'texto', content_type='text/plain')
		resposta = self.client.post('/perfil/', {'acao': 'enviar_espelho', 'espelho': arquivo}, follow=True)
		self.assertNotContains(resposta, 'Ver grades sugeridas')
