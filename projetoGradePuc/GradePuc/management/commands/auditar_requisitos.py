"""Confere no banco real que nenhuma turma sugerida (grades e eletivas) fura a regra de
pré/co-requisito, com as turmas de verdade do micro-horário.

  python manage.py auditar_requisitos

- Para cada aluno com espelho importado: as grades com as preferências dele.
- Para cada currículo cadastrado: históricos sintéticos (sem nada, meio do curso,
  adiantado, com atrasadas, com equivalente do espelho), criados dentro de uma transação
  que é desfeita no fim: nada fica gravado.
A verificação é a de auditoria.py (independente de requisitos.py). No fim:
"N turmas verificadas, 0 violações" ou a lista de violações. Não mostra matrícula nem nota.
"""
from collections import Counter

from django.contrib.auth.models import User
from django.core.management.base import BaseCommand
from django.db import transaction

from ...auditoria import Verificador, historicos_sinteticos, ligar_curriculo
from ...historico import curriculo_do_aluno, salvar_espelho
from ...models import Aluno, Curriculo, RotinaPreferencias


def preferencias_padrao(aluno):
    return RotinaPreferencias(aluno=aluno, turno="sem_preferencia", modalidade="hibrido",
                              distribuicao_aulas="tanto_faz", janelas="tanto_faz", carga_disciplinas="media")


class Command(BaseCommand):
    help = "Confere que as grades sugeridas e as eletivas respeitam os pré/co-requisitos."

    def add_arguments(self, parser):
        parser.add_argument("--so-alunos", action="store_true", help="Só os alunos com espelho (sem os sintéticos).")

    def handle(self, *args, **options):
        verificador = Verificador()
        total, violacoes = 0, []

        self.stdout.write("Alunos com espelho importado:")
        for aluno in Aluno.objects.exclude(espelho_importado_em=None).order_by("id"):
            preferencias = RotinaPreferencias.objects.filter(aluno=aluno).first() or preferencias_padrao(aluno)
            verificadas, problemas, sem_dados = verificador.auditar(aluno, preferencias)
            total += verificadas
            siglas = f"{aluno.curso_sigla}/{aluno.habilitacao_sigla}/{aluno.enfase_sigla or '-'}"
            curriculo = curriculo_do_aluno(aluno)
            self.stdout.write(
                f"  aluno #{aluno.id} ({siglas}, {curriculo or 'curso não reconhecido'}, carga "
                f"{preferencias.carga_disciplinas}): {verificadas} turmas verificadas, {len(problemas)} violações; "
                f"turmas de disciplinas SEM dados de requisito nas grades: {len(sem_dados)}"
                + (f" ({', '.join(f'{c} x{n}' for c, n in sorted(Counter(sem_dados).items()))})" if sem_dados else "")
            )
            violacoes += [f"aluno #{aluno.id}: {p}" for p in problemas]

        if not options["so_alunos"]:
            self.stdout.write("Currículos com históricos sintéticos (desfeito no fim):")
            with transaction.atomic():
                numero = 0
                for curriculo in Curriculo.objects.order_by("curso_nome", "ano", "enfase"):
                    curso, habilitacao = ligar_curriculo(curriculo)
                    verificadas_no_curriculo = 0
                    for nome, disciplinas in historicos_sinteticos(curriculo).items():
                        numero += 1
                        usuario = User.objects.create_user(f"auditoria_{numero}", password=None)
                        aluno = Aluno.objects.create(usuario=usuario, matricula=f"auditoria_{numero}", senha="")
                        salvar_espelho(aluno, {
                            "matricula": "", "curso": curso, "habilitacao": habilitacao, "enfase": "",
                            "ano_curriculo": "", "codigo_curriculo": "", "cr": "", "disciplinas": disciplinas,
                        })
                        verificadas, problemas, _ = verificador.auditar(aluno, preferencias_padrao(aluno))
                        verificadas_no_curriculo += verificadas
                        violacoes += [f"{curriculo} / {nome}: {p}" for p in problemas]
                    total += verificadas_no_curriculo
                    self.stdout.write(f"  {curriculo}: {verificadas_no_curriculo} turmas verificadas")
                transaction.set_rollback(True)

        self.stdout.write("")
        if violacoes:
            self.stdout.write(self.style.ERROR(f"{total} turmas verificadas, {len(violacoes)} violações:"))
            for violacao in violacoes:
                self.stdout.write("  " + violacao)
        else:
            self.stdout.write(self.style.SUCCESS(f"{total} turmas verificadas, 0 violações"))
