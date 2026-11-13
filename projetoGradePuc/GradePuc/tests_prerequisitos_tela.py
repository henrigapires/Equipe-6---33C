"""Tela de pré-requisitos (fluxograma do currículo do aluno), painel Detalhes e busca.

Currículo inventado (códigos PRT, que não existem na PUC):
  1º período: PRT1001 (A), PRT1002 (D), MAT4161 (Cálculo 1)
  2º período: PRT2001 (B, exige A), MAT4162 (exige MAT4161)
  3º período: PRT3001 (C, exige B ou D), PRT3002 (co-requisito de C), PRT3003 (exige PRT9999, fora do currículo)
  4º período: PRT4001 (exige C e PRT3002), PRT0100 (vaga de optativa)
O aluno fez A e MAT1161 (equivalente a MAT4161) e está cursando B.
"""
from django.db import connection
from django.test import TestCase
from django.test.utils import CaptureQueriesContext

from .historico import salvar_espelho
from .models import Disciplina, EmentaLida, LigacaoHabilitacao, Requisito
from .tests_espelho import SemCurriculosCarregados, criar_aluno, criar_curriculo, dados_espelho, disciplina_espelho
from .tests_regras_requisitos import requisito

CURRICULO = [
    ("PRT1001", 1), ("PRT1002", 1), ("MAT4161", 1),
    ("PRT2001", 2), ("MAT4162", 2),
    ("PRT3001", 3), ("PRT3002", 3), ("PRT3003", 3),
    ("PRT4001", 4), ("PRT0100", 4),
]


class TelaDePreRequisitosTestCase(SemCurriculosCarregados, TestCase):
    def setUp(self):
        codigos = [c for c, _ in CURRICULO] + ["PRT5001", "PRT6001", "PRT9999"]
        Requisito.objects.filter(disciplina__in=codigos).delete()
        self.curriculo = criar_curriculo("Curso Fluxograma", CURRICULO)
        LigacaoHabilitacao.objects.create(curso_sigla="CEG", habilitacao_sigla="PRT", enfase_sigla="",
                                          curriculo=self.curriculo, origem="pre_cadastro")
        requisito("PRT2001", "pre", ["PRT1001"])
        requisito("MAT4162", "pre", ["MAT4161"])
        requisito("PRT3001", "pre", ["PRT2001"], ["PRT1002"])          # B ou D
        requisito("PRT3002", "co", ["PRT3001"])
        requisito("PRT3003", "pre", ["PRT9999"])
        requisito("PRT4001", "pre", ["PRT3001", "PRT3002"])          # C e PRT3002
        requisito("PRT5001", "pre", ["PRT3003"])                     # fora do currículo
        Requisito.objects.create(disciplina="PRT1002", tipo="pre", alternativa=0, codigo="",
                                 observacao="MATEMÁTICA (nível 3)")
        self.aluno = criar_aluno("9600001")
        linhas = [disciplina_espelho("PRT1001", "AP", periodo="20251"),
                  disciplina_espelho("MAT1161", "AP", periodo="20251"),
                  disciplina_espelho("PRT2001", "EA", periodo="20252")]
        salvar_espelho(self.aluno, dados_espelho(linhas, curso="CEG", habilitacao="PRT", enfase=""))
        self.client.force_login(self.aluno.usuario)

    def cartoes(self, resposta):
        return {d["codigo"]: d for trilha in resposta.context["trilhas"] for d in trilha["disciplinas"]}


