from django.http import JsonResponse
from django.shortcuts import get_object_or_404, render, redirect
from django.views.decorators.http import require_GET
from .forms import *
from .models import Professor, Disciplina, Turma, Aluno, RotinaPreferencias, Grade, Pergunta
from django.contrib.auth.models import User
from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.decorators import login_required
from django.db import transaction

def obter_aluno(request):
    aluno, criado = Aluno.objects.get_or_create(
        usuario=request.user,
        defaults={
            'matricula': request.user.username,
            'senha': ''
        }
    )
    return aluno

def create_user(request):
    if request.method == 'POST':
        matricula = request.POST.get('matricula', '').strip()
        email = request.POST.get('email', '').strip()
        senha = request.POST.get('password', '')
        confirmar_senha = request.POST.get('confirmar_senha', '')

        if not matricula or not senha:
            return render(request, 'cadastro.html', {
                'error_msg': 'Preencha a matrícula e a senha.'
            })

        if senha != confirmar_senha:
            return render(request, 'cadastro.html', {
                'error_msg': 'As senhas não coincidem.'
            })

        if User.objects.filter(username=matricula).exists():
            return render(request, 'cadastro.html', {
                'error_msg': 'Esta matrícula já possui uma conta.'
            })

        with transaction.atomic():
            usuario = User.objects.create_user(
                username=matricula,
                email=email,
                password=senha
            )

            aluno = Aluno.objects.filter(
                matricula=matricula,
                usuario__isnull=True
            ).first()

            if aluno:
                aluno.usuario = usuario
                aluno.senha = ''
                aluno.save()
            else:
                Aluno.objects.create(
                    usuario=usuario,
                    matricula=matricula,
                    senha=''
                )

        return redirect('home')

    return render(request, 'cadastro.html')

@login_required
def logout_user(request):
    if request.method == 'POST':
        logout(request)
        return redirect('login')
    
    return redirect('home')

OPCOES_TURNO = [
    {'valor': 'manha', 'nome': 'Manhã', 'icone': '☀️', 'descricao': 'Prefiro ter aulas no período da manhã.'},
    {'valor': 'tarde', 'nome': 'Tarde', 'icone': '🌤️', 'descricao': 'Prefiro ter aulas no período da tarde.'},
    {'valor': 'noite', 'nome': 'Noite', 'icone': '🌙', 'descricao': 'Prefiro ter aulas no período da noite.'},
    {'valor': 'sem_preferencia', 'nome': 'Sem preferência', 'icone': '📅', 'descricao': 'Estou aberto a qualquer turno.'},
]

OPCOES_MODALIDADE = [
    {'valor': 'presencial', 'nome': 'Presencial', 'icone': '🏫', 'descricao': 'Aulas na universidade'},
    {'valor': 'online', 'nome': 'Online', 'icone': '💻', 'descricao': 'Aulas à distância'},
    {'valor': 'hibrido', 'nome': 'Híbrido', 'icone': '🔄', 'descricao': 'Parte presencial, parte online'},
]

OPCOES_DISTRIBUICAO = [
    {'valor': 'equilibrado', 'nome': 'Equilibrado pela semana', 'icone': '⚖️', 'descricao': 'Aulas espalhadas de forma parecida em todos os dias'},
    {'valor': 'dia_leve', 'nome': 'Acumular para ter um dia mais leve', 'icone': '🍃', 'descricao': 'Mais aulas em alguns dias para sobrar um dia com poucas aulas'},
    {'valor': 'dia_livre', 'nome': 'Acumular para ter um dia livre', 'icone': '🏖️', 'descricao': 'Aulas concentradas para deixar um dia da semana sem aula'},
    {'valor': 'tanto_faz', 'nome': 'Tanto faz', 'icone': '🤷', 'descricao': 'Não tenho preferência'},
]

OPCOES_JANELAS = [
    {'valor': 'sem_janelas', 'nome': 'Sem janelas', 'icone': '⏩', 'descricao': 'Aulas seguidas, sem horários vagos entre elas'},
    {'valor': 'janelas_curtas', 'nome': 'Aceito janelas curtas', 'icone': '☕', 'descricao': 'Intervalos de até 1 hora entre as aulas'},
    {'valor': 'tanto_faz', 'nome': 'Tanto faz', 'icone': '🤷', 'descricao': 'Não tenho preferência'},
]

