import { lazy, type ComponentType } from "react";

export interface ToolRegistration {
  name: string;
  description: string;
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  component: ComponentType<any>;
}

const registry: Map<string, ToolRegistration> = new Map();

function register(
  name: string,
  description: string,
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  component: ComponentType<any>
) {
  registry.set(name, { name, description, component });
}

// Lazy-load business components — native rendering is rare (HTML-first approach).
// Each chunk only loads when a [RENDER:...] marker actually fires.
const ContactCard = lazy(() => import("@/components/business/contact-card").then(m => ({ default: m.ContactCard })));
const ContactTable = lazy(() => import("@/components/business/contact-table").then(m => ({ default: m.ContactTable })));
const CompanyCard = lazy(() => import("@/components/business/company-card").then(m => ({ default: m.CompanyCard })));
const ConversationList = lazy(() => import("@/components/business/conversation-list").then(m => ({ default: m.ConversationList })));
const ConversationThread = lazy(() => import("@/components/business/conversation-thread").then(m => ({ default: m.ConversationThread })));
const MetricCard = lazy(() => import("@/components/business/metric-card").then(m => ({ default: m.MetricCard })));
const MetricGrid = lazy(() => import("@/components/business/metric-grid").then(m => ({ default: m.MetricGrid })));
const BarChart = lazy(() => import("@/components/business/bar-chart").then(m => ({ default: m.BarChart })));
const LineChart = lazy(() => import("@/components/business/line-chart").then(m => ({ default: m.LineChart })));
const PieChart = lazy(() => import("@/components/business/pie-chart").then(m => ({ default: m.PieChart })));
const DataTable = lazy(() => import("@/components/business/data-table").then(m => ({ default: m.DataTable })));
const Timeline = lazy(() => import("@/components/business/timeline").then(m => ({ default: m.Timeline })));
const MemorySearch = lazy(() => import("@/components/business/memory-search").then(m => ({ default: m.MemorySearch })));
const ServiceHealth = lazy(() => import("@/components/business/service-health").then(m => ({ default: m.ServiceHealth })));
const TaskBoard = lazy(() => import("@/components/business/task-board").then(m => ({ default: m.TaskBoard })));
const MarkdownView = lazy(() => import("@/components/business/markdown-view").then(m => ({ default: m.MarkdownView })));
const FormPanel = lazy(() => import("@/components/business/form-panel").then(m => ({ default: m.FormPanel })));

// Register all business components
register("render_contact_card", "Display a contact card", ContactCard);
register("render_contact_table", "Display contacts in a table", ContactTable);
register("render_company_card", "Display a company card", CompanyCard);
register("render_conversations", "Display conversation list", ConversationList);
register("render_conversation_thread", "Display conversation messages", ConversationThread);
register("render_metric_card", "Display a single metric", MetricCard);
register("render_metric_grid", "Display a grid of metrics", MetricGrid);
register("render_bar_chart", "Display a bar chart", BarChart);
register("render_line_chart", "Display a line chart", LineChart);
register("render_pie_chart", "Display a pie chart", PieChart);
register("render_data_table", "Display a data table", DataTable);
register("render_timeline", "Display a timeline of events", Timeline);
register("render_memory_search", "Display memory search results", MemorySearch);
register("render_service_health", "Display service health status", ServiceHealth);
register("render_task_board", "Display tasks in a kanban board", TaskBoard);
register("render_markdown", "Display markdown content", MarkdownView);
register("render_form", "Display an input form", FormPanel);

export function getComponent(
  toolName: string
): ToolRegistration | undefined {
  return registry.get(toolName);
}

export function getAllTools(): ToolRegistration[] {
  return Array.from(registry.values());
}

export function hasComponent(toolName: string): boolean {
  return registry.has(toolName);
}
