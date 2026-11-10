"""Salva no banco o que foi lido do Espelho do Histórico e responde perguntas sobre ele."""
import re

from django.db import transaction
from django.utils import timezone

from .espelho import SITUACOES_CURSADAS, SITUACOES_EM_ANDAMENTO
from .ligacao import registrar_siglas
from .models import Disciplina, DisciplinaCurriculo, HistoricoDisciplina, LigacaoHabilitacao

# O micro-horário é do PRÓXIMO semestre. O que o aluno está cursando agora (EA)
# já vai estar concluído quando ele fizer as turmas sugeridas, então conta como
# cursada: não é sugerida de novo e vale como pré-requisito.
EM_ANDAMENTO_CONTA_COMO_CURSADA = True

# Escolha manual "Conta como: nenhum" gravada no campo grupo da linha: a disciplina não
# ocupa vaga de optativa (e a regra automática não a coloca de volta).
SEM_VAGA = '-'
# Tipos de disciplina do SAU que são do próprio currículo: nunca ocupam vaga de optativa.
TIPOS_DO_CURRICULO = {'OB', 'OC'}


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
            if linha.grupo and linha.grupo != SEM_VAGA:
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
            criar_linha(aluno, d)

        sincronizar_cursadas(aluno, codigos_antigos)
        return registrar_siglas(aluno)


