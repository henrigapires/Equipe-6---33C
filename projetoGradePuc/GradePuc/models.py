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
