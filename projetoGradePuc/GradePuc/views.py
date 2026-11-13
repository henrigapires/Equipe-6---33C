from django.http import JsonResponse
from django.shortcuts import get_object_or_404, render, redirect
from django.views.decorators.http import require_GET
from .forms import *
from .models import Professor, Disciplina, Turma, Aluno, RotinaPreferencias, Grade, Pergunta
from django.contrib.auth.models import User
from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.decorators import login_required
from django.db import transaction
from .gerador_grades import gerar_grades
from .eletivas import sugerir_para_grades
from .gerador_grades import gerar_grades, interpretar_horarios
from django.contrib import messages
from .espelho import EspelhoInvalido, EspelhoSemTexto, classificar_situacao, ler_espelho
from .historico import curriculo_do_aluno, remover_historico, salvar_espelho
from .historico import (
    SEM_VAGA, SITUACOES_DA_CORRECAO, CorrecaoInvalida, adicionar_ao_historico, curriculo_das_siglas,
    disciplina_digitada, ocupacao_das_vagas, remover_do_historico, trocar_situacao_no_historico,
    trocar_vaga_no_historico, vagas_do_curriculo,
)
from .ligacao import confirmar_curso, deduzir_curriculos
from .models import Curriculo
from .ocr import MENSAGEM_SEM_OCR, OcrIndisponivel, eh_imagem, ler_espelho_por_ocr
from urllib.request import urlopen, Request
from urllib.error import URLError, HTTPError
from html.parser import HTMLParser

class ExtratorEmenta(HTMLParser):

    def __init__(self):
        super().__init__()
        self.dados = {}
        self.campos = {
            "hCodigo": "codigo",
            "hTitulo": "nome",
            "hCreditos": "creditos",
            "pEmenta": "ementa",
            "bibliografia": "bibliografia",
            "bibliografiaComplementar": "bibliografia_complementar",
            "prerequisito": "pre_requisitos",
            "corequisito": "co_requisitos",
            "pUltimaAtualizacao": "atualizacao",
        }
        self.campo_atual = None
        self.tag_atual = None
        self.profundidade = 0
        self.texto_atual = []

    def handle_starttag(self, tag, attrs):
        atributos = dict(attrs)
        identificador = atributos.get("id", "")

        if self.campo_atual is None and identificador in self.campos:
            self.campo_atual = self.campos[identificador]
            self.tag_atual = tag
            self.profundidade = 1

        elif self.campo_atual is not None:
            self.profundidade += 1

    def handle_data(self, dado):
        if self.campo_atual and dado.strip():
            self.texto_atual.append(dado.strip())

    def handle_endtag(self, tag):
        if self.campo_atual is None:
            return

        self.profundidade -= 1

        if self.profundidade == 0:
            self.dados[self.campo_atual] = " ".join(self.texto_atual)
            self.campo_atual = None
            self.tag_atual = None
            self.texto_atual = []

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
        nome = request.POST.get('nome', '').strip()
        matricula = request.POST.get('matricula', '').strip()
        email = request.POST.get('email', '').strip()
        senha = request.POST.get('password', '')
        confirmar_senha = request.POST.get('confirmar_senha', '')

        if not nome:
            return render(request, 'cadastro.html', {
                'error_msg': 'Preencha o nome.'
            })

        partes = nome.split(None, 1)
        primeiro_nome = partes[0]
        sobrenome = partes[1] if len(partes) > 1 else ''

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
                password=senha,
                first_name=primeiro_nome,
                last_name=sobrenome
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
                aluno = Aluno.objects.create(
                    usuario=usuario,
                    matricula=matricula,
                    senha=''
                )

        # O espelho é opcional e um erro nele nunca impede o cadastro: a conta já existe aqui.
        arquivos = request.FILES.getlist('espelho')
        if arquivos:
            # Com espelho, o aluno já entra logado e vai direto para "Meu perfil": lá ele vê o
            # histórico salvo, a conferência da leitura por OCR ou o erro com o formulário
            # para enviar de novo. A leitura fica na sessão de quem acabou de entrar.
            login(request, usuario)
            try:
                situacao, mensagem = importar_espelho_enviado(request, aluno, arquivos)
            except Exception:
                situacao, mensagem = 'erro', 'Não conseguimos ler este arquivo.'
            if situacao == 'salvo':
                messages.success(request, 'Conta criada! ' + mensagem)
                request.session['acabou_de_importar_espelho'] = True
            elif situacao == 'conferir':
                messages.success(
                    request,
                    'Conta criada! Lemos o seu arquivo por OCR: confira as disciplinas abaixo '
                    'e clique em "Confirmar e salvar".'
                )
            else:
                messages.warning(
                    request,
                    'Conta criada, mas o espelho não foi importado: ' + mensagem
                    + ' Envie de novo aqui embaixo.'
                )
            return redirect('perfil')

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
    {'valor': 'leve', 'nome': 'Leve', 'icone': '📗', 'descricao': 'Menos de 20 créditos'},
    {'valor': 'media', 'nome': 'Média', 'icone': '📚', 'descricao': '20 a 25 créditos'},
    {'valor': 'pesada', 'nome': 'Pesada', 'icone': '🏋️', 'descricao': 'Mais de 25 créditos'},
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
    aluno = obter_aluno(request)
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

