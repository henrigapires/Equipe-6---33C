"""Tela de pré-requisitos (fluxograma do curso do aluno), painel de detalhes e busca.

Não reimplementa regra nenhuma: requisitos e equivalências vêm de requisitos.py, o período
atual/de referência e a marca de atrasada vêm do gerador de grades. Tudo numa passada só
(currículo, TabelaDeRequisitos e histórico em memória), sem consulta por cartão.
"""
import unicodedata
from collections import defaultdict

from django.db.models import Q

from .espelho import SITUACOES_CURSADAS, SITUACOES_EM_ANDAMENTO
from .gerador_grades import ordem_do_item, periodos_do_aluno, situacao_do_item
from .historico import SEM_VAGA, curriculo_do_aluno, ocupacao_das_vagas
from .models import Disciplina, DisciplinaCurriculo, EmentaLida, Requisito
from .requisitos import (
    TabelaDeRequisitos, alternativas_de_pre_requisito, classe_de, classes_de_equivalencia, codigos_feitos,
    expandir_equivalencias, pre_requisitos_cumpridos,
)

LIMITE_DA_BUSCA = 20
STATUS_LEGIVEL = {
    "concluida": "Concluída", "andamento": "Em andamento", "disponivel": "Disponível", "bloqueada": "Bloqueada",
}


class EstadoDoAluno:
    """O que o aluno já fez e está fazendo, e os requisitos, carregados uma vez."""

    def __init__(self, aluno):
        self.aluno = aluno
        self.classes = classes_de_equivalencia()
        self.tabela = TabelaDeRequisitos()
        # o que conta como feito para requisito (cursadas + em andamento + grupos do espelho)
        self.feitos = codigos_feitos(aluno, self.classes) if aluno else set()
        concluidas, andamento = set(), set()
        if aluno:
            for codigo, grupo, situacao in aluno.historico.values_list("codigo", "grupo", "situacao"):
                destino = concluidas if situacao in SITUACOES_CURSADAS else andamento if situacao in SITUACOES_EM_ANDAMENTO else None
                if destino is None:
                    continue
                destino.add(codigo)
                if grupo and grupo != SEM_VAGA:
                    destino.add(grupo)
            # a importação do espelho também põe as "EA" em disciplinas_cursadas: lá elas seguem em andamento
            concluidas |= set(aluno.disciplinas_cursadas.values_list("codigo", flat=True)) - andamento
        self.concluidas = expandir_equivalencias(concluidas, self.classes)
        self.andamento = expandir_equivalencias(andamento, self.classes) - self.concluidas

    def status(self, codigo):
        if codigo in self.concluidas:
            return "concluida"
        if codigo in self.andamento:
            return "andamento"
        if pre_requisitos_cumpridos(codigo, self.feitos, self.tabela):
            return "disponivel"
        return "bloqueada"

    def marca(self, codigo):
        if codigo in self.concluidas:
            return "✓"
        if codigo in self.andamento:
            return "▶"
        return "✗"

    def falta(self, codigo):
        """Texto curto do que falta para o pré-requisito (a alternativa mais perto de cumprir)."""
        alternativas = alternativas_de_pre_requisito(codigo, self.tabela)
        if not alternativas:
            return ""
        faltando = [[c for c in alternativa if c not in self.feitos] for alternativa in alternativas]
        melhor = min(faltando, key=len)
        texto = " e ".join(melhor)
        return f"Falta: {texto}" + (" (ou outra alternativa)" if len(alternativas) > 1 else "")


def nomes_dos_codigos(codigos):
    """{código: nome}: do currículo (nome bonito) e, se não tiver, da tabela Disciplina."""
    nomes = dict(DisciplinaCurriculo.objects.filter(codigo__in=codigos, eh_grupo=False).values_list("codigo", "nome"))
    faltam = set(codigos) - set(nomes)
    if faltam:
        for codigo, nome in Disciplina.objects.filter(codigo__in=faltam).values_list("codigo", "nome"):
            nomes.setdefault(codigo, nome)
    return nomes


