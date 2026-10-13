from django.shortcuts import render
from .models import Professor, Disciplina, Turma, Aluno, RotinaPreferencias, Grade

def home(request):
    return render(request, "tela_inicial.html")

def ajuda(request):
    return render(request, "ajuda.html")

def resumo_da_grade(request):
    return render(request, "resumo_da_grade.html")

def eletiva(request):
    return render(request, "eletivas.html")

def questionario(request):
    return render(request, "questionario.html")
