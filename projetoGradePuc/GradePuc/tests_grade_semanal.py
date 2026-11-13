from types import SimpleNamespace

from django.test import SimpleTestCase
from django.template.loader import render_to_string

from .views import montar_grade_semanal


class GradeSemanalTests(SimpleTestCase):
    def test_aula_ocupa_duracao_sem_repetir_celula(self):
        turma = SimpleNamespace(dias_horarios='SEG 08-10; QUA 08-10')
        dias, linhas = montar_grade_semanal([turma])
        self.assertEqual(len(dias), 5)
        self.assertEqual(len(linhas), 2)
        self.assertEqual(linhas[0]['celulas'][0]['rowspan'], 2)
        self.assertIs(linhas[0]['celulas'][2]['turma'], turma)
        self.assertIsNone(linhas[1]['celulas'][0])
        self.assertTrue(linhas[0]['celulas'][1]['vazia'])

    def test_sabado_e_horarios_com_minutos(self):
        turma = SimpleNamespace(dias_horarios='SAB 08:30-10:30')
        dias, linhas = montar_grade_semanal([turma])
        self.assertEqual(dias[-1], ('SAB', 'Sábado'))
        aula = next(linha for linha in linhas if linha['horario'].startswith('08:30-'))
        self.assertEqual(aula['celulas'][5]['rowspan'], 3)

    def test_grade_sem_horario_renderiza_estado_vazio(self):
        dias, linhas = montar_grade_semanal([])
        html = render_to_string('grade_semanal.html', {'dias': dias, 'grade_linhas': linhas})
        self.assertIn('Nenhuma turma foi encontrada', html)
        self.assertIn('colspan="6"', html)
