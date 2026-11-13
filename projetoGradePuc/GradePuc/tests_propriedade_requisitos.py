"""Teste de propriedade: em TODA turma sugerida (grades e eletivas), para todos os currículos
do banco de teste e vários históricos sintéticos, a regra de pré/co-requisito vale.

Os currículos, grupos e requisitos são os de verdade (migrations 0007, 0009 e 0011); as
turmas, os horários e os históricos são inventados. Casos especiais no fim: co-requisito
circular, co-requisito que não cabe em grade nenhuma e pré-requisito em andamento.
"""
from itertools import cycle

from django.contrib.auth.models import User
from django.test import TestCase

from .auditoria import Verificador, codigos_para_turmas, historicos_sinteticos, ligar_curriculo
from .gerador_grades import gerar_grades
from .historico import salvar_espelho
from .models import Aluno, Curriculo, Disciplina, Professor, Requisito, RotinaPreferencias, Turma
from .tests_espelho import SemCurriculosCarregados, criar_aluno, criar_curriculo, dados_espelho, disciplina_espelho

DIAS = ("SEG", "TER", "QUA", "QUI", "SEX")
HORAS = (7, 9, 11, 13, 15, 17)
HORARIOS = [f"{dia} {hora}-{hora + 2}" for hora in HORAS for dia in DIAS]


def preferencias_para(aluno, carga="media"):
    # não precisa estar no banco: o gerador e as eletivas só leem os campos
    return RotinaPreferencias(aluno=aluno, turno="sem_preferencia", modalidade="hibrido",
                              distribuicao_aulas="tanto_faz", janelas="tanto_faz", carga_disciplinas=carga)


class TodasAsTurmasSugeridasRespeitamOsRequisitosTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        codigos = set()
        for curriculo in Curriculo.objects.all():
            codigos |= codigos_para_turmas(curriculo)
        existentes = set(Disciplina.objects.values_list("codigo", flat=True))
        Disciplina.objects.bulk_create([
            Disciplina(codigo=c, nome="Disciplina " + c, creditos=4) for c in sorted(codigos - existentes)
        ])
        professor = Professor.objects.create(nome="Professor Teste")
        horarios = cycle(HORARIOS)
        turmas = []
        for disciplina in Disciplina.objects.filter(codigo__in=codigos).order_by("codigo"):
            for codigo_turma in ("3VA", "3VB"):
                turmas.append(Turma(disciplina=disciplina, professor=professor, codigo_turma=codigo_turma,
                                    dias_horarios=next(horarios), vagas=30, sala="L100"))
        Turma.objects.bulk_create(turmas, batch_size=2000)

    def test_propriedade_em_todos_os_curriculos_e_historicos(self):
        verificador = Verificador()
        verificadas, grades_com_turma, violacoes = 0, 0, []
        numero = 0
        for curriculo in Curriculo.objects.order_by("id"):
            curso, habilitacao = ligar_curriculo(curriculo)
            for nome, disciplinas in historicos_sinteticos(curriculo).items():
                numero += 1
                usuario = User.objects.create_user(f"prop{numero}", password="x")
                aluno = Aluno.objects.create(usuario=usuario, matricula=f"prop{numero}", senha="")
                salvar_espelho(aluno, dados_espelho(disciplinas, curso=curso, habilitacao=habilitacao, enfase=""))
                total, problemas, _ = verificador.auditar(aluno, preferencias_para(aluno))
                verificadas += total
                grades_com_turma += bool(total)
                violacoes += [f"{curriculo} / {nome}: {p}" for p in problemas]

        self.assertEqual(violacoes, [], "\n" + "\n".join(violacoes[:50]))
        # o teste não é vazio: muitas turmas foram de fato sugeridas e conferidas
        self.assertGreater(verificadas, 1000)
        self.assertGreater(grades_com_turma, Curriculo.objects.count())


class CasosEspeciaisDeRequisitoTests(SemCurriculosCarregados, TestCase):
    """Co-requisito circular, co-requisito que não cabe e pré-requisito em andamento."""

    def montar(self, codigos, horarios=None):
        curriculo = criar_curriculo("Curso de Teste", [(c, 1) for c in codigos])
        curso, habilitacao = ligar_curriculo(curriculo, curso="ESP")
        professor = Professor.objects.create(nome="Professor Teste")
        horarios = iter(horarios or HORARIOS)
        Requisito.objects.filter(disciplina__in=codigos).delete()
        for codigo in codigos:
            disciplina = Disciplina.objects.create(codigo=codigo, nome="Disciplina " + codigo, creditos=4)
            horario = next(horarios)
            if horario:
                Turma.objects.create(disciplina=disciplina, professor=professor, codigo_turma="3VA",
                                     dias_horarios=horario, vagas=30, sala="L100")
        return curso, habilitacao

    def requisito(self, disciplina, tipo, *codigos):
        for codigo in codigos:
            Requisito.objects.create(disciplina=disciplina, tipo=tipo, alternativa=0, codigo=codigo)

    def grades(self, curso, habilitacao, historico, carga):
        aluno = criar_aluno("9700001")
        salvar_espelho(aluno, dados_espelho(historico, curso=curso, habilitacao=habilitacao, enfase=""))
        return [{t.disciplina.codigo for t in g["turmas"]} for g in gerar_grades(aluno, preferencias_para(aluno, carga))]

    def test_co_requisito_circular_entra_em_par_ou_nao_entra(self):
        curso, habilitacao = self.montar(["ABC9001", "ABC9002", "ABC9003", "ABC9004"])
        self.requisito("ABC9001", "co", "ABC9002")
        self.requisito("ABC9002", "co", "ABC9001")
        grades = self.grades(curso, habilitacao, [], "leve")       # 3 por grade
        self.assertTrue(grades)
        for codigos in grades:
            self.assertEqual("ABC9001" in codigos, "ABC9002" in codigos)

    def test_co_requisito_que_nao_cabe_em_grade_nenhuma_nao_e_sugerido(self):
        # ABC9001 exige ABC9002 junto, mas ABC9002 não tem turma: ABC9001 nunca entra
        curso, habilitacao = self.montar(["ABC9001", "ABC9002", "ABC9003", "ABC9004", "ABC9005"],
                                         horarios=["SEG 7-9", None, "TER 7-9", "QUA 7-9", "QUI 7-9"])
        self.requisito("ABC9001", "co", "ABC9002")
        grades = self.grades(curso, habilitacao, [], "leve")
        self.assertTrue(grades)
        self.assertFalse(any("ABC9001" in codigos for codigos in grades))

    def test_pre_requisito_em_andamento_conta_como_cumprido(self):
        curso, habilitacao = self.montar(["ABC9001", "ABC9002", "ABC9003", "ABC9004"])
        self.requisito("ABC9002", "pre", "ABC9001")
        historico = [disciplina_espelho("ABC9001", "EA", periodo="20262")]
        grades = self.grades(curso, habilitacao, historico, "leve")
        self.assertTrue(any("ABC9002" in codigos for codigos in grades))
        self.assertFalse(any("ABC9001" in codigos for codigos in grades))
