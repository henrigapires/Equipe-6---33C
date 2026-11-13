"""Pré/co-requisitos lidos das ementas da PUC (ementas.py e importar_requisitos).

As fixtures são trechos mínimos do HTML real de três ementas (MAT4162, FIS4003, ENG4021).
"""
import importlib
import json
import tempfile
from io import StringIO
from pathlib import Path
from unittest.mock import patch

import requests
from django.apps import apps
from django.core.management import call_command
from django.test import TestCase

from . import ementas
from .ementas import interpretar_ementa
from .models import EmentaLida, Requisito

MAT4162 = """
<fieldset id="prerequisito"> <legend>Pr&eacute;-requisitos</legend>
<span id="rptPreRequisito_ctl00_spanPreRequisito" class="links"> <a href='ementa.aspx?cd=MAT1158' title='MAT1158 - CALCULO A UMA VARIAVEL B'>MAT1158</a> <span>e MATEMÁTICA (nivel 3)</span></span> <p>ou </p>
<span id="rptPreRequisito_ctl01_spanPreRequisito" class="links"> <a href='ementa.aspx?cd=MAT1161' title='MAT1161 - CALCULO DE UMA VARIAVEL'>MAT1161</a> <span>e MATEMÁTICA (nivel 3)</span></span> <p>ou </p>
<span id="rptPreRequisito_ctl02_spanPreRequisito" class="links"> <a href='ementa.aspx?cd=MAT1181' title='MAT1181'>MAT1181</a> <span>e MATEMÁTICA (nivel 3)</span></span> <p>ou </p>
<span id="rptPreRequisito_ctl03_spanPreRequisito" class="links"> <a href='ementa.aspx?cd=MAT4161' title='MAT4161'>MAT4161</a> <span>e MATEMÁTICA (nivel 3)</span></span> <p>ou </p>
<span id="rptPreRequisito_ctl04_spanPreRequisito" class="links"> <a href='ementa.aspx?cd=MAT4181' title='MAT4181'>MAT4181</a> <span>e MATEMÁTICA (nivel 3)</span></span> </fieldset>
<fieldset id="corequisito"> <legend>Co-requisitos</legend> <p>Nenhum co-requisito encontrado para MAT4162</p></fieldset>
"""

FIS4003 = """
<fieldset id="prerequisito"> <legend>Pr&eacute;-requisitos</legend>
<span id="rptPreRequisito_ctl00_spanPreRequisito" class="links"> <a href='ementa.aspx?cd=FIS1041' title='FIS1041'>FIS1041</a> </span> <p>ou </p>
<span id="rptPreRequisito_ctl01_spanPreRequisito" class="links"> <a href='ementa.aspx?cd=FIS1071' title='FIS1071'>FIS1071</a> </span> <p>ou </p>
<span id="rptPreRequisito_ctl02_spanPreRequisito" class="links"> <a href='ementa.aspx?cd=FIS4002' title='FIS4002'>FIS4002</a> </span> </fieldset>
<fieldset id="corequisito"> <legend>Co-requisitos</legend> <p>Nenhum co-requisito encontrado para FIS4003</p></fieldset>
"""

ENG4021 = """
<fieldset id="prerequisito"> <legend>Pr&eacute;-requisitos</legend>
<span id="rptPreRequisito_ctl00_spanPreRequisito" class="links"> <a href='ementa.aspx?cd=ENG1000' title='ENG1000'>ENG1000</a> </span> <p>ou </p>
<span id="rptPreRequisito_ctl01_spanPreRequisito" class="links"> <a href='ementa.aspx?cd=ENG1127' title='ENG1127'>ENG1127</a> </span> <p>ou </p>
<span id="rptPreRequisito_ctl02_spanPreRequisito" class="links"> <a href='ementa.aspx?cd=ENG4010' title='ENG4010'>ENG4010</a> </span> </fieldset>
<fieldset id="corequisito"> <legend>Co-requisitos</legend>
<span id="rptCoRequisito_ctl00_spanCoRequisito" class="links"> <a href='ementa.aspx?cd=EMP1320' title='EMP1320'>EMP1320</a> <span> e </span> <a href='ementa.aspx?cd=INF1037' title='INF1037'>INF1037</a> <!----> </span> <p>ou </p>
<span id="rptCoRequisito_ctl01_spanCoRequisito" class="links"> <a href='ementa.aspx?cd=EMP1320' title='EMP1320'>EMP1320</a> <span> e </span> <a href='ementa.aspx?cd=INF1026' title='INF1026'>INF1026</a> <!----> </span> <p>ou </p>
<span id="rptCoRequisito_ctl02_spanCoRequisito" class="links"> <a href='ementa.aspx?cd=EMP1320' title='EMP1320'>EMP1320</a> <span> e </span> <a href='ementa.aspx?cd=INF1007' title='INF1007'>INF1007</a> <!----> </span> </fieldset>
"""

