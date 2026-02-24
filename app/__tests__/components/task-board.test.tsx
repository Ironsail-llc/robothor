import { describe, it, expect, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import { TaskBoard } from "@/components/business/task-board";

const mockTasks = [
  { id: "1", title: "Task A", status: "TODO" as const, priority: "urgent", tags: ["email"] },
  { id: "2", title: "Task B", status: "IN_PROGRESS" as const, assignedToAgent: "email-responder" },
  { id: "3", title: "Task C", status: "REVIEW" as const, priority: "high" },
  { id: "4", title: "Task D", status: "DONE" as const },
  { id: "5", title: "Overdue", status: "TODO" as const, slaDeadlineAt: "2020-01-01T00:00:00Z" },
];

describe("TaskBoard", () => {
  it("renders 4 columns including REVIEW", () => {
    render(<TaskBoard tasks={mockTasks} />);
    expect(screen.getByText("To Do")).toBeDefined();
    expect(screen.getByText("In Progress")).toBeDefined();
    expect(screen.getByText("Review")).toBeDefined();
    expect(screen.getByText("Done")).toBeDefined();
  });

  it("has 4-column grid layout", () => {
    render(<TaskBoard tasks={mockTasks} />);
    const board = screen.getByTestId("task-board");
    expect(board.className).toContain("grid-cols-4");
  });

  it("renders task cards", () => {
    render(<TaskBoard tasks={mockTasks} />);
    const cards = screen.getAllByTestId("task-card");
    expect(cards.length).toBe(5);
  });

  it("renders priority badges for non-normal priorities", () => {
    render(<TaskBoard tasks={mockTasks} />);
    const badges = screen.getAllByTestId("priority-badge");
    // Task A (urgent) and Task C (high) should show badges
    expect(badges.length).toBe(2);
    expect(badges[0].textContent).toBe("urgent");
    expect(badges[1].textContent).toBe("high");
  });

  it("renders tag badges", () => {
    render(<TaskBoard tasks={mockTasks} />);
    expect(screen.getByText("email")).toBeDefined();
  });

  it("renders agent assignment", () => {
    render(<TaskBoard tasks={mockTasks} />);
    expect(screen.getByText("email-responder")).toBeDefined();
  });

  it("applies SLA overdue styling", () => {
    render(<TaskBoard tasks={mockTasks} />);
    // The overdue task should have a red ring
    const overdueCard = screen.getByText("Overdue").closest("[data-testid='task-card']");
    expect(overdueCard?.className).toContain("ring-red-500");
  });

  it("does not apply SLA overdue styling to DONE tasks", () => {
    const doneTasks = [
      { id: "1", title: "Done task", status: "DONE" as const, slaDeadlineAt: "2020-01-01T00:00:00Z" },
    ];
    render(<TaskBoard tasks={doneTasks} />);
    const card = screen.getByText("Done task").closest("[data-testid='task-card']");
    expect(card?.className).not.toContain("ring-red-500");
  });

  it("renders approve/reject buttons on REVIEW tasks", () => {
    render(<TaskBoard tasks={mockTasks} />);
    const reviewActions = screen.getByTestId("review-actions");
    expect(reviewActions).toBeDefined();
    expect(screen.getByTestId("approve-button")).toBeDefined();
    expect(screen.getByTestId("reject-button")).toBeDefined();
  });

  it("does not render approve/reject buttons on non-REVIEW tasks", () => {
    const noReviewTasks = [
      { id: "1", title: "Task A", status: "TODO" as const },
      { id: "2", title: "Task B", status: "IN_PROGRESS" as const },
      { id: "3", title: "Task D", status: "DONE" as const },
    ];
    render(<TaskBoard tasks={noReviewTasks} />);
    expect(screen.queryByTestId("review-actions")).toBeNull();
  });

  it("calls onApprove callback when approve is clicked", async () => {
    const onApprove = vi.fn();
    render(<TaskBoard tasks={mockTasks} onApprove={onApprove} />);
    const approveBtn = screen.getByTestId("approve-button");
    approveBtn.click();
    expect(onApprove).toHaveBeenCalledWith("3", "Approved via Helm");
  });

  it("calls onReject callback when reject is clicked", async () => {
    const onReject = vi.fn();
    render(<TaskBoard tasks={mockTasks} onReject={onReject} />);
    const rejectBtn = screen.getByTestId("reject-button");
    rejectBtn.click();
    expect(onReject).toHaveBeenCalledWith("3", "Rejected via Helm");
  });
});
