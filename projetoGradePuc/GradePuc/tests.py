import re

from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse

from .models import Aluno, Disciplina, RotinaPreferencias


def criar_preferencias_completas(aluno):
	RotinaPreferencias.objects.create(
		aluno=aluno, turno='sem_preferencia', modalidade='hibrido',
		distribuicao_aulas='tanto_faz', janelas='tanto_faz', carga_disciplinas='media',
	)


class PreRequisitosApiTests(TestCase):
	def setUp(self):
		usuario = User.objects.create_user(username='12345', password='Senha!123')
		self.aluno = Aluno.objects.create(
			usuario=usuario, matricula='12345', senha='teste'
		)
		self.client.force_login(usuario)
		self.introducao = Disciplina.objects.create(codigo='ENG100', nome='Introdução')
		self.calculo = Disciplina.objects.create(codigo='MAT200', nome='Cálculo')
		self.calculo.pre_requisitos.add(self.introducao)

	def test_api_returns_discipline_and_prerequisite(self):
		response = self.client.get(reverse('api_disciplina', args=[self.calculo.id]))

		self.assertEqual(response.status_code, 200)
		dados = response.json()
		# os campos de sempre continuam iguais...
		self.assertEqual({chave: dados[chave] for chave in ('id', 'codigo', 'nome', 'pre_requisitos')}, {
			'id': self.calculo.id,
			'codigo': 'MAT200',
			'nome': 'Cálculo',
			'pre_requisitos': [{
				'id': self.introducao.id,
				'codigo': 'ENG100',
				'nome': 'Introdução',
			}],
		})
		# ...e chegam os do painel Detalhes
		for chave in ('creditos', 'periodo', 'status', 'pre', 'co', 'libera', 'nivelamento', 'ementa_url'):
			self.assertIn(chave, dados)
		self.assertEqual(dados['ementa_url'], '/eletivas/MAT200/')

	def test_api_exige_login(self):
		self.client.logout()
		response = self.client.get(reverse('api_disciplina', args=[self.calculo.id]))
		self.assertEqual(response.status_code, 302)

	def test_api_returns_404_for_unknown_discipline(self):
		response = self.client.get(reverse('api_disciplina', args=[99999]))

		self.assertEqual(response.status_code, 404)

	def test_prerequisite_page_sem_curso_pede_o_perfil(self):
		# sem curso conhecido não há fluxograma: aviso + botão para o perfil (a busca continua)
		response = self.client.get('/pre-requisitos/')

		self.assertEqual(response.status_code, 200)
		self.assertContains(response, 'Ainda não sabemos qual é o seu curso')
		self.assertContains(response, 'Ir para o meu perfil')
		self.assertContains(response, 'Buscar qualquer disciplina')

	def test_distribution_questionnaire_renders_on_get(self):
		response = self.client.get('/questionario/distribuicao/')

		self.assertEqual(response.status_code, 200)
		self.assertContains(response, 'Como você prefere distribuir as aulas')


class TransicoesEntreTelasTests(TestCase):
	PAGINAS = [
		'/ajuda/',
		'/pre-requisitos/',
		'/eletivas/',
		'/resumodagrade/',
		'/grades-sugeridas/',
		'/questionario/',
		'/questionario/modalidade/',
		'/questionario/distribuicao/',
		'/questionario/janelas/',
		'/questionario/carga/',
	]

	def setUp(self):
		usuario = User.objects.create_user(username='9999999', password='Senha!123', first_name='Teste')
		aluno = Aluno.objects.create(usuario=usuario, matricula='9999999', senha='')
		criar_preferencias_completas(aluno)
		self.client.force_login(usuario)

	def destinos_internos(self, html):
		destinos = re.findall(r'href="([^"]*)"', html)
		destinos += re.findall(r"window\.location\.href\s*=\s*'([^']*)'", html)
		internos = []
		for destino in destinos:
			if not destino.startswith('/') or destino.startswith('//'):
				continue
			if destino.lower().startswith(('/static/', '/admin/', '/api/')):
				continue
			internos.append(destino)
		return internos

	def test_todos_os_links_e_botoes_levam_a_uma_pagina_que_existe(self):
		for pagina in self.PAGINAS:
			with self.subTest(pagina=pagina):
				resposta = self.client.get(pagina)
				self.assertEqual(resposta.status_code, 200)
				html = resposta.content.decode()

				self.assertEqual(html.count('href=""'), 0)
				for href in re.findall(r'href="([^"]*)"', html):
					self.assertFalse(href.endswith('.html'), href)

				destinos = self.destinos_internos(html)
				self.assertTrue(destinos)
				for destino in destinos:
					with self.subTest(pagina=pagina, destino=destino):
						self.assertIn(self.client.get(destino).status_code, [200, 302])


class BaseHtmlTests(TestCase):
	def setUp(self):
		usuario = User.objects.create_user(username='8888888', password='Senha!123', first_name='Teste')
		aluno = Aluno.objects.create(usuario=usuario, matricula='8888888', senha='')
		criar_preferencias_completas(aluno)
		self.client.force_login(usuario)

	def conferir(self, pagina, item_ativo):
		resposta = self.client.get(pagina)
		self.assertEqual(resposta.status_code, 200)
		html = resposta.content.decode()

		self.assertEqual(html.count('class="site-header"'), 1)
		self.assertEqual(html.count('class="site-footer"'), 1)
		self.assertEqual(html.count('<footer'), 1)
		self.assertNotIn('class="navbar"', html)
		self.assertNotIn('class="cabecalho"', html)

		self.assertIn('Olá, Teste', html)
		self.assertIn('<form action="/logout/" method="post"', html)
		self.assertIn('class="btn-sair"', html)

		ativos = re.findall(r'class="site-header__link ativo"\s*aria-current="page">([^<]+)</a>', html)
		self.assertEqual(ativos, [item_ativo])
		self.assertEqual(html.count('aria-current="page"'), 1)

	def test_resumo_da_grade(self):
		self.conferir('/resumodagrade/', 'Minha grade')

	def test_eletivas(self):
		self.conferir('/eletivas/', 'Minha grade')

	def test_pre_requisitos(self):
		self.conferir('/pre-requisitos/', 'Minha grade')

	def test_grades_sugeridas(self):
		self.conferir('/grades-sugeridas/', 'Grades sugeridas')

	def test_questionario(self):
		self.conferir('/questionario/', 'Questionário')

	def test_questionario_modalidade(self):
		self.conferir('/questionario/modalidade/', 'Questionário')

	def test_questionario_distribuicao(self):
		self.conferir('/questionario/distribuicao/', 'Questionário')

	def test_questionario_janelas(self):
		self.conferir('/questionario/janelas/', 'Questionário')

	def test_questionario_carga(self):
		self.conferir('/questionario/carga/', 'Questionário')

	def test_ajuda(self):
		self.conferir('/ajuda/', 'Ajuda')
