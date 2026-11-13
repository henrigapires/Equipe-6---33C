
import re
from collections import defaultdict

from .models import Turma
from .historico import curriculo_do_aluno
from .requisitos import (
    TabelaDeRequisitos, classe_de, classes_de_equivalencia, co_requisitos_cumpridos, codigos_feitos,
    expandir_equivalencias, pre_requisitos_cumpridos,
)


CARGAS = {
    "leve": 3,
    "media": 5,
    "pesada": 7,
}

DIAS = {
    "SEG": 0, "TER": 1, "QUA": 2,
    "QUI": 3, "SEX": 4, "SAB": 5,
}



def interpretar_horarios(texto):
    """Converte horários do micro-horário em intervalos."""
    if not texto:
        return None

    resultado = []
    padrao = r"(SEG|TER|QUA|QUI|SEX|SAB)\s*(\d{1,2})(?::(\d{2}))?\s*[-–]\s*(\d{1,2})(?::(\d{2}))?"

    for dia, hora_inicio, minuto_inicio, hora_fim, minuto_fim in re.findall(
        padrao, texto.upper()
    ):
        inicio = int(hora_inicio) * 60 + int(minuto_inicio or 0)
        fim = int(hora_fim) * 60 + int(minuto_fim or 0)

        if inicio >= fim or fim > 24 * 60:
            return None

        resultado.append((DIAS[dia], inicio, fim))

    return resultado or None


def tem_conflito(horarios, novos):
    return any(
        dia == outro_dia and inicio < outro_fim and outro_inicio < fim
        for dia, inicio, fim in horarios
        for outro_dia, outro_inicio, outro_fim in novos
    )


def pontuar_grade(turmas, preferencias):
    por_dia = defaultdict(list)
    pontos = 0

    for turma, horarios in turmas:
        for dia, inicio, fim in horarios:
            por_dia[dia].append((inicio, fim))

            turno = preferencias.turno
            if turno != "sem_preferencia":
                turno_real = (
                    "manha" if inicio < 12 * 60
                    else "tarde" if inicio < 18 * 60
                    else "noite"
                )
                pontos += 10 if turno == turno_real else -5

    quantidades = [len(por_dia[d]) for d in range(5)]
    distribuicao = preferencias.distribuicao_aulas

    if distribuicao == "equilibrado":
        pontos -= (max(quantidades) - min(quantidades)) * 5
    elif distribuicao == "dia_livre":
        pontos += quantidades.count(0) * 15
    elif distribuicao == "dia_leve":
        pontos += sum(q <= 1 for q in quantidades) * 8

    for aulas in por_dia.values():
        aulas.sort()
        for anterior, seguinte in zip(aulas, aulas[1:]):
            intervalo = seguinte[0] - anterior[1]
            if intervalo <= 0:
                continue
            if preferencias.janelas == "sem_janelas":
                pontos -= intervalo / 10
            elif preferencias.janelas == "janelas_curtas":
                pontos += 3 if intervalo <= 60 else -5

    return pontos


def sem_co_requisito_faltando(escolhidas, feitos, tabela):
    """Tira da grade as disciplinas cujo co-requisito não está feito nem na própria grade
    (repete porque tirar uma pode deixar outra sem o co-requisito dela)."""
    while True:
        codigos = {turma.disciplina.codigo for turma, _ in escolhidas}
        restantes = [
            (turma, horarios) for turma, horarios in escolhidas
            if co_requisitos_cumpridos(turma.disciplina.codigo, feitos, codigos, tabela)
        ]
        if len(restantes) == len(escolhidas):
            return escolhidas
        escolhidas = restantes


# ---------- Grades guiadas pela grade da PUC e pelo histórico do aluno ----------
#
# Cada disciplina pendente que o aluno pode cursar recebe uma importância:
#   situação em relação ao período de referência (do período 10, atrasada 6, adiantada 3)
#   + 4 por disciplina pendente do currículo que depende dela (direta ou indiretamente).
# Assim uma disciplina que destrava muita coisa (Cálculo, Física) pesa mais, e uma atrasada
# que não destrava nada pode esperar. As quatro grades seguem estratégias diferentes; dentro
# de cada uma, a escolha das turmas é a busca de sempre (pontuar_grade, sem conflito).

