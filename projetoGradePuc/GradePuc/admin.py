from django.contrib import admin
from .models import (
    Professor, Disciplina, Turma, Aluno, RotinaPreferencias, Grade, Pergunta,
    HistoricoDisciplina, Curriculo, DisciplinaCurriculo, LigacaoHabilitacao, DisciplinaDoGrupo,
)

admin.site.register(Professor)
admin.site.register(Disciplina)
admin.site.register(Turma)
admin.site.register(RotinaPreferencias)
admin.site.register(Grade)
admin.site.register(Pergunta)


class HistoricoInline(admin.TabularInline):
    """Histórico do espelho dentro da página do aluno (só leitura)."""
    model = HistoricoDisciplina
    fields = ('periodo', 'codigo', 'nome', 'turma', 'grau', 'situacao', 'tipo', 'grupo', 'creditos')
    readonly_fields = fields
    extra = 0
    can_delete = False

    def has_add_permission(self, request, obj=None):
        return False


@admin.register(Aluno)
class AlunoAdmin(admin.ModelAdmin):
    list_display = ('matricula', 'curso_sigla', 'habilitacao_sigla', 'enfase_sigla', 'espelho_importado_em')
    search_fields = ('matricula', 'matricula_espelho')
    inlines = [HistoricoInline]


@admin.register(HistoricoDisciplina)
class HistoricoDisciplinaAdmin(admin.ModelAdmin):
    list_display = ('aluno', 'periodo', 'codigo', 'nome', 'turma', 'grau', 'situacao', 'tipo', 'grupo', 'creditos', 'disciplina')
    list_filter = ('situacao', 'periodo', 'tipo')
    search_fields = ('codigo', 'aluno__matricula')


class DisciplinaCurriculoInline(admin.TabularInline):
    model = DisciplinaCurriculo
    extra = 0


@admin.register(Curriculo)
class CurriculoAdmin(admin.ModelAdmin):
    list_display = ('curso_nome', 'ano', 'enfase', 'importado_em')
    list_filter = ('curso_nome', 'ano')
    search_fields = ('curso_nome', 'enfase')
    inlines = [DisciplinaCurriculoInline]


@admin.register(DisciplinaDoGrupo)
class DisciplinaDoGrupoAdmin(admin.ModelAdmin):
    list_display = ('grupo', 'codigo', 'nome')
    search_fields = ('grupo', 'codigo', 'nome')


class SemLigacaoFilter(admin.SimpleListFilter):
    title = 'ligação'
    parameter_name = 'ligacao'

    def lookups(self, request, model_admin):
        return [('sem', 'Sem ligação'), ('com', 'Com currículo')]

    def queryset(self, request, queryset):
        if self.value() == 'sem':
            return queryset.filter(curriculo__isnull=True)
        if self.value() == 'com':
            return queryset.filter(curriculo__isnull=False)
        return queryset


@admin.register(LigacaoHabilitacao)
class LigacaoHabilitacaoAdmin(admin.ModelAdmin):
    list_display = ('curso_sigla', 'habilitacao_sigla', 'enfase_sigla', 'curriculo', 'origem', 'confirmado_por', 'atualizado_em')
    list_editable = ('curriculo',)
    list_filter = (SemLigacaoFilter, 'origem')
    search_fields = ('curso_sigla', 'habilitacao_sigla', 'enfase_sigla')

    def save_model(self, request, obj, form, change):
        # Quando o admin escolhe o currículo, a ligação passa a ser do admin:
        # a confirmação de um aluno não sobrescreve mais.
        if 'curriculo' in form.changed_data:
            obj.origem = 'admin'
        super().save_model(request, obj, form, change)
