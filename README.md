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

Para conferir que nenhuma grade sugerida (nem eletiva) fura um pré/co-requisito, com as
turmas reais do micro-horário:

```
python manage.py auditar_requisitos
```

Roda para cada aluno com espelho importado e para cada currículo com históricos inventados
(desfeitos no fim, nada fica gravado) e termina com "N turmas verificadas, 0 violações" ou a
lista do que faltou. O teste `tests_propriedade_requisitos` faz a mesma conferência para todos
os currículos no banco de teste (é o teste mais demorado da suíte, uns 6 minutos).

**Limitação conhecida (requisitos):** algumas disciplinas existem na PUC, mas a página de
ementa vem sem texto ("Disciplina sem ementa cadastrada", como ENG4418): sem descrição, sem
bibliografia e sem o quadro de requisitos. Para essas, não sabemos os pré/co-requisitos, e o
site as trata como **sem pré-requisito**. Elas ficam listadas em `sem_ementa` no
`requisitos.json`, junto com os códigos que nem existem na PUC.

**Equivalências (disciplinas que a PUC aceita uma no lugar da outra):** só as confirmadas.
Quem fez uma conta como tendo feito todas da classe, e uma grade nunca recebe duas da mesma.

- A lista confirmada fica em `GradePuc/requisitos.py` (`EQUIVALENCIAS_CONFIRMADAS`):
  Cálculo 1, Física II e Álgebra Linear I. Mais os pares do campo "Grupo" dos espelhos
  (ex.: MAT4181 com Grupo MAT4161).
- INF1037, INF1007, INF1026 e INF1620 nunca são equivalentes (`NUNCA_EQUIVALENTES`): são
  alternativas de co-requisito, não a mesma disciplina.
- `python manage.py sugerir_equivalencias --cache cache_ementas` gera
  `revisao/equivalencias_sugeridas.txt`, só para revisão: o site não lê esse arquivo.
  Para ativar uma classe, revise e copie para `EQUIVALENCIAS_CONFIRMADAS`.

**Grades sugeridas (como são montadas):** partem da grade que a PUC recomenda (periodização
do currículo do aluno), guiadas pelo histórico do espelho.

- **Período atual** = o período do currículo da maioria das disciplinas em andamento (EA).
  **Período de referência** = atual + 1 (sem nada em andamento: o menor período com
  pendência). A tela mostra os dois.
- Cada disciplina pendente que o aluno pode cursar (pré/co-requisitos, vagas, turno,
  modalidade, horário) é **atrasada** (período ≤ atual), **do período** (= referência) ou
  **adiantada** (> referência), e ganha uma importância: 10 / 6 / 3 + 4 por disciplina
  pendente que depende dela. Gargalos (Cálculo, Física...) pesam mais; atraso não é
  prioridade absoluta.
- As quatro opções seguem estratégias diferentes: "Segue a grade da PUC", "Em dia +
  recupera atrasada", "Só o período, outra combinação" e "Variação: adianta ..." (sem teto
  de adiantadas). Quando uma não existe, entra uma variação com outras turmas. A escolha das
  turmas é a de sempre (`pontuar_grade`, sem conflito). Sem disciplinas suficientes, vem
  uma grade menor com aviso.
