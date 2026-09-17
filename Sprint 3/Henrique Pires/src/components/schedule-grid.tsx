import { disciplinas, type Dia, type Turma } from "@/lib/grade-data";
import { cn } from "@/lib/utils";

const dias: { key: Dia; label: string }[] = [
  { key: "Seg", label: "Segunda" },
  { key: "Ter", label: "Terça" },
  { key: "Qua", label: "Quarta" },
  { key: "Qui", label: "Quinta" },
  { key: "Sex", label: "Sexta" },
];

const hours = Array.from({ length: 14 }, (_, i) => `${String(i + 8).padStart(2, "0")}:00`);
const index = (t: string) => Number(t.slice(0, 2)) - 8;

export function ScheduleGrid({
  classes,
  compact = false,
  onRemove,
}: {
  classes: Turma[];
  compact?: boolean;
  onRemove?: (id: string) => void;
}) {
  return (
    <div className="self-start overflow-x-auto rounded-xl border border-border bg-surface p-2 shadow-sm">
      <div
        className="schedule-grid min-w-[760px]"
        style={{ gridTemplateRows: `44px repeat(14, ${compact ? "30px" : "36px"})` }}
      >
        <div className="schedule-head font-display font-semibold text-foreground">Horários</div>
        {dias.map((d) => (
          <div className="schedule-head font-display font-semibold text-foreground" key={d.key}>
            {d.label}
          </div>
        ))}
        {hours.map((h, i) => (
          <div
            key={h}
            className="schedule-time font-mono text-xs text-muted-foreground"
            style={{ gridColumn: 1, gridRow: i + 2 }}
          >
            {h} – {`${String(i + 9).padStart(2, "0")}:00`}
          </div>
        ))}
        {dias.flatMap((d, di) =>
          hours.map((h, hi) => (
            <div
              key={`${d.key}${h}`}
              className="border-b border-r border-border/40"
              style={{ gridColumn: di + 2, gridRow: hi + 2 }}
            />
          ))
        )}
        {classes.flatMap((t) =>
          t.diasHorarios.map((slot, k) => {
            const disc = disciplinas.find((d) => d.codigo === t.codigoDisciplina);
            if (!disc) return null;

            return (
              <button
                key={`${t.id}${k}`}
                title={onRemove ? "Clique para remover da grade" : disc.nome}
                onClick={() => onRemove?.(t.id)}
                className={cn(
                  "m-0.5 flex flex-col justify-between rounded-lg p-1.5 shadow-md transition-all hover:scale-[1.02] hover:shadow-lg focus:outline-none focus:ring-2 focus:ring-primary",
                  `subject-${disc.cor}`,
                  // Destaque visual sólido caso as classes dinâmicas falhem
                  "bg-primary/10 border-l-4 border-primary text-foreground"
                )}
                style={{
                  gridColumn: dias.findIndex((d) => d.key === slot.dia) + 2,
                  gridRow: `${index(slot.inicio) + 2} / ${index(slot.fim) + 2}`,
                }}
              >
                <strong className="font-display text-xs font-bold leading-tight text-foreground">
                  {disc.nome}
                </strong>
                {!compact && (
                  <div className="mt-1 flex flex-col font-mono text-[10px] text-muted-foreground">
                    <span>{slot.inicio} – {slot.fim}</span>
                    <span className="font-semibold text-primary">{t.sala}</span>
                  </div>
                )}
              </button>
            );
          })
        )}
      </div>
    </div>
  );
}
