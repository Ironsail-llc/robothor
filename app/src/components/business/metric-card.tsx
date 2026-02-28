"use client";

import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";

interface MetricCardProps {
  title: string;
  value: string | number;
  description?: string;
  trend?: "up" | "down" | "neutral";
  trendValue?: string;
  accentColor?: string;
}

export function MetricCard({
  title,
  value,
  description,
  trend,
  trendValue,
  accentColor,
}: MetricCardProps) {
  const trendColor =
    trend === "up"
      ? "text-emerald-400"
      : trend === "down"
        ? "text-red-400"
        : "text-muted-foreground";

  return (
    <Card
      className="glass-panel"
      style={accentColor ? { borderLeft: `2px solid ${accentColor}` } : undefined}
      data-testid="metric-card"
    >
      <CardHeader className="pb-2">
        <CardTitle className="text-sm font-medium text-muted-foreground">
          {title}
        </CardTitle>
      </CardHeader>
      <CardContent>
        <div className="text-2xl font-bold text-primary" data-testid="metric-value">
          {value}
        </div>
        {(description || trendValue) && (
          <p className={`text-xs mt-1 ${trendColor}`}>
            {trendValue && (
              <span>
                {trend === "up" ? "\u2191" : trend === "down" ? "\u2193" : "\u2192"}{" "}
                {trendValue}{" "}
              </span>
            )}
            {description}
          </p>
        )}
      </CardContent>
    </Card>
  );
}
