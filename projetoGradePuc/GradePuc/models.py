from django.db import models
from django.conf import settings 

class Professor(models.Model):
    nome = models.CharField(max_length=100)
    avaliacoes = models.FloatField(default=0)

    def __str__(self):
        return self.nome
    
class Disciplina(models.Model):
    codigo = models.CharField(max_length=20)
    nome = models.CharField(max_length=100)
    creditos = models.IntegerField(default=0)
    departamento = models.CharField(max_length=10, blank=True)

    pre_requisitos = models.ManyToManyField("self", symmetrical=False, blank=True)

    def __str__(self):
        return self.codigo + " - " + self.nome
    
class Turma(models.Model):
    disciplina = models.ForeignKey(Disciplina, on_delete=models.CASCADE)
    professor = models.ForeignKey(Professor, on_delete=models.CASCADE)
    codigo_turma = models.CharField(max_length=10)
    destino = models.CharField(max_length=10, blank=True)
    turno = models.CharField(max_length=5, blank=True)
    dias_horarios = models.CharField(max_length=300, blank=True)
    vagas = models.IntegerField(default=0)
    sala = models.CharField(max_length=50, blank=True)

    def __str__(self):
        return str(self.disciplina) + " - " + self.codigo_turma
    
class Aluno(models.Model):
    usuario = models.OneToOneField(
    settings.AUTH_USER_MODEL,
    on_delete=models.CASCADE,
    null=True,
    blank=True
    )
    matricula = models.CharField(max_length=20)
    senha = models.CharField(max_length=100)
    disciplinas_cursadas = models.ManyToManyField(Disciplina, blank=True)

    # Dados lidos do Espelho do Histórico (SAU)
    curso_sigla = models.CharField(max_length=10, blank=True)
    habilitacao_sigla = models.CharField(max_length=10, blank=True)
    enfase_sigla = models.CharField(max_length=10, blank=True)
    ano_curriculo = models.CharField(max_length=10, blank=True)
    codigo_curriculo = models.CharField(max_length=20, blank=True)
    cr = models.CharField(max_length=10, blank=True)
    matricula_espelho = models.CharField(max_length=20, blank=True)
    espelho_importado_em = models.DateTimeField(null=True, blank=True)

    @property
    def precisa_confirmar_curso(self):
        """Tem espelho, mas a sigla do curso ainda não está ligada a nenhum currículo."""
        if not self.espelho_importado_em or not self.curso_sigla:
            return False
        return LigacaoHabilitacao.para_siglas(self.curso_sigla, self.habilitacao_sigla, self.enfase_sigla) is None

    def __str__(self):
        return self.matricula
    
class RotinaPreferencias(models.Model):
    aluno = models.OneToOneField(Aluno, on_delete=models.CASCADE)
    horarios_trabalho = models.CharField(max_length=100, blank=True)
    distribuicao_aulas = models.CharField(max_length=100, blank=True)
    turno = models.CharField(max_length=20)
    modalidade = models.CharField(max_length=20)
    janelas = models.CharField(max_length=20, blank=True)
    carga_disciplinas = models.CharField(max_length=20, blank=True)

    def __str__(self):
        return "Preferências de " + str(self.aluno)
class Grade(models.Model):
    aluno = models.ForeignKey(Aluno, on_delete=models.CASCADE)
    turmas = models.ManyToManyField(Turma)
    descricao = models.CharField(max_length=200, blank=True)

    def __str__(self):
        return "Grade de " + str(self.aluno)
    
class Pergunta(models.Model):
    pergunta = models.CharField(max_length=200)
    resposta = models.TextField()
    ordem = models.IntegerField(default=0)

    class Meta:
        ordering = ['ordem']

    def __str__(self):
        return self.pergunta


class HistoricoDisciplina(models.Model):
    """Uma linha do Espelho do Histórico do aluno."""
    aluno = models.ForeignKey(Aluno, on_delete=models.CASCADE, related_name='historico')
    periodo = models.CharField(max_length=10)
    codigo = models.CharField(max_length=20)
    nome = models.CharField(max_length=200)
    turma = models.CharField(max_length=10, blank=True)
    grau = models.CharField(max_length=10, blank=True)
    situacao = models.CharField(max_length=10)
    tipo = models.CharField(max_length=100, blank=True)
    grupo = models.CharField(max_length=20, blank=True)
    creditos = models.IntegerField(default=0)
    disciplina = models.ForeignKey(Disciplina, on_delete=models.SET_NULL, null=True, blank=True)

    class Meta:
        ordering = ['periodo', 'codigo']

    def __str__(self):
        return f"{self.aluno} - {self.periodo} - {self.codigo} ({self.situacao})"


class Curriculo(models.Model):
    """Periodização de um curso (uma variante por ênfase), lida do site da PUC."""
    curso_nome = models.CharField(max_length=200)
    ano = models.IntegerField(null=True, blank=True)
    enfase = models.CharField(max_length=200, blank=True)
    titulo = models.CharField(max_length=300)
    url_pagina = models.URLField(max_length=300)
    importado_em = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['curso_nome', 'enfase']

    def __str__(self):
        texto = self.curso_nome
        if self.ano:
            texto += f" ({self.ano})"
        if self.enfase:
            texto += f" - {self.enfase}"
        return texto


