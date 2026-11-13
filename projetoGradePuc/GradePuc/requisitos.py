"""Regra única de pré-requisito e co-requisito, usada pelo gerador de grades, pelas eletivas
e pelas telas (resumo da grade, pré-requisitos, api de disciplina).

Os requisitos vêm das ementas da PUC (modelo Requisito, ver ementas.py): alternativas
ligadas por OU, e dentro de cada alternativa códigos ligados por E. Uma disciplina sem
nenhum Requisito usa o M2M antigo Disciplina.pre_requisitos (dados de exemplo e testes antigos).

Os códigos "feitos" já vêm expandidos pelas equivalências (quem fez MAT4181 conta como
tendo feito MAT4161, MAT1161...).
"""
import re

from .historico import codigos_bloqueados
from .models import Disciplina, Requisito

CODIGO = re.compile(r"^[A-Z]{3}\d{4}$")


class TabelaDeRequisitos:
    """Todos os requisitos lidos de uma vez: o gerador consulta centenas de turmas."""

    def __init__(self, codigos=None):
        linhas = Requisito.objects.all()
        if codigos is not None:
            linhas = linhas.filter(disciplina__in=list(codigos))
        self.alternativas = {}           # (disciplina, tipo) -> {número da alternativa: {códigos}}
        self.com_registro = set()        # disciplinas que têm alguma linha em Requisito
        for disciplina, tipo, alternativa, codigo in linhas.values_list("disciplina", "tipo", "alternativa", "codigo"):
            self.com_registro.add(disciplina)
            exigidos = self.alternativas.setdefault((disciplina, tipo), {}).setdefault(alternativa, set())
            if codigo:      # alternativa só com nivelamento fica vazia: não exige disciplina
                exigidos.add(codigo)

        # M2M antigo (fallback), por código
        self.antigos = {}
        ligacoes = Disciplina.pre_requisitos.through.objects.values_list("from_disciplina__codigo", "to_disciplina__codigo")
        if codigos is not None:
            ligacoes = ligacoes.filter(from_disciplina__codigo__in=list(codigos))
        for disciplina, exigido in ligacoes:
            self.antigos.setdefault(disciplina, set()).add(exigido)

    def de(self, codigo, tipo):
        """[{códigos}] das alternativas (OU) de um tipo; lista vazia se não há requisito."""
        return list(self.alternativas.get((codigo, tipo), {}).values())

    def usa_m2m_antigo(self, codigo):
        return codigo not in self.com_registro and codigo in self.antigos


def tabela_para(codigo, tabela):
    return tabela if tabela is not None else TabelaDeRequisitos([codigo])


def pre_requisitos_cumpridos(codigo, codigos_feitos, tabela=None):
    """Sem pré-requisito: True. Com alternativas: True se ALGUMA tem todos os códigos feitos."""
    tabela = tabela_para(codigo, tabela)
    feitos = set(codigos_feitos)
    if tabela.usa_m2m_antigo(codigo):
        return tabela.antigos[codigo] <= feitos
    alternativas = tabela.de(codigo, "pre")
    if not alternativas:
        return True
    return any(exigidos <= feitos for exigidos in alternativas)


def co_requisitos_cumpridos(codigo, codigos_feitos, codigos_na_grade, tabela=None):
    """Como o pré-requisito, mas o código exigido também vale se está na grade em montagem."""
    tabela = tabela_para(codigo, tabela)
    alternativas = tabela.de(codigo, "co")
    if not alternativas:
        return True
    disponiveis = set(codigos_feitos) | expandir_equivalencias(codigos_na_grade)
    return any(exigidos <= disponiveis for exigidos in alternativas)


def alternativas_de_pre_requisito(codigo, tabela=None):
    """[[códigos]] das alternativas de pré-requisito (ou o M2M antigo como uma alternativa)."""
    tabela = tabela_para(codigo, tabela)
    if tabela.usa_m2m_antigo(codigo):
        return [sorted(tabela.antigos[codigo])]
    return [sorted(exigidos) for exigidos in tabela.de(codigo, "pre")]


