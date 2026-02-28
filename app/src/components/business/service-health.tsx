"use client";

import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import type { ServiceHealth as ServiceHealthType } from "@/lib/api/types";

interface ServiceHealthProps {
  services: ServiceHealthType[];
  overallStatus?: "ok" | "degraded";
}

function LatencyBar({ ms }: { ms?: number }) {
  if (ms === undefined) return null;
  // Scale: 0-50ms = short, 50-200 = medium, 200+ = long
  const pct = Math.min(100, (ms / 200) * 100);
  const color =
    ms < 50 ? "bg-emerald-400" : ms < 200 ? "bg-amber-400" : "bg-red-400";
  return (
    <div className="w-full h-1 rounded-full bg-muted/50 mt-1" data-testid="latency-bar">
      <div
        className={`h-full rounded-full ${color}`}
        style={{ width: `${pct}%` }}
      />
    </div>
  );
}

export function ServiceHealth({ services, overallStatus }: ServiceHealthProps) {
  return (
    <div data-testid="service-health">
      <div className="flex items-center gap-2 mb-4">
        <h3 className="font-medium">Service Health</h3>
        {overallStatus && (
          <Badge
            variant={overallStatus === "ok" ? "default" : "destructive"}
            data-testid="overall-status"
          >
            {overallStatus === "ok" ? "All Systems Operational" : "Degraded"}
          </Badge>
        )}
      </div>
      <div className="grid grid-cols-2 md:grid-cols-3 gap-3">
        {services.map((service) => {
          const isHealthy = service.status === "healthy";
          return (
            <Card
              key={service.name}
              className={`glass-panel ${isHealthy ? "bg-emerald-500/[0.02]" : "bg-red-500/[0.04]"}`}
              data-testid="service-card"
            >
              <CardHeader className="pb-1 pt-3 px-3">
                <CardTitle className="text-sm font-medium flex items-center gap-2">
                  <span
                    className={`w-2 h-2 rounded-full ${
                      isHealthy ? "bg-green-400" : "bg-red-400"
                    }`}
                  />
                  {service.name}
                </CardTitle>
              </CardHeader>
              <CardContent className="px-3 pb-3">
                <p className="text-xs text-muted-foreground">
                  {service.responseTime !== undefined
                    ? `${service.responseTime}ms`
                    : service.status}
                </p>
                <LatencyBar ms={service.responseTime} />
              </CardContent>
            </Card>
          );
        })}
      </div>
    </div>
  );
}