SEM_REQUISITO = """
<fieldset id="prerequisito"> <legend>Pr&eacute;-requisitos</legend> <p>Nenhum pré-requisito encontrado para FIS4001</p></fieldset>
<fieldset id="corequisito"> <legend>Co-requisitos</legend> <p>Nenhum co-requisito encontrado para FIS4001</p></fieldset>
"""

SEM_EMENTA = "<html><body>Ementa de Disciplina ZZZ9999 | 0 créditos Disciplina sem ementa cadastrada.</body></html>"


class InterpretarEmentaTests(TestCase):
    def test_ou_entre_alternativas_e_nivelamento_como_observacao(self):
        lido = interpretar_ementa(MAT4162)
        self.assertEqual(lido["pre"], [["MAT1158"], ["MAT1161"], ["MAT1181"], ["MAT4161"], ["MAT4181"]])
        self.assertEqual(lido["observacoes"]["pre"], ["MATEMÁTICA (nivel 3)"] * 5)
        self.assertEqual(lido["co"], [])
        self.assertTrue(lido["encontrada"])

    def test_alternativas_de_um_codigo(self):
        self.assertEqual(interpretar_ementa(FIS4003)["pre"], [["FIS1041"], ["FIS1071"], ["FIS4002"]])

    def test_e_dentro_da_alternativa(self):
        lido = interpretar_ementa(ENG4021)
        self.assertEqual(lido["pre"], [["ENG1000"], ["ENG1127"], ["ENG4010"]])
        self.assertEqual(lido["co"], [["EMP1320", "INF1037"], ["EMP1320", "INF1026"], ["EMP1320", "INF1007"]])
        self.assertEqual(lido["observacoes"]["co"], ["", "", ""])

    def test_nenhum_requisito(self):
        lido = interpretar_ementa(SEM_REQUISITO)
        self.assertEqual((lido["pre"], lido["co"], lido["encontrada"]), ([], [], True))

    def test_codigo_sem_ementa(self):
        self.assertFalse(interpretar_ementa(SEM_EMENTA)["encontrada"])


class GravarEExportarTests(TestCase):
    def setUp(self):
        Requisito.objects.all().delete()
        EmentaLida.objects.all().delete()

    def test_gravar_e_ler_de_volta(self):
        ementas.gravar_requisitos("MAT4162", interpretar_ementa(MAT4162))
        ementas.gravar_requisitos("ENG4021", interpretar_ementa(ENG4021))
        self.assertEqual(Requisito.objects.filter(disciplina="MAT4162", tipo="pre").count(), 5)
        self.assertEqual(
            Requisito.objects.get(disciplina="MAT4162", codigo="MAT4181").observacao, "MATEMÁTICA (nivel 3)"
        )
        lidos = ementas.requisitos_do_banco()
        self.assertEqual(lidos["ENG4021"]["co"][1], ["EMP1320", "INF1026"])
        self.assertTrue(EmentaLida.objects.get(codigo="MAT4162").encontrada)

    def test_gravar_de_novo_troca_os_requisitos(self):
        ementas.gravar_requisitos("FIS4003", interpretar_ementa(FIS4003))
        ementas.gravar_requisitos("FIS4003", interpretar_ementa(SEM_REQUISITO))
        self.assertFalse(Requisito.objects.filter(disciplina="FIS4003").exists())

    def test_exportar_e_carregar(self):
        ementas.gravar_requisitos("ENG4021", interpretar_ementa(ENG4021))
        ementas.gravar_requisitos("ZZZ9999", interpretar_ementa(SEM_EMENTA))
        with tempfile.TemporaryDirectory() as pasta:
            arquivo = Path(pasta) / "requisitos.json"
            with patch.object(ementas, "ARQUIVO", arquivo):
                ementas.exportar_arquivo()
            dados = json.loads(arquivo.read_text(encoding="utf-8"))
        self.assertEqual(dados["sem_ementa"], ["ZZZ9999"])
        self.assertIn("ENG4021", dados["lidas"])
        Requisito.objects.all().delete()
        EmentaLida.objects.all().delete()
        ementas.carregar_dados(dados)
        self.assertEqual(ementas.requisitos_do_banco()["ENG4021"]["co"][0], ["EMP1320", "INF1037"])
        self.assertFalse(EmentaLida.objects.get(codigo="ZZZ9999").encontrada)