def fluxograma_do_aluno(aluno):
    """Contexto da tela: colunas por período do currículo, coluna de optativas e o estado."""
    estado = EstadoDoAluno(aluno)
    curriculo = curriculo_do_aluno(aluno) if aluno else None
    if curriculo is None:
        return {"curriculo": None, "trilhas": [], "estado": estado}

    itens = list(curriculo.itens.all())
    disciplinas = {}
    for item in sorted(itens, key=lambda i: (ordem_do_item(i.periodo), i.ordem)):
        if not item.eh_grupo:
            disciplinas.setdefault(item.codigo, item)
    codigos = set(disciplinas)

    # período atual/de referência e marca de atrasada: as mesmas funções do gerador
    pendentes = {c for c in codigos if c not in estado.feitos}
    pendentes_por_periodo = defaultdict(set)
    for codigo in pendentes:
        pendentes_por_periodo[disciplinas[codigo].periodo].add(codigo)
    atual, referencia = periodos_do_aluno(aluno, curriculo, pendentes_por_periodo, estado.classes)

    # para as setas: um código exigido vale pelo código do currículo da mesma classe
    no_curriculo = {}
    for codigo in codigos:
        no_curriculo[codigo] = codigo
        no_curriculo.setdefault(classe_de(codigo, estado.classes), codigo)

    def no_fluxograma(codigo):
        return no_curriculo.get(codigo) or no_curriculo.get(classe_de(codigo, estado.classes))

    colunas = defaultdict(list)
    for codigo, item in disciplinas.items():
        status = estado.status(codigo)
        exige = set()
        for alternativa in alternativas_de_pre_requisito(codigo, estado.tabela):
            for exigido in alternativa:
                destino = no_fluxograma(exigido)
                if destino and destino != codigo:
                    exige.add(destino)
        colunas[item.periodo].append({
            "codigo": codigo,
            "nome": item.nome,
            "creditos": item.creditos,
            "status": status,
            "status_legivel": STATUS_LEGIVEL[status],
            "falta": estado.falta(codigo) if status == "bloqueada" else "",
            "atrasada": codigo in pendentes and situacao_do_item(item.periodo, atual, referencia) == "atrasada",
            "exige": " ".join(sorted(exige)),
        })

    trilhas = [
        {"nome": f"{periodo}º período" if periodo is not None else "Sem período", "disciplinas": colunas[periodo]}
        for periodo in sorted(colunas, key=ordem_do_item)
    ]

    # optativas: um cartão por grupo, com quantas vagas faltam
    pendentes_de_grupo, _ = ocupacao_das_vagas(aluno, curriculo)
    faltam = defaultdict(int)
    for item in pendentes_de_grupo:
        if item.eh_grupo:
            faltam[item.codigo] += 1
    grupos = []
    for item in sorted(itens, key=lambda i: (ordem_do_item(i.periodo), i.ordem)):
        if item.eh_grupo and item.codigo not in {g["codigo"] for g in grupos}:
            grupos.append({"codigo": item.codigo, "nome": item.nome, "faltam": faltam.get(item.codigo, 0)})

    return {
        "curriculo": curriculo,
        "trilhas": trilhas,
        "grupos": grupos,
        "estado": estado,
        "periodo_atual": atual,
        "periodo_referencia": referencia,
    }


def cadeia_de_pre_requisitos(codigo, estado, limite_de_niveis=8):
    """O que precisa ser feito antes, nível a nível (seguindo, em cada disciplina que falta,
    a alternativa mais perto de cumprir). Devolve ([[{codigo, status}]], quantas faltam)."""
    custos = {}

    def custo(c, profundidade=0):
        """Quantas disciplinas faltam, no total, para poder cursar c (pelo caminho mais curto)."""
        if c in estado.feitos:
            return 0
        if c not in custos:
            custos[c] = limite_de_niveis * 10       # trava contra ciclo enquanto calcula
            alternativas = alternativas_de_pre_requisito(c, estado.tabela)
            if profundidade < limite_de_niveis and alternativas:
                custos[c] = 1 + min(sum(custo(x, profundidade + 1) for x in a) for a in alternativas)
            else:
                custos[c] = 1
        return custos[c]

    niveis, vistos, atual = [], {codigo}, [codigo]
    faltam = set()
    for _ in range(limite_de_niveis):
        proximo = []
        for c in atual:
            if c != codigo and c in estado.feitos:
                continue
            alternativas = alternativas_de_pre_requisito(c, estado.tabela)
            if not alternativas:
                continue
            melhor = min(alternativas, key=lambda a: sum(custo(x) for x in a))
            for exigido in melhor:
                if exigido not in vistos:
                    vistos.add(exigido)
                    proximo.append(exigido)
        if not proximo:
            break
        niveis.append(proximo)
        faltam |= {c for c in proximo if c not in estado.feitos}
        atual = proximo
    nomes = nomes_dos_codigos({c for nivel in niveis for c in nivel})
    return [[{"codigo": c, "nome": nomes.get(c, ""), "status": estado.status(c)} for c in nivel] for nivel in niveis], len(faltam)


