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