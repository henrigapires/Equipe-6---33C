"""Grades guiadas pela grade da PUC (periodização) e pelo histórico do aluno.

Currículo inventado de 4 períodos (códigos TST, que não existem na PUC), com cadeias de
pré-requisito que fazem gargalos:
  TST1001 -> TST2001 -> TST3001 -> TST4001        (TST1001 destrava 3)
  TST3002 -> TST4002, TST4003, TST4004            (TST3002 destrava 3)
  TST1004, TST4005 não destravam nada
"""
from itertools import combinations

from django.test import TestCase

from .gerador_grades import gerar_grades, interpretar_horarios, tem_conflito
from .historico import salvar_espelho
from .models import Disciplina, LigacaoHabilitacao, Professor, Requisito, RotinaPreferencias, Turma
from .tests_espelho import SemCurriculosCarregados, criar_aluno, criar_curriculo, dados_espelho, disciplina_espelho

PERIODOS = {
    1: ["TST1001", "TST1002", "TST1003", "TST1004"],
    2: ["TST2001", "TST2002", "TST2003", "TST2004"],
    3: ["TST3001", "TST3002", "TST3003", "TST3004", "TST3005"],
    4: ["TST4001", "TST4002", "TST4003", "TST4004", "TST4005"],
}
PRE = {
    "TST2001": "TST1001", "TST3001": "TST2001", "TST4001": "TST3001",
    "TST4002": "TST3002", "TST4003": "TST3002", "TST4004": "TST3002",
}
HORARIOS = [f"{dia} {hora}-{hora + 2}" for hora in (7, 9, 11, 13, 15, 17, 19) for dia in ("SEG", "TER", "QUA", "QUI", "SEX", "SAB")]


class GradesDaPucTestCase(SemCurriculosCarregados, TestCase):
    def setUp(self):
        todos = [c for codigos in PERIODOS.values() for c in codigos]
        Requisito.objects.filter(disciplina__in=todos).delete()
        curriculo = criar_curriculo("Curso de Teste", [(c, p) for p, codigos in PERIODOS.items() for c in codigos])
        LigacaoHabilitacao.objects.create(curso_sigla="CEG", habilitacao_sigla="TST", enfase_sigla="",
                                          curriculo=curriculo, origem="pre_cadastro")
        for disciplina, exigido in PRE.items():
            Requisito.objects.create(disciplina=disciplina, tipo="pre", alternativa=0, codigo=exigido)
        professor = Professor.objects.create(nome="Professor Teste")
        horarios = iter(HORARIOS)
        for codigo in todos:
            disciplina = Disciplina.objects.create(codigo=codigo, nome="Disciplina " + codigo, creditos=4)
            for turma in ("3VA", "3VB"):
                Turma.objects.create(disciplina=disciplina, professor=professor, codigo_turma=turma,
                                     dias_horarios=next(horarios, "SAB 21-23"), vagas=30, sala="L100")

    def aluno_com(self, matricula, cursadas=(), em_andamento=()):
        aluno = criar_aluno(matricula)
        linhas = [disciplina_espelho(c, "AP", periodo="20251") for c in cursadas]
        linhas += [disciplina_espelho(c, "EA", periodo="20252") for c in em_andamento]
        salvar_espelho(aluno, dados_espelho(linhas, curso="CEG", habilitacao="TST", enfase=""))
        return aluno

    def grades(self, aluno, carga="media"):
        preferencias = RotinaPreferencias(aluno=aluno, turno="sem_preferencia", modalidade="hibrido",
                                          distribuicao_aulas="tanto_faz", janelas="tanto_faz", carga_disciplinas=carga)
        return gerar_grades(aluno, preferencias)

    def codigos(self, grade):
        return [t.disciplina.codigo for t in grade["turmas"]]

    def conferir_basico(self, grades, quantidade):
        self.assertTrue(grades)
        chaves = [tuple(sorted(t.id for t in g["turmas"])) for g in grades]
        self.assertEqual(len(chaves), len(set(chaves)), "grade repetida")
        for grade in grades:
            self.assertLessEqual(len(grade["turmas"]), quantidade)
            self.assertTrue(grade["rotulo"])
            self.assertEqual(set(grade["marcas"]), {t.id for t in grade["turmas"]})
            self.assertTrue(set(grade["marcas"].values()) <= {"atrasada", "do período", "adiantada"})
            horarios = [interpretar_horarios(t.dias_horarios) for t in grade["turmas"]]
            for a, b in combinations(horarios, 2):
                self.assertFalse(tem_conflito(a, b), "conflito de horário")
            self.assertEqual(grade["creditos"], 4 * len(grade["turmas"]))


