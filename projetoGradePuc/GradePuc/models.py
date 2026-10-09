from django.db import models
class Professor(models.Model):
    nome = models.CharField(max_length=100)
    avaliacoes = models.FloatField(default=0)

    def __str__(self):
        return self.nome
class Disciplina(models.Model):
    codigo = models.CharField(max_length=20)
    nome = models.CharField(max_length=100)
    pre_requisitos = models.ManyToManyField("self", symmetrical=False, blank=True)

    def __str__(self):
        return self.codigo + " - " + self.nome
class Turma(models.Model):
    disciplina = models.ForeignKey(Disciplina, on_delete=models.CASCADE)
    professor = models.ForeignKey(Professor, on_delete=models.CASCADE)
    dias_horarios = models.CharField(max_length=100)
    vagas = models.IntegerField()
    sala = models.CharField(max_length=20)

    def __str__(self):
        return str(self.disciplina) + " - " + self.dias_horarios
class Aluno(models.Model):
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

    def __str__(self):
        return "Preferências de " + str(self.aluno)
class Grade(models.Model):
    aluno = models.ForeignKey(Aluno, on_delete=models.CASCADE)
    turmas = models.ManyToManyField(Turma)
    descricao = models.CharField(max_length=200, blank=True)

    def __str__(self):
        return "Grade de " + str(self.aluno)
