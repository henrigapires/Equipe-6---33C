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