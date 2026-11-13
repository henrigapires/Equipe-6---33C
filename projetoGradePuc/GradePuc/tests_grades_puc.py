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

    def grades(self, aluno, carga="media", turno="sem_preferencia", modalidade="hibrido"):
        preferencias = RotinaPreferencias(aluno=aluno, turno=turno, modalidade=modalidade,
                                          distribuicao_aulas="tanto_faz", janelas="tanto_faz", carga_disciplinas=carga)
        return gerar_grades(aluno, preferencias)

    def codigos(self, grade):
        return [t.disciplina.codigo for t in grade["turmas"]]

    def da_puc(self, grades):
        """A grade "Segue a grade da PUC" (sem depender da posição na lista)."""
        achadas = [g for g in grades if g["estrategia"] == "puc"]
        self.assertEqual(len(achadas), 1, "sem grade da PUC")
        return achadas[0]

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
        puc = self.da_puc(grades)
        self.assertEqual(puc["rotulo"], "Segue a grade da PUC (3º período)")
        self.assertEqual(sorted(self.codigos(puc)), PERIODOS[3])
        marcas = [m for g in grades for m in g["marcas"].values()]
        self.assertGreater(marcas.count("do período"), len(marcas) / 2)

    def test_cargas_leve_media_e_pesada(self):
        aluno = self.aluno_com("9800011", cursadas=PERIODOS[1], em_andamento=PERIODOS[2])
        for carga, quantidade in (("leve", 3), ("media", 5)):
            grades = self.grades(aluno, carga)
            self.conferir_basico(grades, quantidade)
            self.assertEqual(len(self.da_puc(grades)["turmas"]), quantidade)
        self.assertEqual(self.da_puc(self.grades(aluno, "media"))["aviso"], "")
        # pesada (7): a grade da PUC fica com as 5 do 3º período (não completa com outros);
        # outra opção chega a 6 (5 do 3º + TST4005) e avisa que é menor que o pedido
        pesada = self.grades(aluno, "pesada")
        self.conferir_basico(pesada, 7)
        self.assertEqual(sorted(self.codigos(self.da_puc(pesada))), PERIODOS[3])
        self.assertIn("Só há 5 disciplina(s) do 3º período", self.da_puc(pesada)["aviso"])
        self.assertTrue(any(len(g["turmas"]) == 6 and "Só encontramos 6" in g["aviso"] for g in pesada))


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
        por_estrategia = {g["estrategia"]: g for g in grades}
        self.assertEqual(set(por_estrategia), {"puc", "recupera", "so_periodo", "adianta"})
        self.assertEqual(por_estrategia["recupera"]["rotulo"], "Em dia + recupera atrasada: Disciplina TST1004")
        self.assertTrue(por_estrategia["adianta"]["rotulo"].startswith("Adianta: "))
        # "da PUC" e "só o período" não têm atrasada nem adiantada
        self.assertEqual(set(por_estrategia["puc"]["marcas"].values()), {"do período"})
        self.assertEqual(set(por_estrategia["so_periodo"]["marcas"].values()), {"do período"})

    def test_atrasada_sem_dependentes_pesa_menos_que_do_periodo_que_destrava_muito(self):
        cursadas = [c for c in PERIODOS[1] if c != "TST1004"]
        aluno = self.aluno_com("9800022", cursadas=cursadas, em_andamento=PERIODOS[2])
        importancias = self.grades(aluno)[0]["importancias"]
        self.assertEqual(importancias["TST1004"], 6)                    # atrasada, não destrava nada
        self.assertEqual(importancias["TST3002"], 10 + 4 * 3)           # do período, destrava 3
        self.assertLess(importancias["TST1004"], importancias["TST3002"])

    def test_atrasada_gargalo_pesa_mais_e_entra_na_que_recupera(self):
        # não fez TST1001 (destrava TST2001 -> TST3001 -> TST4001)
        cursadas = [c for c in PERIODOS[1] if c != "TST1001"]
        aluno = self.aluno_com("9800023", cursadas=cursadas, em_andamento=[c for c in PERIODOS[2] if c != "TST2001"])
        grades = self.grades(aluno, "leve")
        self.conferir_basico(grades, 3)
        self.assertEqual(grades[0]["importancias"]["TST1001"], 6 + 4 * 3)   # atrasada sem dependentes: 6
        self.assertNotIn("TST1001", self.codigos(self.da_puc(grades)))      # a da PUC é só do período
        recupera = [g for g in grades if g["estrategia"] == "recupera"][0]
        self.assertIn("TST1001", self.codigos(recupera))


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


