from django.shortcuts import render, redirect
from .forms import *
from .models import Professor, Disciplina, Turma, Aluno, RotinaPreferencias, Grade, Pergunta

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

OPCOES_GRADE = [
    {'numero': '1', 'titulo': 'Equilíbrio entre teoria e prática', 
     'codigos': ['ECO1301', 'AMB1103', 'INF1771']},
    {'numero': '2', 'titulo': 'Mais aulas pela manhã', 
     'codigos': ['ADM1710', 'ECO1301']},
    {'numero': '3', 'titulo': 'Com disciplinas eletivas', 
     'codigos': ['HIS2001', 'AMB1103', 'ECO1401']},
    {'numero': '4', 'titulo': 'Menos dias na semana', 
     'codigos': ['ECO1301', 'ADM1710']},
]

def home(request):

    aluno = Aluno.objects.first()

    if request.method == 'POST':
        form = TelaInicialForm(request.POST)

        if form.is_valid():
            return redirect('/questionario/')

    else:
        form = TelaInicialForm()

    return render(request, "tela_inicial.html", {
        'form': form,
        'aluno': aluno,
    })

def ajuda(request):
    perguntas = [
        {'titulo': 'Como montar minha grade?', 
         'texto': 'Adicione disciplinas pelo catálogo. Conflitos de horário são bloqueados automaticamente.'},
        {'titulo': 'Como usar uma sugestão?', 
         'texto': 'Abra Grades sugeridas, compare as opções e clique em Usar esta grade.'},
        {'titulo': 'Onde faço a matrícula?', 
         'texto': 'O grade.puc ajuda no planejamento. A matrícula oficial continua sendo feita no Portal SAU.'},
    ]
    return render(request, 'ajuda.html', {'perguntas': perguntas})

def pre_requisitos(request):
    disciplinas = Disciplina.objects.prefetch_related('pre_requisitos').all()

    return render(request, "pre_requisitos.html", {
        'disciplinas': disciplinas,
    })

def resumo_da_grade(request):
    aluno = Aluno.objects.first()
    grade = Grade.objects.filter(aluno=aluno).last()
    turmas = grade.turmas.select_related('disciplina') if grade else []

    form = BuscaDisciplinaForm(request.GET)

    if grade and form.is_valid() and form.cleaned_data['busca']:
        turmas = turmas.filter(
            disciplina__nome__icontains=form.cleaned_data['busca']
        )

    cursadas = set(aluno.disciplinas_cursadas.all())

    for t in turmas:
        pre = set(t.disciplina.pre_requisitos.all())
        t.pendente = not pre.issubset(cursadas)

    return render(request, 'resumo_da_grade.html', {
        'form': form,
        'turmas': turmas,
    })

def eletiva(request):
    aluno = Aluno.objects.first()
    turmas = Turma.objects.all()
    if aluno != None:
        turmas = turmas.exclude(disciplina__in=aluno.disciplinas_cursadas.all())

    form = EletivasForm(request.GET)
    busca = ''
    filtro = 'todas'
    if form.is_valid():
        busca = form.cleaned_data['busca']
        if form.cleaned_data['filtro'] != '':
            filtro = form.cleaned_data['filtro']

    lista = []
    for turma in turmas:
        if turma.vagas <= 5:
            tipo = 'alta_demanda'
            etiqueta = 'Alta demanda'
        elif turma.professor.avaliacoes >= 4.5:
            tipo = 'popular'
            etiqueta = 'Popular'
        else:
            tipo = 'recomendado'
            etiqueta = 'Recomendado'

        if filtro != 'todas' and filtro != tipo:
            mostrar = False
        else:
            mostrar = True

        if mostrar and busca != '':
            nome = turma.disciplina.nome.lower()
            codigo = turma.disciplina.codigo.lower()
            if busca.lower() not in nome and busca.lower() not in codigo:
                mostrar = False

        if mostrar:
            lista.append({'turma': turma, 'etiqueta': etiqueta})

    return render(request, "eletivas.html", {
        'eletivas': lista,
        'busca': busca,
        'filtro': filtro,
        'filtros': FILTROS_ELETIVAS,
    })

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
    aluno = Aluno.objects.first() # provisório, igual ao questionário
    
    if request.method == 'POST':
        form = UsarGradeForm(request.POST)
        if form.is_valid():
            numero = form.cleaned_data['opcao']
            opcao = [o for o in OPCOES_GRADE if o['numero'] == numero][0]
            
            grade = Grade.objects.create(aluno=aluno, descricao=opcao['titulo'])
            grade.turmas.set(
                Turma.objects.filter(disciplina__codigo__in=opcao['codigos'])
            )
            return redirect('/resumodagrade/')
            
    opcoes = []
    for o in OPCOES_GRADE:
        turmas = Turma.objects.filter(disciplina__codigo__in=o['codigos'])
        opcoes.append({
            'numero': o['numero'],
            'titulo': o['titulo'],
            'turmas': turmas.select_related('disciplina', 'professor')
        })
        
    return render(request, 'grades-sugeridas.html', {'opcoes': opcoes})