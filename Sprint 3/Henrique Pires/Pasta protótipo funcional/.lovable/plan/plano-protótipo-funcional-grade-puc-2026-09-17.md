# Plano — Protótipo funcional grade.puc

## Resultado
Construir um protótipo navegável em React/Tailwind com as sete telas do PRD, dados locais tipados e identidade visual fiel às referências anexadas.

## Telas e navegação
- Criar rotas para Login, Questionário, Grades Sugeridas, Minha Grade, Resumo, Eletivas e Fluxograma.
- Manter a tela inicial em `/` redirecionando para `/login`.
- Criar cabeçalho e rodapé compartilhados nas telas internas, com navegação funcional e adaptação para notebooks.

## Experiência funcional
- Login direciona ao questionário.
- Questionário permite escolher turno e avançar para as sugestões; o atalho abre diretamente Minha Grade.
- Grades sugeridas terão quatro opções expansíveis; “Usar esta grade” carrega a opção escolhida no editor.
- Editor terá busca de disciplinas, adição e remoção, título editável, limpeza, salvamento e bloqueio de conflitos com aviso visível.
- Resumo calculará disciplinas e créditos, simulará exportação e exibirá aviso sobre matrícula oficial.
- Eletivas terão busca e filtros funcionais.
- Fluxograma mostrará trilhas, estados e pré-requisitos pendentes ao selecionar uma matéria bloqueada.

## Design e conteúdo
- Aplicar exatamente a paleta terrosa especificada com tokens semânticos, usando Fredoka, Nunito e IBM Plex Mono.
- Usar o logo enviado na interface e criar a versão quadrada do favicon.
- Reproduzir a composição das referências: superfícies claras, bordas suaves, tabelas densas, blocos coloridos e hierarquia institucional.
- Garantir que status sempre tenham ícone e texto, não apenas cor.

## Estrutura técnica
- Definir os tipos e mock data do PRD em módulos reutilizáveis.
- Usar contexto React para compartilhar preferências e grade selecionada entre rotas.
- Criar componentes reutilizáveis para agenda semanal, cabeçalho, rodapé, cards de disciplina e mensagens.
- Adicionar metadados próprios em cada rota e validar compilação, navegação e interações principais no desktop e notebook.