PESO_DA_SITUACAO = {"do período": 10, "atrasada": 6, "adiantada": 3}
PESO_POR_DEPENDENTE = 4
GARGALO = 3                 # destrava pelo menos isso: entra até na grade "da PUC"
PENALIDADE_TURMA_REPETIDA = 15      # para as grades não repetirem as mesmas turmas
TENTATIVAS_DE_VARIACAO = 12


def ordem_do_item(periodo):
    return periodo if periodo is not None else 99


def periodos_do_aluno(aluno, curriculo, pendentes_por_periodo, classes):
    """(período atual, período de referência).

    Período atual = o período do currículo das disciplinas que o aluno está cursando agora
    (EA); com mais de um, o da maioria (empate: o mais adiantado). Uma optativa em andamento
    que ocupa uma vaga de grupo conta pelo período da vaga.
    Referência = atual + 1 (a grade é para o semestre seguinte). Sem nada em andamento:
    o menor período que ainda tem pendências (e o atual fica sendo o anterior a ele)."""
    from .espelho import SITUACOES_EM_ANDAMENTO
    from .historico import ocupacao_das_vagas

    periodo_do_codigo = {}
    for item in curriculo.itens.all():
        if item.periodo is not None:
            for codigo in [item.codigo] + [c for c, k in classes.items() if k == classes.get(item.codigo)]:
                periodo_do_codigo.setdefault(codigo, item.periodo)
    _, conta_como = ocupacao_das_vagas(aluno, curriculo)

    contagem = defaultdict(int)
    for linha in aluno.historico.filter(situacao__in=SITUACOES_EM_ANDAMENTO):
        periodo = periodo_do_codigo.get(linha.codigo)
        if periodo is None and linha.id in conta_como:
            periodo = periodo_do_codigo.get(conta_como[linha.id])
        if periodo is None and linha.grupo:
            periodo = periodo_do_codigo.get(linha.grupo)
        if periodo is not None:
            contagem[periodo] += 1

    if contagem:
        atual = max(contagem, key=lambda p: (contagem[p], p))
        return atual, atual + 1
    com_pendencia = sorted(p for p in pendentes_por_periodo if p is not None)
    referencia = com_pendencia[0] if com_pendencia else 1
    return referencia - 1, referencia


def situacao_do_item(periodo, atual, referencia):
    if periodo is None or periodo > referencia:
        return "adiantada"
    if periodo <= atual:
        return "atrasada"
    return "do período" if periodo == referencia else "adiantada"


def dependentes_pendentes(pendentes, tabela, classes):
    """{código: quantas disciplinas pendentes do currículo dependem dele} (direta ou
    indiretamente), pelos pré-requisitos: basta aparecer em alguma alternativa."""
    diretos = defaultdict(set)          # código exigido -> pendentes que o exigem
    for codigo in pendentes:
        for alternativa in tabela.de(codigo, "pre"):
            for exigido in alternativa:
                for equivalente in expandir_equivalencias([exigido], classes):
                    diretos[equivalente].add(codigo)
        for exigido in tabela.antigos.get(codigo, ()) if tabela.usa_m2m_antigo(codigo) else ():
            diretos[exigido].add(codigo)

    def alcancados(codigo):
        vistos, fila = set(), [codigo]
        while fila:
            atual = fila.pop()
            for dependente in diretos.get(atual, ()):
                if dependente not in vistos and dependente != codigo:
                    vistos.add(dependente)
                    fila.append(dependente)
        return vistos

    return {codigo: len(alcancados(codigo)) for codigo in pendentes}


