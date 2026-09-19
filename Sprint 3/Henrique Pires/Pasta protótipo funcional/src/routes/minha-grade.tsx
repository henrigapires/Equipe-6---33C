import { createFileRoute, Link } from "@tanstack/react-router";
import { BookOpen, Check, GitFork, Pencil, Plus, Save, Search, Trash2, Lock } from "lucide-react";
import { useMemo, useState } from "react";
import { toast } from "sonner";
import { AppShell } from "@/components/app-shell";
import { ScheduleGrid } from "@/components/schedule-grid";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { disciplinas, turmas, type Turma, type Disciplina } from "@/lib/grade-data";
import { getTurmas, useGrade } from "@/lib/grade-context";

export const Route = createFileRoute("/minha-grade")({
  head: () => ({
    meta: [
      { title: "Minha grade — grade.puc" },
      { name: "description", content: "Monte e confira sua grade semanal da PUC-Rio." },
    ],
  }),
  component: Page,
});

// Exemplo do histórico do aluno logado (Ex: Maria já fez Cálculo I)
const historicoAluno = ["MAT1101"]; // Cálculo I concluído

function overlaps(a: Turma, b: Turma) {
  return a.diasHorarios.some((x) =>
    b.diasHorarios.some((y) => x.dia === y.dia && x.inicio < y.fim && y.inicio < x.fim)
  );
}