class PeriodoDeReferenciaTests(GradesDaPucTestCase):
    def test_proximo_periodo_de_quem_esta_cursando(self):
        aluno = self.aluno_com("9800001", cursadas=PERIODOS[1], em_andamento=PERIODOS[2])
        grade = self.grades(aluno)[0]
        self.assertEqual((grade["periodo_atual"], grade["periodo_referencia"]), (2, 3))

    def test_maioria_das_em_andamento(self):
        aluno = self.aluno_com("9800002", cursadas=PERIODOS[1] + PERIODOS[2][:2],
                               em_andamento=PERIODOS[2][2:] + PERIODOS[3][:3])
        self.assertEqual(self.grades(aluno)[0]["periodo_referencia"], 4)

    def test_sem_nada_em_andamento_usa_o_menor_periodo_com_pendencia(self):
        aluno = self.aluno_com("9800003", cursadas=PERIODOS[1])
        grade = self.grades(aluno)[0]
        self.assertEqual((grade["periodo_atual"], grade["periodo_referencia"]), (1, 2))
        sem_nada = self.grades(criar_aluno("9800004"))
        self.assertEqual(sem_nada, [])       # sem espelho: sem currículo reconhecido, como antes


class AlunoEmDiaTests(GradesDaPucTestCase):
    def test_majoritariamente_o_periodo_de_referencia(self):
        aluno = self.aluno_com("9800010", cursadas=PERIODOS[1], em_andamento=PERIODOS[2])
        grades = self.grades(aluno, "media")
        self.conferir_basico(grades, 5)
        puc = grades[0]
        self.assertEqual(puc["estrategia"], "puc")
        self.assertEqual(puc["rotulo"], "Segue a grade da PUC (3º período)")
        self.assertEqual(sorted(self.codigos(puc)), PERIODOS[3])
        marcas = [m for g in grades for m in g["marcas"].values()]
        self.assertGreater(marcas.count("do período"), len(marcas) / 2)

    def test_cargas_leve_media_e_pesada(self):
        aluno = self.aluno_com("9800011", cursadas=PERIODOS[1], em_andamento=PERIODOS[2])
        for carga, quantidade in (("leve", 3), ("media", 5)):
            grades = self.grades(aluno, carga)
            self.conferir_basico(grades, quantidade)
            self.assertEqual(len(grades[0]["turmas"]), quantidade)
            self.assertEqual(grades[0]["aviso"], "")
        # pesada (7): só há 6 que ele pode cursar (5 do 3º + TST4005): grade menor com aviso
        pesada = self.grades(aluno, "pesada")
        self.conferir_basico(pesada, 7)
        self.assertEqual(len(pesada[0]["turmas"]), 6)
        self.assertIn("Só encontramos 6 disciplina(s)", pesada[0]["aviso"])