OPCOES_CARGA = [
    {'valor': 'leve', 'nome': 'Leve', 'icone': '📗', 'descricao': '3 a 4 disciplinas'},
    {'valor': 'media', 'nome': 'Média', 'icone': '📚', 'descricao': '5 a 6 disciplinas'},
    {'valor': 'pesada', 'nome': 'Pesada', 'icone': '🏋️', 'descricao': '7 ou mais disciplinas'},
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
    if request.user.is_authenticated:
        return redirect('/questionario/')

    if request.method == 'POST':
        matricula = request.POST.get('matricula', '').strip()
        senha = request.POST.get('password', '')

        usuario = authenticate(
            request,
            username=matricula,
            password=senha
        )

        if usuario is not None:
            login(request, usuario)
            return redirect('/questionario/')

        return render(request, 'tela_inicial.html', {
            'error_msg': 'Matrícula ou senha incorreta.'
        })

    return render(request, 'tela_inicial.html')

@login_required
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

@login_required
def pre_requisitos(request):
    disciplinas = list(Disciplina.objects.prefetch_related('pre_requisitos').order_by('codigo'))
    aluno = Aluno.objects.first()
    concluidas = set(aluno.disciplinas_cursadas.values_list('id', flat=True)) if aluno else set()

    # Organiza as disciplinas por nível de dependência sem pressupor uma grade fixa.
    niveis = {}
    pendentes = {disciplina.id: disciplina for disciplina in disciplinas}
    while pendentes:
        prontos = [
            disciplina for disciplina in pendentes.values()
            if all(pre.id in niveis for pre in disciplina.pre_requisitos.all())
        ]
        if not prontos:  # Evita perder disciplinas caso existam dependências cíclicas.
            prontos = list(pendentes.values())
        for disciplina in prontos:
            pre_requisitos = list(disciplina.pre_requisitos.all())
            niveis[disciplina.id] = max(
                (niveis.get(pre.id, -1) + 1 for pre in pre_requisitos), default=0
            )
            del pendentes[disciplina.id]

    trilhas_por_nivel = {}
    for disciplina in disciplinas:
        pre_ids = set(disciplina.pre_requisitos.values_list('id', flat=True))
        if disciplina.id in concluidas:
            status = 'concluida'
        elif pre_ids.issubset(concluidas):
            status = 'disponivel'
        else:
            status = 'bloqueada'
        nivel = niveis[disciplina.id]
        trilhas_por_nivel.setdefault(nivel, []).append({
            'id': disciplina.id,
            'nome': disciplina.nome,
            'codigo': disciplina.codigo,
            'status': status,
        })

    trilhas = [
        {'nome': f'Etapa {nivel + 1}', 'disciplinas': itens}
        for nivel, itens in sorted(trilhas_por_nivel.items())
    ]

    return render(request, "pre_requisitos.html", {
        'trilhas': trilhas,
    })


@require_GET
def api_disciplina(request, disciplina_id):
    disciplina = get_object_or_404(
        Disciplina.objects.prefetch_related('pre_requisitos'), pk=disciplina_id
    )
    return JsonResponse({
        'id': disciplina.id,
        'codigo': disciplina.codigo,
        'nome': disciplina.nome,
        'pre_requisitos': [
            {'id': requisito.id, 'codigo': requisito.codigo, 'nome': requisito.nome}
            for requisito in disciplina.pre_requisitos.all()
        ],
    })

@login_required
def resumo_da_grade(request):
    aluno = obter_aluno(request)
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

@login_required
def eletiva(request):
    aluno = obter_aluno(request)
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

@login_required
def questionario(request):
    aluno = obter_aluno(request)
    rotina = RotinaPreferencias.objects.filter(aluno=aluno).first()

    if request.method == 'POST':
        form = TurnoForm(request.POST, instance=rotina)
        if form.is_valid():
            preferencias = form.save(commit=False)
            preferencias.aluno = aluno
            preferencias.save()
            return redirect('/questionario/modalidade/')
    else:
        form = TurnoForm(instance=rotina)

    return render(request, 'questionario.html', {
        'form': form,
        'opcoes_turno': OPCOES_TURNO,
    })

def questionario_modalidade(request):
    aluno = Aluno.objects.first()
    rotina = RotinaPreferencias.objects.filter(aluno=aluno).first()

    if request.method == 'POST':
        form = ModalidadeForm(request.POST, instance=rotina)
        if form.is_valid():
            preferencias = form.save(commit=False)
            preferencias.aluno = aluno
            preferencias.save()
            return redirect('/questionario/distribuicao/')
    else:
        form = ModalidadeForm(instance=rotina)

    return render(request, 'questionario_modalidade.html', {
        'form': form,
        'opcoes_modalidade': OPCOES_MODALIDADE,
    })

def questionario_distribuicao(request):
    aluno = Aluno.objects.first()
    rotina = RotinaPreferencias.objects.filter(aluno=aluno).first()

    if request.method == 'POST':
        form = DistribuicaoForm(request.POST, instance=rotina)
        if form.is_valid():
            preferencias = form.save(commit=False)
            preferencias.aluno = aluno
            preferencias.save()
            return redirect('/questionario/janelas/')
    else:
        form = DistribuicaoForm(instance=rotina)

    return render(request, 'questionario_distribuicao.html', {
        'form': form,
        'opcoes_distribuicao': OPCOES_DISTRIBUICAO,
    })

def questionario_janelas(request):
    aluno = Aluno.objects.first()
    rotina = RotinaPreferencias.objects.filter(aluno=aluno).first()

    if request.method == 'POST':
        form = JanelasForm(request.POST, instance=rotina)
        if form.is_valid():
            preferencias = form.save(commit=False)
            preferencias.aluno = aluno
            preferencias.save()
            return redirect('/questionario/carga/')
    else:
        form = JanelasForm(instance=rotina)

    return render(request, 'questionario_janelas.html', {
        'form': form,
        'opcoes_janelas': OPCOES_JANELAS,
    })

def questionario_carga(request):
    aluno = Aluno.objects.first()
    rotina = RotinaPreferencias.objects.filter(aluno=aluno).first()

    if request.method == 'POST':
        form = CargaForm(request.POST, instance=rotina)
        if form.is_valid():
            preferencias = form.save(commit=False)
            preferencias.aluno = aluno
            preferencias.save()
            return redirect('/grades-sugeridas/')
    else:
        form = CargaForm(instance=rotina)

    return render(request, 'questionario_carga.html', {
        'form': form,
        'opcoes_carga': OPCOES_CARGA,
    })

@login_required
def gradessugeridas(request):
    aluno = obter_aluno(request) # provisório, igual ao questionário
    
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