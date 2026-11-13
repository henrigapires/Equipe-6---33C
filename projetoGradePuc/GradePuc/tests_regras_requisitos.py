"""Regra única de pré/co-requisito (requisitos.py) e o uso dela no gerador de grades.

Os requisitos são criados no próprio teste (com os códigos reais das ementas usadas como
exemplo), para não depender do conteúdo de requisitos.json. Históricos inventados.
"""
from django.test import TestCase

from .gerador_grades import gerar_grades, sem_co_requisito_faltando
from .historico import salvar_espelho
from .models import Disciplina, LigacaoHabilitacao, Professor, Requisito, RotinaPreferencias, Turma
from .requisitos import (
    TabelaDeRequisitos, alternativas_de_pre_requisito, co_requisitos_cumpridos, codigos_feitos,
    pre_requisitos_cumpridos,
)
from .tests_espelho import SemCurriculosCarregados, criar_aluno, criar_curriculo, dados_espelho, disciplina_espelho


def requisito(disciplina, tipo, *alternativas, observacao=""):
    """requisito('MAT4162', 'pre', ['MAT4161'], ['MAT4181']): uma lista por alternativa (OU)."""
    Requisito.objects.filter(disciplina=disciplina, tipo=tipo).delete()
    for numero, codigos in enumerate(alternativas):
        for codigo in codigos or [""]:
            Requisito.objects.create(disciplina=disciplina, tipo=tipo, alternativa=numero,
                                     codigo=codigo, observacao=observacao)


class RegrasTests(TestCase):
    def test_ou_entre_alternativas_e_dentro_delas(self):
        requisito("ENG4021", "pre", ["ENG1000"], ["ENG1127"], ["ENG4010"])
        requisito("ENG4021", "co", ["EMP1320", "INF1037"], ["EMP1320", "INF1026"])
        self.assertFalse(pre_requisitos_cumpridos("ENG4021", set()))
        self.assertTrue(pre_requisitos_cumpridos("ENG4021", {"ENG4010"}))
        self.assertFalse(co_requisitos_cumpridos("ENG4021", {"EMP1320"}, set()))
        self.assertTrue(co_requisitos_cumpridos("ENG4021", {"EMP1320"}, {"INF1026"}))     # junto, na grade
        self.assertTrue(co_requisitos_cumpridos("ENG4021", set(), {"EMP1320", "INF1037"}))

    def test_nivelamento_nao_bloqueia(self):
        requisito("MAT4162", "pre", ["MAT4161"], ["MAT4181"], observacao="MATEMÁTICA (nivel 3)")
        self.assertTrue(pre_requisitos_cumpridos("MAT4162", {"MAT4181"}))
        requisito("ABC9001", "pre", [], observacao="MATEMÁTICA (nivel 3)")     # só nivelamento
        self.assertTrue(pre_requisitos_cumpridos("ABC9001", set()))

    def test_sem_requisito_e_fallback_do_m2m_antigo(self):
        Requisito.objects.filter(disciplina__in=["ABC9002", "ABC9003"]).delete()
        self.assertTrue(pre_requisitos_cumpridos("ABC9002", set()))
        antiga = Disciplina.objects.create(codigo="ABC9003", nome="Antiga")
        antiga.pre_requisitos.add(Disciplina.objects.create(codigo="ABC9004", nome="Requisito antigo"))
        self.assertFalse(pre_requisitos_cumpridos("ABC9003", set()))
        self.assertTrue(pre_requisitos_cumpridos("ABC9003", {"ABC9004"}))
        self.assertEqual(alternativas_de_pre_requisito("ABC9003"), [["ABC9004"]])

    def test_tabela_carregada_de_uma_vez(self):
        requisito("FIS4003", "pre", ["FIS1041"], ["FIS1071"], ["FIS4002"])
        tabela = TabelaDeRequisitos()
        self.assertTrue(pre_requisitos_cumpridos("FIS4003", {"FIS4002"}, tabela))
        self.assertFalse(pre_requisitos_cumpridos("FIS4003", {"FIS4001"}, tabela))

    def test_codigos_feitos_vem_do_historico_com_os_grupos(self):
        aluno = criar_aluno("9500001")
        salvar_espelho(aluno, dados_espelho([
            disciplina_espelho("MAT4181", "AP", grupo="MAT4161"),
            disciplina_espelho("FIS4001", "EA", periodo="20262"),
            disciplina_espelho("INF1007", "RM"),
        ]))
        feitos = codigos_feitos(aluno)
        self.assertTrue({"MAT4181", "MAT4161", "FIS4001"} <= feitos)
        self.assertNotIn("INF1007", feitos)     # reprovada não conta


