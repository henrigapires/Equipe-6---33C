import pandas as pd
import re

from pathlib import Path
from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from ...models import Disciplina, Professor, Turma

def texto(valor):
    if pd.isna(valor):
        return ""
    return str(valor).strip()

def numero(valor):
    valor = texto(valor)

    if not valor:
        return 0

    try:
        return int(float(valor.replace(",",".")))
    except ValueError:
        return 0

def separar_horario_sala(valor):
    linhas = texto(valor).splitlines()

    horarios = []
    salas = []

    for linha in linhas:
        linha = linha.strip()

        if not linha:
            continue

        partes = linha.split()

        if len(partes) >= 2:
            sala = partes[-1]
            horario = " ".join(partes[:-1])

            horarios.append(horario)

            if sala not in salas:
                salas.append(sala)

    return "; ".join(horarios), ", ".join(salas)

class Command(BaseCommand):
    help = "Importa disciplinas, professores e turmas do Micro-horário."

    def handle(self, *args, **options):

        caminho = (
            Path(settings.BASE_DIR)
            / "Horario_das_Disciplinas_04112026.xlsx"
        )

        if not caminho.exists():
            raise CommandError(
                f"Arquivo não encontrado: {caminho}"
            )

        self.stdout.write("Lendo planilha... ")

        df = pd.read_excel(
            caminho,
            header=1,
            dtype=str
        )

        df.columns = df.columns.str.strip()

        colunas_obrigatorias = [
            "Disciplina",
            "Professor",
            "Créditos",
            "Turma",
            "Destino",
            "Vagas",
            "Turno",
            "Horário/Sala",
            "Pré Req",
            "Depto"
        ]

        faltantes = [
            coluna for coluna in colunas_obrigatorias
            if coluna not in df.columns
        ]

        if faltantes:
            raise CommandError(
                f"Colunas não encontradas {faltantes}"
            )

        disciplinas_criadas = 0
        professores_criados = 0
        turmas_criadas = 0
        turmas_atualizadas = 0

        self.stdout.write(
            f"Encontradas {len(df)} linhas."
        )

        with transaction.atomic():
            for _, linha in df.iterrows():
                nome_completo = texto(linha["Disciplina"])

                if " - " not in nome_completo:
                    continue

                codigo, nome = nome_completo.split(" - ", 1)

                codigo = codigo.strip()
                nome = nome.strip()

                disciplina, criada = (
                    Disciplina.objects.update_or_create(
                        codigo=codigo,
                        defaults={
                            "nome": nome,
                            "creditos": numero(linha["Créditos"]),
                            "departamento": texto(linha["Depto"]),
                        }
                    )
                )

                if criada:
                    disciplinas_criadas += 1

                nome_professor = texto(linha["Professor"])

                if not nome_professor:
                    raise CommandError(
                        f"Professor não informado: {codigo}"
                    )

                professor, criada = (Professor.objects.get_or_create(nome=nome_professor))

                if criada:
                    professores_criados += 1

                horarios, sala = separar_horario_sala(linha["Horário/Sala"])

                codigo_turma = texto(linha["Turma"])
                destino = texto(linha["Destino"])
                turno = texto(linha["Turno"])
                vagas = numero(linha["Vagas"])

                turma, criada = Turma.objects.update_or_create(
                    disciplina=disciplina,
                    codigo_turma=codigo_turma,
                    destino=destino,
                    defaults={
                        "professor": professor,
                        "turno": turno,
                        "dias_horarios": horarios,
                        "vagas": vagas,
                        "sala": sala,
                    }
                )

                if criada:
                    turmas_criadas += 1 
                else:
                    turmas_atualizadas += 1

        self.stdout.write(
            self.style.SUCCESS(
                "\nIMPORTAÇÃO CONCLUÍDA!\n"
                f"Disciplinas novas: {disciplinas_criadas}\n"
                f"Professores novas: {professores_criados}\n"
                f"Turmas novas: {turmas_criadas}\n"
                f"Turmas atualizadas: {turmas_atualizadas}"
            )
        )   