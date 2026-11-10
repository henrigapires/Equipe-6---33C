"""Currículos que vêm junto com o projeto (migration 0007) e o "Confirme seu curso" do perfil.

Os históricos aqui são inventados; os códigos de disciplina são os dos currículos públicos da PUC.
"""
import importlib
import json
import re

from django.apps import apps
from django.test import TestCase

from .historico import salvar_espelho
from .models import Curriculo, DisciplinaCurriculo, LigacaoHabilitacao
from .tests_espelho import criar_aluno, dados_espelho, disciplina_espelho

migracao = importlib.import_module('GradePuc.migrations.0007_carregar_curriculos')


def esvaziar_curriculos():
	LigacaoHabilitacao.objects.all().delete()
	DisciplinaCurriculo.objects.all().delete()
	Curriculo.objects.all().delete()


class MigrationDosCurriculosTests(TestCase):
	def test_banco_vazio_recebe_os_curriculos_e_a_ligacao_ceg_bco(self):
		esvaziar_curriculos()
		migracao.carregar_curriculos(apps, None)
		arquivo = json.loads(migracao.ARQUIVO.read_text(encoding='utf-8'))
		self.assertEqual(Curriculo.objects.count(), len(arquivo['curriculos']))
		self.assertEqual(DisciplinaCurriculo.objects.count(), sum(len(c['itens']) for c in arquivo['curriculos']))
		self.assertGreater(Curriculo.objects.count(), 50)
		ligacao = LigacaoHabilitacao.objects.get(curso_sigla='CEG', habilitacao_sigla='BCO', enfase_sigla='')
		self.assertEqual(ligacao.origem, 'pre_cadastro')
		self.assertEqual(ligacao.curriculo.curso_nome, 'Engenharia de Computação')
		# a ordem das disciplinas é a do arquivo
		primeiro = arquivo['curriculos'][0]
		itens = Curriculo.objects.get(titulo=primeiro['titulo']).itens.order_by('ordem')
		self.assertEqual([i.codigo for i in itens], [linha[1] for linha in primeiro['itens']])

	def test_banco_que_ja_tem_curriculo_nao_muda(self):
		esvaziar_curriculos()
		Curriculo.objects.create(curso_nome='Já importado', ano=2025, titulo='Já importado', url_pagina='https://exemplo.invalid/')
		migracao.carregar_curriculos(apps, None)
		self.assertEqual(list(Curriculo.objects.values_list('titulo', flat=True)), ['Já importado'])
		self.assertFalse(LigacaoHabilitacao.objects.exists())

	def test_rodar_de_novo_nao_duplica(self):
		antes = Curriculo.objects.count()      # o banco de teste já passou pela migration
		migracao.carregar_curriculos(apps, None)
		self.assertEqual(Curriculo.objects.count(), antes)

	def test_arquivo_so_tem_curriculos_e_ligacoes_de_pre_cadastro(self):
		arquivo = json.loads(migracao.ARQUIVO.read_text(encoding='utf-8'))
		self.assertEqual(set(arquivo), {'sobre', 'colunas_dos_itens', 'curriculos', 'ligacoes_pre_cadastradas'})
		self.assertEqual(
			set(arquivo['curriculos'][0]), {'titulo', 'curso_nome', 'ano', 'enfase', 'url_pagina', 'itens'}
		)
		for ligacao in arquivo['ligacoes_pre_cadastradas']:
			self.assertEqual(set(ligacao), {'curso_sigla', 'habilitacao_sigla', 'enfase_sigla', 'curriculo'})


def historico_de_producao_inventado():
	"""Disciplinas dos primeiros períodos de Engenharia de Produção, como cursadas (notas inventadas)."""
	producao = Curriculo.objects.filter(curso_nome='Engenharia de Produção').first()
	itens = producao.itens.filter(eh_grupo=False, periodo__lte=4)
	return [disciplina_espelho(item.codigo, 'AP') for item in itens]


class ConfirmeSeuCursoTests(TestCase):
	def setUp(self):
		self.aluno = criar_aluno('9200001')
		self.client.force_login(self.aluno.usuario)

	def test_sem_curriculos_mostra_o_aviso_e_nao_o_select(self):
		esvaziar_curriculos()
		salvar_espelho(self.aluno, dados_espelho([disciplina_espelho('MAT9161', 'AP')], habilitacao='BPD'))
		resposta = self.client.get('/perfil/')
		self.assertContains(resposta, 'Os currículos ainda não foram carregados.')
		self.assertContains(resposta, 'python manage.py importar_curriculos')
		self.assertNotContains(resposta, 'name="curriculo"')
		self.assertNotContains(resposta, 'Confirmar curso')

	def test_caso_ceg_bpd_ccb_em_banco_novo_lista_os_cursos_e_sugere(self):
		# banco novo: só o que a migration carregou; siglas sem ligação pré-cadastrada
		salvar_espelho(self.aluno, dados_espelho(historico_de_producao_inventado(), curso='CEG', habilitacao='BPD', enfase='CCB'))
		resposta = self.client.get('/perfil/')
		self.assertContains(resposta, 'Confirme seu curso')
		self.assertNotContains(resposta, 'Os currículos ainda não foram carregados.')
		select = re.search(r'<select name="curriculo".*?</select>', resposta.content.decode('utf-8'), re.S).group(0)
		self.assertEqual(select.count('<option value="'), Curriculo.objects.count() + 1)   # + "Escolha seu curso"
		sugerido = resposta.context['sugerido']
		self.assertEqual(sugerido.curso_nome, 'Engenharia de Produção')
		self.assertContains(resposta, f'<option value="{sugerido.id}" selected>')
		self.assertContains(resposta, 'Confirmar curso')

	def test_ceg_bco_e_reconhecido_direto_pelo_pre_cadastro(self):
		salvar_espelho(self.aluno, dados_espelho([disciplina_espelho('CTC4001', 'AP')], curso='CEG', habilitacao='BCO', enfase='CCB'))
		resposta = self.client.get('/perfil/')
		self.assertContains(resposta, 'Curso reconhecido: <strong>Engenharia de Computação')
		self.assertNotContains(resposta, 'name="curriculo"')