class MigrationDosRequisitosTests(TestCase):
    def test_banco_vazio_recebe_o_arquivo_e_banco_cheio_nao_muda(self):
        migracao = importlib.import_module("GradePuc.migrations.0011_carregar_requisitos")
        dados = json.loads(migracao.ARQUIVO.read_text(encoding="utf-8"))
        Requisito.objects.all().delete()
        EmentaLida.objects.all().delete()
        migracao.carregar_requisitos(apps, None)
        self.assertEqual(EmentaLida.objects.count(), len(dados["lidas"]) + len(dados["sem_ementa"]))
        self.assertEqual(sorted(set(Requisito.objects.values_list("disciplina", flat=True))), sorted(dados["requisitos"]))
        antes = Requisito.objects.count()
        migracao.carregar_requisitos(apps, None)        # já tem: não duplica
        self.assertEqual(Requisito.objects.count(), antes)


class RespostaFalsa:
    def __init__(self, html, status=200):
        self.content = html.encode("cp1252")
        self.status_code = status

    def raise_for_status(self):
        if self.status_code >= 400:
            raise requests.HTTPError(f"{self.status_code}")


class ImportarRequisitosCommandTests(TestCase):
    """Sem internet: o requests.get é trocado por páginas falsas."""

    PAGINAS = {"ENG4021": ENG4021, "FIS4003": FIS4003, "ZZZ9999": SEM_EMENTA}

    def setUp(self):
        Requisito.objects.all().delete()
        EmentaLida.objects.all().delete()
        self.pedidos = []

    def get_falso(self, url, **kwargs):
        codigo = url.rsplit("=", 1)[1]
        self.pedidos.append(codigo)
        if codigo == "INF1007":
            raise requests.ConnectionError("fora do ar")
        return RespostaFalsa(self.PAGINAS.get(codigo, SEM_REQUISITO))

    def rodar(self, *argumentos):
        saida = StringIO()
        modulo = "GradePuc.management.commands.importar_requisitos"
        with tempfile.TemporaryDirectory() as pasta, \
                patch.object(ementas, "ARQUIVO", Path(pasta) / "requisitos.json"), \
                patch(f"{modulo}.requests.get", side_effect=self.get_falso), \
                patch(f"{modulo}.time.sleep"), patch(f"{modulo}.INTERVALO", 0):
            call_command("importar_requisitos", *argumentos, stdout=saida)
        return saida.getvalue()

    def test_segue_a_rede_ate_fechar_e_relata_os_erros(self):
        saida = self.rodar("--codigos", "ENG4021", "ZZZ9999")
        lidas = set(EmentaLida.objects.values_list("codigo", flat=True))
        # ENG4021 puxa ENG1000, ENG1127, ENG4010, EMP1320, INF1037, INF1026 (INF1007 falhou)
        self.assertEqual(lidas, {"ENG4021", "ZZZ9999", "ENG1000", "ENG1127", "ENG4010", "EMP1320", "INF1037", "INF1026"})
        self.assertIn("Códigos sem ementa na PUC (1): ZZZ9999", saida)
        self.assertIn("INF1007: ConnectionError", saida)
        self.assertEqual(self.pedidos.count("INF1007"), 3)          # três tentativas

    def test_retomavel_so_baixa_o_que_falta(self):
        self.rodar("--codigos", "ENG4021")
        self.pedidos.clear()
        self.rodar("--codigos", "ENG4021")
        self.assertEqual(self.pedidos, ["INF1007"] * 3)           # só o que tinha dado erro

    def test_refazer_baixa_tudo_de_novo(self):
        self.rodar("--codigos", "FIS4003")
        self.pedidos.clear()
        self.rodar("--codigos", "FIS4003", "--refazer")
        self.assertEqual(sorted(self.pedidos), ["FIS1041", "FIS1071", "FIS4002", "FIS4003"])
