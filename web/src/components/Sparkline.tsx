/** Tiny inline trend line; green when the last value is above the first. */
export function Sparkline({
  values,
  width = 80,
  height = 22,
  invert = false,
}: {
  values: number[];
  width?: number;
  height?: number;
  /** For series where rising is bad (e.g. mortgage rates). */
  invert?: boolean;
}) {
  if (values.length < 2) return <svg width={width} height={height} aria-hidden />;
  const min = Math.min(...values);
  const max = Math.max(...values);
  const span = max - min || 1;
  const pts = values
    .map((v, i) => {
      const x = (i / (values.length - 1)) * (width - 2) + 1;
      const y = height - 1 - ((v - min) / span) * (height - 2);
      return `${x.toFixed(1)},${y.toFixed(1)}`;
    })
    .join(" ");
  const rising = values[values.length - 1]! >= values[0]!;
  const good = invert ? !rising : rising;
  return (
    <svg width={width} height={height} aria-hidden className="spark">
      <polyline
        points={pts}
        fill="none"
        stroke={good ? "var(--up)" : "var(--down)"}
        strokeWidth={1.25}
        strokeLinejoin="round"
      />
    </svg>
  );
}
