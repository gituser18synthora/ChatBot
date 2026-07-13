import {
  Area,
  AreaChart,
  Bar,
  BarChart,
  Cell,
  Legend,
  Pie,
  PieChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import { EmptyState } from "../ui/primitives";

// A single, consistent, accessible categorical palette used across every chart
// so the dashboard reads as one system.
export const CHART_COLORS = [
  "#335dff", // brand blue
  "#7c5cff", // violet
  "#12b981", // emerald
  "#f59e0b", // amber
  "#f43f5e", // rose
  "#06b6d4", // cyan
  "#8b5cf6",
  "#64748b",
];

const axisProps = {
  tick: { fill: "#94a3b8", fontSize: 12 },
  axisLine: { stroke: "#e2e8f0" },
  tickLine: false,
};

function TooltipBox({ active, payload, label, formatter }: any) {
  if (!active || !payload?.length) return null;
  return (
    <div className="rounded-lg border border-slate-200 bg-white px-3 py-2 text-xs shadow-pop">
      {label != null && <p className="mb-1 font-semibold text-slate-700">{label}</p>}
      {payload.map((p: any, i: number) => (
        <p key={i} className="flex items-center gap-2 text-slate-600">
          <span className="inline-block h-2 w-2 rounded-full" style={{ background: p.color || p.fill }} />
          {p.name}: <span className="font-medium text-slate-800">{formatter ? formatter(p.value) : p.value}</span>
        </p>
      ))}
    </div>
  );
}

export function ChartCard({
  title,
  subtitle,
  children,
  empty,
}: {
  title: string;
  subtitle?: string;
  children: React.ReactNode;
  empty?: boolean;
}) {
  return (
    <div className="card p-5">
      <div className="mb-4">
        <h3 className="text-sm font-semibold text-slate-800">{title}</h3>
        {subtitle && <p className="text-xs text-slate-400">{subtitle}</p>}
      </div>
      {empty ? (
        <div className="flex h-56 items-center justify-center text-sm text-slate-400">No data yet</div>
      ) : (
        <div className="h-56 w-full">{children}</div>
      )}
    </div>
  );
}

export function TrendArea({
  data,
  dataKey,
  xKey,
  color = CHART_COLORS[0],
  formatter,
}: {
  data: any[];
  dataKey: string;
  xKey: string;
  color?: string;
  formatter?: (v: number) => string;
}) {
  return (
    <ResponsiveContainer width="100%" height="100%">
      <AreaChart data={data} margin={{ top: 5, right: 8, left: -12, bottom: 0 }}>
        <defs>
          <linearGradient id={`grad-${dataKey}`} x1="0" y1="0" x2="0" y2="1">
            <stop offset="0%" stopColor={color} stopOpacity={0.28} />
            <stop offset="100%" stopColor={color} stopOpacity={0} />
          </linearGradient>
        </defs>
        <XAxis dataKey={xKey} {...axisProps} />
        <YAxis {...axisProps} width={48} />
        <Tooltip content={<TooltipBox formatter={formatter} />} />
        <Area
          type="monotone"
          dataKey={dataKey}
          stroke={color}
          strokeWidth={2}
          fill={`url(#grad-${dataKey})`}
          dot={false}
          activeDot={{ r: 4 }}
        />
      </AreaChart>
    </ResponsiveContainer>
  );
}

export function BarSeries({
  data,
  dataKey,
  xKey,
  color = CHART_COLORS[0],
  formatter,
}: {
  data: any[];
  dataKey: string;
  xKey: string;
  color?: string;
  formatter?: (v: number) => string;
}) {
  return (
    <ResponsiveContainer width="100%" height="100%">
      <BarChart data={data} margin={{ top: 5, right: 8, left: -12, bottom: 0 }}>
        <XAxis dataKey={xKey} {...axisProps} />
        <YAxis {...axisProps} width={48} />
        <Tooltip cursor={{ fill: "#f1f5f9" }} content={<TooltipBox formatter={formatter} />} />
        <Bar dataKey={dataKey} radius={[6, 6, 0, 0]} maxBarSize={44}>
          {data.map((_, i) => (
            <Cell key={i} fill={color} />
          ))}
        </Bar>
      </BarChart>
    </ResponsiveContainer>
  );
}

export function DonutChart({
  data,
  formatter,
}: {
  data: { name: string; value: number }[];
  formatter?: (v: number) => string;
}) {
  const total = data.reduce((s, d) => s + d.value, 0);
  if (total === 0) {
    return (
      <div className="flex h-full items-center justify-center">
        <EmptyState title="No data yet" />
      </div>
    );
  }
  return (
    <ResponsiveContainer width="100%" height="100%">
      <PieChart>
        <Pie data={data} dataKey="value" nameKey="name" innerRadius={52} outerRadius={80} paddingAngle={2}>
          {data.map((_, i) => (
            <Cell key={i} fill={CHART_COLORS[i % CHART_COLORS.length]} />
          ))}
        </Pie>
        <Tooltip content={<TooltipBox formatter={formatter} />} />
        <Legend
          iconType="circle"
          formatter={(v) => <span className="text-xs text-slate-600">{v}</span>}
        />
      </PieChart>
    </ResponsiveContainer>
  );
}
