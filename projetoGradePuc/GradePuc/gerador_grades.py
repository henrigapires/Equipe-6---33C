
import re
from collections import defaultdict

from .models import Turma
from .historico import curriculo_do_aluno


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


def gerar_grades(aluno, preferencias, limite=4):
    """Gera até quatro grades sem conflitos conhecidos."""
    cursadas = set(
        aluno.disciplinas_cursadas.values_list("id", flat=True)
    )

    candidatos = defaultdict(list)
    curriculo = curriculo_do_aluno(aluno)

    if curriculo is None:
        return []

    codigos_curriculo = set(
        curriculo.itens
        .filter(eh_grupo=False)
        .values_list("codigo", flat=True)
    )

    turmas = (
        Turma.objects
        .select_related("disciplina", "professor")
        .prefetch_related("disciplina__pre_requisitos")
        .filter(
    vagas__gt=0,
    disciplina__codigo__in=codigos_curriculo
)
        .exclude(disciplina_id__in=cursadas)
        .order_by("disciplina__codigo", "codigo_turma")
    )
    if preferencias.modalidade == 'online':
        turmas = turmas.filter(sala__icontains='VIRTUAL')
    elif preferencias.modalidade == 'presencial':
        turmas = turmas.exclude(sala__icontains='VIRTUAL')

    for turma in turmas:
        requisitos = {
            d.id for d in turma.disciplina.pre_requisitos.all()
        }
        if not requisitos.issubset(cursadas):
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

    grupos = sorted(
        candidatos.values(),
        key=lambda grupo: len(grupo)
    )

    quantidade = CARGAS.get(preferencias.carga_disciplinas, 5)
    resultados = []
    vistos = set()

    # Limita a busca para evitar processar combinações excessivas.
    for deslocamento in range(min(len(grupos), 30)):
        escolhidas = []
        ocupados = []

        ordem = grupos[deslocamento:] + grupos[:deslocamento]

        for grupo in ordem:
            melhor = None
            melhor_pontuacao = float("-inf")

            for turma, horarios in grupo[:12]:
                if tem_conflito(ocupados, horarios):
                    continue

                nota = pontuar_grade(
                    escolhidas + [(turma, horarios)],
                    preferencias
                )
                if nota > melhor_pontuacao:
                    melhor = (turma, horarios)
                    melhor_pontuacao = nota

            if melhor:
                escolhidas.append(melhor)
                ocupados.extend(melhor[1])

            if len(escolhidas) >= quantidade:
                break

        if len(escolhidas) != quantidade:
            continue

        chave = tuple(sorted(turma.id for turma, _ in escolhidas))
        if chave in vistos:
            continue

        vistos.add(chave)
        resultados.append({
            "turmas": [turma for turma, _ in escolhidas],
            "pontuacao": pontuar_grade(escolhidas, preferencias),
        })

    resultados.sort(
        key=lambda grade: grade["pontuacao"],
        reverse=True
    )

    return resultados[:limite]
