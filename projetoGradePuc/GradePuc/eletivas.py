"""Sugestão de eletivas que complementam cada grade sugerida.

Não monta grade nenhuma: parte das grades que gerar_grades já criou e das respostas do
questionário, e procura turmas de eletivas do curso (veja grupos.py) que cabem nelas.
"""
import re

from .gerador_grades import interpretar_horarios, pontuar_grade, tem_conflito
from .grupos import eletivas_do_curriculo
from .historico import curriculo_do_aluno, ocupacao_das_vagas
from .models import Turma
from .requisitos import (
    TabelaDeRequisitos, classe_de, classes_de_equivalencia, co_requisitos_cumpridos, codigos_feitos,
    pre_requisitos_cumpridos,
)

# Teto de créditos de cada opção de carga do questionário
# (Leve: menos de 20; Média: 20 a 25; Pesada: mais de 25).
# A pesada não tem teto no questionário: 32 é uma suposição nossa.
LIMITE_DE_CREDITOS = {
    "leve": 19,
    "media": 25,
    "pesada": 32,
}

# Período usado para grupos de "período indeterminado": ficam depois dos outros.
PERIODO_INDETERMINADO = 99

# Faixas da ordem das sugestões (vêm antes dos pontos do questionário).
FAIXA_DO_PERIODO = 0        # grupo no período de referência da grade (o "nativo")
FAIXA_ATRASADA = 1          # grupo de período até o atual: vaga que já devia estar preenchida
FAIXA_A_FRENTE = 2          # grupo de período mais à frente
FAIXA_SEM_PERIODO = 3       # grupo de período indeterminado

# Só a hora, sem dia nem sala: "13-16".
SO_HORA = re.compile(r"^\d{1,2}-\d{1,2}$")


def turno_do_horario(inicio):
    """Mesma divisão de turnos do gerador de grades (inicio em minutos)."""
    if inicio < 12 * 60:
        return "manha"
    elif inicio < 18 * 60:
        return "tarde"
    return "noite"


def horarios_da_turma(turma):
    """Lê o campo dias_horarios ("TER 13-15; QUI 13-15") com a função do gerador de grades.

    Dois cuidados com o que veio do micro-horário:
    - "SÁB" com acento vira "SAB" (a função do gerador só conhece sem acento);
    - quando a linha do Excel não tinha sala, o importar_microhorario guardou só o dia em
      dias_horarios ("SEG") e a hora em sala ("13-16"). Aqui os dois são juntados de novo.
    Devolve a lista [(dia, início, fim)] ou None se não der para saber o horário."""
    texto = turma.dias_horarios.replace("SÁB", "SAB")

    if texto and not re.search(r"\d", texto) and SO_HORA.match(turma.sala):
        partes = []
        for dia in texto.split(";"):
            partes.append(dia.strip() + " " + turma.sala)
        texto = "; ".join(partes)

    return interpretar_horarios(texto)


def respeita_o_turno(horarios, turno):
    if turno == "sem_preferencia":
        return True
    for dia, inicio, fim in horarios:
        if turno_do_horario(inicio) != turno:
            return False
    return True


def turmas_candidatas(aluno, preferencias):
    """Turmas de eletivas que o aluno pode fazer, antes de olhar para qualquer grade.

    Entram só as disciplinas dos grupos de optativa que o aluno ainda tem para preencher,
    que ele não cursou e cujos pré-requisitos já cumpriu, em turmas com vaga, com horário
    conhecido, na modalidade e no turno do questionário.
    Cada candidata é um dicionário {turma, horarios, grupos, periodo, periodos}."""
    curriculo = curriculo_do_aluno(aluno)
    if curriculo is None:
        return []

    # Vagas de optativa ainda abertas, com o período em que o currículo recomenda fazer.
    pendentes = ocupacao_das_vagas(aluno, curriculo)[0]
    periodo_do_grupo = {}
    nome_do_grupo = {}
    for item in pendentes:
        if item.eh_grupo and item.codigo not in periodo_do_grupo:
            periodo_do_grupo[item.codigo] = item.periodo or PERIODO_INDETERMINADO
            nome_do_grupo[item.codigo] = item.nome

    eletivas = eletivas_do_curriculo(curriculo, grupos=periodo_do_grupo)
    cursadas = set(aluno.disciplinas_cursadas.values_list("id", flat=True))
    # mesma regra do gerador de grades (requisitos.py), com as equivalências
    feitos = codigos_feitos(aluno)
    tabela = TabelaDeRequisitos()

    turmas = (
        Turma.objects
        .select_related("disciplina", "professor")
        .filter(disciplina__in=list(eletivas), vagas__gt=0)
        .exclude(disciplina_id__in=cursadas)
        .exclude(disciplina__codigo__in=feitos)
        .order_by("disciplina__codigo", "codigo_turma", "-vagas")
    )
    if preferencias.modalidade == "online":
        turmas = turmas.filter(sala__icontains="VIRTUAL")
    elif preferencias.modalidade == "presencial":
        turmas = turmas.exclude(sala__icontains="VIRTUAL")

    candidatas = []
    vistas = []
    for turma in turmas:
        # No micro-horário a mesma turma aparece uma vez por Destino (vagas reservadas
        # para cada curso). Fica só a primeira, que é a de mais vagas.
        chave = (turma.disciplina_id, turma.codigo_turma)
        if chave in vistas:
            continue
        vistas.append(chave)

        if not pre_requisitos_cumpridos(turma.disciplina.codigo, feitos, tabela):
            continue

        horarios = horarios_da_turma(turma)
        if horarios is None:
            continue
        if not respeita_o_turno(horarios, preferencias.turno):
            continue

        grupos = eletivas[turma.disciplina]
        periodo = PERIODO_INDETERMINADO
        nomes = []
        periodos = set()        # de todos os grupos a que ela serve
        for grupo in grupos:
            periodo = min(periodo, periodo_do_grupo[grupo])
            periodos.add(periodo_do_grupo[grupo])
            nomes.append(nome_do_grupo[grupo])

        candidatas.append({
            "turma": turma,
            "horarios": horarios,
            "grupos": nomes,
            "periodo": periodo,
            "periodos": periodos,
            "feitos": feitos,
            "tabela": tabela,
        })
    return candidatas


