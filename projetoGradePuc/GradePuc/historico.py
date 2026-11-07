"""Salva no banco o que foi lido do Espelho do Histórico e responde perguntas sobre ele."""
from django.db import transaction
from django.utils import timezone

from .espelho import SITUACOES_CURSADAS, SITUACOES_EM_ANDAMENTO
from .ligacao import registrar_siglas
from .models import Disciplina, HistoricoDisciplina, LigacaoHabilitacao

# O micro-horário é do PRÓXIMO semestre. O que o aluno está cursando agora (EA)
# já vai estar concluído quando ele fizer as turmas sugeridas, então conta como
# cursada: não é sugerida de novo e vale como pré-requisito.
EM_ANDAMENTO_CONTA_COMO_CURSADA = True


def situacoes_que_bloqueiam():
    situacoes = set(SITUACOES_CURSADAS)
    if EM_ANDAMENTO_CONTA_COMO_CURSADA:
        situacoes |= SITUACOES_EM_ANDAMENTO
    return situacoes


def codigos_bloqueados(aluno):
    """Códigos que não devem ser sugeridos: cursadas, em andamento e seus grupos
    (quem fez MAT4181 com Grupo MAT4161 conta como tendo feito MAT4161)."""
    bloqueiam = situacoes_que_bloqueiam()
    codigos = set()
    for linha in aluno.historico.all():
        if linha.situacao in bloqueiam:
            codigos.add(linha.codigo)
            if linha.grupo:
                codigos.add(linha.grupo)
    return codigos


def sincronizar_cursadas(aluno, codigos_antigos):
    """Troca, em aluno.disciplinas_cursadas, o que veio do espelho anterior pelo atual.
    Marca TODAS as Disciplina com o código (o código não é único no banco e o
    gerador de grades compara pelo id)."""
    aluno.disciplinas_cursadas.remove(*Disciplina.objects.filter(codigo__in=codigos_antigos))
    aluno.disciplinas_cursadas.add(*Disciplina.objects.filter(codigo__in=codigos_bloqueados(aluno)))


def salvar_espelho(aluno, dados):
    """Grava o espelho lido (substitui o anterior). Devolve True se o curso foi reconhecido."""
    with transaction.atomic():
        codigos_antigos = codigos_bloqueados(aluno)

        aluno.curso_sigla = dados['curso']
        aluno.habilitacao_sigla = dados['habilitacao']
        aluno.enfase_sigla = dados['enfase']
        aluno.ano_curriculo = dados['ano_curriculo']
        aluno.codigo_curriculo = dados['codigo_curriculo']
        aluno.cr = dados['cr']
        aluno.matricula_espelho = dados['matricula']
        aluno.espelho_importado_em = timezone.now()
        aluno.save()

        aluno.historico.all().delete()
        for d in dados['disciplinas']:
            disciplina = Disciplina.objects.filter(codigo=d['codigo']).first()
            if disciplina is None:
                disciplina = Disciplina.objects.create(
                    codigo=d['codigo'],
                    nome=d['nome'][:100],
                    creditos=d['creditos'],
                    departamento=d['codigo'][:3],
                )
            HistoricoDisciplina.objects.create(
                aluno=aluno,
                periodo=d['periodo'],
                codigo=d['codigo'],
                nome=d['nome'],
                turma=d['turma'],
                grau=d['grau'],
                situacao=d['situacao'],
                tipo=d['tipo'],
                grupo=d['grupo'],
                creditos=d['creditos'],
                disciplina=disciplina,
            )

        sincronizar_cursadas(aluno, codigos_antigos)
        return registrar_siglas(aluno)


def remover_historico(aluno):
    """Apaga o histórico, os dados de curso e as cursadas que vieram do espelho."""
    with transaction.atomic():
        codigos = codigos_bloqueados(aluno)
        aluno.historico.all().delete()
        aluno.disciplinas_cursadas.remove(*Disciplina.objects.filter(codigo__in=codigos))

        aluno.curso_sigla = ''
        aluno.habilitacao_sigla = ''
        aluno.enfase_sigla = ''
        aluno.ano_curriculo = ''
        aluno.codigo_curriculo = ''
        aluno.cr = ''
        aluno.matricula_espelho = ''
        aluno.espelho_importado_em = None
        aluno.save()


def curriculo_do_aluno(aluno):
    if not aluno.curso_sigla:
        return None
    ligacao = LigacaoHabilitacao.para_siglas(aluno.curso_sigla, aluno.habilitacao_sigla, aluno.enfase_sigla)
    return ligacao.curriculo if ligacao else None


def pendentes_do_curriculo(aluno):
    """Itens do currículo do aluno que ainda não foram cumpridos, pelo período recomendado
    (os de período indeterminado ficam no fim)."""
    curriculo = curriculo_do_aluno(aluno)
    if curriculo is None:
        return []
    feitos = codigos_bloqueados(aluno)
    itens = [item for item in curriculo.itens.all() if item.codigo not in feitos]
    itens.sort(key=lambda item: (item.periodo is None, item.periodo or 0, item.ordem))
    return itens
