"use client";

import { Component, Suspense, type ErrorInfo, type ReactNode } from "react";
import { getComponent } from "@/lib/component-registry";
import { Skeleton } from "@/components/ui/skeleton";
import { reportDashboardError } from "@/lib/dashboard/error-reporter";

interface ComponentRendererProps {
  toolName: string;
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  props: Record<string, any>;
}

interface ErrorBoundaryProps {
  children: ReactNode;
  fallback: ReactNode;
  toolName?: string;
}

interface ErrorBoundaryState {
  hasError: boolean;
}

class ErrorBoundary extends Component<ErrorBoundaryProps, ErrorBoundaryState> {
  constructor(props: ErrorBoundaryProps) {
    super(props);
    this.state = { hasError: false };
  }

  static getDerivedStateFromError(): ErrorBoundaryState {
    return { hasError: true };
  }

  componentDidCatch(error: Error, errorInfo: ErrorInfo) {
    console.error("Component render error:", error, errorInfo);
    reportDashboardError(
      `component/${this.props.toolName || "unknown"}`,
      error.message,
      { stack: errorInfo.componentStack?.slice(0, 500) },
    );
  }

  render() {
    if (this.state.hasError) {
      return this.props.fallback;
    }
    return this.props.children;
  }
}

export function ComponentRenderer({ toolName, props }: ComponentRendererProps) {
  const registration = getComponent(toolName);

  if (!registration) {
    return (
      <div
        className="p-4 text-sm text-muted-foreground"
        data-testid="unknown-component"
      >
        Unknown component: {toolName}
      </div>
    );
  }

  const Comp = registration.component;

  return (
    <ErrorBoundary
      toolName={toolName}
      fallback={
        <div className="p-4 text-sm text-destructive" data-testid="component-error">
          Error rendering {toolName}
        </div>
      }
    >
      <Suspense fallback={<ComponentLoading />}>
        <div data-testid="rendered-component">
          <Comp {...props} />
        </div>
      </Suspense>
    </ErrorBoundary>
  );
}

export function ComponentLoading() {
  return (
    <div className="p-4 space-y-3" data-testid="component-loading">
      <Skeleton className="h-8 w-48" />
      <Skeleton className="h-4 w-full" />
      <Skeleton className="h-4 w-3/4" />
      <Skeleton className="h-32 w-full" />
    </div>
  );
}
