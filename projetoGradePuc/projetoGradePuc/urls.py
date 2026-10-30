"""
URL configuration for projetoGradePuc project.

The `urlpatterns` list routes URLs to views. For more information please see:
    https://docs.djangoproject.com/en/6.1/topics/http/urls/
Examples:
Function views
    1. Add an import:  from my_app import views
    2. Add a URL to urlpatterns:  path('', views.home, name='home')
Class-based views
    1. Add an import:  from other_app.views import Home
    2. Add a URL to urlpatterns:  path('', Home.as_view(), name='home')
Including another URLconf
    1. Import the include() function: from django.urls import include, path
    2. Add a URL to urlpatterns:  path('blog/', include('blog.urls'))
"""
from django.contrib import admin
from django.urls import path
from GradePuc.views import *

urlpatterns = [
    path('admin/', admin.site.urls),
    path('', home, name='home'),
    path('ajuda/', ajuda),
    path('pre-requisitos/', pre_requisitos),
    path('api/disciplinas/<int:disciplina_id>/', api_disciplina, name='api_disciplina'),
    path('resumodagrade/', resumo_da_grade),
    path('eletivas/', eletiva),
    path('questionario/', questionario, name='questionario'),
    path('questionario/modalidade/', questionario_modalidade, name='questionario_modalidade'),
    path('questionario/distribuicao/', questionario_distribuicao, name='questionario_distribuicao'),
    path('questionario/janelas/', questionario_janelas, name='questionario_janelas'),
    path('questionario/carga/', questionario_carga, name='questionario_carga'),
    path('grades-sugeridas/', gradessugeridas),
]