class DisciplinaCurriculo(models.Model):
    """Uma linha da tabela de periodização de um currículo."""
    curriculo = models.ForeignKey(Curriculo, on_delete=models.CASCADE, related_name='itens')
    periodo = models.IntegerField(null=True, blank=True)
    codigo = models.CharField(max_length=20)
    nome = models.CharField(max_length=200)
    creditos = models.IntegerField(default=0)
    ch_extensao = models.CharField(max_length=20, blank=True)
    eh_grupo = models.BooleanField(default=False)
    ordem = models.IntegerField(default=0)

    class Meta:
        ordering = ['ordem']

    def __str__(self):
        periodo = f"{self.periodo}º período" if self.periodo else "período indeterminado"
        return f"{self.codigo} - {self.nome} ({periodo})"


class DisciplinaDoGrupo(models.Model):
    """Uma disciplina que conta para um grupo de optativas do currículo (ENG0561 -> ENG4500).

    Lida da ementa do grupo no site da PUC. As turmas e horários continuam em Turma:
    a ligação é pelo código da disciplina."""
    grupo = models.CharField(max_length=20)
    codigo = models.CharField(max_length=20)
    nome = models.CharField(max_length=200)

    class Meta:
        ordering = ['grupo', 'codigo']
        unique_together = ('grupo', 'codigo')

    def __str__(self):
        return f"{self.grupo} -> {self.codigo} - {self.nome}"


class LigacaoHabilitacao(models.Model):
    """Liga as siglas do SAU (curso/habilitação/ênfase) a um currículo do site."""
    ORIGENS = [
        ('pre_cadastro', 'Pré-cadastro'),
        ('aluno', 'Confirmado por aluno'),
        ('admin', 'Admin'),
    ]

    curso_sigla = models.CharField(max_length=10)
    habilitacao_sigla = models.CharField(max_length=10)
    enfase_sigla = models.CharField(max_length=10, blank=True)
    curriculo = models.ForeignKey(Curriculo, on_delete=models.SET_NULL, null=True, blank=True)
    origem = models.CharField(max_length=20, choices=ORIGENS, default='aluno')
    confirmado_por = models.ForeignKey(Aluno, on_delete=models.SET_NULL, null=True, blank=True)
    criado_em = models.DateTimeField(auto_now_add=True)
    atualizado_em = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = ('curso_sigla', 'habilitacao_sigla', 'enfase_sigla')

    @classmethod
    def para_siglas(cls, curso, habilitacao, enfase):
        """Ligação com currículo: primeiro a sigla exata, depois a que vale para qualquer ênfase."""
        ligacoes = cls.objects.filter(curso_sigla=curso, habilitacao_sigla=habilitacao, curriculo__isnull=False)
        return ligacoes.filter(enfase_sigla=enfase).first() or ligacoes.filter(enfase_sigla='').first()

    def __str__(self):
        siglas = f"{self.curso_sigla}/{self.habilitacao_sigla}/{self.enfase_sigla or '*'}"
        return f"{siglas} -> {self.curriculo or 'sem ligação'}"


class Requisito(models.Model):
    """Pré-requisito ou co-requisito de uma disciplina, lido da ementa no site da PUC.

    A ementa traz alternativas ligadas por OU, e cada alternativa pode exigir vários
    códigos ligados por E: (EMP1320 e INF1037) ou (EMP1320 e INF1026). Cada linha é um
    código de uma alternativa. Os códigos ficam como texto: o código exigido pode nem
    existir em Disciplina. A observação ("MATEMÁTICA (nivel 3)") é nivelamento, não
    disciplina, e não bloqueia; uma alternativa só com observação fica com codigo vazio.
    """
    TIPOS = [('pre', 'Pré-requisito'), ('co', 'Co-requisito')]

    disciplina = models.CharField(max_length=20, db_index=True)
    tipo = models.CharField(max_length=3, choices=TIPOS)
    alternativa = models.IntegerField()
    codigo = models.CharField(max_length=20, blank=True)
    observacao = models.CharField(max_length=200, blank=True)

    class Meta:
        ordering = ['disciplina', 'tipo', 'alternativa', 'codigo']

    def __str__(self):
        exigido = self.codigo or self.observacao
        return f"{self.disciplina} {self.tipo} #{self.alternativa}: {exigido}"


class EmentaLida(models.Model):
    """Códigos cuja ementa já foi lida pelo importar_requisitos (com ou sem requisitos).
    'encontrada' = False quando a PUC não tem ementa para o código."""
    codigo = models.CharField(max_length=20, unique=True)
    encontrada = models.BooleanField(default=True)

    class Meta:
        ordering = ['codigo']

    def __str__(self):
        return self.codigo if self.encontrada else f"{self.codigo} (sem ementa)"