class FluxogramaTests(TelaDePreRequisitosTestCase):
    def test_colunas_por_periodo_e_coluna_de_optativas(self):
        resposta = self.client.get("/pre-requisitos/")
        self.assertEqual([t["nome"] for t in resposta.context["trilhas"]],
                         ["1º período", "2º período", "3º período", "4º período"])
        self.assertNotIn("PRT0100", self.cartoes(resposta))              # vaga de optativa não é cartão de disciplina
        self.assertEqual([(g["codigo"], g["faltam"]) for g in resposta.context["grupos"]], [("PRT0100", 1)])
        self.assertContains(resposta, "Eletivas / optativas")
        self.assertContains(resposta, "Curso Fluxograma")
        self.assertContains(resposta, 'href="/eletivas/"')

    def test_status_de_cada_cartao(self):
        cartoes = self.cartoes(self.client.get("/pre-requisitos/"))
        status = {codigo: d["status"] for codigo, d in cartoes.items()}
        self.assertEqual(status["PRT1001"], "concluida")
        self.assertEqual(status["PRT2001"], "andamento")
        self.assertEqual(status["PRT3001"], "disponivel")       # B (em andamento) cumpre "B ou D"
        self.assertEqual(status["PRT1002"], "disponivel")       # nivelamento não bloqueia
        self.assertEqual(status["PRT3003"], "bloqueada")
        self.assertEqual(cartoes["PRT3003"]["falta"], "Falta: PRT9999")
        self.assertEqual(cartoes["PRT4001"]["falta"], "Falta: PRT3001 e PRT3002")
        self.assertEqual(cartoes["PRT3001"]["falta"], "")

    def test_equivalencia_conta_como_feita(self):
        status = {c: d["status"] for c, d in self.cartoes(self.client.get("/pre-requisitos/")).items()}
        self.assertEqual((status["MAT4161"], status["MAT4162"]), ("concluida", "disponivel"))

    def test_marca_de_atrasada(self):
        # período atual = 2º (o do que está em andamento): o que sobrou do 1º está atrasado
        resposta = self.client.get("/pre-requisitos/")
        self.assertEqual((resposta.context["periodo_atual"], resposta.context["periodo_referencia"]), (2, 3))
        # (mesma regra do gerador: pendente de período até o atual = atrasada)
        cartoes = self.cartoes(resposta)
        self.assertTrue(cartoes["PRT1002"]["atrasada"])
        self.assertTrue(cartoes["MAT4162"]["atrasada"])
        self.assertFalse(cartoes["PRT1001"]["atrasada"])        # já feita
        self.assertFalse(cartoes["PRT2001"]["atrasada"])        # em andamento
        self.assertFalse(cartoes["PRT3001"]["atrasada"])        # do período de referência
        self.assertContains(resposta, 'class="marca-atrasada"', count=2)

    def test_exige_liga_os_cartoes_para_as_setas(self):
        cartoes = self.cartoes(self.client.get("/pre-requisitos/"))
        self.assertEqual(cartoes["PRT3001"]["exige"], "PRT1002 PRT2001")
        self.assertEqual(cartoes["PRT4001"]["exige"], "PRT3001 PRT3002")
        self.assertEqual(cartoes["PRT3003"]["exige"], "")        # PRT9999 não está no fluxograma
        self.assertEqual(cartoes["MAT4162"]["exige"], "MAT4161")

    def test_cartao_acessivel_por_teclado(self):
        resposta = self.client.get("/pre-requisitos/")
        self.assertContains(resposta, 'data-codigo="PRT3001" data-exige="PRT1002 PRT2001"')
        self.assertContains(resposta, 'role="button" tabindex="0"', count=9)

    def test_sem_curriculo_mostra_aviso_e_botao_do_perfil(self):
        aluno = criar_aluno("9600002")
        self.client.force_login(aluno.usuario)
        resposta = self.client.get("/pre-requisitos/")
        self.assertEqual(resposta.context["trilhas"], [])
        self.assertContains(resposta, "Ainda não sabemos qual é o seu curso")
        self.assertContains(resposta, "window.location.href='/perfil/'")
        self.assertContains(resposta, "Buscar qualquer disciplina")

    def test_mostra_so_o_curriculo_do_aluno(self):
        outro = criar_curriculo("Outro Curso", [("OUT1001", 1), ("OUT2001", 2)])
        LigacaoHabilitacao.objects.create(curso_sigla="CEG", habilitacao_sigla="OUT", enfase_sigla="",
                                          curriculo=outro, origem="pre_cadastro")
        resposta = self.client.get("/pre-requisitos/")
        self.assertNotContains(resposta, "OUT1001")
        self.assertNotContains(resposta, "Outro Curso")

    def test_consultas_nao_crescem_com_o_curriculo(self):
        with CaptureQueriesContext(connection) as pequeno:
            self.client.get("/pre-requisitos/")
        # mais 50 disciplinas (com requisito) no currículo: o mesmo número de consultas
        from .models import DisciplinaCurriculo
        for numero in range(50):
            codigo = f"PRT7{numero:03d}"
            DisciplinaCurriculo.objects.create(curriculo=self.curriculo, codigo=codigo, nome="Disciplina " + codigo,
                                               periodo=5 + numero % 5, creditos=4, ordem=100 + numero)
            Requisito.objects.create(disciplina=codigo, tipo="pre", alternativa=0, codigo="PRT3001")
        with self.assertNumQueries(len(pequeno.captured_queries)):
            resposta = self.client.get("/pre-requisitos/")
        self.assertEqual(len(self.cartoes(resposta)), 59)


