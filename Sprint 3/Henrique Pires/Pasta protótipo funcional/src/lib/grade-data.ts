export type Dia = "Seg" | "Ter" | "Qua" | "Qui" | "Sex";
export type Disciplina = { codigo:string; nome:string; creditos:number; preRequisitos:string[]; trilha:string; categoria:"obrigatoria"|"eletiva"; cor:"moss"|"ochre"|"terracotta"|"clay"|"lilac"; descricao?:string };
export type Turma = { id:string; codigoDisciplina:string; professor:{nome:string;avaliacao:number}; diasHorarios:{dia:Dia;inicio:string;fim:string}[]; vagasTotais:number; vagasDisponiveis:number; sala:string; modalidade:"presencial"|"online" };
export type RotinaPreferencias = { turno:"Manhã"|"Tarde"|"Noite"|"Sem preferência"; modalidadePref:"presencial"|"online"|"ambas"; compromissosFixos:{dia:string;inicio:string;fim:string;descricao:string}[] };
export const aluno={matricula:"2412345",nome:"Maria",curso:"Engenharia de Produção",historicoDisciplinas:["MAT1101","ECO1101","ECO1201"]};
export const disciplinas:Disciplina[]=[
{codigo:"MAT1101",nome:"Cálculo I",creditos:4,preRequisitos:[],trilha:"Fundamentos de Matemática",categoria:"obrigatoria",cor:"moss"},
{codigo:"MAT1102",nome:"Cálculo II",creditos:4,preRequisitos:["MAT1101"],trilha:"Fundamentos de Matemática",categoria:"obrigatoria",cor:"ochre"},
{codigo:"MAT1103",nome:"Cálculo III",creditos:4,preRequisitos:["MAT1102"],trilha:"Fundamentos de Matemática",categoria:"obrigatoria",cor:"clay"},
{codigo:"INF1005",nome:"Algoritmos",creditos:4,preRequisitos:[],trilha:"Ciência de Dados",categoria:"obrigatoria",cor:"ochre",descricao:"Fundamentos de programação, lógica e resolução estruturada de problemas."},
{codigo:"INF1006",nome:"Estruturas de Dados",creditos:4,preRequisitos:["INF1005"],trilha:"Ciência de Dados",categoria:"obrigatoria",cor:"clay"},
{codigo:"INF1771",nome:"Inteligência Artificial",creditos:4,preRequisitos:["INF1006"],trilha:"Ciência de Dados",categoria:"eletiva",cor:"clay",descricao:"Conceitos e aplicações de inteligência artificial em problemas reais."},
{codigo:"ECO1101",nome:"Introdução à Economia",creditos:4,preRequisitos:[],trilha:"Economia",categoria:"obrigatoria",cor:"terracotta"},
{codigo:"ECO1201",nome:"Microeconomia",creditos:4,preRequisitos:["ECO1101"],trilha:"Economia",categoria:"obrigatoria",cor:"moss"},
{codigo:"ECO1301",nome:"Economia Brasileira",creditos:4,preRequisitos:["ECO1201"],trilha:"Economia",categoria:"eletiva",cor:"ochre"},
{codigo:"ECO1401",nome:"Economia Internacional",creditos:4,preRequisitos:["ECO1301"],trilha:"Economia",categoria:"eletiva",cor:"clay"},
{codigo:"FIL1001",nome:"Filosofia",creditos:4,preRequisitos:[],trilha:"Humanidades",categoria:"obrigatoria",cor:"clay"},
{codigo:"LET1003",nome:"Inglês Acadêmico",creditos:4,preRequisitos:[],trilha:"Humanidades",categoria:"obrigatoria",cor:"moss"},
{codigo:"SOC1001",nome:"Sociologia",creditos:4,preRequisitos:[],trilha:"Humanidades",categoria:"obrigatoria",cor:"terracotta"},
{codigo:"ADM1710",nome:"Empreendedorismo",creditos:4,preRequisitos:[],trilha:"Gestão",categoria:"eletiva",cor:"moss",descricao:"Desenvolve competências empreendedoras e a capacidade de identificar oportunidades."},
{codigo:"AMB1103",nome:"Sustentabilidade e Sociedade",creditos:4,preRequisitos:[],trilha:"Sociedade",categoria:"eletiva",cor:"ochre",descricao:"Discute desafios socioambientais e suas relações com economia e gestão."},
{codigo:"HIS2001",nome:"Arte e Cultura",creditos:4,preRequisitos:[],trilha:"Humanidades",categoria:"eletiva",cor:"lilac"},
];
export const turmas:Turma[]=[
{id:"MAT-A",codigoDisciplina:"MAT1101",professor:{nome:"Ana Ribeiro",avaliacao:4.8},diasHorarios:[{dia:"Seg",inicio:"08:00",fim:"10:00"},{dia:"Qua",inicio:"08:00",fim:"10:00"}],vagasTotais:30,vagasDisponiveis:12,sala:"LDS – 101",modalidade:"presencial"},
{id:"ECO-A",codigoDisciplina:"ECO1101",professor:{nome:"Mariana Costa",avaliacao:4.6},diasHorarios:[{dia:"Ter",inicio:"09:00",fim:"11:00"},{dia:"Qui",inicio:"09:00",fim:"11:00"}],vagasTotais:25,vagasDisponiveis:8,sala:"LDS – 102",modalidade:"presencial"},
{id:"FIL-A",codigoDisciplina:"FIL1001",professor:{nome:"Paulo Nunes",avaliacao:4.7},diasHorarios:[{dia:"Seg",inicio:"10:00",fim:"12:00"},{dia:"Qua",inicio:"10:00",fim:"12:00"}],vagasTotais:30,vagasDisponiveis:18,sala:"LDS – 205",modalidade:"presencial"},
{id:"ALG-A",codigoDisciplina:"INF1005",professor:{nome:"Rafael Menezes",avaliacao:4.9},diasHorarios:[{dia:"Seg",inicio:"14:00",fim:"16:00"},{dia:"Qua",inicio:"14:00",fim:"16:00"}],vagasTotais:30,vagasDisponiveis:3,sala:"LDS – 303",modalidade:"presencial"},
{id:"ING-A",codigoDisciplina:"LET1003",professor:{nome:"Clara Lima",avaliacao:4.5},diasHorarios:[{dia:"Ter",inicio:"16:00",fim:"18:00"},{dia:"Qui",inicio:"13:00",fim:"15:00"}],vagasTotais:24,vagasDisponiveis:10,sala:"LDS – 304",modalidade:"presencial"},
{id:"SOC-A",codigoDisciplina:"SOC1001",professor:{nome:"João Freitas",avaliacao:4.4},diasHorarios:[{dia:"Ter",inicio:"13:00",fim:"15:00"},{dia:"Qua",inicio:"18:00",fim:"20:00"}],vagasTotais:30,vagasDisponiveis:14,sala:"LDS – 207",modalidade:"presencial"},
{id:"ADM-A",codigoDisciplina:"ADM1710",professor:{nome:"Carlos Alberto Pereira",avaliacao:4.8},diasHorarios:[{dia:"Seg",inicio:"09:00",fim:"11:00"}],vagasTotais:30,vagasDisponiveis:12,sala:"IAG – 201",modalidade:"presencial"},
{id:"AMB-A",codigoDisciplina:"AMB1103",professor:{nome:"Mariana Costa",avaliacao:4.7},diasHorarios:[{dia:"Ter",inicio:"13:00",fim:"15:00"}],vagasTotais:25,vagasDisponiveis:8,sala:"KEN – 401",modalidade:"online"},
{id:"IA-A",codigoDisciplina:"INF1771",professor:{nome:"Rafael Menezes",avaliacao:4.9},diasHorarios:[{dia:"Qua",inicio:"15:00",fim:"17:00"}],vagasTotais:30,vagasDisponiveis:3,sala:"LDS – 303",modalidade:"presencial"},
{id:"HIS-A",codigoDisciplina:"HIS2001",professor:{nome:"Beatriz Dias",avaliacao:4.6},diasHorarios:[{dia:"Ter",inicio:"16:00",fim:"18:00"}],vagasTotais:25,vagasDisponiveis:9,sala:"FAT – 110",modalidade:"presencial"},
{id:"MAT-B",codigoDisciplina:"MAT1101",professor:{nome:"Sérgio Braga",avaliacao:4.3},diasHorarios:[{dia:"Ter",inicio:"14:00",fim:"16:00"},{dia:"Qui",inicio:"14:00",fim:"16:00"}],vagasTotais:30,vagasDisponiveis:7,sala:"LDS – 104",modalidade:"presencial"},
{id:"MAT2-A",codigoDisciplina:"MAT1102",professor:{nome:"Ana Ribeiro",avaliacao:4.8},diasHorarios:[{dia:"Seg",inicio:"10:00",fim:"12:00"},{dia:"Qua",inicio:"10:00",fim:"12:00"}],vagasTotais:30,vagasDisponiveis:11,sala:"LDS – 105",modalidade:"presencial"},
{id:"MAT2-B",codigoDisciplina:"MAT1102",professor:{nome:"Luiz Tavares",avaliacao:4.2},diasHorarios:[{dia:"Ter",inicio:"08:00",fim:"10:00"},{dia:"Qui",inicio:"08:00",fim:"10:00"}],vagasTotais:30,vagasDisponiveis:19,sala:"LDS – 106",modalidade:"presencial"},
{id:"MAT3-A",codigoDisciplina:"MAT1103",professor:{nome:"Helena Prado",avaliacao:4.5},diasHorarios:[{dia:"Seg",inicio:"16:00",fim:"18:00"},{dia:"Qua",inicio:"16:00",fim:"18:00"}],vagasTotais:25,vagasDisponiveis:6,sala:"LDS – 107",modalidade:"presencial"},
{id:"ALG-B",codigoDisciplina:"INF1005",professor:{nome:"Tiago Moura",avaliacao:4.4},diasHorarios:[{dia:"Ter",inicio:"19:00",fim:"21:00"},{dia:"Qui",inicio:"19:00",fim:"21:00"}],vagasTotais:30,vagasDisponiveis:15,sala:"LDS – 305",modalidade:"online"},
{id:"INF6-A",codigoDisciplina:"INF1006",professor:{nome:"Rafael Menezes",avaliacao:4.9},diasHorarios:[{dia:"Ter",inicio:"14:00",fim:"16:00"},{dia:"Qui",inicio:"16:00",fim:"18:00"}],vagasTotais:30,vagasDisponiveis:5,sala:"LDS – 306",modalidade:"presencial"},
{id:"INF6-B",codigoDisciplina:"INF1006",professor:{nome:"Tiago Moura",avaliacao:4.4},diasHorarios:[{dia:"Seg",inicio:"19:00",fim:"21:00"},{dia:"Qua",inicio:"19:00",fim:"21:00"}],vagasTotais:30,vagasDisponiveis:17,sala:"LDS – 307",modalidade:"presencial"},
{id:"ECO2-A",codigoDisciplina:"ECO1201",professor:{nome:"Mariana Costa",avaliacao:4.6},diasHorarios:[{dia:"Ter",inicio:"10:00",fim:"12:00"},{dia:"Qui",inicio:"10:00",fim:"12:00"}],vagasTotais:25,vagasDisponiveis:9,sala:"IAG – 202",modalidade:"presencial"},
{id:"ECO3-A",codigoDisciplina:"ECO1301",professor:{nome:"Paulo Nunes",avaliacao:4.7},diasHorarios:[{dia:"Seg",inicio:"13:00",fim:"15:00"},{dia:"Qua",inicio:"13:00",fim:"15:00"}],vagasTotais:25,vagasDisponiveis:13,sala:"IAG – 203",modalidade:"presencial"},
{id:"ECO3-B",codigoDisciplina:"ECO1301",professor:{nome:"Beatriz Dias",avaliacao:4.6},diasHorarios:[{dia:"Sex",inicio:"09:00",fim:"13:00"}],vagasTotais:20,vagasDisponiveis:4,sala:"IAG – 204",modalidade:"online"},
{id:"ECO4-A",codigoDisciplina:"ECO1401",professor:{nome:"Carlos Alberto Pereira",avaliacao:4.8},diasHorarios:[{dia:"Qui",inicio:"18:00",fim:"20:00"}],vagasTotais:20,vagasDisponiveis:8,sala:"IAG – 205",modalidade:"presencial"},
{id:"FIL-B",codigoDisciplina:"FIL1001",professor:{nome:"Clara Lima",avaliacao:4.5},diasHorarios:[{dia:"Sex",inicio:"14:00",fim:"18:00"}],vagasTotais:30,vagasDisponiveis:21,sala:"LDS – 206",modalidade:"presencial"},
{id:"ING-B",codigoDisciplina:"LET1003",professor:{nome:"Clara Lima",avaliacao:4.5},diasHorarios:[{dia:"Seg",inicio:"18:00",fim:"20:00"},{dia:"Qua",inicio:"18:00",fim:"20:00"}],vagasTotais:24,vagasDisponiveis:6,sala:"LDS – 308",modalidade:"online"},
{id:"SOC-B",codigoDisciplina:"SOC1001",professor:{nome:"João Freitas",avaliacao:4.4},diasHorarios:[{dia:"Sex",inicio:"08:00",fim:"12:00"}],vagasTotais:30,vagasDisponiveis:20,sala:"LDS – 208",modalidade:"presencial"},
{id:"ADM-B",codigoDisciplina:"ADM1710",professor:{nome:"Beatriz Dias",avaliacao:4.6},diasHorarios:[{dia:"Qui",inicio:"16:00",fim:"18:00"}],vagasTotais:30,vagasDisponiveis:16,sala:"IAG – 206",modalidade:"online"},
{id:"AMB-B",codigoDisciplina:"AMB1103",professor:{nome:"Helena Prado",avaliacao:4.5},diasHorarios:[{dia:"Sex",inicio:"13:00",fim:"15:00"}],vagasTotais:25,vagasDisponiveis:11,sala:"KEN – 402",modalidade:"presencial"},
{id:"IA-B",codigoDisciplina:"INF1771",professor:{nome:"Rafael Menezes",avaliacao:4.9},diasHorarios:[{dia:"Sex",inicio:"15:00",fim:"17:00"}],vagasTotais:30,vagasDisponiveis:2,sala:"LDS – 309",modalidade:"presencial"},
{id:"HIS-B",codigoDisciplina:"HIS2001",professor:{nome:"Paulo Nunes",avaliacao:4.7},diasHorarios:[{dia:"Qua",inicio:"20:00",fim:"22:00"}],vagasTotais:25,vagasDisponiveis:12,sala:"FAT – 111",modalidade:"presencial"},
];
export type StatusDisciplina="Concluída"|"Disponível"|"Bloqueada";
export function preRequisitosPendentes(codigo:string,concluidas:string[]=aluno.historicoDisciplinas){const d=disciplinas.find(x=>x.codigo===codigo);return d?d.preRequisitos.filter(p=>!concluidas.includes(p)):[]}
export function statusDisciplina(codigo:string,concluidas:string[]=aluno.historicoDisciplinas):StatusDisciplina{if(concluidas.includes(codigo))return"Concluída";return preRequisitosPendentes(codigo,concluidas).length===0?"Disponível":"Bloqueada"}
export function turmasDaDisciplina(codigo:string){return turmas.filter(t=>t.codigoDisciplina===codigo)}
export function nomeDisciplina(codigo:string){return disciplinas.find(d=>d.codigo===codigo)?.nome??codigo}
export const gradeOptions=[
{titulo:"Equilíbrio entre teoria e prática",ids:["MAT-A","ECO-A","FIL-A","ALG-A","ING-A"]},
{titulo:"Mais aulas pela manhã",ids:["MAT-A","ECO-A","FIL-A","ADM-A","IA-A"]},
{titulo:"Com disciplinas eletivas",ids:["MAT-A","ECO-A","SOC-A","HIS-A","ING-A"]},
{titulo:"Menos dias na semana",ids:["MAT-A","FIL-A","ECO-A","ALG-A","SOC-A"]},
];