def detalhes_da_disciplina(codigo, aluno, disciplina=None):
    """Dados do painel "Detalhes" (e da api_disciplina)."""
    estado = EstadoDoAluno(aluno)
    curriculo = curriculo_do_aluno(aluno) if aluno else None
    item = curriculo.itens.filter(codigo=codigo, eh_grupo=False).first() if curriculo else None
    disciplina = disciplina or Disciplina.objects.filter(codigo=codigo).first()

    linhas = list(Requisito.objects.filter(disciplina=codigo).order_by("tipo", "alternativa", "id"))
    exigidos = {r.codigo for r in linhas if r.codigo}
    for alternativa in alternativas_de_pre_requisito(codigo, estado.tabela):
        exigidos |= set(alternativa)
    libera_codigos = set()
    if curriculo:
        for c in curriculo.itens.filter(eh_grupo=False).values_list("codigo", flat=True):
            if any(codigo in a or classe_de(codigo, estado.classes) in {classe_de(x, estado.classes) for x in a}
                   for a in alternativas_de_pre_requisito(c, estado.tabela)) and c != codigo:
                libera_codigos.add(c)
    nomes = nomes_dos_codigos(exigidos | libera_codigos | {codigo})

    def descrever(alternativas):
        return [[{"codigo": c, "nome": nomes.get(c, ""), "marca": estado.marca(c)} for c in sorted(a)] for a in alternativas]

    co = [sorted(a) for a in estado.tabela.de(codigo, "co")]
    nivelamento = sorted({r.observacao for r in linhas if r.observacao})
    cadeia, faltam = cadeia_de_pre_requisitos(codigo, estado)
    status = estado.status(codigo)
    return {
        "codigo": codigo,
        "nome": (item.nome if item else None) or (disciplina.nome if disciplina else nomes.get(codigo, "")),
        "creditos": (item.creditos if item else None) or (disciplina.creditos if disciplina else None),
        "periodo": item.periodo if item else None,
        "status": status,
        "status_legivel": STATUS_LEGIVEL[status],
        # alternativa só com nivelamento fica vazia: o nivelamento já aparece à parte
        "pre": descrever([a for a in alternativas_de_pre_requisito(codigo, estado.tabela) if a]),
        "co": descrever(co),
        "libera": [{"codigo": c, "nome": nomes.get(c, "")} for c in sorted(libera_codigos)],
        "nivelamento": nivelamento,
        "cadeia": cadeia,
        "faltam_na_cadeia": faltam,
        "ementa_url": f"/eletivas/{codigo}/",
        "sem_informacao": codigo not in estado.tabela.com_registro
                          and not estado.tabela.usa_m2m_antigo(codigo)
                          and not EmentaLida.objects.filter(codigo=codigo, encontrada=True).exists(),
    }


def buscar_disciplinas(texto, aluno, so_sem_pre=False, limite=LIMITE_DA_BUSCA):
    """Qualquer disciplina (para escolher eletiva), por código ou nome, com o status do aluno."""
    texto = (texto or "").strip()
    estado = EstadoDoAluno(aluno)
    consulta = Disciplina.objects.all()
    if texto:
        # os nomes vindos do SAU não têm acento ("FISICA"): busca com e sem acento
        sem_acento = "".join(c for c in unicodedata.normalize("NFD", texto) if unicodedata.category(c) != "Mn")
        consulta = consulta.filter(Q(codigo__icontains=texto) | Q(nome__icontains=texto) | Q(nome__icontains=sem_acento))
    lidas_sem_ementa = set(EmentaLida.objects.filter(encontrada=False).values_list("codigo", flat=True))
    resultados, vistos = [], set()
    for codigo, nome, creditos in consulta.order_by("codigo").values_list("codigo", "nome", "creditos"):
        if codigo in vistos:
            continue
        vistos.add(codigo)
        alternativas = alternativas_de_pre_requisito(codigo, estado.tabela)
        sem_pre = not alternativas or not all(alternativas)     # só nivelamento também não exige disciplina
        if so_sem_pre and (not sem_pre or codigo in lidas_sem_ementa):
            continue        # "sem pré-requisito" só quando a ementa foi lida e não tem
        status = estado.status(codigo)
        resultados.append({
            "codigo": codigo, "nome": nome, "creditos": creditos, "status": status,
            "status_legivel": STATUS_LEGIVEL[status], "sem_pre_requisito": sem_pre,
        })
        if len(resultados) >= limite:
            break
    return resultados