# ---------- Equivalências ----------

# Só equivalências confirmadas, revisadas à mão. Outras classes candidatas (regra estrita
# sobre os requisitos + mesmo título) ficam em revisao/equivalencias_sugeridas.txt, fora do
# site, até alguém revisar e trazer para cá.
EQUIVALENCIAS_CONFIRMADAS = [
    ["MAT1158", "MAT1161", "MAT1181", "MAT4161", "MAT4181"],              # Cálculo 1 (a uma variável)
    ["FIS1041", "FIS1071", "FIS4002"],                                    # Física II
    ["MAT1200", "MAT1250", "MAT1260", "MAT1280", "MAT4200", "MAT4280"],   # Álgebra Linear I (sem as "para Economia")
]
# Aparecem como alternativas de co-requisito (ENG4021: EMP1320 e INF1037 ou INF1026 ou
# INF1007), mas são disciplinas diferentes: nunca entram em classe nenhuma.
NUNCA_EQUIVALENTES = {"INF1037", "INF1007", "INF1026", "INF1620"}


def classes_de_equivalencia():
    """{código: classe} das disciplinas que a PUC aceita uma no lugar da outra.

    Duas fontes: a lista confirmada acima e o campo grupo dos espelhos (o SAU marca
    MAT4181 com Grupo MAT4161). Do espelho ficam de fora as vagas de optativa (INF0307,
    4º caractere 0) e a escolha "nenhum" do perfil. A classe é o menor código dela."""
    from .historico import SEM_VAGA
    from .models import HistoricoDisciplina

    pai = {}

    def raiz(codigo):
        pai.setdefault(codigo, codigo)
        while pai[codigo] != codigo:
            pai[codigo] = pai[pai[codigo]]
            codigo = pai[codigo]
        return codigo

    def unir(a, b):
        if a in NUNCA_EQUIVALENTES or b in NUNCA_EQUIVALENTES:
            return
        ra, rb = raiz(a), raiz(b)
        if ra != rb:
            pai[max(ra, rb)] = min(ra, rb)

    for classe in EQUIVALENCIAS_CONFIRMADAS:
        for outro in classe[1:]:
            unir(classe[0], outro)
    pares = HistoricoDisciplina.objects.exclude(grupo="").exclude(grupo=SEM_VAGA).values_list("codigo", "grupo").distinct()
    for codigo, grupo in pares:
        if CODIGO.match(codigo) and CODIGO.match(grupo) and grupo[3] != "0" and grupo != codigo:
            unir(codigo, grupo)

    classes = {}
    for codigo in list(pai):
        classes[codigo] = raiz(codigo)
    tamanhos = {}
    for classe in classes.values():
        tamanhos[classe] = tamanhos.get(classe, 0) + 1
    return {codigo: classe for codigo, classe in classes.items() if tamanhos[classe] > 1}


def classe_de(codigo, classes=None):
    """Representante da classe de equivalência do código (o próprio código se não tem)."""
    classes = classes_de_equivalencia() if classes is None else classes
    return classes.get(codigo, codigo)


def expandir_equivalencias(codigos, classes=None):
    """Os códigos e todos os equivalentes a eles."""
    classes = classes_de_equivalencia() if classes is None else classes
    membros = {}
    for codigo, classe in classes.items():
        membros.setdefault(classe, set()).add(codigo)
    resultado = set(codigos)
    for codigo in list(resultado):
        resultado |= membros.get(classes.get(codigo), set())
    return resultado


def codigos_feitos(aluno, classes=None):
    """O que conta como cursado: histórico (cursadas e em andamento, com os grupos) e
    aluno.disciplinas_cursadas, expandidos pelas equivalências."""
    feitos = set(codigos_bloqueados(aluno))
    feitos |= set(aluno.disciplinas_cursadas.values_list("codigo", flat=True))
    return expandir_equivalencias(feitos, classes)