def montar_grade(ordem, quantidade, preferencias, feitos, tabela, classes, todos, turmas_usadas, extras_permitidos=True):
    """A busca de sempre (melhor turma de cada disciplina pela pontuar_grade, sem conflito),
    seguindo a ordem da estratégia. Quando uma disciplina entra e o co-requisito dela não está
    feito, o par vai para a frente da fila. No fim, sai quem ficou sem co-requisito e a busca
    tenta completar a grade de novo."""
    escolhidas, ocupados = [], []
    fila = list(ordem)
    tentados = set()
    for _ in range(3):
        while fila and len(escolhidas) < quantidade:
            disciplina = fila.pop(0)
            if disciplina["chave"] in tentados:
                continue
            tentados.add(disciplina["chave"])
            classes_na_grade = {classe_de(t.disciplina.codigo, classes) for t, _ in escolhidas}
            if classe_de(disciplina["codigo"], classes) in classes_na_grade:
                continue

            melhor, melhor_nota = None, float("-inf")
            for turma, horarios in disciplina["turmas"][:12]:
                if tem_conflito(ocupados, horarios):
                    continue
                nota = pontuar_grade(escolhidas + [(turma, horarios)], preferencias)
                if turma.id in turmas_usadas:
                    nota -= PENALIDADE_TURMA_REPETIDA
                if nota > melhor_nota:
                    melhor, melhor_nota = (turma, horarios), nota
            if melhor is None:
                continue
            escolhidas.append(melhor)
            ocupados.extend(melhor[1])

            na_grade = {t.disciplina.codigo for t, _ in escolhidas}
            if not co_requisitos_cumpridos(disciplina["codigo"], feitos, na_grade, tabela):
                for alternativa in tabela.de(disciplina["codigo"], "co"):
                    faltam = [c for c in alternativa if c not in feitos and c not in na_grade]
                    pares = [todos[c] for c in faltam if c in todos]
                    if len(pares) == len(faltam) and (extras_permitidos or all(p in ordem for p in pares)):
                        for par in reversed(pares):
                            tentados.discard(par["chave"])
                            fila.insert(0, par)
                        break

        restantes = sem_co_requisito_faltando(escolhidas, feitos, tabela)
        if len(restantes) == len(escolhidas):
            break
        escolhidas = restantes
        ocupados = [h for _, horarios in escolhidas for h in horarios]
    return escolhidas


