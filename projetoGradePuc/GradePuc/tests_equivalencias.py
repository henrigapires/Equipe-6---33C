"""Equivalências (opção 3): só as confirmadas à mão e os pares do campo grupo dos espelhos.
INF1037, INF1007, INF1026 e INF1620 nunca entram em classe. As sugestões da regra estrita
ficam num arquivo de revisão que o site não usa. Históricos inventados.
"""
import tempfile
from io import StringIO
from pathlib import Path
from unittest.mock import patch

from django.core.management import call_command
from django.test import TestCase

from .eletivas import sugerir_eletivas
from .gerador_grades import gerar_grades
from .historico import SEM_VAGA, salvar_espelho
from .management.commands import sugerir_equivalencias
from .models import Disciplina, HistoricoDisciplina, LigacaoHabilitacao, Professor, Requisito, RotinaPreferencias, Turma
from .requisitos import (
    EQUIVALENCIAS_CONFIRMADAS, NUNCA_EQUIVALENTES, classe_de, classes_de_equivalencia, codigos_feitos,
    pre_requisitos_cumpridos,
)
from .tests_eletivas import EletivasTestCase
from .tests_espelho import SemCurriculosCarregados, criar_aluno, criar_curriculo, dados_espelho, disciplina_espelho
from .tests_regras_requisitos import requisito

CALCULO_1 = ["MAT1158", "MAT1161", "MAT1181", "MAT4161", "MAT4181"]


def membros(classes, codigo):
    return sorted(c for c, classe in classes.items() if classe == classes.get(codigo))


class ClassesConfirmadasTests(TestCase):
    def test_calculo_1_fisica_2_e_algebra_linear(self):
        HistoricoDisciplina.objects.all().delete()
        classes = classes_de_equivalencia()
        self.assertEqual(membros(classes, "MAT4181"), CALCULO_1)
        self.assertEqual(membros(classes, "FIS4002"), ["FIS1041", "FIS1071", "FIS4002"])
        self.assertIn("MAT4200", membros(classes, "MAT1200"))
        self.assertNotIn("MAT1215", classes)          # Álgebra Linear para Economia fica de fora
        self.assertNotIn("FIS4003", classes)
        self.assertEqual(classe_de("MAT4181", classes), "MAT1158")

    def test_disciplinas_de_programacao_nunca_entram(self):
        self.assertEqual(NUNCA_EQUIVALENTES, {"INF1037", "INF1007", "INF1026", "INF1620"})
        aluno = criar_aluno("9600001")
        # mesmo que um espelho dissesse que uma vale pela outra
        HistoricoDisciplina.objects.create(aluno=aluno, periodo="20251", codigo="INF1037", nome="X", situacao="AP", grupo="INF1007")
        classes = classes_de_equivalencia()
        self.assertFalse(NUNCA_EQUIVALENTES & set(classes))
        self.assertFalse(any(NUNCA_EQUIVALENTES & set(classe) for classe in EQUIVALENCIAS_CONFIRMADAS))

    def test_par_do_espelho_une_mas_vaga_de_optativa_e_nenhum_nao(self):
        aluno = criar_aluno("9600002")
        for codigo, grupo in (("ABC4181", "ABC4161"), ("XYZ1026", "INF0307"), ("ENG1234", SEM_VAGA)):
            HistoricoDisciplina.objects.create(aluno=aluno, periodo="20251", codigo=codigo, nome="X", situacao="AP", grupo=grupo)
        classes = classes_de_equivalencia()
        self.assertEqual(membros(classes, "ABC4181"), ["ABC4161", "ABC4181"])
        self.assertFalse({"XYZ1026", "INF0307", "ENG1234", SEM_VAGA} & set(classes))


class FeitosComEquivalenciasTests(TestCase):
    def test_quem_fez_mat4181_tem_calculo_1_feito(self):
        aluno = criar_aluno("9600003")
        salvar_espelho(aluno, dados_espelho([disciplina_espelho("MAT4181", "AP", grupo="MAT4161")]))
        feitos = codigos_feitos(aluno)
        self.assertTrue(set(CALCULO_1) <= feitos)
        requisito("ABC9162", "pre", ["MAT1161"])          # exige outro código da classe
        self.assertTrue(pre_requisitos_cumpridos("ABC9162", feitos))


HORARIOS = [f"{dia} {hora}-{hora + 2}" for hora in (7, 9, 11, 13) for dia in ("SEG", "TER", "QUA", "QUI", "SEX")]