def montar_grade_semanal(turmas_lista):
    dias = [
        ('SEG', 'Segunda'),
        ('TER', 'Terça'),
        ('QUA', 'Quarta'),
        ('QUI', 'Quinta'),
        ('SEX', 'Sexta'),
    ]

    aulas = []
    limites = set()
    for turma in turmas_lista:
        for dia, inicio, fim in interpretar_horarios(turma.dias_horarios) or []:
            aulas.append((dia, inicio, fim, turma))
            limites.update((inicio, fim))

    if any(dia == 5 for dia, _, _, _ in aulas):
        dias.append(('SAB', 'Sábado'))

    if not limites:
        return dias, []

    # Mantém linhas de uma hora e inclui os minutos exatos de início e fim.
    limites.update(range(min(limites) // 60 * 60, max(limites), 60))
    horarios = sorted(limites)
    indices = {hora: indice for indice, hora in enumerate(horarios)}
    aulas_por_dia = [{} for _ in dias]
    for dia, inicio, fim, turma in aulas:
        aulas_por_dia[dia][inicio] = {
            'turma': turma,
            'rowspan': indices[fim] - indices[inicio],
            'vazia': False,
        }
        for hora in horarios[indices[inicio] + 1:indices[fim]]:
            aulas_por_dia[dia][hora] = None

    def formatar(hora):
        horas, minutos = divmod(hora, 60)
        return f'{horas:02d}:{minutos:02d}' if minutos else f'{horas:02d}'

    grade_linhas = [
        {
            'horario': f'{formatar(inicio)}-{formatar(fim)}',
            'celulas': [dia.get(inicio, {'vazia': True}) for dia in aulas_por_dia],
        }
        for inicio, fim in zip(horarios, horarios[1:])
    ]

    return dias, grade_linhas


@login_required
def resumo_da_grade(request):
    aluno = obter_aluno(request)
    grade = Grade.objects.filter(aluno=aluno).last()
    turmas = (
        grade.turmas.select_related('disciplina', 'professor') 
        if grade else []
    )

    form = BuscaDisciplinaForm(request.GET)

    if grade and form.is_valid() and form.cleaned_data['busca']:
        turmas = turmas.filter(
            disciplina__nome__icontains=form.cleaned_data['busca']
        )

    cursadas = set(aluno.disciplinas_cursadas.all())
    total_creditos = 0

    turmas_lista = list(turmas)

    for t in turmas_lista:
        pre = set(t.disciplina.pre_requisitos.all())
        t.pendente = not pre.issubset(cursadas)
        total_creditos += t.disciplina.creditos or 0

    dias, grade_linhas = montar_grade_semanal(turmas_lista)

    return render(request, 'resumo_da_grade.html', {
        'form': form,
        'turmas': turmas,
        'total_creditos': total_creditos,
        'dias': dias,
        'grade_linhas': grade_linhas,
    })

ELETIVAS_POR_GRADE = 6

@login_required
def eletiva(request):
    aluno = obter_aluno(request)

    preferencias = RotinaPreferencias.objects.filter(
        aluno=aluno
    ).first()

    if not preferencias or not all([
        preferencias.turno,
        preferencias.modalidade,
        preferencias.distribuicao_aulas,
        preferencias.janelas,
        preferencias.carga_disciplinas,
    ]):
        return redirect('/questionario/')

    form = EletivasForm(request.GET)
    busca = ''
    filtro = 'todas'
    if form.is_valid():
        busca = form.cleaned_data['busca']
        if form.cleaned_data['filtro'] != '':
            filtro = form.cleaned_data['filtro']

    # As mesmas grades da tela Grades sugeridas; para cada uma, as eletivas que cabem nela.
    grades = gerar_grades(aluno, preferencias)
    sugestoes_por_grade = sugerir_para_grades(aluno, preferencias, grades)

    lista_de_grades = []
    for indice in range(len(grades)):
        lista = []
        mostradas = []
        for sugestao in sugestoes_por_grade[indice]:
            turma = sugestao['turma']

            # Uma turma por disciplina (a mais bem colocada) e no máximo ELETIVAS_POR_GRADE.
            if turma.disciplina_id in mostradas or len(lista) >= ELETIVAS_POR_GRADE:
                continue

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
                mostradas.append(turma.disciplina_id)
                lista.append({
                    'turma': turma,
                    'etiqueta': etiqueta,
                    'grupos': ', '.join(sugestao['grupos']),
                })

        lista_de_grades.append({
            'titulo': f'Grade sugerida {indice + 1}',
            'turmas': grades[indice]['turmas'],
            'eletivas': lista,
        })

    return render(request, "eletivas.html", {
        'grades': lista_de_grades,
        'busca': busca,
        'filtro': filtro,
        'filtros': FILTROS_ELETIVAS,
    })

@login_required
def detalhes_eletiva(request, codigo):

    codigo = codigo.upper()

    # Verifica se o código é válido
    if not codigo.isalnum():
        return render(request, "detalhes_eletiva.html", {
            "erro": "Código de disciplina inválido."
        })

    # Monta o endereço da página oficial da PUC
    url = f"https://www.puc-rio.br/ferramentas/ementas/ementa.aspx?cd={codigo}"

    try:
        requisicao = Request(
            url,
            headers={"User-Agent": "Mozilla/5.0"}
        )

        resposta = urlopen(requisicao, timeout=15)

        html = resposta.read().decode("cp1252", errors="replace")

    except (HTTPError, URLError, TimeoutError):
        return render(request, "detalhes_eletiva.html", {
            "erro": "Não foi possível acessar a página de ementas da PUC."
        })

    # Extrai as informações da disciplina
    extrator = ExtratorEmenta()
    extrator.feed(html)

    dados = extrator.dados

    # Verifica se a PUC encontrou a disciplina
    if not dados.get("codigo"):
        return render(request, "detalhes_eletiva.html", {
            "erro": "Não encontramos a ementa dessa disciplina na PUC."
        })

    return render(request, "detalhes_eletiva.html", {
        "disciplina": dados
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

@login_required
def questionario_modalidade(request):
    aluno = obter_aluno(request)
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

@login_required
def questionario_distribuicao(request):
    aluno = obter_aluno(request)
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

@login_required
def questionario_janelas(request):
    aluno = obter_aluno(request)
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

@login_required
def questionario_carga(request):
    aluno = obter_aluno(request)
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
    aluno = obter_aluno(request)

    preferencias = RotinaPreferencias.objects.filter(
        aluno=aluno
    ).first()

    if not preferencias or not all([
        preferencias.turno,
        preferencias.modalidade,
        preferencias.distribuicao_aulas,
        preferencias.janelas,
        preferencias.carga_disciplinas,
    ]):
        return redirect('/questionario/')

    grades = gerar_grades(aluno, preferencias)

    opcoes = [
        {
            'numero': str(indice),
            'titulo': f'Grade sugerida {indice}',
            'turmas': grade['turmas'],
            'pontuacao': grade['pontuacao'],
        }
        for indice, grade in enumerate(grades, start=1)
    ]

    if request.method == 'POST':
        form = UsarGradeForm(request.POST)

        if form.is_valid():
            numero = int(form.cleaned_data['opcao'])

            if 1 <= numero <= len(opcoes):
                opcao = opcoes[numero - 1]

                with transaction.atomic():
                    grade = Grade.objects.create(
                        aluno=aluno,
                        descricao=opcao['titulo']
                    )
                    grade.turmas.set(
                        turma.id for turma in opcao['turmas']
                    )

                return redirect('/resumodagrade/')

    for opcao in opcoes:
        opcao['dias'], opcao['grade_linhas'] = montar_grade_semanal(opcao['turmas'])
        opcao['total_creditos'] = sum(
            turma.disciplina.creditos or 0 for turma in opcao['turmas']
        )

    return render(request, 'grades-sugeridas.html', {
        'opcoes': opcoes,
    })


TAMANHO_MAXIMO_ESPELHO = 5 * 1024 * 1024  # 5 MB (PDF)
TAMANHO_MAXIMO_IMAGEM = 8 * 1024 * 1024   # 8 MB (print da tela, lido por OCR)
MAXIMO_DE_ARQUIVOS = 6                    # o OCR leva uns 10 s por imagem

NOMES_DAS_SITUACOES = {
    'cursada': 'Cursada',
    'em_andamento': 'Em andamento',
    'pode_cursar': 'Pode cursar de novo',
}


CHAVE_LEITURA_OCR = 'espelho_lido_por_ocr'


def ler_arquivo_enviado(arquivos):
    """Um PDF com texto: leitura direta. PDF sem texto ou imagens (um ou vários prints,
    em ordem): OCR. Devolve (dados, lido_por_ocr) ou levanta EspelhoInvalido com uma
    mensagem amigável."""
    if len(arquivos) == 1 and not eh_imagem(arquivos[0].name):
        try:
            return ler_espelho(arquivos[0]), False
        except EspelhoSemTexto:
            pass
    try:
        return ler_espelho_por_ocr(arquivos), True
    except OcrIndisponivel:
        # OCR não instalado (Python 3.13+ ou requirements não instalados): mensagem própria,
        # que manda enviar o PDF, em vez do "não conseguimos ler" de uma leitura que falhou
        raise EspelhoInvalido(MENSAGEM_SEM_OCR)


def importar_espelho_enviado(request, aluno, arquivos):
    """Lê o(s) arquivo(s) enviado(s). Nada fica salvo no servidor: só os dados lidos.
    Devolve (situacao, mensagem), com situacao 'salvo', 'conferir' (leitura por OCR,
    guardada na sessão até o aluno confirmar) ou 'erro'."""
    if not isinstance(arquivos, (list, tuple)):
        arquivos = [arquivos]
    if len(arquivos) > MAXIMO_DE_ARQUIVOS:
        return 'erro', f'Envie no máximo {MAXIMO_DE_ARQUIVOS} arquivos de uma vez.'
    for arquivo in arquivos:
        if eh_imagem(arquivo.name):
            if arquivo.size > TAMANHO_MAXIMO_IMAGEM:
                return 'erro', 'A imagem tem mais de 8 MB. Envie um print menor ou o PDF do SAU.'
        elif arquivo.name.lower().endswith('.pdf'):
            if arquivo.size > TAMANHO_MAXIMO_ESPELHO:
                return 'erro', 'O arquivo tem mais de 5 MB. Envie o PDF do espelho baixado do SAU.'
            if len(arquivos) > 1:
                return 'erro', 'Para enviar vários arquivos, use só prints (PNG ou JPG). O PDF vai sozinho.'
        else:
            return 'erro', 'Envie o espelho em PDF, PNG ou JPG.'

    try:
        dados, lido_por_ocr = ler_arquivo_enviado(arquivos)
    except (EspelhoInvalido, EspelhoSemTexto) as erro:
        return 'erro', str(erro)
    except Exception:
        return 'erro', 'Não conseguimos ler este PDF. Envie o PDF original baixado do SAU.'

    if lido_por_ocr:
        request.session[CHAVE_LEITURA_OCR] = {'aluno': aluno.id, 'dados': dados}
        return 'conferir', 'Lemos o arquivo por OCR: confira as disciplinas antes de salvar.'

    reconhecido = salvar_espelho(aluno, dados)
    mensagem = f"Histórico importado: {len(dados['disciplinas'])} disciplinas."
    if not reconhecido:
        mensagem += ' Confirme seu curso no seu perfil.'
    return 'salvo', mensagem


def leitura_ocr_pendente(request, aluno):
    """A leitura por OCR que espera conferência, só se for deste aluno."""
    pendente = request.session.get(CHAVE_LEITURA_OCR)
    if pendente and pendente.get('aluno') != aluno.id:
        request.session.pop(CHAVE_LEITURA_OCR)
        return None
    return pendente


def formatar_periodo(periodo):
    """'20261' -> '2026.1'"""
    if len(periodo) == 5 and periodo.isdigit():
        return periodo[:4] + '.' + periodo[4]
    return periodo


@login_required
def perfil(request):
    aluno = obter_aluno(request)

    if request.method == 'POST':
        acao = request.POST.get('acao')

        if acao == 'enviar_espelho':
            arquivos = request.FILES.getlist('espelho')
            if not arquivos:
                messages.error(request, 'Escolha o arquivo do espelho para enviar.')
            else:
                situacao, mensagem = importar_espelho_enviado(request, aluno, arquivos)
                if situacao == 'salvo':
                    messages.success(request, mensagem)
                    request.session['acabou_de_importar_espelho'] = True
                elif situacao == 'conferir':
                    messages.info(request, mensagem)
                else:
                    messages.error(request, mensagem)

        elif acao == 'confirmar_ocr':
            pendente = leitura_ocr_pendente(request, aluno)
            if pendente:
                request.session.pop(CHAVE_LEITURA_OCR)
                reconhecido = salvar_espelho(aluno, pendente['dados'])
                mensagem = f"Histórico importado: {len(pendente['dados']['disciplinas'])} disciplinas."
                if not reconhecido:
                    mensagem += ' Confirme seu curso abaixo.'
                messages.success(request, mensagem)
                request.session['acabou_de_importar_espelho'] = True

        elif acao == 'descartar_ocr':
            request.session.pop(CHAVE_LEITURA_OCR, None)
            messages.info(request, 'Leitura descartada. Envie outro arquivo.')

        elif acao == 'confirmar_curso':
            curriculo = Curriculo.objects.filter(id=request.POST.get('curriculo') or 0).first()
            if curriculo is None or not aluno.curso_sigla:
                messages.error(request, 'Escolha um curso da lista.')
            elif confirmar_curso(aluno, curriculo):
                messages.success(request, f'Curso confirmado: {curriculo}.')
            else:
                messages.error(request, 'O curso desta sigla já foi definido pela administração do site.')

        elif acao == 'remover_historico':
            if request.POST.get('confirmo') == 'sim':
                remover_historico(aluno)
                messages.success(request, 'Seu histórico foi removido.')
            else:
                messages.error(request, 'Marque a confirmação para remover o histórico.')

        elif acao in ('adicionar_disciplina', 'remover_disciplina', 'trocar_situacao', 'conta_como'):
            corrigir_historico(request, aluno, acao)
            resposta = redirect('perfil')
            resposta['Location'] += '#historico'      # volta para a lista que estava sendo corrigida
            return resposta

        return redirect('perfil')

    pendente = leitura_ocr_pendente(request, aluno)
    if pendente:
        # Prévia da leitura por OCR com a mesma cara do perfil: grava dentro de uma
        # transação, monta a página e desfaz tudo. Só fica salvo em "Confirmar e salvar".
        dados = pendente['dados']
        contagem = dados.get('ocr', {})
        with transaction.atomic():
            salvar_espelho(aluno, dados)
            # as linhas foram criadas na ordem da leitura: o id de cada uma leva à posição
            # dela na lista da sessão, que é o que as correções à mão usam
            ids = aluno.historico.order_by('id').values_list('id', flat=True)
            chaves = {id_linha: posicao for posicao, id_linha in enumerate(ids)}
            # o que conferir em cada linha: o código (letra perdida) ou o período (print cortado)
            para_conferir = {
                i: 'o código' if d.get('confira') else 'o período'
                for i, d in enumerate(dados['disciplinas']) if d.get('confira') or d.get('confira_periodo')
            }
            contexto = contexto_do_perfil(request, aluno, chaves, para_conferir)
            contexto['conferencia'] = {
                'contagem': contagem,
                'pode_ter_faltado': not dados.get('corrigido_a_mao') and (
                    contagem.get('codigos') != contagem.get('situacoes')
                    or any(not d['situacao'] or not d['periodo'] for d in dados['disciplinas'])
                ),
                'total': len(dados['disciplinas']),
            }
            contexto['mostrar_link_grades'] = False
            resposta = render(request, 'perfil.html', contexto)
            transaction.set_rollback(True)
        aluno.refresh_from_db()
        return resposta

    return render(request, 'perfil.html', contexto_do_perfil(request, aluno))


def contexto_do_perfil(request, aluno, chaves=None, para_conferir=None):
    """Dados da página do perfil. Na conferência do OCR, 'chaves' leva o id de cada linha
    à posição dela na leitura da sessão e 'para_conferir' diz o que conferir em cada linha incerta."""
    curriculo = curriculo_do_aluno(aluno)
    pendentes, conta_como = ocupacao_das_vagas(aluno, curriculo)
    vagas = vagas_do_curriculo(curriculo) if curriculo else []
    codigos_das_vagas = {codigo for codigo, _ in vagas}
    itens_do_curriculo = set(curriculo.itens.filter(eh_grupo=False).values_list('codigo', flat=True)) if curriculo else set()

    def pode_contar_como(linha):
        """Mostra o "Conta como" para optativas: quem já ocupa uma vaga, ou quem não é item
        do currículo e não tem equivalência do SAU para um item (como MAT4181 -> MAT4161)."""
        if not vagas:
            return False
        if linha.id in conta_como:
            return True
        return linha.codigo not in itens_do_curriculo and (
            not linha.grupo or linha.grupo == SEM_VAGA or linha.grupo in codigos_das_vagas
        )

    periodos = []
    for linha in aluno.historico.all():
        if not periodos or periodos[-1]['periodo'] != linha.periodo:
            periodos.append({'periodo': linha.periodo, 'nome': formatar_periodo(linha.periodo), 'linhas': []})
        if linha.situacao:
            situacao = classificar_situacao(linha.situacao)
            nome_situacao = NOMES_DAS_SITUACOES[situacao]
        else:
            situacao, nome_situacao = 'nao-lida', 'Não lida'   # só acontece na leitura por OCR
        chave = chaves[linha.id] if chaves is not None else linha.id
        periodos[-1]['linhas'].append({
            'linha': linha,
            'classe': situacao,
            'situacao': nome_situacao,
            'chave': chave,
            'confira': (para_conferir or {}).get(chave, ''),
            'conta_como': conta_como.get(linha.id, ''),
            'pode_contar_como': pode_contar_como(linha),
        })

    sugestoes = deduzir_curriculos(aluno) if aluno.precisa_confirmar_curso else []

    return {
        'aluno': aluno,
        'curriculo': curriculo,
        'periodos': periodos,
        'pendentes': pendentes[:10],
        'vagas': vagas,
        'sugestoes': sugestoes,
        'sugerido': sugestoes[0]['curriculo'] if sugestoes else None,
        'curriculos': Curriculo.objects.all(),
        # o link para as grades aparece uma vez, logo depois de importar
        'mostrar_link_grades': request.session.pop('acabou_de_importar_espelho', False),
        # correções à mão: período sugerido para uma disciplina nova e situações possíveis
        'ultimo_periodo': max((p['periodo'] for p in periodos), default=''),
        'situacoes_da_correcao': SITUACOES_DA_CORRECAO.items(),
    }


def corrigir_historico(request, aluno, acao):
    """Correções à mão: adicionar, remover ou trocar a situação de uma disciplina.
    Na conferência do OCR mexem na leitura guardada na sessão (nada vai para o banco antes
    de "Confirmar e salvar"); no perfil já salvo mexem no histórico do banco."""
    pendente = leitura_ocr_pendente(request, aluno)
    try:
        if acao == 'adicionar_disciplina':
            d = disciplina_digitada(
                request.POST.get('codigo'), request.POST.get('situacao'), request.POST.get('periodo')
            )
            if pendente:
                linhas = pendente['dados']['disciplinas']
                if any(x['periodo'] == d['periodo'] and x['codigo'] == d['codigo'] for x in linhas):
                    raise CorrecaoInvalida(f"{d['codigo']} já está na lista em {d['periodo']}.")
                linhas.append(d)
            else:
                adicionar_ao_historico(aluno, d)
            mensagem = f"{d['codigo']} adicionada."
        else:
            chave = request.POST.get('linha', '')
            situacao = request.POST.get('situacao')
            if acao == 'trocar_situacao' and situacao not in SITUACOES_DA_CORRECAO:
                raise CorrecaoInvalida('Escolha uma situação da lista.')
            if acao == 'conta_como':
                # "Conta como": uma vaga de optativa do currículo, ou "nenhum" (SEM_VAGA)
                if pendente:
                    d = pendente['dados']
                    curriculo = curriculo_das_siglas(d['curso'], d['habilitacao'], d['enfase'])
                else:
                    curriculo = curriculo_do_aluno(aluno)
                escolhido = (request.POST.get('grupo') or '').strip().upper()
                validos = {codigo for codigo, _ in vagas_do_curriculo(curriculo)} if curriculo else set()
                if escolhido and escolhido not in validos:
                    raise CorrecaoInvalida('Escolha uma vaga de optativa do seu currículo.')
                grupo = escolhido or SEM_VAGA
            if pendente:
                linhas = pendente['dados']['disciplinas']
                if not chave.isdigit() or int(chave) >= len(linhas):
                    raise CorrecaoInvalida('Não encontramos essa disciplina na lista.')
                linha = linhas[int(chave)]
                if acao == 'remover_disciplina':
                    linhas.remove(linha)
                elif acao == 'conta_como':
                    linha['grupo'] = grupo
                else:
                    linha['situacao'] = situacao
                codigo = linha['codigo']
            else:
                linha = aluno.historico.filter(id=int(chave) if chave.isdigit() else 0).first()
                if linha is None:
                    raise CorrecaoInvalida('Não encontramos essa disciplina no seu histórico.')
                codigo = linha.codigo
                if acao == 'remover_disciplina':
                    remover_do_historico(aluno, linha.id)
                elif acao == 'conta_como':
                    trocar_vaga_no_historico(aluno, linha.id, grupo)
                else:
                    trocar_situacao_no_historico(aluno, linha.id, situacao)
            if acao == 'remover_disciplina':
                mensagem = f'{codigo} removida.'
            elif acao == 'conta_como':
                mensagem = f'{codigo} agora conta como {escolhido}.' if escolhido else f'{codigo} não ocupa vaga de optativa.'
            else:
                mensagem = f'Situação de {codigo} trocada.'
    except CorrecaoInvalida as erro:
        messages.error(request, str(erro))
        return
    if pendente:
        pendente['dados']['corrigido_a_mao'] = True
        request.session[CHAVE_LEITURA_OCR] = pendente
    messages.success(request, mensagem)
