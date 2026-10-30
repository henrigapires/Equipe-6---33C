from django import forms
from .models import RotinaPreferencias

TURNOS = [
    ('manha', 'Manhã'),
    ('tarde', 'Tarde'),
    ('noite', 'Noite'),
    ('sem_preferencia', 'Sem preferência'),
]

MODALIDADES = [
    ('presencial', 'Presencial'),
    ('online', 'Online'),
    ('hibrido', 'Híbrido'),
]

DISTRIBUICOES = [
    ('equilibrado', 'Equilibrado pela semana'),
    ('dia_leve', 'Acumular para ter um dia mais leve'),
    ('dia_livre', 'Acumular para ter um dia livre'),
    ('tanto_faz', 'Tanto faz'),
]

JANELAS = [
    ('sem_janelas', 'Sem janelas'),
    ('janelas_curtas', 'Aceito janelas curtas'),
    ('tanto_faz', 'Tanto faz'),
]

CARGAS = [
    ('leve', 'Leve'),
    ('media', 'Média'),
    ('pesada', 'Pesada'),
]


FILTROS_ELETIVAS = [
    ('todas', 'Todas'),
    ('recomendado', 'Recomendado'),
    ('popular', 'Popular'),
    ('alta_demanda', 'Alta demanda'),
]


class EletivasForm(forms.Form):
    busca = forms.CharField(required=False, max_length=100)
    filtro = forms.ChoiceField(choices=FILTROS_ELETIVAS, required=False)


class TurnoForm(forms.ModelForm):
    turno = forms.ChoiceField(choices=TURNOS)

    class Meta:
        model = RotinaPreferencias
        fields = ['turno']

class ModalidadeForm(forms.ModelForm):
    modalidade = forms.ChoiceField(choices=MODALIDADES)

    class Meta:
        model = RotinaPreferencias
        fields = ['modalidade']

class DistribuicaoForm(forms.ModelForm):
    distribuicao_aulas = forms.ChoiceField(choices=DISTRIBUICOES)

    class Meta:
        model = RotinaPreferencias
        fields = ['distribuicao_aulas']

class JanelasForm(forms.ModelForm):
    janelas = forms.ChoiceField(choices=JANELAS)

    class Meta:
        model = RotinaPreferencias
        fields = ['janelas']

class CargaForm(forms.ModelForm):
    carga_disciplinas = forms.ChoiceField(choices=CARGAS)

    class Meta:
        model = RotinaPreferencias
        fields = ['carga_disciplinas']

class TelaInicialForm(forms.Form):
    usuario = forms.CharField(
        label='Usuário',
        max_length=100,
        widget=forms.TextInput(attrs={
            'placeholder': 'Digite seu usuário',
            'class': 'campo-input',
            'id': 'usuario',
        })
    )

    email = forms.EmailField(
        label='Email',
        widget=forms.EmailInput(attrs={
            'placeholder': 'Digite seu email',
            'class': 'campo-input',
            'id': 'email',
        })
    )
class BuscaDisciplinaForm(forms.Form):
    busca = forms.CharField(
        required=False,
        widget=forms.TextInput(attrs={'placeholder': 'Buscar disciplina...'}),
    )
    
class UsarGradeForm(forms.Form):
    OPCOES = [
        ('1', 'Opção 1'),
        ('2', 'Opção 2'),
        ('3', 'Opção 3'),
        ('4', 'Opção 4'),
    ]
    opcao = forms.ChoiceField(choices=OPCOES)