class TelaDeGradesSugeridasTests(GradesDaPucTestCase):
    def test_mostra_periodo_rotulo_marcas_e_creditos(self):
        cursadas = [c for c in PERIODOS[1] if c != "TST1004"]
        aluno = self.aluno_com("9800050", cursadas=cursadas, em_andamento=PERIODOS[2])
        RotinaPreferencias.objects.create(aluno=aluno, turno="sem_preferencia", modalidade="hibrido",
                                          distribuicao_aulas="tanto_faz", janelas="tanto_faz", carga_disciplinas="leve")
        self.client.force_login(aluno.usuario)
        resposta = self.client.get("/grades-sugeridas/")
        self.assertContains(resposta, "Grades para o 3º período")
        self.assertContains(resposta, "período atual detectado: 2º")
        self.assertContains(resposta, "Segue a grade da PUC (3º período)")
        self.assertContains(resposta, "Em dia + recupera atrasada")
        self.assertContains(resposta, 'class="marca marca-atrasada"')
        self.assertContains(resposta, 'class="marca marca-do-periodo"')
        self.assertContains(resposta, "Quantidade de créditos")


class GradeDaPucAjustadaAoQuestionarioTests(GradesDaPucTestCase):
    """A grade "Segue a grade da PUC": só disciplinas do período de referência, as mais
    importantes até a carga. Estica só o turno manhã/tarde; noite e modalidade são filtro."""

    def em_dia(self, matricula):
        return self.aluno_com(matricula, cursadas=PERIODOS[1], em_andamento=PERIODOS[2])

    def test_carga_leve_com_cinco_cursaveis_ficam_as_tres_mais_importantes(self):
        puc = self.da_puc(self.grades(self.em_dia("9800060"), "leve"))
        # TST3002 destrava 3 (22), TST3001 destrava 1 (14), depois a ordem do currículo
        self.assertEqual(sorted(self.codigos(puc)), ["TST3001", "TST3002", "TST3003"])
        self.assertIn("com as 3 disciplinas mais importantes; ficaram de fora: Disciplina TST3004, Disciplina TST3005",
                      puc["aviso"])

    def test_carga_pesada_com_quatro_cursaveis_nao_completa_com_outros_periodos(self):
        aluno = self.aluno_com("9800061", cursadas=PERIODOS[1] + ["TST3005"], em_andamento=PERIODOS[2])
        puc = self.da_puc(self.grades(aluno, "pesada"))
        self.assertEqual(sorted(self.codigos(puc)), ["TST3001", "TST3002", "TST3003", "TST3004"])
        self.assertEqual(set(puc["marcas"].values()), {"do período"})
        self.assertIn("Só há 4 disciplina(s) do 3º período", puc["aviso"])

    def test_turno_manha_estica_so_na_grade_da_puc_e_avisa(self):
        # só TST3001 tem turma de manhã; as outras quatro só à tarde
        grades = self.grades(self.em_dia("9800062"), "media", turno="manha")
        puc = self.da_puc(grades)
        self.assertEqual(sorted(self.codigos(puc)), PERIODOS[3])
        self.assertIn("4 aula(s) fora do turno da manhã", puc["aviso"])
        manha = [t for t in puc["turmas"] if t.disciplina.codigo == "TST3001"][0]
        self.assertTrue(manha.dias_horarios.endswith("11-13"))
        # as outras grades continuam com o turno como filtro
        for grade in grades:
            if grade["estrategia"] != "puc":
                self.assertNotIn("TST3002", self.codigos(grade))

    def test_turno_noite_e_online_nao_esticam_e_a_mensagem_continua_igual(self):
        aluno = self.em_dia("9800063")
        self.assertEqual(self.grades(aluno, "media", turno="noite"), [])
        self.assertEqual(self.grades(aluno, "media", modalidade="online"), [])
        RotinaPreferencias.objects.create(aluno=aluno, turno="noite", modalidade="hibrido",
                                          distribuicao_aulas="tanto_faz", janelas="tanto_faz", carga_disciplinas="media")
        self.client.force_login(aluno.usuario)
        resposta = self.client.get("/grades-sugeridas/")
        self.assertContains(resposta, "Não foi possível gerar grades")
        self.assertContains(resposta, "Tente alterar o turno ou a modalidade para")

    def test_conflito_inevitavel_sai_a_menos_importante_com_aviso(self):
        # as duas turmas de TST3003 ocupam os dois horários de TST3002 (SEG e TER 13-15)
        Turma.objects.filter(disciplina__codigo="TST3003").update(dias_horarios="SEG 13-15; TER 13-15")
        puc = self.da_puc(self.grades(self.em_dia("9800064"), "media"))
        self.assertIn("TST3002", self.codigos(puc))
        self.assertNotIn("TST3003", self.codigos(puc))
        self.assertIn("Disciplina TST3003 não entra: as turmas batem com Disciplina TST3002", puc["aviso"])

    def test_troca_de_turma_para_as_duas_caberem(self):
        # TST3003 só tem uma turma, no mesmo horário de uma das turmas de TST3002
        Turma.objects.filter(disciplina__codigo="TST3003", codigo_turma="3VB").delete()
        Turma.objects.filter(disciplina__codigo="TST3003").update(dias_horarios="SEG 13-15")
        puc = self.da_puc(self.grades(self.em_dia("9800065"), "media"))
        self.assertTrue({"TST3002", "TST3003"} <= set(self.codigos(puc)))
        self.assertNotIn("não entra", puc["aviso"])

    def test_disciplina_do_periodo_que_nao_pode_entrar_aparece_no_aviso(self):
        Turma.objects.filter(disciplina__codigo="TST3005").update(vagas=0)
        puc = self.da_puc(self.grades(self.em_dia("9800066"), "media"))
        self.assertIn("Disciplina TST3005 não entra: sem vaga", puc["aviso"])


