"""Auditoria das grades sugeridas e das eletivas: confere, turma por turma, se a regra de
pré/co-requisito foi respeitada. Usada pelo teste de propriedade e pelo comando
auditar_requisitos.

De propósito NÃO usa requisitos.py: lê os Requisito direto do banco e calcula sozinho o
que conta como feito, para um erro na regra não se esconder atrás dela mesma.

Para cada turma sugerida confere:
  (a) pré-requisito cumprido por alguma alternativa completa, contando só o histórico
      (cursadas e em andamento) e as disciplinas cursadas, nunca a própria grade;
  (b) co-requisito cumprido pelo histórico OU por outra turma da mesma grade;
  (c) a disciplina não foi cursada;
  (d) nenhuma classe de equivalência aparece duas vezes na grade.
"""
from .espelho import SITUACOES_CURSADAS, SITUACOES_EM_ANDAMENTO
from .historico import EM_ANDAMENTO_CONTA_COMO_CURSADA, SEM_VAGA
from .models import Disciplina, DisciplinaDoGrupo, EmentaLida, LigacaoHabilitacao, Requisito
from .requisitos import classe_de, classes_de_equivalencia, expandir_equivalencias


class Verificador:
    def __init__(self):
        self.alternativas = {}           # (disciplina, tipo) -> {alternativa: {códigos}}
        for disciplina, tipo, alternativa, codigo in Requisito.objects.values_list(
            "disciplina", "tipo", "alternativa", "codigo"
        ):
            exigidos = self.alternativas.setdefault((disciplina, tipo), {}).setdefault(alternativa, set())
            if codigo:
                exigidos.add(codigo)
        self.com_registro = {disciplina for disciplina, _ in self.alternativas}
        self.m2m = {}
        for disciplina, exigido in Disciplina.pre_requisitos.through.objects.values_list(
            "from_disciplina__codigo", "to_disciplina__codigo"
        ):
            self.m2m.setdefault(disciplina, set()).add(exigido)
        self.classes = classes_de_equivalencia()
        # ementas lidas com o quadro de requisitos (mesmo que vazio = "nenhum requisito")
        self.ementa_encontrada = set(EmentaLida.objects.filter(encontrada=True).values_list("codigo", flat=True))

    def feitos(self, aluno):
        """O que conta como feito, calculado aqui mesmo (sem requisitos.codigos_feitos)."""
        valem = set(SITUACOES_CURSADAS)
        if EM_ANDAMENTO_CONTA_COMO_CURSADA:
            valem |= SITUACOES_EM_ANDAMENTO
        feitos = set()
        for codigo, grupo, situacao in aluno.historico.values_list("codigo", "grupo", "situacao"):
            if situacao in valem:
                feitos.add(codigo)
                if grupo and grupo != SEM_VAGA:
                    feitos.add(grupo)
        feitos |= set(aluno.disciplinas_cursadas.values_list("codigo", flat=True))
        return expandir_equivalencias(feitos, self.classes)

    def sem_dados(self, codigo):
        """Disciplina cujos requisitos NÃO conhecemos: a ementa veio sem texto (como ENG4418)
        ou não foi lida, e não há M2M antigo. Uma ementa lida sem requisito não entra aqui:
        ela é conhecida ("nenhum requisito")."""
        return codigo not in self.ementa_encontrada and codigo not in self.com_registro and codigo not in self.m2m

    def descrever(self, alternativas):
        return " ou ".join("+".join(sorted(a)) or "(nivelamento)" for a in alternativas)

    def problemas(self, turmas, feitos, ids_cursadas, so_estas=None):
        """Lista de violações (texto) de uma grade. 'so_estas': confere só essas turmas
        (as outras da grade valem como "na mesma grade" para o co-requisito)."""
        problemas = []
        codigos_da_grade = [t.disciplina.codigo for t in turmas]
        conferir = so_estas if so_estas is not None else turmas
        for turma in conferir:
            codigo = turma.disciplina.codigo
            outras = set(expandir_equivalencias([c for c in codigos_da_grade if c != codigo], self.classes))

            # (a) pré-requisito: só histórico, nunca a grade
            if codigo in self.com_registro:
                pre = list(self.alternativas.get((codigo, "pre"), {}).values())
                if pre and not any(alternativa <= feitos for alternativa in pre):
                    problemas.append(f"{codigo}: falta pré-requisito ({self.descrever(pre)})")
            elif codigo in self.m2m and not self.m2m[codigo] <= feitos:
                problemas.append(f"{codigo}: falta pré-requisito ({self.descrever([self.m2m[codigo]])})")

            # (b) co-requisito: histórico ou outra turma da mesma grade
            co = list(self.alternativas.get((codigo, "co"), {}).values())
            if co and not any(alternativa <= (feitos | outras) for alternativa in co):
                problemas.append(f"{codigo}: falta co-requisito ({self.descrever(co)})")

            # (c) não cursada
            if codigo in feitos or turma.disciplina_id in ids_cursadas:
                problemas.append(f"{codigo}: já foi cursada")

            # (d) uma classe de equivalência por grade
            classe = classe_de(codigo, self.classes)
            if sum(1 for c in codigos_da_grade if classe_de(c, self.classes) == classe) > 1:
                problemas.append(f"{codigo}: outra disciplina da mesma classe ({classe}) na grade")
        return problemas

    def auditar(self, aluno, preferencias):
        """(turmas verificadas, violações, turmas sem dados de requisito) das grades
        sugeridas e das eletivas de um aluno."""
        from .eletivas import sugerir_para_grades
        from .gerador_grades import gerar_grades

        feitos = self.feitos(aluno)
        ids_cursadas = set(aluno.disciplinas_cursadas.values_list("id", flat=True))
        grades = gerar_grades(aluno, preferencias)
        sugestoes = sugerir_para_grades(aluno, preferencias, grades)
        verificadas, violacoes, sem_dados = 0, [], []
        for numero, grade in enumerate(grades, start=1):
            turmas = list(grade["turmas"])
            verificadas += len(turmas)
            violacoes += [f"grade {numero}: {p}" for p in self.problemas(turmas, feitos, ids_cursadas)]
            sem_dados += [t.disciplina.codigo for t in turmas if self.sem_dados(t.disciplina.codigo)]
            for sugestao in sugestoes[numero - 1]:
                eletiva = sugestao["turma"]
                verificadas += 1
                violacoes += [
                    f"grade {numero}, eletiva: {p}"
                    for p in self.problemas(turmas + [eletiva], feitos, ids_cursadas, so_estas=[eletiva])
                ]
        return verificadas, violacoes, sem_dados


