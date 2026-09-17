# Grade Ideal PUC

Crie um protótipo funcional em React/Tailwind para o projeto grade.puc seguindo estritamente a especificação técnica em Markdown e as imagens em anexo como referência de layout.                                                                                                                                    # Product Requirement Document (PRD) & Prompt — grade.puc

## 1. Contexto e Objetivo do Projeto

O **grade.puc** é um simulador interativo de grade horária feito para alunos da PUC-Rio. O objetivo do sistema é facilitar o planejamento de disciplinas antes da matrícula oficial, sugerindo grades otimizadas com base nas preferências do usuário, calculando conflitos de horários e exibindo o pré-requisito das disciplinas.

---

## 2. Design System & Identidade Visual

### Paleta de Cores (Cores Terrosas e Neutras Foscas)

- **Fundo da Página**: `#F1ECE4`

- **Superfície (Cards, Painéis, Modal)**: `#FBF8F3`

- **Tinta (Texto Principal)**: `#2A211B`

- **Tinta Secundária (Texto de Apoio)**: `#6E5F52`

- **Terracota (Ação / Botão Primário)**: `#9C4526`

- **Musgo (Disponível / Vaga Aberta)**: `#5F6B3F`

- **Ocre (Alerta / Poucas Vagas / Sugestão)**: `#7A5A1A`

- **Barro Queimado (Bloqueada / Pré-requisito Pendente)**: `#8B3A30`

### Tipografia

- **Títulos e Interface**: Font family 'Fredoka', sans-serif (terminações arredondadas).

- **Texto Corrido**: Font family 'Nunito', sans-serif.

- **Dados Técnicos (Códigos, Horários, Salas, Créditos)**: Font family 'IBM Plex Mono', monospace.

### Regras Visuais

- Botões e cards devem utilizar bordas levemente arredondadas (`rounded-xl` ou `rounded-2xl`).

- O contraste de cor deve respeitar acessibilidade (WCAG AA). Textos sobre botões coloridos devem manter legibilidade máxima.

- A distinção de status nunca deve depender apenas da cor; sempre inclua um rótulo de texto explicativo (ex: "Concluída", "Disponível", "Bloqueada").

---

## 3. Modelo de Dados (Estado Local / Mock Data)

Crie um estado local em TypeScript/React simulando os seguintes objetos de dados:

### Aluno

- `matricula`: string

- `nome`: string

- `curso`: string

- `historicoDisciplinas`: string[] (códigos das disciplinas já concluídas)

### Disciplina

- `codigo`: string (ex: "MAT1101")

- `nome`: string (ex: "Cálculo I")

- `creditos`: number

- `preRequisitos`: string[]

- `trilha`: string (ex: "Fundamentos de Matemática", "Economia", "Ciência de Dados")

- `categoria`: "obrigatoria" | "eletiva"

### Turma

- `id`: string

- `codigoDisciplina`: string

- `professor`: { nome: string, avaliacao: number }

- `diasHorarios`: { dia: "Seg"|"Ter"|"Qua"|"Qui"|"Sex", inicio: "08:00", fim: "10:00" }[]

- `vagasTotais`: number

- `vagasDisponiveis`: number

- `sala`: string

- `modalidade`: "presencial" | "online"

### RotinaPreferencias

- `turno`: "Manhã" | "Tarde" | "Noite" | "Sem preferência"

- `modalidadePref`: "presencial" | "online" | "ambas"

- `compromissosFixos`: { dia: string, inicio: string, fim: string, descricao: string }[]

---

## 4. Fluxo de Navegação e Arquitetura de Telas

Implemente um roteamento flexível entre as seguintes 7 telas:

1. **Tela 1: Login (`/login`)**

2. **Tela 2: Questionário de Preferências (`/questionario`)**

3. **Tela 3: Grades Sugeridas (`/grades-sugeridas`)**

4. **Tela 4: Painel Principal / Editor de Grade (`/minha-grade`)**

5. **Tela 5: Resumo da Grade Confirmada (`/resumo`)**

6. **Tela 6: Eletivas Sugeridas (`/eletivas`)**

7. **Tela 7: Fluxograma de Pré-requisitos (`/fluxograma`)**

---

## 5. Especificação Detalhada das Telas

### Tela 1: Login

- Layout Split Screen: Lado esquerdo com imagem institucional e texto "Seu futuro, mais organizado." Lado direito com o formulário.

- Campos: "Usuário" (Matrícula) e "Email".

- Botões: "Log in" (Terracota), botão secundário "Entrar com Google" e link "Pular/Cadastre-se".

- Redirecionamento ao clicar em "Log in": Envia para o Questionário (`/questionario`).

### Tela 2: Questionário de Preferências

- Barra de progresso superior (ex: "2 de 7").

- Pergunta principal: "Qual é o seu turno preferido?".

- Opções com botões de seleção únicos (Radio cards): Manhã, Tarde, Noite, Sem preferência.

- Ações: Botão "Voltar", Botão "Próximo" (Terracota) e link secundário "Já respondi o questionário" (pula direto para `/minha-grade`).