class AlunoComAtrasadaTests(GradesDaPucTestCase):
    def test_atrasada_que_nao_destrava_nada_entra_em_alguma_e_falta_em_alguma(self):
        cursadas = [c for c in PERIODOS[1] if c != "TST1004"]
        aluno = self.aluno_com("9800020", cursadas=cursadas, em_andamento=PERIODOS[2])
        grades = self.grades(aluno, "leve")
        self.conferir_basico(grades, 3)
        com = [g for g in grades if "TST1004" in self.codigos(g)]
        self.assertTrue(com)
        self.assertLess(len(com), len(grades))
        for g in com:
            self.assertEqual(g["marcas"][[t.id for t in g["turmas"] if t.disciplina.codigo == "TST1004"][0]], "atrasada")

    def test_quatro_estrategias_diferentes(self):
        cursadas = [c for c in PERIODOS[1] if c != "TST1004"]
        aluno = self.aluno_com("9800021", cursadas=cursadas, em_andamento=PERIODOS[2])
        grades = self.grades(aluno, "leve")
        self.assertEqual([g["estrategia"] for g in grades], ["puc", "recupera", "so_periodo", "adianta"])
        self.assertEqual(grades[1]["rotulo"], "Em dia + recupera atrasada: Disciplina TST1004")
        self.assertTrue(grades[3]["rotulo"].startswith("Variação: adianta "))
        # "só o período" não tem atrasada nem adiantada
        self.assertEqual(set(grades[2]["marcas"].values()), {"do período"})

    def test_atrasada_sem_dependentes_pesa_menos_que_do_periodo_que_destrava_muito(self):
        cursadas = [c for c in PERIODOS[1] if c != "TST1004"]
        aluno = self.aluno_com("9800022", cursadas=cursadas, em_andamento=PERIODOS[2])
        importancias = self.grades(aluno)[0]["importancias"]
        self.assertEqual(importancias["TST1004"], 6)                    # atrasada, não destrava nada
        self.assertEqual(importancias["TST3002"], 10 + 4 * 3)           # do período, destrava 3
        self.assertLess(importancias["TST1004"], importancias["TST3002"])

    def test_atrasada_gargalo_pesa_mais_e_entra_ate_na_grade_da_puc(self):
        # não fez TST1001 (destrava TST2001 -> TST3001 -> TST4001)
        cursadas = [c for c in PERIODOS[1] if c != "TST1001"]
        aluno = self.aluno_com("9800023", cursadas=cursadas, em_andamento=[c for c in PERIODOS[2] if c != "TST2001"])
        grades = self.grades(aluno, "leve")
        self.conferir_basico(grades, 3)
        self.assertEqual(grades[0]["importancias"]["TST1001"], 6 + 4 * 3)
        self.assertIn("TST1001", self.codigos(grades[0]))              # grade "da PUC"
        self.assertGreater(sum("TST1001" in self.codigos(g) for g in grades), 1)


class AlunoAdiantadoTests(GradesDaPucTestCase):
    def test_recebe_adiantadas_sem_teto_fixo(self):
        # já fez TST3001 e TST3002 adiantado: libera TST4001..TST4004
        aluno = self.aluno_com("9800030", cursadas=PERIODOS[1] + ["TST3001", "TST3002"], em_andamento=PERIODOS[2])
        grades = self.grades(aluno, "pesada")
        self.conferir_basico(grades, 7)
        adianta = [g for g in grades if g["estrategia"] == "adianta"]
        self.assertTrue(adianta)
        adiantadas = [m for m in adianta[0]["marcas"].values() if m == "adiantada"]
        self.assertGreaterEqual(len(adiantadas), 3)                     # duas, três... quantas couberem
        self.assertTrue(any("adiantada" in g["marcas"].values() for g in grades))


class FimDoCursoTests(GradesDaPucTestCase):
    def test_poucas_disciplinas_devolve_grade_menor_com_aviso(self):
        restantes = ["TST4004", "TST4005"]
        cursadas = [c for p in (1, 2, 3) for c in PERIODOS[p]]
        aluno = self.aluno_com("9800040", cursadas=cursadas, em_andamento=[c for c in PERIODOS[4] if c not in restantes])
        grades = self.grades(aluno, "media")
        self.assertTrue(grades)
        self.assertEqual(sorted(self.codigos(grades[0])), restantes)
        self.assertIn("você pediu 5", grades[0]["aviso"])