function Page() {
  const { selectedIds, setSelectedIds, gradeName, setGradeName } = useGrade();
  const [query, setQuery] = useState("");
  const [editing, setEditing] = useState(false);

  const selected = getTurmas(selectedIds);

  const list = useMemo(
    () =>
      disciplinas
        .filter(
          (d) =>
            d.nome.toLowerCase().includes(query.toLowerCase()) ||
            d.codigo.toLowerCase().includes(query.toLowerCase())
        )
        .slice(0, 10),
    [query]
  );

  function add(disc: Disciplina): void {
    // 1. Checar se o aluno já cursou essa disciplina
    if (historicoAluno.includes(disc.codigo)) {
      toast.error(`Você já concluiu a disciplina ${disc.nome}. Não é possível cursá-la novamente.`);
      return;
    }

    // 2. Checar se faltam pré-requisitos
    const preRequisitosFaltantes = (disc.preRequisitos || []).filter(
      (preReq) => !historicoAluno.includes(preReq)
    );

    if (preRequisitosFaltantes.length > 0) {
      const nomesPreReqs = preRequisitosFaltantes
        .map((code) => disciplinas.find((d) => d.codigo === code)?.nome || code)
        .join(", ");
      toast.error(`Pré-requisito pendente para ${disc.nome}: ${nomesPreReqs}.`);
      return;
    }

    // 3. Checar dependência com matérias já selecionadas na grade atual (mesmo semestre)
    const codigosNaGrade = selected.map((t) => t.codigoDisciplina);
    const dependeDeMateriaNaGrade = (disc.preRequisitos || []).some((preReq) =>
      codigosNaGrade.includes(preReq)
    );

    if (dependeDeMateriaNaGrade) {
      toast.error(`Não é possível cursar ${disc.nome} e seus pré-requisitos no mesmo semestre.`);
      return;
    }

    // 4. Buscar turma
    const turma = turmas.find((t) => t.codigoDisciplina === disc.codigo);
    if (!turma) {
      toast.error("Não há turma disponível para esta disciplina.");
      return;
    }

    if (selectedIds.includes(turma.id)) {
      toast.info("Esta disciplina já está na sua grade.");
      return;
    }

    // 5. Checar conflito de horários
    const conflict = selected.find((t) => overlaps(t, turma));
    if (conflict) {
      const name = disciplinas.find((d) => d.codigo === conflict.codigoDisciplina)?.nome;
      toast.error(`Conflito de horário com ${name}. A disciplina não foi adicionada.`);
      return;
    }

    setSelectedIds([...selectedIds, turma.id]);
    toast.success(`${disc.nome} adicionada à grade.`);
  }

  return (
    <AppShell>
      <main className="page-wrap">
        <div className="mb-5 flex flex-col justify-between gap-4 lg:flex-row lg:items-start">
          <div>
            {editing ? (
              <Input
                autoFocus
                value={gradeName}
                onChange={(e) => setGradeName(e.target.value)}
                onBlur={() => setEditing(false)}
                className="h-12 max-w-sm font-display text-3xl font-semibold"
              />
            ) : (
              <h1>
                <button
                  onClick={() => setEditing(true)}
                  className="flex items-center gap-3 font-display text-4xl font-semibold text-primary"
                >
                  {gradeName}
                  <Pencil size={23} />
                </button>
              </h1>
            )}
            <p className="mt-1 text-muted-foreground">
              Selecione as disciplinas, edite os horários e monte sua grade ideal.
            </p>
          </div>
          <div className="flex gap-3">
            <Button
              variant="outline"
              onClick={() => {
                setSelectedIds([]);
                toast.success("Grade limpa.");
              }}
            >
              <Trash2 />
              Limpar grade
            </Button>
            <Button asChild>
              <Link to="/resumo" onClick={() => toast.success("Grade salva com sucesso.")}>
                <Save />
                Salvar grade
              </Link>
            </Button>
          </div>
        </div>

        <div className="grid gap-5 xl:grid-cols-[1fr_340px]">
          <ScheduleGrid
            classes={selected}
            onRemove={(id) => {
              setSelectedIds(selectedIds.filter((x) => x !== id));
              toast.success("Disciplina removida.");
            }}
          />

          <aside className="panel self-start p-4">
            <div className="relative">
              <Search className="absolute left-3 top-2.5 text-primary" size={18} />
              <Input
                aria-label="Buscar disciplina"
                value={query}
                onChange={(e) => setQuery(e.target.value)}
                placeholder="Buscar disciplina..."
                className="bg-surface pl-10"
              />
            </div>
            <h2 className="mt-4 font-display text-2xl font-semibold">Disciplinas</h2>
            <p className="text-sm text-muted-foreground">Clique em + para adicionar à grade.</p>

            <div className="mt-3 space-y-2">
              {list.map((d) => {
                const picked = selected.some((t) => t.codigoDisciplina === d.codigo);
                const jaCursou = historicoAluno.includes(d.codigo);
                const preReqsFaltantes = (d.preRequisitos || []).filter(
                  (pre) => !historicoAluno.includes(pre)
                );
                const bloqueada = preReqsFaltantes.length > 0;

                return (
                  <div
                    key={d.codigo}
                    className={`flex items-center rounded-lg border border-border p-3 shadow-sm transition-all ${
                      jaCursou
                        ? "bg-muted/40 opacity-60"
                        : bloqueada
                        ? "bg-destructive/5 border-destructive/20"
                        : "bg-surface hover:border-primary/50"
                    }`}
                  >
                    <div className="min-w-0 flex-1">
                      <b className="block truncate font-display text-sm text-foreground">
                        {d.nome}
                      </b>
                      <span className="technical text-xs text-muted-foreground">
                        {d.codigo} • {d.creditos} cr
                      </span>
                      {jaCursou && (
                        <span className="block text-[10px] font-semibold text-muted-foreground">
                          ✓ Cursada
                        </span>
                      )}
                      {bloqueada && (
                        <span className="block text-[10px] font-semibold text-destructive">
                          🔒 Pré-requisito pendente
                        </span>
                      )}
                    </div>
                    <Button
                      size="icon"
                      variant={picked ? "secondary" : jaCursou || bloqueada ? "outline" : "ghost"}
                      aria-label={picked ? `${d.nome} adicionada` : `Adicionar ${d.nome}`}
                      onClick={() => add(d)}
                      disabled={jaCursou || bloqueada}
                    >
                      {picked ? <Check /> : jaCursou ? <Check className="text-muted-foreground" /> : bloqueada ? <Lock size={16} /> : <Plus />}
                    </Button>
                  </div>
                );
              })}
            </div>
            <Button variant="outline" className="mt-4 w-full">
              Ver todas as disciplinas
            </Button>
          </aside>
        </div>

        <div className="mt-5 grid gap-4 md:grid-cols-2">
          <Button variant="outline" asChild className="h-auto justify-start p-5">
            <Link to="/eletivas">
              <BookOpen className="size-9" />
              <span className="text-left">
                <b className="block text-base">Ver eletivas</b>
                <small className="font-sans font-normal text-muted-foreground">
                  Explore as disciplinas eletivas disponíveis.
                </small>
              </span>
            </Link>
          </Button>
          <Button variant="outline" asChild className="h-auto justify-start p-5">
            <Link to="/fluxograma">
              <GitFork className="size-9" />
              <span className="text-left">
                <b className="block text-base">Ver fluxograma</b>
                <small className="font-sans font-normal text-muted-foreground">
                  Consulte o fluxo do curso e pré-requisitos.
                </small>
              </span>
            </Link>
          </Button>
        </div>
      </main>
    </AppShell>
  );
}