### Tela 3: Grades Sugeridas

- Cabeçalho com o botão "Refazer questionário".

- Lista de 3 a 4 opções de grades geradas automaticamente em formato Accordion/Cards expansíveis:

  - **Opção 1**: "Equilíbrio entre teoria e prática"

  - **Opção 2**: "Mais aulas pela manhã"

  - **Opção 3**: "Com disciplinas eletivas"

  - **Opção 4**: "Menos dias na semana"

- Cada card exibe a carga horária em créditos (ex: "20 créditos"), a tabela de horários com os chips coloridos por matéria e o botão "Usar esta grade" (Verde Musgo / Terracota).

- Ao clicar em "Usar esta grade", carrega essa opção no Painel Principal (`/minha-grade`).

### Tela 4: Painel Principal (Editor de Grade)

- Topbar de navegação com links para: *Minha grade*, *Grades sugeridas*, *Questionário*, *Ajuda*.

- Título da grade editável (ex: "Grade 1") + Ações "Limpar grade" e "Salvar grade" (Terracota).

- **Grid da Grade Semanal**:

  - Tabela com colunas (Horários, Segunda, Terça, Quarta, Quinta, Sexta) e linhas de horários de 08:00 às 22:00.

  - Células onde disciplinas adicionadas aparecem como blocos coloridos contendo: Nome da disciplina, Horário, Sala (ex: `LDS - 101`).

- **Barra Lateral Direita (Catálogo de Disciplinas)**:

  - Campo de busca funcional "Buscar disciplina...".

  - Lista de disciplinas com botão "+" para adicionar à grade.

  - Link/Botão no rodape lateral: "Ver todas as disciplinas".

- **Banner/Atalhos Inferiores**:

  - Card 1: "Ver eletivas" (Navega para `/eletivas`).

  - Card 2: "Ver fluxograma" (Navega para `/fluxograma`).

### Tela 5: Resumo da Grade (Grade Confirmada)

- Título: "Resumo da grade (Grade Confirmada)".

- Exibe uma visão em tabela limpa e compacta da grade semanal.

- Métricas no rodapé: "Quantidade de disciplinas: X" | "Total de créditos: Y".

- Botões de Ação:

  - "Exportar Calendário" (Simular download/integração).

  - "Editar Grade" (Volta para `/minha-grade`).

  - "Portal SAU PUC" (Link externo/simulado com aviso informando que a matrícula oficial deve ser feita no portal da universidade).

### Tela 6: Eletivas Sugeridas

- Campo de busca e filtro de categorias.

- Cards em grid com disciplinas recomendadas.

- Cada card contém:

  - Tag de destaque (ex: "Recomendado", "Popular", "Alta demanda").

  - Nome da matéria, código, descrição curta.

  - Detalhes técnicos (fonte `IBM Plex Mono`): Créditos, Horário sugerido, Professor, Vagas disponíveis.

  - Botão "Ver disciplina ->".

- Footer do card com aviso de personalização e botão "Editar preferências".

### Tela 7: Fluxograma de Pré-requisitos

- Seletor de Curso (Dropdown, ex: "Engenharia de Produção").

- Organização em colunas representando Trilhas do conhecimento (ex: *Fundamentos de Matemática*, *Economia*, *Ciência de Dados*).

- Cards de disciplina empilhados na vertical com setas conectoras de pré-requisitos:

  - **Verde (Concluída)**: Ícone de Check ✓ (ex: Cálculo I).

  - **Ocre (Disponível)**: Ícone de Play ▶ (ex: Cálculo II).

  - **Vermelho/Barro Queimado (Bloqueada)**: Ícone de Cadeado 🔒 (ex: Cálculo III).

- Painel lateral fixo explicando a legenda dos status.

- Botão no rodapé: "← Voltar para minha grade".

---

## 6. Regras de Negócio Importantes

1. **Conflito de Horário**: Se o usuário tentar adicionar uma disciplina no mesmo dia/horário de outra já presente na grade, o sistema deve emitir um aviso/toast e impedir a sobreposição.

2. **Alertas de Pré-requisito**: Ao visualizar matérias bloqueadas no fluxograma, mostrar quais matérias precisam ser concluídas primeiro.

3. **Responsividade**: Garantir layout fluido para telas desktop e notebooks.

This project was built with [Lovable](https://lovable.dev).

## Build with Lovable

Continue developing this project in the [Lovable editor](https://lovable.dev/projects/2f52b918-cb4e-4707-9c5f-7043af3f6e3f).

- **Ship faster**: describe what you want to build and Lovable handles the code.
- **Stay in sync**: every change made in Lovable is committed straight to this repository.
- **Full ownership**: this code is yours. Push to `main` on GitHub and your changes sync back into Lovable, ready for your next prompt.

## Development

Prefer working locally? You need Node.js and npm — [install with nvm](https://github.com/nvm-sh/nvm#installing-and-updating).

```sh
git clone <this-repository-url>
cd <repository-name>
npm i
npm run dev
```
