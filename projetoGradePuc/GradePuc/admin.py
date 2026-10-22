from django.contrib import admin
from .models import Professor, Disciplina, Turma, Aluno, RotinaPreferencias, Grade, Pergunta

admin.site.register(Professor)
admin.site.register(Disciplina)
admin.site.register(Turma)
admin.site.register(Aluno)
admin.site.register(RotinaPreferencias)
admin.site.register(Grade)
admin.site.register(Pergunta)