def criar_linha(aluno, d):
    """Uma linha do histórico (e a Disciplina do código, se ainda não existir)."""
    disciplina = Disciplina.objects.filter(codigo=d['codigo']).first()
    if disciplina is None:
        disciplina = Disciplina.objects.create(
            codigo=d['codigo'],
            nome=d['nome'][:100],
            creditos=d['creditos'],
            departamento=d['codigo'][:3],
        )
    return HistoricoDisciplina.objects.create(
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


# ---------- Correções à mão (quando a leitura errou) ----------

# Situações que o aluno pode escolher ao corrigir uma linha
SITUACOES_DA_CORRECAO = {'AP': 'Cursada', 'EA': 'Em andamento', 'RM': 'Reprovada'}
SITUACOES_AO_ADICIONAR = ('AP', 'EA')


class CorrecaoInvalida(Exception):
    pass


def disciplina_digitada(codigo, situacao, periodo):
    """Disciplina que o aluno acrescentou à mão. Nome e créditos vêm do banco;
    se o código não for conhecido, levanta CorrecaoInvalida com a mensagem para a tela."""
    codigo = re.sub(r'\s+', '', codigo or '').upper()
    periodo = re.sub(r'[.\s/-]', '', periodo or '')
    if not re.fullmatch(r'[A-Z]{3}\d{4}', codigo):
        raise CorrecaoInvalida('Digite o código da disciplina com 3 letras e 4 números, por exemplo MAT4161.')
    if situacao not in SITUACOES_AO_ADICIONAR:
        raise CorrecaoInvalida('Escolha se a disciplina foi cursada ou está em andamento.')
    if not re.fullmatch(r'\d{4}[0-3]', periodo):
        raise CorrecaoInvalida('Digite o período no formato 20261 (ano e semestre).')
    oficial = dados_oficiais(codigo)
    if oficial is None:
        raise CorrecaoInvalida(f'Não encontramos a disciplina {codigo}. Confira o código no SAU.')
    nome, creditos = oficial
    return {
        'periodo': periodo, 'codigo': codigo, 'nome': nome, 'turma': '', 'grau': '',
        'situacao': situacao, 'tipo': '', 'grupo': '', 'creditos': creditos,
    }


def adicionar_ao_historico(aluno, d):
    if aluno.historico.filter(periodo=d['periodo'], codigo=d['codigo']).exists():
        raise CorrecaoInvalida(f"{d['codigo']} já está no seu histórico em {d['periodo']}.")
    with transaction.atomic():
        codigos_antigos = codigos_bloqueados(aluno)
        criar_linha(aluno, d)
        sincronizar_cursadas(aluno, codigos_antigos)


def remover_do_historico(aluno, linha_id):
    with transaction.atomic():
        codigos_antigos = codigos_bloqueados(aluno)
        apagadas, _ = aluno.historico.filter(id=linha_id).delete()
        sincronizar_cursadas(aluno, codigos_antigos)
    return apagadas > 0


def trocar_vaga_no_historico(aluno, linha_id, grupo):
    """'Conta como': grava no grupo da linha a vaga de optativa que ela ocupa (ou SEM_VAGA)."""
    with transaction.atomic():
        codigos_antigos = codigos_bloqueados(aluno)
        trocadas = aluno.historico.filter(id=linha_id).update(grupo=grupo)
        sincronizar_cursadas(aluno, codigos_antigos)
    return trocadas > 0


def trocar_situacao_no_historico(aluno, linha_id, situacao):
    if situacao not in SITUACOES_DA_CORRECAO:
        raise CorrecaoInvalida('Escolha uma situação da lista.')
    with transaction.atomic():
        codigos_antigos = codigos_bloqueados(aluno)
        trocadas = aluno.historico.filter(id=linha_id).update(situacao=situacao)
        sincronizar_cursadas(aluno, codigos_antigos)
    return trocadas > 0


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


def curriculo_das_siglas(curso, habilitacao, enfase):
    if not curso:
        return None
    ligacao = LigacaoHabilitacao.para_siglas(curso, habilitacao, enfase)
    return ligacao.curriculo if ligacao else None


def curriculo_do_aluno(aluno):
    return curriculo_das_siglas(aluno.curso_sigla, aluno.habilitacao_sigla, aluno.enfase_sigla)


def ordem_do_curriculo(item):
    return (item.periodo is None, item.periodo or 0, item.ordem)


def ocupacao_das_vagas(aluno, curriculo=None):
    """Liga as disciplinas feitas (ou em andamento) às vagas de optativa do currículo.

    Os itens de grupo do currículo (4º caractere do código = 0: INF0307, ENG0561...) são
    vagas a preencher, e o histórico traz a disciplina real (INF1026), nunca o código do
    grupo. Uma disciplina ocupa no máximo uma vaga, quando:
      (a) o campo grupo da linha é o código da vaga (escolha manual em "Conta como", ou o
          próprio SAU); ou
      (b) automático: ela NÃO é item do currículo, o tipo dela (se o SAU trouxer) não é
          OB/OC e as 3 letras do código batem com as da vaga (INF1026 -> INF0307).
          Nas linhas em andamento (EA) o SAU deixa Tipo e Grupo vazios, por isso a regra
          não depende do tipo.
    Se o currículo tem mais de um grupo com as mesmas 3 letras (ENG0561, ENG0562...), a
    escolha é ambígua: nada é adivinhado, a vaga fica pendente até o aluno escolher.

    Item do currículo nunca ocupa vaga: em Engenharia de Produção 2023, por exemplo,
    CRE1200 (O Humano e o Fenômeno Religioso) é disciplina do 1º período, então não fecha
    a vaga CRE0712 (Optativas de Cristianismo).

    Devolve (pendentes, conta_como): os itens do currículo que faltam, na ordem do
    currículo, e {id da linha do histórico: código da vaga que ela ocupa}."""
    curriculo = curriculo or curriculo_do_aluno(aluno)
    if curriculo is None:
        return [], {}
    itens = sorted(curriculo.itens.all(), key=ordem_do_curriculo)
    codigos_dos_itens = {item.codigo for item in itens if not item.eh_grupo}
    grupos_por_prefixo = {}
    for item in itens:
        if item.eh_grupo:
            grupos_por_prefixo.setdefault(item.codigo[:3], set()).add(item.codigo)

    bloqueiam = situacoes_que_bloqueiam()
    linhas = [linha for linha in aluno.historico.order_by('periodo', 'id') if linha.situacao in bloqueiam]
    livres = [item for item in itens if item.eh_grupo]     # vagas, na ordem do currículo
    conta_como = {}

    def ocupar(linha, codigo_da_vaga):
        vaga = next((v for v in livres if v.codigo == codigo_da_vaga), None)
        if vaga is not None:
            livres.remove(vaga)
            conta_como[linha.id] = vaga.codigo

    for linha in linhas:                                    # (a) grupo da linha
        if linha.grupo:
            ocupar(linha, linha.grupo)
    for linha in linhas:                                    # (b) automático pelo prefixo
        if linha.grupo or linha.codigo in codigos_dos_itens or linha.tipo in TIPOS_DO_CURRICULO:
            continue
        grupos = grupos_por_prefixo.get(linha.codigo[:3], set())
        if len(grupos) == 1:
            ocupar(linha, next(iter(grupos)))

    feitos = codigos_bloqueados(aluno)
    pendentes = [
        item for item in itens
        if ((item in livres) if item.eh_grupo else (item.codigo not in feitos))
    ]
    return pendentes, conta_como


def pendentes_do_curriculo(aluno):
    """Itens do currículo do aluno que ainda não foram cumpridos, pelo período recomendado
    (os de período indeterminado ficam no fim). Cada optativa feita fecha uma vaga de grupo."""
    return ocupacao_das_vagas(aluno)[0]


def vagas_do_curriculo(curriculo):
    """[(código, nome)] dos grupos de optativa do currículo, sem repetir, na ordem do currículo."""
    vistas = {}
    for item in sorted(curriculo.itens.filter(eh_grupo=True), key=ordem_do_curriculo):
        vistas.setdefault(item.codigo, item.nome)
    return list(vistas.items())


def dados_oficiais(codigo):
    """(nome, créditos) de uma disciplina pelo código: primeiro o currículo importado do site
    da PUC, depois a tabela Disciplina. None se o código não for conhecido."""
    item = DisciplinaCurriculo.objects.filter(codigo=codigo, eh_grupo=False).first()
    if item:
        return item.nome, item.creditos
    disciplina = Disciplina.objects.filter(codigo=codigo).first()
    if disciplina:
        return disciplina.nome, disciplina.creditos
    return None


def letras_em_ordem(poucas, todas):
    """'FS' cabe em 'FIS' (as letras aparecem na mesma ordem)."""
    resto = iter(todas)
    return all(letra in resto for letra in poucas)


def reparar_codigo(codigo):
    """Código lido pelo OCR com uma letra perdida ('FS4001'): devolve o código conhecido com
    os mesmos 4 dígitos e letras compatíveis ('FIS4001'). Se o código já existe, devolve ele
    mesmo. None se não houver exatamente um candidato."""
    if dados_oficiais(codigo):
        return codigo
    letras, numeros = codigo[:-4], codigo[-4:]
    conhecidos = set(DisciplinaCurriculo.objects.filter(codigo__endswith=numeros).values_list('codigo', flat=True))
    conhecidos |= set(Disciplina.objects.filter(codigo__endswith=numeros).values_list('codigo', flat=True))
    candidatos = {c for c in conhecidos if len(c) == 7 and letras_em_ordem(letras, c[:3])}
    return candidatos.pop() if len(candidatos) == 1 else None
