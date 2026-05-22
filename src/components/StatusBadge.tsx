/**
 * Badge colorido pro status da meeting — derivado de `phaseFromStatus`
 * + cor por categoria (running / completed / failed).
 */

import { phaseFromStatus } from "@/lib/pipelineProgress";
import type { MeetingStatus } from "@/types/meeting";
import { cn } from "@/lib/utils";

export function StatusBadge({ status }: { status: MeetingStatus }) {
  const phase = phaseFromStatus(status);
  const palette = paletteFor(status);
  return (
    <span
      className={cn(
        "inline-flex items-center gap-1.5 rounded-full",
        "px-2.5 py-0.5 text-xs font-medium",
        palette,
      )}
    >
      <span className={cn("size-1.5 rounded-full", dotColor(status))} />
      {phase.label}
    </span>
  );
}

function paletteFor(status: MeetingStatus): string {
  if (status === "completed") {
    return "bg-emerald-500/10 text-emerald-700 border border-emerald-500/20";
  }
  if (status === "failed") {
    return "bg-destructive/10 text-destructive border border-destructive/20";
  }
  if (status === "pending") {
    return "bg-muted text-muted-foreground border";
  }
  return "bg-amber-500/10 text-amber-700 border border-amber-500/20";
}

function dotColor(status: MeetingStatus): string {
  if (status === "completed") return "bg-emerald-500";
  if (status === "failed") return "bg-destructive";
  if (status === "pending") return "bg-muted-foreground/50";
  return "bg-amber-500 animate-pulse";
}