class AdiantaTemDisciplinaDoPeriodoTests(GradesDaPucTestCase):
    def adianta(self, carga):
        aluno = self.aluno_com(f"98001{carga[:2]}", cursadas=PERIODOS[1], em_andamento=PERIODOS[2])
        achadas = [g for g in self.grades(aluno, carga) if g["estrategia"] == "adianta"]
        self.assertEqual(len(achadas), 1)
        return achadas[0]

    def test_leve_uma_do_periodo_a_que_destrava_mais(self):
        grade = self.adianta("leve")
        do_periodo = [t.disciplina.codigo for t in grade["turmas"] if grade["marcas"][t.id] == "do período"]
        self.assertEqual(do_periodo, ["TST3002"])                       # destrava 3
        self.assertIn("adiantada", grade["marcas"].values())
        self.assertTrue(grade["rotulo"].startswith("Adianta: Disciplina TST4005 + Disciplina TST3002"))

    def test_media_duas_do_periodo_e_nunca_so_adiantadas(self):
        grade = self.adianta("media")
        do_periodo = sorted(t.disciplina.codigo for t in grade["turmas"] if grade["marcas"][t.id] == "do período")
        self.assertEqual(do_periodo, ["TST3001", "TST3002"])            # as de mais dependentes
        self.assertGreaterEqual(list(grade["marcas"].values()).count("adiantada"), 1)
