import { useMemo } from "react";
import { analyticsApi } from "@/api/services";
import { useAsync } from "@/hooks/useAsync";
import { useAuth } from "@/context/AuthContext";
import { useTenantScope, TenantPicker } from "@/components/common/TenantPicker";
import { PageHeader, Card, LoadingBlock, ErrorState } from "@/components/ui/primitives";
import { ChartCard, TrendArea, BarSeries, DonutChart, CHART_COLORS } from "@/components/charts/Charts";
import { formatCurrency, formatNumber } from "@/lib/utils";
import type { CostBreakdown, TokenBreakdown } from "@/api/types";

export function AnalyticsPage() {
  const { isSuperAdmin } = useAuth();
  const scope = useTenantScope(true);
  const tenantParam = isSuperAdmin ? scope.selected || undefined : undefined;

  const costs = useAsync<CostBreakdown>(() => analyticsApi.costs(tenantParam, 30), [tenantParam]);
  const tokens = useAsync<TokenBreakdown>(() => analyticsApi.tokens(tenantParam, 30), [tenantParam]);

  const modelData = useMemo(
    () => (costs.data?.by_model || []).map((m) => ({ name: m.model, value: m.cost_usd })),
    [costs.data],
  );
  const tenantData = useMemo(
    () => (costs.data?.by_tenant || []).map((t) => ({ name: t.tenant_name || "—", cost_usd: t.cost_usd })),
    [costs.data],
  );
  const queryMix = useMemo(
    () => [
      { name: "Knowledge Base", value: costs.data?.rag_queries || 0 },
      { name: "General AI", value: costs.data?.general_queries || 0 },
    ],
    [costs.data],
  );

  return (
    <div>
      <PageHeader
        title="Usage & Costs"
        subtitle="OpenAI token usage and cost analytics (last 30 days)"
        actions={
          isSuperAdmin ? (
            <TenantPicker tenants={scope.tenants} value={scope.selected} onChange={scope.setSelected} allowAll className="w-56" />
          ) : undefined
        }
      />

      {costs.loading ? (
        <LoadingBlock label="Loading analytics…" />
      ) : costs.error ? (
        <ErrorState message={costs.error} onRetry={costs.reload} />
      ) : (
        <>
          <div className="grid grid-cols-2 gap-4 lg:grid-cols-4">
            <MiniStat label="Input Tokens" value={formatNumber(tokens.data?.input_tokens)} />
            <MiniStat label="Output Tokens" value={formatNumber(tokens.data?.output_tokens)} />
            <MiniStat label="Total Tokens" value={formatNumber(tokens.data?.total_tokens)} />
            <MiniStat
              label="30-Day Cost"
              value={formatCurrency((costs.data?.daily || []).reduce((s, d) => s + d.cost_usd, 0), 2)}
            />
          </div>

          <div className="mt-6 grid grid-cols-1 gap-4 lg:grid-cols-3">
            <div className="lg:col-span-2">
              <ChartCard title="Daily Cost" subtitle="USD per day" empty={!costs.data?.daily?.length}>
                <TrendArea data={costs.data?.daily || []} xKey="day" dataKey="cost_usd" formatter={(v) => formatCurrency(v)} />
              </ChartCard>
            </div>
            <ChartCard title="Query Mix" empty={!queryMix.some((q) => q.value > 0)}>
              <DonutChart data={queryMix} formatter={(v) => formatNumber(v)} />
            </ChartCard>
          </div>

          <div className="mt-4 grid grid-cols-1 gap-4 lg:grid-cols-2">
            <ChartCard title="Daily Tokens" empty={!costs.data?.daily?.length}>
              <BarSeries data={costs.data?.daily || []} xKey="day" dataKey="tokens" color={CHART_COLORS[1]} formatter={(v) => formatNumber(v)} />
            </ChartCard>
            <ChartCard title="Cost by Model" empty={!modelData.length}>
              <DonutChart data={modelData} formatter={(v) => formatCurrency(v)} />
            </ChartCard>
          </div>

          {isSuperAdmin && !scope.selected && (
            <div className="mt-4">
              <ChartCard title="Cost by Tenant" subtitle="Across all tenants" empty={!tenantData.length}>
                <BarSeries data={tenantData} xKey="name" dataKey="cost_usd" color={CHART_COLORS[2]} formatter={(v) => formatCurrency(v)} />
              </ChartCard>
            </div>
          )}
        </>
      )}
    </div>
  );
}

function MiniStat({ label, value }: { label: string; value: string }) {
  return (
    <Card className="p-4">
      <p className="text-xs font-medium text-slate-500">{label}</p>
      <p className="mt-1.5 text-xl font-bold text-slate-900">{value}</p>
    </Card>
  );
}
