"use client";

import { useState, useEffect, useCallback } from "react";
import { Badge } from "@/components/ui/badge";

interface Tenant {
  id: string;
  displayName: string;
  parentTenantId?: string;
  active: boolean;
}

interface TenantSelectorProps {
  onSelect?: (tenantId: string) => void;
  currentTenantId?: string;
}

export function TenantSelector({ onSelect, currentTenantId }: TenantSelectorProps) {
  const [tenants, setTenants] = useState<Tenant[]>([]);
  const [selected, setSelected] = useState(currentTenantId || "robothor-primary");
  const [isLoading, setIsLoading] = useState(true);

  const fetchTenants = useCallback(async () => {
    try {
      setIsLoading(true);
      const res = await fetch("/api/actions/execute", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ tool: "list_tenants", params: { activeOnly: true } }),
      });
      if (res.ok) {
        const json = await res.json();
        setTenants(json.data?.tenants || []);
      }
    } finally {
      setIsLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchTenants();
  }, [fetchTenants]);

  const handleChange = (e: React.ChangeEvent<HTMLSelectElement>) => {
    const value = e.target.value;
    setSelected(value);
    onSelect?.(value);
  };

  if (isLoading || tenants.length <= 1) return null;

  return (
    <div className="flex items-center gap-2" data-testid="tenant-selector">
      <Badge variant="outline" className="text-[10px]">Tenant</Badge>
      <select
        value={selected}
        onChange={handleChange}
        className="text-sm bg-zinc-900 border border-zinc-700 rounded px-2 py-1 text-zinc-200"
        data-testid="tenant-select"
      >
        {tenants.map((t) => (
          <option key={t.id} value={t.id}>
            {t.displayName}
          </option>
        ))}
      </select>
    </div>
  );
}