HORARIOS = [f"{dia} {hora}-{hora + 2}" for hora in (7, 9, 11, 13) for dia in ("SEG", "TER", "QUA", "QUI", "SEX")]


class GeradorComRequisitosTests(SemCurriculosCarregados, TestCase):
    """Currículo pequeno com os códigos reais e os requisitos das ementas."""

    CODIGOS = ["FIS4001", "FIS4002", "FIS4003", "MAT4161", "MAT4162", "MAT4163", "INF1037", "EMP1320", "ENG4021"]

    def setUp(self):
        curriculo = criar_curriculo("Curso de Teste", [(codigo, 1) for codigo in self.CODIGOS])
        LigacaoHabilitacao.objects.create(curso_sigla="CEG", habilitacao_sigla="BCO", enfase_sigla="",
                                          curriculo=curriculo, origem="pre_cadastro")
        professor = Professor.objects.create(nome="Professor Teste")
        horarios = iter(HORARIOS)
        for codigo in self.CODIGOS:
            disciplina = Disciplina.objects.create(codigo=codigo, nome="Disciplina " + codigo, creditos=4)
            for turma in ("3VA", "3VB"):
                Turma.objects.create(disciplina=disciplina, professor=professor, codigo_turma=turma,
                                     dias_horarios=next(horarios), vagas=30, sala="L100")
        Requisito.objects.filter(disciplina__in=self.CODIGOS).delete()   # só os requisitos deste teste
        requisito("FIS4002", "pre", ["FIS4001"])
        requisito("FIS4003", "pre", ["FIS1041"], ["FIS1071"], ["FIS4002"])
        requisito("MAT4162", "pre", ["MAT1158"], ["MAT1161"], ["MAT1181"], ["MAT4161"], ["MAT4181"],
                  observacao="MATEMÁTICA (nivel 3)")
        requisito("MAT4163", "pre", ["MAT4162"])
        requisito("ENG4021", "co", ["EMP1320", "INF1037"])

    def preferencias(self, aluno, carga="leve"):
        return RotinaPreferencias.objects.update_or_create(aluno=aluno, defaults=dict(
            turno="sem_preferencia", modalidade="hibrido",
            distribuicao_aulas="tanto_faz", janelas="tanto_faz", carga_disciplinas=carga,
        ))[0]

    def codigos(self, grade):
        return {turma.disciplina.codigo for turma in grade["turmas"]}

    def test_caso_do_dan_fisica_3_nunca_e_sugerida(self):
        # cursando FIS4001, MAT4162, INF1037, EMP1320 (EA); fez MAT4181 com grupo MAT4161
        aluno = criar_aluno("9500002")
        salvar_espelho(aluno, dados_espelho([
            disciplina_espelho("MAT4181", "AP", grupo="MAT4161"),
            *[disciplina_espelho(c, "EA", periodo="20262") for c in ("FIS4001", "MAT4162", "INF1037", "EMP1320")],
        ]))
        grades = gerar_grades(aluno, self.preferencias(aluno, "leve"))
        self.assertTrue(grades)
        feitos = codigos_feitos(aluno)
        for grade in grades:
            codigos = self.codigos(grade)
            self.assertNotIn("FIS4003", codigos)
            self.assertFalse(codigos & {"FIS4001", "MAT4161", "MAT4162", "INF1037", "EMP1320"})   # já feitas
            for codigo in codigos:
                self.assertTrue(pre_requisitos_cumpridos(codigo, feitos), codigo)

    def test_calculo_1_e_calculo_2_nunca_juntos(self):
        aluno = criar_aluno("9500003")
        salvar_espelho(aluno, dados_espelho([disciplina_espelho("FIS4001", "AP")]))
        for carga in ("leve", "media"):
            for grade in gerar_grades(aluno, self.preferencias(aluno, carga)):
                self.assertFalse({"MAT4161", "MAT4162"} <= self.codigos(grade))
                self.assertNotIn("MAT4163", self.codigos(grade))

    def test_co_requisito_cumprido_pela_mesma_grade(self):
        aluno = criar_aluno("9500004")
        salvar_espelho(aluno, dados_espelho([disciplina_espelho("FIS4001", "AP")]))
        grades = gerar_grades(aluno, self.preferencias(aluno, "media"))
        self.assertTrue(grades)
        for grade in grades:
            codigos = self.codigos(grade)
            if "ENG4021" in codigos:
                self.assertTrue({"EMP1320", "INF1037"} <= codigos)

    def test_tira_da_grade_quem_ficou_sem_co_requisito(self):
        turmas = {t.disciplina.codigo: t for t in Turma.objects.filter(codigo_turma="3VA")}
        tabela = TabelaDeRequisitos()
        escolhidas = [(turmas["ENG4021"], []), (turmas["EMP1320"], [])]
        self.assertEqual([t.disciplina.codigo for t, _ in sem_co_requisito_faltando(escolhidas, set(), tabela)], ["EMP1320"])
        escolhidas.append((turmas["INF1037"], []))
        self.assertEqual(len(sem_co_requisito_faltando(escolhidas, set(), tabela)), 3)


