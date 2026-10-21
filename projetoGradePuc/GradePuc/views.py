from django.shortcuts import render, redirect
from .forms import *
from .models import Professor, Disciplina, Turma, Aluno, RotinaPreferencias, Grade

OPCOES_TURNO = [
    {'valor': 'manha', 'nome': 'Manhã', 'icone': '☀️', 'descricao': 'Prefiro ter aulas no período da manhã.'},
    {'valor': 'tarde', 'nome': 'Tarde', 'icone': '🌤️', 'descricao': 'Prefiro ter aulas no período da tarde.'},
    {'valor': 'noite', 'nome': 'Noite', 'icone': '🌙', 'descricao': 'Prefiro ter aulas no período da noite.'},
    {'valor': 'sem_preferencia', 'nome': 'Sem preferência', 'icone': '📅', 'descricao': 'Estou aberto a qualquer turno.'},
]

OPCOES_MODALIDADE = [
    {'valor': 'presencial', 'nome': 'Presencial'},
    {'valor': 'online', 'nome': 'Online'},
    {'valor': 'hibrido', 'nome': 'Híbrido'},
]

def home(request):
    return render(request, "tela_inicial.html")

def ajuda(request):
    return render(request, "ajuda.html")

def pre_requisitos(request):
    return render(request, "pre_requisitos.html")

def resumo_da_grade(request):
    return render(request, "resumo_da_grade.html")

def eletiva(request):
    return render(request, "eletivas.html")

def questionario(request):
    aluno = Aluno.objects.first()
    rotina = RotinaPreferencias.objects.filter(aluno=aluno).first()

    if request.method == 'POST':
        form = RotinaPreferenciasForm(request.POST, instance=rotina)
        if form.is_valid():
            preferencias = form.save(commit=False)
            preferencias.aluno = aluno
            preferencias.save()
            return redirect('/grades-sugeridas/')
    else:
        form = RotinaPreferenciasForm(instance=rotina)

    return render(request, 'questionario.html', {
        'form': form,
        'opcoes_turno': OPCOES_TURNO,
        'opcoes_modalidade': OPCOES_MODALIDADE,
    })

def gradessugeridas(request):
    return render(request, "grades-sugeridas.html")