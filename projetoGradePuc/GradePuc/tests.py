import re

from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse

from .models import Aluno, Disciplina


class PreRequisitosApiTests(TestCase):
	def setUp(self):
		self.aluno = Aluno.objects.create(matricula='12345', senha='teste')
		self.introducao = Disciplina.objects.create(codigo='ENG100', nome='Introdução')
		self.calculo = Disciplina.objects.create(codigo='MAT200', nome='Cálculo')
		self.calculo.pre_requisitos.add(self.introducao)

	def test_api_returns_discipline_and_prerequisite(self):
		response = self.client.get(reverse('api_disciplina', args=[self.calculo.id]))

		self.assertEqual(response.status_code, 200)
		self.assertEqual(response.json(), {
			'id': self.calculo.id,
			'codigo': 'MAT200',
			'nome': 'Cálculo',
			'pre_requisitos': [{
				'id': self.introducao.id,
				'codigo': 'ENG100',
				'nome': 'Introdução',
			}],
		})

	def test_api_returns_404_for_unknown_discipline(self):
		response = self.client.get(reverse('api_disciplina', args=[99999]))

		self.assertEqual(response.status_code, 404)

	def test_prerequisite_page_renders_dependency_stages(self):
		response = self.client.get('/pre-requisitos/')

		self.assertEqual(response.status_code, 200)
		self.assertContains(response, 'Introdução')
		self.assertContains(response, 'Cálculo')
		self.assertContains(response, 'Etapa 1')
		self.assertContains(response, 'Etapa 2')

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
		Aluno.objects.create(usuario=usuario, matricula='9999999', senha='')
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
