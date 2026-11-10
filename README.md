# Equipe-6---33C

## Responsividade e API de pré-requisitos

As telas de pré-requisitos e de distribuição do questionário foram ajustadas para
layouts de desktop, tablet e celular, com breakpoints e larguras fluidas.

A tela de pré-requisitos consulta `GET /api/disciplinas/<id>/` quando uma disciplina
é selecionada. A resposta JSON contém código, nome e pré-requisitos. O endpoint usa
o banco de dados Django como fonte única de informação, evitando duplicar dados no
JavaScript.

**Escolha da API:** foi adotado um endpoint REST interno em Django, em vez de uma
API externa. O repositório não configura nem documenta uma API oficial da PUC-Rio
para esse catálogo; depender de um serviço não confirmado introduziria indisponibilidade,
credenciais e divergência de dados. O endpoint interno reutiliza os dados já mantidos
pela aplicação, não exige dependências novas e pode ser consumido por outras telas
ou clientes no futuro.

Para validar as telas e a integração, execute os testes Django no diretório
`projetoGradePuc` com `python manage.py test GradePuc`.
## Como rodar o projeto (espelho do histórico e currículos)

No diretório `projetoGradePuc`:

```
pip install -r requirements.txt
python manage.py migrate
python manage.py runserver
```

**Currículos dos cursos:** já vêm com o projeto. O `migrate` carrega
`GradePuc/dados/curriculos.json` (cursos de graduação da PUC-Rio, com as disciplinas
de cada período) quando o banco ainda não tem nenhum currículo, sem precisar de internet.
É o que aparece no "Confirme seu curso" do Meu perfil.

- `python manage.py importar_curriculos` serve só para **atualizar** os currículos a partir
  do site da PUC (baixa umas 150 páginas).
- Depois de atualizar, `python manage.py exportar_curriculos` regrava o
  `curriculos.json` para o resto do time receber pelo Git.
