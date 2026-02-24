"use client";

import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import cronstrue from "cronstrue";

interface Routine {
  id: string;
  title: string;
  cronExpr: string;
  timezone?: string;
  assignedToAgent?: string;
  priority?: string;
  tags?: string[];
  active: boolean;
  nextRunAt?: string;
  lastRunAt?: string;
  body?: string;
}

interface RoutinesManagerProps {
  routines: Routine[];
}

const priorityColors: Record<string, string> = {
  urgent: "bg-red-500/20 text-red-400",
  high: "bg-orange-500/20 text-orange-400",
  normal: "bg-zinc-500/20 text-zinc-400",
  low: "bg-zinc-700/20 text-zinc-500",
};

function humanCron(expr: string): string {
  try {
    return cronstrue.toString(expr, { use24HourTimeFormat: true });
  } catch {
    return expr;
  }
}

function formatRelativeTime(iso?: string): string {
  if (!iso) return "-";
  const diff = new Date(iso).getTime() - Date.now();
  if (diff < 0) {
    const past = -diff;
    if (past < 60_000) return "just now";
    if (past < 3_600_000) return `${Math.floor(past / 60_000)}m ago`;
    if (past < 86_400_000) return `${Math.floor(past / 3_600_000)}h ago`;
    return `${Math.floor(past / 86_400_000)}d ago`;
  }
  if (diff < 60_000) return "in <1m";
  if (diff < 3_600_000) return `in ${Math.floor(diff / 60_000)}m`;
  if (diff < 86_400_000) return `in ${Math.floor(diff / 3_600_000)}h`;
  return `in ${Math.floor(diff / 86_400_000)}d`;
}

export function RoutinesManager({ routines }: RoutinesManagerProps) {
  return (
    <div className="space-y-3" data-testid="routines-manager">
      {routines.length === 0 && (
        <p className="text-sm text-muted-foreground">No routines configured.</p>
      )}
      {routines.map((routine) => (
        <Card
          key={routine.id}
          className={`glass-panel ${!routine.active ? "opacity-50" : ""}`}
          data-testid="routine-card"
        >
          <CardHeader className="pb-1 pt-3 px-3">
            <div className="flex items-center gap-2">
              <CardTitle className="text-sm flex-1">{routine.title}</CardTitle>
              {routine.priority && routine.priority !== "normal" && (
                <Badge className={`text-[10px] px-1 py-0 ${priorityColors[routine.priority] || ""}`}>
                  {routine.priority}
                </Badge>
              )}
              <Badge variant={routine.active ? "default" : "secondary"} className="text-[10px] px-1 py-0">
                {routine.active ? "active" : "paused"}
              </Badge>
            </div>
          </CardHeader>
          <CardContent className="px-3 pb-3 space-y-1">
            <p className="text-xs text-muted-foreground" data-testid="cron-human">
              {humanCron(routine.cronExpr)}
            </p>
            <div className="flex justify-between text-xs text-muted-foreground">
              <span>Next: {formatRelativeTime(routine.nextRunAt)}</span>
              <span>Last: {formatRelativeTime(routine.lastRunAt)}</span>
            </div>
            {routine.assignedToAgent && (
              <p className="text-xs text-muted-foreground">
                Agent: {routine.assignedToAgent}
              </p>
            )}
            {routine.tags && routine.tags.length > 0 && (
              <div className="flex flex-wrap gap-1 mt-1">
                {routine.tags.map((tag) => (
                  <Badge key={tag} variant="outline" className="text-[10px] px-1 py-0">
                    {tag}
                  </Badge>
                ))}
              </div>
            )}
          </CardContent>
        </Card>
      ))}
    </div>
  );
}