def faixa_da_optativa(periodos, referencia, atual):
    """Do período nativo (algum grupo no período de referência) > atrasada (grupo de período
    até o atual) > à frente > período indeterminado. `referencia` e `atual` vêm da grade
    (periodos_do_aluno, no gerador); sem período atual, "atrasada" é antes da referência."""
    conhecidos = {p for p in periodos if p != PERIODO_INDETERMINADO}
    if referencia is not None and referencia in conhecidos:
        return FAIXA_DO_PERIODO
    if not conhecidos:
        return FAIXA_SEM_PERIODO
    limite = atual if atual is not None else (referencia - 1 if referencia is not None else None)
    if limite is not None and min(conhecidos) <= limite:
        return FAIXA_ATRASADA
    return FAIXA_A_FRENTE


def rotulo_da_faixa(faixa, referencia):
    if faixa == FAIXA_DO_PERIODO:
        return f"Optativa do {referencia}º período"
    if faixa == FAIXA_ATRASADA:
        return "Optativa de período anterior"
    if faixa == FAIXA_A_FRENTE:
        return "Optativa de período à frente"
    return ""


def ordem_da_sugestao(sugestao):
    """Primeiro a faixa (as do período nativo na frente); dentro dela, mais pontos primeiro;
    empate: grupo de período mais cedo no currículo, depois o código."""
    return (
        sugestao["faixa"],
        -sugestao["pontos"],
        sugestao["periodo"],
        sugestao["turma"].disciplina.codigo,
        sugestao["turma"].codigo_turma,
    )


def sugerir_eletivas(aluno, preferencias, grade, candidatas=None):
    """Turmas de eletivas que cabem em uma grade sugerida: primeiro as optativas do período
    de referência da grade, depois as atrasadas, as de períodos à frente e as sem período;
    dentro de cada faixa, da que mais combina com o questionário para a que menos combina.

    `grade` é um dos resultados de gerar_grades ({"turmas": [...], "pontuacao": ...}).
    Uma eletiva cabe quando não bate horário com nenhuma aula da grade, não é disciplina
    que a grade já tem e não passa do teto de créditos da carga escolhida.
    Os pontos são quanto a nota da grade (pontuar_grade: turno, distribuição e janelas)
    muda ao colocar a eletiva nela."""
    if candidatas is None:
        candidatas = turmas_candidatas(aluno, preferencias)

    turmas_da_grade = []
    ocupados = []
    disciplinas_da_grade = []
    creditos = 0
    for turma in grade["turmas"]:
        horarios = horarios_da_turma(turma) or []
        turmas_da_grade.append((turma, horarios))
        ocupados.extend(horarios)
        disciplinas_da_grade.append(turma.disciplina_id)
        creditos += turma.disciplina.creditos

    limite = LIMITE_DE_CREDITOS.get(preferencias.carga_disciplinas, LIMITE_DE_CREDITOS["media"])
    pontos_da_grade = pontuar_grade(turmas_da_grade, preferencias)

    # co-requisito: vale o que o aluno já fez ou o que está na própria grade; e nunca duas
    # disciplinas da mesma classe de equivalência na grade
    classes = classes_de_equivalencia()
    codigos_da_grade = {turma.disciplina.codigo for turma in grade["turmas"]}
    classes_da_grade = {classe_de(codigo, classes) for codigo in codigos_da_grade}

    # período de referência e atual: os da própria grade (gerador_grades.periodos_do_aluno)
    referencia = grade.get("periodo_referencia")
    atual = grade.get("periodo_atual")

    sugestoes = []
    for candidata in candidatas:
        turma = candidata["turma"]
        if turma.disciplina_id in disciplinas_da_grade:
            continue
        if classe_de(turma.disciplina.codigo, classes) in classes_da_grade:
            continue
        if not co_requisitos_cumpridos(turma.disciplina.codigo, candidata["feitos"], codigos_da_grade, candidata["tabela"]):
            continue
        if creditos + turma.disciplina.creditos > limite:
            continue
        if tem_conflito(ocupados, candidata["horarios"]):
            continue

        com_a_eletiva = turmas_da_grade + [(turma, candidata["horarios"])]
        faixa = faixa_da_optativa(candidata.get("periodos", {candidata["periodo"]}), referencia, atual)
        sugestoes.append({
            "turma": turma,
            "grupos": candidata["grupos"],
            "periodo": candidata["periodo"],
            "faixa": faixa,
            "rotulo": rotulo_da_faixa(faixa, referencia),
            "pontos": pontuar_grade(com_a_eletiva, preferencias) - pontos_da_grade,
        })

    sugestoes.sort(key=ordem_da_sugestao)
    return sugestoes


def sugerir_para_grades(aluno, preferencias, grades):
    """Uma lista de sugestões para cada grade, na mesma ordem das grades."""
    candidatas = turmas_candidatas(aluno, preferencias)
    resultado = []
    for grade in grades:
        resultado.append(sugerir_eletivas(aluno, preferencias, grade, candidatas))
    return resultado
