from django.shortcuts import render
from .models import Professor, Disciplina, Turma, Aluno, RotinaPreferencias, Grade

def home(request):
    return render(request, "tela_inicial.html")

def ajuda(request):
    return render(request, "ajuda.html")

def pre_requisitos(request):
    return render(request, "pre_requisitos.html")