class TelasComRequisitosTests(TestCase):
    def setUp(self):
        self.aluno = criar_aluno("9500005")
        self.client.force_login(self.aluno.usuario)
        RotinaPreferencias.objects.create(
            aluno=self.aluno, turno="sem_preferencia", modalidade="hibrido",
            distribuicao_aulas="tanto_faz", janelas="tanto_faz", carga_disciplinas="leve",
        )

    def test_api_mostra_as_alternativas(self):
        requisito("FIS4003", "pre", ["FIS1041"], ["FIS1071"], ["FIS4002"])
        fisica = Disciplina.objects.create(codigo="FIS4003", nome="Física III")
        Disciplina.objects.create(codigo="FIS4002", nome="Física II")
        dados = self.client.get(f"/api/disciplinas/{fisica.id}/").json()
        self.assertEqual([[item["codigo"] for item in alt] for alt in dados["alternativas"]],
                         [["FIS1041"], ["FIS1071"], ["FIS4002"]])
        self.assertEqual(dados["alternativas"][2][0]["nome"], "Física II")

    def test_pagina_de_pre_requisitos_usa_a_regra_nova(self):
        requisito("FIS4003", "pre", ["FIS4002"])
        Disciplina.objects.create(codigo="FIS4002", nome="Física II")
        Disciplina.objects.create(codigo="FIS4003", nome="Física III")
        Requisito.objects.filter(disciplina="FIS4002").delete()
        # o fluxograma é o do currículo do aluno (colunas por período)
        curriculo = criar_curriculo("Curso Requisitos", [("FIS4002", 1), ("FIS4003", 2)])
        LigacaoHabilitacao.objects.create(curso_sigla="CEG", habilitacao_sigla="RQT", enfase_sigla="",
                                          curriculo=curriculo, origem="pre_cadastro")
        self.aluno.curso_sigla, self.aluno.habilitacao_sigla = "CEG", "RQT"
        self.aluno.save()
        resposta = self.client.get("/pre-requisitos/")
        status = {d["codigo"]: d["status"] for trilha in resposta.context["trilhas"] for d in trilha["disciplinas"]}
        self.assertEqual((status["FIS4002"], status["FIS4003"]), ("disponivel", "bloqueada"))
        colunas = {d["codigo"]: trilha["nome"] for trilha in resposta.context["trilhas"] for d in trilha["disciplinas"]}
        self.assertEqual((colunas["FIS4002"], colunas["FIS4003"]), ("1º período", "2º período"))
