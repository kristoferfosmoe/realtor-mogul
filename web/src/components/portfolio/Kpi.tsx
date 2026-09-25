export function Kpi({
  label,
  value,
  sub,
  tone = "flat",
  title,
}: {
  label: string;
  value: string;
  sub?: string;
  tone?: "up" | "down" | "flat";
  title?: string;
}) {
  return (
    <div className={`kpi ${tone === "flat" ? "" : tone}`} title={title}>
      <div className="stat-label">{label}</div>
      <div className={`kpi-value num ${tone}`}>{value}</div>
      {sub && <div className="kpi-delta num muted">{sub}</div>}
    </div>
  );
}
