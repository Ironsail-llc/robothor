"use client";

import { AppShell } from "@/components/layout/app-shell";
import { VisualStateProvider } from "@/hooks/use-visual-state";

export default function Home() {
  return (
    <VisualStateProvider>
      <main className="h-screen w-screen overflow-hidden">
        <AppShell />
      </main>
    </VisualStateProvider>
  );
}
