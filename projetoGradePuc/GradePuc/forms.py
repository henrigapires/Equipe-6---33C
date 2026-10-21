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


class RotinaPreferenciasForm(forms.ModelForm):
    turno = forms.ChoiceField(choices=TURNOS)
    modalidade = forms.ChoiceField(choices=MODALIDADES)

    class Meta:
        model = RotinaPreferencias
        fields = ['turno', 'modalidade']