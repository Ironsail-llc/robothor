"use client";

import { LiveCanvas } from "@/components/canvas/live-canvas";

interface DashboardViewProps {
  visible: boolean;
}

export function DashboardView({ visible }: DashboardViewProps) {
  return (
    <div
      className="h-full w-full flex-col"
      style={{ display: visible ? "flex" : "none" }}
      data-testid="dashboard-view"
    >
      <LiveCanvas />
    </div>
  );
}