def gerar_grades(aluno, preferencias, limite=4):
    """Gera até quatro grades sem conflitos conhecidos, guiadas pela grade da PUC
    (periodização do currículo) e pelo histórico do aluno.

    Cada grade é {"turmas", "pontuacao", "rotulo", "estrategia", "marcas" (turma.id ->
    atrasada/do período/adiantada), "creditos", "aviso", "periodo_atual", "periodo_referencia"}."""
    cursadas = set(aluno.disciplinas_cursadas.values_list("id", flat=True))
    curriculo = curriculo_do_aluno(aluno)
    if curriculo is None:
        return []

    # Pré/co-requisitos das ementas da PUC (requisitos.py) e o que conta como feito,
    # com as equivalências (quem fez MAT4181 não recebe MAT1161 nem MAT4161).
    classes = classes_de_equivalencia()
    feitos = codigos_feitos(aluno, classes)
    tabela = TabelaDeRequisitos()

    itens = [item for item in curriculo.itens.all() if not item.eh_grupo]
    periodo_no_curriculo, nome_no_curriculo, creditos_no_curriculo = {}, {}, {}
    for item in itens:
        if item.codigo not in periodo_no_curriculo or ordem_do_item(item.periodo) < ordem_do_item(periodo_no_curriculo[item.codigo]):
            periodo_no_curriculo[item.codigo] = item.periodo
        nome_no_curriculo.setdefault(item.codigo, item.nome)
        creditos_no_curriculo.setdefault(item.codigo, item.creditos)
    pendentes = {c for c in periodo_no_curriculo if c not in feitos}
    pendentes_por_periodo = defaultdict(set)
    for codigo in pendentes:
        pendentes_por_periodo[periodo_no_curriculo[codigo]].add(codigo)

    candidatos = defaultdict(list)
    turmas = (
        Turma.objects
        .select_related("disciplina", "professor")
        .filter(
    vagas__gt=0,
    disciplina__codigo__in=pendentes
)
        .exclude(disciplina_id__in=cursadas)
        .exclude(disciplina__codigo__in=feitos)
        .order_by("disciplina__codigo", "codigo_turma")
    )
    if preferencias.modalidade == 'online':
        turmas = turmas.filter(sala__icontains='VIRTUAL')
    elif preferencias.modalidade == 'presencial':
        turmas = turmas.exclude(sala__icontains='VIRTUAL')

    for turma in turmas:
        if not pre_requisitos_cumpridos(turma.disciplina.codigo, feitos, tabela):
            continue

        horarios = interpretar_horarios(turma.dias_horarios)
        if horarios is None:
            continue
        turno = preferencias.turno

        if turno != "sem_preferencia":
            def turno_do_horario(inicio):
                if inicio < 12 * 60:
                    return "manha"
                elif inicio < 18 * 60:
                    return "tarde"
                return "noite"

            if any(
                turno_do_horario(inicio) != turno
                for dia, inicio, fim in horarios
            ):
                continue

        candidatos[turma.disciplina_id].append((turma, horarios))

    # Co-requisito: precisa estar feito ou poder entrar na mesma grade.
    codigos_candidatos = {grupo[0][0].disciplina.codigo for grupo in candidatos.values()}
    candidatos = {
        disciplina: grupo for disciplina, grupo in candidatos.items()
        if co_requisitos_cumpridos(grupo[0][0].disciplina.codigo, feitos, codigos_candidatos, tabela)
    }
    if not candidatos:
        return []

    atual, referencia = periodos_do_aluno(aluno, curriculo, pendentes_por_periodo, classes)
    dependentes = dependentes_pendentes(pendentes, tabela, classes)
    elegiveis = []
    for chave, grupo in candidatos.items():
        codigo = grupo[0][0].disciplina.codigo
        periodo = periodo_no_curriculo.get(codigo)
        situacao = situacao_do_item(periodo, atual, referencia)
        elegiveis.append({
            "chave": chave, "codigo": codigo, "turmas": grupo, "periodo": periodo, "situacao": situacao,
            "dependentes": dependentes.get(codigo, 0),
            "importancia": PESO_DA_SITUACAO[situacao] + PESO_POR_DEPENDENTE * dependentes.get(codigo, 0),
            "nome": nome_no_curriculo.get(codigo) or grupo[0][0].disciplina.nome,
            "creditos": creditos_no_curriculo.get(codigo) or grupo[0][0].disciplina.creditos or 0,
        })
    elegiveis.sort(key=lambda d: (-d["importancia"], ordem_do_item(d["periodo"]), d["codigo"]))
    todos = {d["codigo"]: d for d in elegiveis}

    do_periodo = [d for d in elegiveis if d["situacao"] == "do período"]
    atrasadas = [d for d in elegiveis if d["situacao"] == "atrasada"]
    adiantadas = [d for d in elegiveis if d["situacao"] == "adiantada"]
    gargalos = [d for d in atrasadas + adiantadas if d["dependentes"] >= GARGALO]
    resto = [d for d in elegiveis if d not in do_periodo and d not in gargalos]
    por_importancia = lambda lista: sorted(lista, key=lambda d: (-d["importancia"], ordem_do_item(d["periodo"]), d["codigo"]))

    quantidade = CARGAS.get(preferencias.carga_disciplinas, 5)
    alvo_de_creditos = sum(c for codigo, c in creditos_no_curriculo.items() if periodo_no_curriculo.get(codigo) == referencia)

    def nomes(lista):
        return ", ".join(d["nome"] for d in lista[:2]) + ("..." if len(lista) > 2 else "")

    estrategias = [
        # Segue a grade da PUC: o período de referência; atrasada/adiantada só se for gargalo
        # (e, se faltar disciplina para a carga, o resto pela importância).
        ("puc", por_importancia(do_periodo + gargalos) + resto, True,
         lambda d_: f"Segue a grade da PUC ({referencia}º período)"),
        # Em dia + recupera atrasada
        ("recupera", por_importancia(atrasadas) + por_importancia(do_periodo + [g for g in gargalos if g not in atrasadas])
         + [d for d in resto if d not in atrasadas], True,
         lambda d_: "Em dia + recupera atrasada: " + nomes([d for d in d_ if d["situacao"] == "atrasada"])),
        # Só o período, outra combinação (turmas e professores diferentes; pode trocar uma disciplina)
        ("so_periodo", (do_periodo[:quantidade - 1] + do_periodo[quantidade:] + [do_periodo[quantidade - 1]])
         if len(do_periodo) > quantidade else list(do_periodo), False,
         lambda d_: f"Só o {referencia}º período, outra combinação"),
        # Adianta: disciplinas de períodos à frente, as que destravam mais primeiro
        ("adianta", por_importancia(adiantadas) + do_periodo, True,
         lambda d_: "Variação: adianta " + nomes([d for d in d_ if d["situacao"] == "adiantada"])),
    ]

    resultados, vistos, turmas_usadas = [], set(), set()

    def registrar(estrategia, escolhidas, rotulo_de):
        if not escolhidas:
            return False
        chave = tuple(sorted(turma.id for turma, _ in escolhidas))
        if chave in vistos:
            return False
        por_chave = {d["chave"]: d for d in elegiveis}
        disciplinas = [por_chave[turma.disciplina_id] for turma, _ in escolhidas]
        if estrategia == "recupera" and not any(d["situacao"] == "atrasada" for d in disciplinas):
            return False
        if estrategia == "adianta" and not any(d["situacao"] == "adiantada" for d in disciplinas):
            return False
        vistos.add(chave)
        turmas_usadas.update(turma.id for turma, _ in escolhidas)
        creditos = sum(d["creditos"] for d in disciplinas)
        aviso = ""
        if len(escolhidas) < quantidade and estrategia == "so_periodo":
            # esta opção fica só no período de referência de propósito
            aviso = (f"Só há {len(escolhidas)} disciplina(s) do {referencia}º período que você pode cursar "
                     f"(você pediu {quantidade}); as outras opções completam com disciplinas de outros períodos.")
        elif len(escolhidas) < quantidade:
            aviso = (f"Só encontramos {len(escolhidas)} disciplina(s) que você pode cursar nesta combinação "
                     f"(você pediu {quantidade}).")
        resultados.append({
            "turmas": [turma for turma, _ in escolhidas],
            "pontuacao": pontuar_grade(escolhidas, preferencias),
            "rotulo": rotulo_de(disciplinas),
            "estrategia": estrategia,
            "marcas": {turma.id: d["situacao"] for (turma, _), d in zip(escolhidas, disciplinas)},
            "creditos": creditos,
            "aviso": aviso,
            "periodo_atual": atual,
            "periodo_referencia": referencia,
            "importancias": {d["codigo"]: d["importancia"] for d in elegiveis},
        })
        return True

    def melhor_versao(ordem, extras_permitidos):
        """A ordem da estratégia e duas trocas (a última escolhida pela próxima da mesma
        situação): com a mesma quantidade de disciplinas, fica a de créditos mais perto do
        que a PUC sugere para o período de referência."""
        versoes = [ordem]
        for troca in range(1, 3):
            if len(ordem) > quantidade + troca - 1:
                base = list(ordem)
                fora = base.pop(quantidade - troca)
                versoes.append(base + [fora])
        candidatas = []
        por_chave = {d["chave"]: d for d in elegiveis}
        for versao in versoes:
            escolhidas = montar_grade(versao, quantidade, preferencias, feitos, tabela, classes, todos,
                                      turmas_usadas, extras_permitidos)
            importancia = sum(por_chave[t.disciplina_id]["importancia"] for t, _ in escolhidas)
            creditos = sum(por_chave[t.disciplina_id]["creditos"] for t, _ in escolhidas)
            candidatas.append((escolhidas, importancia, creditos))
        maior = max(len(c[0]) for c in candidatas)
        mesmas = [c for c in candidatas if len(c[0]) == maior]
        topo = max(c[1] for c in mesmas)
        perto = [c for c in mesmas if c[1] >= topo - 3]      # nunca troca um gargalo por créditos
        return min(perto, key=lambda c: (abs(c[2] - alvo_de_creditos), -pontuar_grade(c[0], preferencias)))[0]

    for estrategia, ordem, extras, rotulo_de in estrategias:
        if len(resultados) >= limite or not ordem:
            continue
        registrar(estrategia, melhor_versao(ordem, extras), rotulo_de)

    # Estratégia que não pôde existir (sem atrasada, sem como adiantar...): variações da
    # grade da PUC com outras turmas, professores e horários, nunca repetindo uma grade.
    base = por_importancia(do_periodo + gargalos) + resto
    for deslocamento in range(1, TENTATIVAS_DE_VARIACAO + 1):
        if len(resultados) >= limite or not base:
            break
        k = deslocamento % len(base)
        ordem = base[k:] + base[:k] if deslocamento > 1 else base
        registrar("variacao", montar_grade(ordem, quantidade, preferencias, feitos, tabela, classes, todos,
                                           turmas_usadas), lambda d_: "Variação: outra combinação de turmas")

    return resultados[:limite]