class GradeComEquivalenciasTests(SemCurriculosCarregados, TestCase):
    CODIGOS = ["MAT1161", "MAT4161", "FIS4001", "INF1037", "EMP1320", "ENG4010"]

    def setUp(self):
        Requisito.objects.filter(disciplina__in=self.CODIGOS).delete()
        curriculo = criar_curriculo("Curso de Teste", [(c, 1) for c in self.CODIGOS])
        LigacaoHabilitacao.objects.create(curso_sigla="CEG", habilitacao_sigla="BCO", enfase_sigla="",
                                          curriculo=curriculo, origem="pre_cadastro")
        professor = Professor.objects.create(nome="Professor Teste")
        horarios = iter(HORARIOS)
        for codigo in self.CODIGOS:
            disciplina = Disciplina.objects.create(codigo=codigo, nome="Disciplina " + codigo, creditos=4)
            for turma in ("3VA", "3VB"):
                Turma.objects.create(disciplina=disciplina, professor=professor, codigo_turma=turma,
                                     dias_horarios=next(horarios), vagas=30, sala="L100")

    def preferencias(self, aluno, carga):
        return RotinaPreferencias(aluno=aluno, turno="sem_preferencia", modalidade="hibrido",
                                  distribuicao_aulas="tanto_faz", janelas="tanto_faz", carga_disciplinas=carga)

    def test_quem_fez_mat4181_nao_recebe_mat1161_nem_mat4161(self):
        aluno = criar_aluno("9600004")
        salvar_espelho(aluno, dados_espelho([disciplina_espelho("MAT4181", "AP", grupo="MAT4161")]))
        grades = gerar_grades(aluno, self.preferencias(aluno, "leve"))
        self.assertTrue(grades)
        for grade in grades:
            self.assertFalse({t.disciplina.codigo for t in grade["turmas"]} & {"MAT1161", "MAT4161"})

    def test_nunca_duas_da_mesma_classe_na_mesma_grade(self):
        aluno = criar_aluno("9600005")
        salvar_espelho(aluno, dados_espelho([disciplina_espelho("ABC9999", "AP")]))
        grades = gerar_grades(aluno, self.preferencias(aluno, "media"))
        self.assertTrue(grades)
        for grade in grades:
            classes = [classe_de(t.disciplina.codigo) for t in grade["turmas"]]
            self.assertEqual(len(classes), len(set(classes)))
            self.assertFalse({"MAT1161", "MAT4161"} <= {t.disciplina.codigo for t in grade["turmas"]})


class EletivasComEquivalenciasTests(EletivasTestCase):
    def test_eletiva_equivalente_ao_que_ja_fez_ou_ao_que_esta_na_grade(self):
        # um espelho (de outro aluno) diz que FIL9002 vale como FIL9001
        outro = criar_aluno("9600006")
        HistoricoDisciplina.objects.create(aluno=outro, periodo="20251", codigo="FIL9002", nome="X", situacao="AP", grupo="FIL9001")
        obrigatoria = self.criar_turma("ENG9001", "SEG 07-09")
        self.criar_turma("FIL9001", "TER 07-09")
        self.criar_turma("FIL9002", "QUA 07-09")
        com_fil9001 = self.grade(obrigatoria, Turma.objects.get(disciplina__codigo="FIL9001"))
        self.assertNotIn("FIL9002", self.codigos(sugerir_eletivas(self.aluno, self.preferencias(), com_fil9001)))
        self.aluno.disciplinas_cursadas.add(Disciplina.objects.get(codigo="FIL9002"))
        sugeridas = self.codigos(sugerir_eletivas(self.aluno, self.preferencias(), self.grade(obrigatoria)))
        self.assertNotIn("FIL9001", sugeridas)


class SugestoesDeEquivalenciaTests(TestCase):
    def test_titulo_normalizado(self):
        normalizar = sugerir_equivalencias.titulo_normalizado
        self.assertEqual(normalizar("ÁLGEBRA LINEAR I"), normalizar("ALGEBRA LINEAR 1"))
        self.assertEqual(normalizar("Física  II"), "FISICA")
        self.assertNotEqual(normalizar("ALGEBRA LINEAR 1 ESPECIAL"), normalizar("ALGEBRA LINEAR 1"))

    def test_grava_so_o_arquivo_de_revisao_e_nao_ativa_nada(self):
        Requisito.objects.all().delete()
        # ABC9001 e ABC9002 aparecem juntas como alternativas únicas em 2 requisitos; INF1037/INF1026 também
        for disciplina in ("XYZ9001", "XYZ9002"):
            requisito(disciplina, "pre", ["ABC9001"], ["ABC9002"])
            requisito(disciplina, "co", ["INF1037"], ["INF1026"])
        antes = classes_de_equivalencia()
        with tempfile.TemporaryDirectory() as pasta:
            cache = Path(pasta) / "cache"
            cache.mkdir()
            for codigo, titulo in (("ABC9001", "TÓPICOS I"), ("ABC9002", "TOPICOS 2"),
                                   ("INF1037", "PROGRAMACAO"), ("INF1026", "PROGRAMACAO")):
                (cache / f"{codigo}.html").write_bytes(f'<span id="hTitulo">{titulo}</span>'.encode("cp1252"))
            arquivo = Path(pasta) / "revisao" / "equivalencias_sugeridas.txt"
            with patch.object(sugerir_equivalencias, "ARQUIVO", arquivo):
                call_command("sugerir_equivalencias", "--cache", str(cache), stdout=StringIO())
            texto = arquivo.read_text(encoding="utf-8")
        self.assertIn("ABC9001 (TÓPICOS I) = ABC9002 (TOPICOS 2)", texto)
        self.assertNotIn("INF1037", texto)
        self.assertEqual(classes_de_equivalencia(), antes)       # nada foi ativado