# ---------- Históricos sintéticos (teste de propriedade e auditoria) ----------

def disciplina_inventada(codigo, situacao, periodo, grupo=""):
    return {"periodo": periodo, "codigo": codigo, "nome": "Disciplina " + codigo, "turma": "",
            "grau": "", "situacao": situacao, "tipo": "", "grupo": grupo, "creditos": 4}


def historicos_sinteticos(curriculo):
    """{nome: [disciplinas do espelho]} para um currículo: sem nada, no meio do curso,
    adiantado, com atrasadas e com um equivalente do espelho."""
    itens = list(curriculo.itens.filter(eh_grupo=False).exclude(periodo=None).order_by("periodo", "ordem"))
    if not itens:
        return {"sem nada": []}
    ultimo = max(item.periodo for item in itens)
    meio = max(1, ultimo // 2)
    ate_o_meio = [i for i in itens if i.periodo <= meio]
    seguinte = [i for i in itens if i.periodo == meio + 1]

    def cursadas(lista):
        return [disciplina_inventada(i.codigo, "AP", f"20{20 + min(i.periodo, 9)}1") for i in lista]

    atrasadas = [i for i in ate_o_meio if i.periodo <= 2][:2]
    historicos = {
        "sem nada": [],
        "meio do curso": cursadas(ate_o_meio),
        "adiantado": cursadas(ate_o_meio + seguinte[:2]),
        "com atrasadas": cursadas([i for i in ate_o_meio if i not in atrasadas]),
    }
    if ate_o_meio:
        # a primeira disciplina foi feita com outro código, que o SAU marca como equivalente
        primeira = ate_o_meio[0]
        equivalente = disciplina_inventada("EQV" + primeira.codigo[3:], "AP", "20211", grupo=primeira.codigo)
        historicos["equivalente do espelho"] = [equivalente] + cursadas(ate_o_meio[1:])
    return historicos


def ligar_curriculo(curriculo, curso="AUD"):
    """Siglas inventadas que levam ao currículo (para salvar_espelho reconhecer o curso)."""
    habilitacao = f"C{curriculo.id:04d}"
    LigacaoHabilitacao.objects.update_or_create(
        curso_sigla=curso, habilitacao_sigla=habilitacao, enfase_sigla="",
        defaults={"curriculo": curriculo, "origem": "admin"},
    )
    return curso, habilitacao


def codigos_para_turmas(curriculo):
    """Códigos que precisam de turma para o gerador e as eletivas: itens do currículo e
    disciplinas dos grupos de optativa dele."""
    itens = set(curriculo.itens.filter(eh_grupo=False).values_list("codigo", flat=True))
    grupos = set(curriculo.itens.filter(eh_grupo=True).values_list("codigo", flat=True))
    itens |= set(DisciplinaDoGrupo.objects.filter(grupo__in=grupos).values_list("codigo", flat=True))
    return itens