class ApiDaDisciplinaTests(TelaDePreRequisitosTestCase):
    def api(self, codigo):
        resposta = self.client.get(f"/api/disciplinas/codigo/{codigo}/")
        self.assertEqual(resposta.status_code, 200)
        return resposta.json()

    def test_campos_do_painel(self):
        dados = self.api("PRT3001")
        self.assertEqual((dados["codigo"], dados["creditos"], dados["periodo"]), ("PRT3001", 4, 3))
        self.assertEqual(dados["status"], "disponivel")
        self.assertEqual(dados["ementa_url"], "/eletivas/PRT3001/")
        # "B ou D", com a marca de cada uma: ▶ em andamento, ✗ falta
        self.assertEqual([[(x["codigo"], x["marca"]) for x in alt] for alt in dados["pre"]],
                         [[("PRT2001", "▶")], [("PRT1002", "✗")]])
        self.assertEqual([x["codigo"] for x in dados["libera"]], ["PRT4001"])
        self.assertFalse(dados["sem_informacao"])

    def test_co_requisito_libera_e_marca_de_concluida(self):
        self.assertEqual([[x["codigo"] for x in alt] for alt in self.api("PRT3002")["co"]], [["PRT3001"]])
        dados = self.api("PRT1001")
        self.assertEqual([x["codigo"] for x in dados["libera"]], ["PRT2001"])
        self.assertEqual(self.api("PRT2001")["pre"], [[{"codigo": "PRT1001", "nome": "Disciplina PRT1001", "marca": "✓"}]])

    def test_nivelamento_aparece_e_nao_bloqueia(self):
        dados = self.api("PRT1002")
        self.assertEqual(dados["nivelamento"], ["MATEMÁTICA (nível 3)"])
        self.assertEqual(dados["pre"], [])
        self.assertEqual(dados["status"], "disponivel")

    def test_cadeia_de_disciplina_fora_do_curriculo(self):
        dados = self.api("PRT5001")
        self.assertIsNone(dados["periodo"])
        self.assertEqual([[x["codigo"] for x in nivel] for nivel in dados["cadeia"]], [["PRT3003"], ["PRT9999"]])
        self.assertEqual(dados["faltam_na_cadeia"], 2)
        self.assertEqual(dados["status"], "bloqueada")

    def test_cadeia_segue_o_caminho_mais_curto(self):
        # PRT3003 (falta PRT9999 antes) ou PRT3001 (já pode cursar): a cadeia vai por PRT3001,
        # e de PRT3001 pela alternativa que o aluno já está cursando (PRT2001, que não conta como falta)
        requisito("PRT5002", "pre", ["PRT3003"], ["PRT3001"])
        dados = self.api("PRT5002")
        self.assertEqual([[(x["codigo"], x["status"]) for x in nivel] for nivel in dados["cadeia"]],
                         [[("PRT3001", "disponivel")], [("PRT2001", "andamento")]])
        self.assertEqual(dados["faltam_na_cadeia"], 1)

    def test_sem_informacao_de_requisitos(self):
        self.assertTrue(self.api("PRT6001")["sem_informacao"])
        EmentaLida.objects.create(codigo="PRT6001", encontrada=True)    # lida, sem requisito
        self.assertFalse(self.api("PRT6001")["sem_informacao"])

    def test_api_por_id_continua_com_alternativas(self):
        disciplina = Disciplina.objects.create(codigo="PRT3001", nome="Disciplina C", creditos=4)
        Disciplina.objects.create(codigo="PRT2001", nome="Disciplina B", creditos=4)
        dados = self.client.get(f"/api/disciplinas/{disciplina.id}/").json()
        self.assertEqual(dados["id"], disciplina.id)
        self.assertEqual([[x["codigo"] for x in alt] for alt in dados["alternativas"]], [["PRT2001"], ["PRT1002"]])
        self.assertEqual(dados["alternativas"][0][0]["nome"], "Disciplina B")
        self.assertIn("libera", dados)

    def test_exigem_login(self):
        self.client.logout()
        for url in ("/api/disciplinas/codigo/PRT3001/", "/api/disciplinas/busca/?q=PRT", "/pre-requisitos/"):
            self.assertEqual(self.client.get(url).status_code, 302, url)


