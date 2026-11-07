"""Ligação entre a sigla do curso no SAU e um currículo do site da PUC.

A tabela LigacaoHabilitacao "aprende com o uso": quando um aluno confirma o
curso, todos os outros com a mesma sigla passam a ser reconhecidos direto.
"""
import math

from .models import Curriculo, LigacaoHabilitacao

# A primeira sugestão só é "forte" se tiver pelo menos esta vantagem sobre a segunda
VANTAGEM_SUGESTAO_FORTE = 1.5


def registrar_siglas(aluno):
    """Depois de salvar o espelho: devolve True se o curso do aluno já é reconhecido.
    Se a sigla nunca foi vista, cria uma ligação vazia (aparece como pendente no admin)."""
    if not aluno.curso_sigla:
        return False
    if LigacaoHabilitacao.para_siglas(aluno.curso_sigla, aluno.habilitacao_sigla, aluno.enfase_sigla):
        return True

    LigacaoHabilitacao.objects.get_or_create(
        curso_sigla=aluno.curso_sigla,
        habilitacao_sigla=aluno.habilitacao_sigla,
        enfase_sigla=aluno.enfase_sigla,
        defaults={'curriculo': None, 'origem': 'aluno'},
    )
    return False


def deduzir_curriculos(aluno, limite=5):
    """Sugere os currículos mais parecidos com o histórico do aluno. É só sugestão:
    quem decide é o aluno (confirmar_curso) ou o admin.

    Cada código em comum vale log((N + 1) / em quantos currículos ele aparece):
    código raro pesa muito, código do ciclo básico (comum a todas as engenharias) pesa pouco.
    """
    from .historico import codigos_bloqueados  # import aqui para evitar import circular

    codigos_do_aluno = codigos_bloqueados(aluno)
    if not codigos_do_aluno:
        return []

    curriculos = list(Curriculo.objects.prefetch_related('itens'))
    codigos_por_curriculo = {
        curriculo: {item.codigo for item in curriculo.itens.all() if not item.eh_grupo}
        for curriculo in curriculos
    }

    quantos_tem = {}
    for codigos in codigos_por_curriculo.values():
        for codigo in codigos:
            quantos_tem[codigo] = quantos_tem.get(codigo, 0) + 1

    total = len(curriculos)
    resultados = []
    for curriculo, codigos in codigos_por_curriculo.items():
        em_comum = codigos & codigos_do_aluno
        pontos = sum(math.log((total + 1) / quantos_tem[codigo]) for codigo in em_comum)
        if pontos > 0:
            resultados.append({'curriculo': curriculo, 'pontos': round(pontos, 2),
                               'em_comum': len(em_comum), 'forte': False})

    resultados.sort(key=lambda r: r['pontos'], reverse=True)
    resultados = resultados[:limite]

    if resultados:
        segundo = resultados[1]['pontos'] if len(resultados) > 1 else 0
        resultados[0]['forte'] = resultados[0]['pontos'] >= VANTAGEM_SUGESTAO_FORTE * segundo
    return resultados


def confirmar_curso(aluno, curriculo):
    """O aluno confirma o curso: grava a ligação da sigla exata dele.
    Não sobrescreve uma ligação feita pelo admin. Devolve True se gravou."""
    ligacao, criada = LigacaoHabilitacao.objects.get_or_create(
        curso_sigla=aluno.curso_sigla,
        habilitacao_sigla=aluno.habilitacao_sigla,
        enfase_sigla=aluno.enfase_sigla,
        defaults={'curriculo': curriculo, 'origem': 'aluno', 'confirmado_por': aluno},
    )
    if criada:
        return True
    if ligacao.origem == 'admin' and ligacao.curriculo and ligacao.curriculo != curriculo:
        return False

    ligacao.curriculo = curriculo
    ligacao.origem = 'aluno'
    ligacao.confirmado_por = aluno
    ligacao.save()
    return True
