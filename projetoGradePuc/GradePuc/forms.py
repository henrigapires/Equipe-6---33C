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


FILTROS_ELETIVAS = [
    ('todas', 'Todas'),
    ('recomendado', 'Recomendado'),
    ('popular', 'Popular'),
    ('alta_demanda', 'Alta demanda'),
]


class EletivasForm(forms.Form):
    busca = forms.CharField(required=False, max_length=100)
    filtro = forms.ChoiceField(choices=FILTROS_ELETIVAS, required=False)


class RotinaPreferenciasForm(forms.ModelForm):
    turno = forms.ChoiceField(choices=TURNOS)
    modalidade = forms.ChoiceField(choices=MODALIDADES)

    class Meta:
        model = RotinaPreferencias
        fields = ['turno', 'modalidade']

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
