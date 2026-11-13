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

**Espelho do histórico (Meu perfil e cadastro):**

- **PDF do espelho** (no SAU, Imprimir → Salvar como PDF): funciona em qualquer versão do Python.
- **Prints da tela** (PNG/JPG) e PDF escaneado: usam OCR (`rapidocr-onnxruntime`), que só
  instala com **Python 3.12 ou anterior**. Em Python 3.13+ o `pip install -r requirements.txt`
  pula o OCR; o site continua funcionando e avisa, ao lado do campo, para enviar o PDF.
- Vários prints podem ser enviados de uma vez, em qualquer ordem. O motivo de uma leitura que
  falhou (OCR ausente, quantas caixas de texto, se achou o cabeçalho, quantas linhas) aparece
  no log do servidor, sem dados do aluno.

**Pré-requisitos e co-requisitos:** também vêm com o projeto. O `migrate` carrega
`GradePuc/dados/requisitos.json` (lido das ementas no site da PUC) quando o banco ainda não
tem nenhum requisito. Cada requisito pode ter alternativas (OU), e cada alternativa pode
exigir mais de uma disciplina (E); o nivelamento ("MATEMÁTICA (nivel 3)") não bloqueia.

Para atualizar a partir do site da PUC:

```
python manage.py importar_requisitos --cache cache_ementas
```

- Começa pelos códigos das disciplinas, dos currículos e das optativas e segue a rede de
  requisitos até fechar. Faz no máximo ~3 requisições por segundo (leva cerca de uma hora).
- Pode ser interrompido e rodado de novo: por padrão só baixa o que falta
  (`--so-faltantes`); `--refazer` baixa tudo de novo. Com `--cache`, o HTML fica guardado
  em `cache_ementas/` (fora do Git).
- No fim regrava `requisitos.json` (só requisitos, nada de aluno) e lista os códigos sem
  ementa e os que deram erro. Commite o `requisitos.json` para o time receber.
- `python manage.py importar_requisitos --so-exportar` só regrava o arquivo com o que está no banco.

**Limitação conhecida (requisitos):** algumas disciplinas existem na PUC, mas a página de
ementa vem sem texto ("Disciplina sem ementa cadastrada", como ENG4418): sem descrição, sem
bibliografia e sem o quadro de requisitos. Para essas, não sabemos os pré/co-requisitos, e o
site as trata como **sem pré-requisito**. Elas ficam listadas em `sem_ementa` no
`requisitos.json`, junto com os códigos que nem existem na PUC.
