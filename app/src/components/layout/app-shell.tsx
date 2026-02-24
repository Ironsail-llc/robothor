"use client";

import { useState } from "react";
import { Sidebar, type ViewId } from "./sidebar";
import { ChatPanel } from "@/components/chat-panel";
import { DashboardView } from "@/components/views/dashboard-view";
import { TasksView } from "@/components/views/tasks-view";
import { AgentsView } from "@/components/views/agents-view";
import { useTasks } from "@/hooks/use-tasks";
import { useAgents } from "@/hooks/use-agents";

export function AppShell() {
  const [activeView, setActiveView] = useState<ViewId>("dashboard");
  const [chatOpen, setChatOpen] = useState(true);

  // Lift data fetching — single source for sidebar badges + views
  const { tasks, isLoading: tasksLoading, approveTask, rejectTask } = useTasks({ live: true });
  const { agents, summary: agentSummary, isLoading: agentsLoading } = useAgents();

  const reviewCount = tasks.filter((t) => t.status === "REVIEW").length;
  const unhealthyCount = agentSummary.degraded + agentSummary.failed;

  return (
    <div className="flex h-full w-full" data-testid="app-shell">
      <Sidebar
        activeView={activeView}
        onViewChange={setActiveView}
        chatOpen={chatOpen}
        onChatToggle={() => setChatOpen((prev) => !prev)}
        reviewCount={reviewCount}
        unhealthyCount={unhealthyCount}
      />

      {/* Main content area — all views stay mounted */}
      <div className="flex-1 min-w-0 h-full relative">
        <DashboardView visible={activeView === "dashboard"} />
        <TasksView
          visible={activeView === "tasks"}
          tasks={tasks}
          isLoading={tasksLoading}
          onApprove={approveTask}
          onReject={rejectTask}
        />
        <AgentsView
          visible={activeView === "agents"}
          agents={agents}
          summary={agentSummary}
          isLoading={agentsLoading}
        />
      </div>

      {/* Collapsible chat panel */}
      <div
        className="shrink-0 border-l border-border transition-[width] duration-200 overflow-hidden"
        style={{ width: chatOpen ? 400 : 0 }}
        data-testid="chat-container"
      >
        <div className="h-full w-[400px]">
          <ChatPanel />
        </div>
      </div>
    </div>
  );
}