class BuscaDeDisciplinasTests(TelaDePreRequisitosTestCase):
    def setUp(self):
        super().setUp()
        for codigo, nome in (("PRT3001", "Disciplina C"), ("PRT1002", "Laboratório D"), ("PRT6001", "Seminário Livre"),
                             ("PRT3003", "Disciplina Bloqueada"), ("PRT1001", "Disciplina A")):
            Disciplina.objects.create(codigo=codigo, nome=nome, creditos=4)

    def busca(self, consulta):
        resposta = self.client.get("/api/disciplinas/busca/" + consulta)
        self.assertEqual(resposta.status_code, 200)
        return {r["codigo"]: r for r in resposta.json()["resultados"]}

    def test_por_codigo_ou_nome_com_status(self):
        achadas = self.busca("?q=prt")
        # (PRT2001 entrou em Disciplina pela importação do espelho)
        self.assertEqual(set(achadas), {"PRT1001", "PRT1002", "PRT2001", "PRT3001", "PRT3003", "PRT6001"})
        self.assertEqual(achadas["PRT1001"]["status"], "concluida")
        self.assertEqual(achadas["PRT2001"]["status"], "andamento")
        self.assertEqual(achadas["PRT3003"]["status"], "bloqueada")
        self.assertEqual(set(self.busca("?q=semin")), {"PRT6001"})

    def test_so_sem_pre_requisito(self):
        # PRT6001: a PUC não tem ementa (sem informação), então não entra no filtro;
        # PRT1002 só tem nivelamento, que não exige disciplina
        EmentaLida.objects.create(codigo="PRT6001", encontrada=False)
        self.assertEqual(set(self.busca("?q=PRT&sem_pre=1")), {"PRT1001", "PRT1002"})

    def test_busca_com_acento_acha_nome_sem_acento(self):
        Disciplina.objects.create(codigo="PRT6002", nome="FISICA DE TESTE", creditos=4)
        self.assertEqual(set(self.busca("?q=Física")), {"PRT6002"})

    def test_limite_de_resultados(self):
        for numero in range(30):
            Disciplina.objects.create(codigo=f"PRT8{numero:03d}", nome="Muitas", creditos=2)
        self.assertEqual(len(self.busca("?q=Muitas")), 20)
