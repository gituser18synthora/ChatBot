import { useMemo } from "react";
import { analyticsApi } from "@/api/services";
import { useAsync } from "@/hooks/useAsync";
import { useAuth } from "@/context/AuthContext";
import { PageHeader, LoadingBlock, ErrorState, Card } from "@/components/ui/primitives";
import { Icon } from "@/components/ui/Icons";
import { ChartCard, TrendArea, DonutChart, CHART_COLORS, BarSeries } from "@/components/charts/Charts";
import { formatCurrency, formatNumber } from "@/lib/utils";
import type { DashboardStats, CostBreakdown } from "@/api/types";

function StatCard({
  label,
  value,
  icon,
  tone = "brand",
  hint,
}: {
  label: string;
  value: string;
  icon: (p: any) => JSX.Element;
  tone?: "brand" | "green" | "amber" | "rose" | "violet";
  hint?: string;
}) {
  const Ico = icon;
  const tones: Record<string, string> = {
    brand: "bg-brand-50 text-brand-600",
    green: "bg-emerald-50 text-emerald-600",
    amber: "bg-amber-50 text-amber-600",
    rose: "bg-rose-50 text-rose-600",
    violet: "bg-violet-50 text-violet-600",
  };
  return (
    <Card className="p-5">
      <div className="flex items-start justify-between">
        <div>
          <p className="text-sm font-medium text-slate-500">{label}</p>
          <p className="mt-2 text-2xl font-bold text-slate-900">{value}</p>
          {hint && <p className="mt-1 text-xs text-slate-400">{hint}</p>}
        </div>
        <span className={`flex h-10 w-10 items-center justify-center rounded-lg ${tones[tone]}`}>
          <Ico width={20} height={20} />
        </span>
      </div>
    </Card>
  );
}

export function DashboardPage() {
  const { isSuperAdmin, user } = useAuth();
  const scope = isSuperAdmin ? undefined : user?.tenant_id || undefined;

  const stats = useAsync<DashboardStats>(() => analyticsApi.dashboard(scope), [scope]);
  const costs = useAsync<CostBreakdown>(() => analyticsApi.costs(scope, 30), [scope]);

  const docStatusData = useMemo(() => {
    const s = stats.data;
    if (!s) return [];
    const completed = Math.max(
      0,
      s.total_documents - s.documents_processing - s.failed_documents,
    );
    return [
      { name: "Completed", value: completed },
      { name: "Processing", value: s.documents_processing },
      { name: "Failed", value: s.failed_documents },
    ];
  }, [stats.data]);

  const queryMix = useMemo(() => {
    const c = costs.data;
    if (!c) return [];
    return [
      { name: "Knowledge Base", value: c.rag_queries },
      { name: "General AI", value: c.general_queries },
    ];
  }, [costs.data]);

  if (stats.loading) return <LoadingBlock label="Loading dashboard…" />;
  if (stats.error) return <ErrorState message={stats.error} onRetry={stats.reload} />;
  const s = stats.data!;

  return (
    <div>
      <PageHeader
        title="Dashboard"
        subtitle={isSuperAdmin ? "Platform-wide overview" : "Your tenant overview"}
      />

      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 xl:grid-cols-4">
        {isSuperAdmin && (
          <StatCard label="Active Tenants" value={`${s.active_tenants} / ${s.total_tenants}`} icon={Icon.Building} tone="violet" />
        )}
        <StatCard label="Knowledge Bases" value={formatNumber(s.total_knowledge_bases)} icon={Icon.Book} tone="brand" />
        <StatCard
          label="Documents"
          value={formatNumber(s.total_documents)}
          icon={Icon.Doc}
          tone="green"
          hint={`${s.documents_processing} processing · ${s.failed_documents} failed`}
        />
        <StatCard label="Users" value={formatNumber(s.total_users)} icon={Icon.Users} tone="brand" />
        <StatCard label="Conversations" value={formatNumber(s.total_conversations)} icon={Icon.Chat} tone="violet" />
        <StatCard label="Today's Tokens" value={formatNumber(s.today_token_usage)} icon={Icon.Chart} tone="amber" />
        <StatCard label="Today's Cost" value={formatCurrency(s.today_openai_cost)} icon={Icon.Sparkle} tone="green" />
        <StatCard label="Monthly Cost" value={formatCurrency(s.monthly_openai_cost, 2)} icon={Icon.Sparkle} tone="rose" />
      </div>

      <div className="mt-6 grid grid-cols-1 gap-4 lg:grid-cols-3">
        <div className="lg:col-span-2">
          <ChartCard title="Daily Cost Trend" subtitle="Last 30 days" empty={!costs.data?.daily?.length}>
            <TrendArea
              data={costs.data?.daily || []}
              xKey="day"
              dataKey="cost_usd"
              formatter={(v) => formatCurrency(v)}
            />
          </ChartCard>
        </div>
        <ChartCard title="Document Status" empty={!s.total_documents}>
          <DonutChart data={docStatusData} formatter={(v) => formatNumber(v)} />
        </ChartCard>
      </div>

      <div className="mt-4 grid grid-cols-1 gap-4 lg:grid-cols-3">
        <div className="lg:col-span-2">
          <ChartCard title="Daily Token Usage" subtitle="Last 30 days" empty={!costs.data?.daily?.length}>
            <BarSeries
              data={costs.data?.daily || []}
              xKey="day"
              dataKey="tokens"
              color={CHART_COLORS[1]}
              formatter={(v) => formatNumber(v)}
            />
          </ChartCard>
        </div>
        <ChartCard title="RAG vs General Queries" empty={!queryMix.some((q) => q.value > 0)}>
          <DonutChart data={queryMix} formatter={(v) => formatNumber(v)} />
        </ChartCard>
      </div>
    </div>
  );
}
