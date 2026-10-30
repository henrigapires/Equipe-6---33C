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
