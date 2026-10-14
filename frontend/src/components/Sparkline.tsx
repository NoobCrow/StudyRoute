import { useState } from "react";
import type { KeyboardEvent, PointerEvent } from "react";

export interface RatePoint { date: string; rate: string }

const W = 420;
const H = 150;
const PAD = { left: 10, right: 54, top: 14, bottom: 24 };

/** Rates keep their exact text; for axis labels we only cut the string, no number formatting. */
function brief(rate: string): string {
  const dot = rate.indexOf(".");
  return dot < 0 ? rate : rate.slice(0, dot + 3);
}

function shortDate(iso: string): string {
  const d = new Date(`${iso}T00:00:00Z`);
  return Number.isNaN(d.getTime())
    ? iso
    : d.toLocaleDateString("en-GB", { day: "2-digit", month: "short", timeZone: "UTC" });
}

interface Props { points: RatePoint[]; average: string; currency: string }

/**
 * One series, a dashed average reference line and today's point highlighted. The line is 2px,
 * the end marker is 10px with a 2px surface ring, text uses text tokens (never the series
 * colour), and the same values are available as a table. Hover or arrow keys move a crosshair.
 */
export function Sparkline({ points, average, currency }: Props) {
  const [active, setActive] = useState<number | null>(null);
  const n = points.length;
  if (n < 2) return <p className="muted">Not enough history to draw.</p>;

  const values = points.map((p) => Number(p.rate));
  const lo = Math.min(...values);
  const hi = Math.max(...values);
  const avg = Number(average);
  const span = hi - lo || 1;
  const plotW = W - PAD.left - PAD.right;
  const baseY = H - PAD.bottom;
  const x = (i: number) => PAD.left + (i * plotW) / (n - 1);
  const y = (v: number) => PAD.top + (1 - (v - lo) / span) * (baseY - PAD.top);
  const line = values.map((v, i) => `${i === 0 ? "M" : "L"}${x(i).toFixed(1)} ${y(v).toFixed(1)}`).join(" ");
  const area = `${line} L${x(n - 1).toFixed(1)} ${baseY} L${x(0).toFixed(1)} ${baseY} Z`;
  const first = points[0] as RatePoint;
  const last = points[n - 1] as RatePoint;
  const lowest = points[values.indexOf(lo)] as RatePoint;
  const highest = points[values.indexOf(hi)] as RatePoint;
  const label =
    `Synthetic ${currency} rate in BDT per unit over ${n} days. Today ${last.rate}, ` +
    `average ${brief(average)}, lowest ${lowest.rate} on ${lowest.date}, ` +
    `highest ${highest.rate} on ${highest.date}.`;

  function nearest(event: PointerEvent<SVGSVGElement>) {
    const box = event.currentTarget.getBoundingClientRect();
    if (box.width === 0) return;
    const vx = ((event.clientX - box.left) / box.width) * W;
    const index = Math.round(((vx - PAD.left) / plotW) * (n - 1));
    setActive(Math.min(n - 1, Math.max(0, index)));
  }

  function onKey(event: KeyboardEvent<HTMLDivElement>) {
    if (event.key === "ArrowLeft") setActive((a) => Math.max(0, (a ?? n) - 1));
    else if (event.key === "ArrowRight") setActive((a) => Math.min(n - 1, (a ?? -1) + 1));
    else if (event.key === "Escape") setActive(null);
    else return;
    event.preventDefault();
  }

  const shown = active === null ? null : (points[active] as RatePoint);
  const tipX = active === null ? 0 : active > n / 2 ? x(active) - 130 : x(active) + 10;

  return (
    <div className="spark-wrap" tabIndex={0} onKeyDown={onKey} onBlur={() => setActive(null)} aria-describedby="spark-live">
      <svg className="spark" viewBox={`0 0 ${W} ${H}`} role="img" aria-label={label} onPointerMove={nearest} onPointerLeave={() => setActive(null)}>
        <line className="grid" x1={PAD.left} x2={W - PAD.right} y1={baseY} y2={baseY} />
        <path className="area" d={area} />
        <line className="avg" x1={PAD.left} x2={W - PAD.right} y1={y(avg)} y2={y(avg)} />
        <path className="line" d={line} />
        <text x={W - PAD.right + 6} y={y(avg) + 4}>avg {brief(average)}</text>
        <text x={W - PAD.right + 6} y={PAD.top + 4}>{brief(String(hi))}</text>
        <text x={W - PAD.right + 6} y={baseY}>{brief(String(lo))}</text>
        <text x={PAD.left} y={H - 6}>{shortDate(first.date)}</text>
        <text x={W - PAD.right} y={H - 6} textAnchor="end">today</text>
        <circle className="dot" cx={x(n - 1)} cy={y(values[n - 1] as number)} r="5" />
        {shown && active !== null ? (
          <g>
            <line className="cross" x1={x(active)} x2={x(active)} y1={PAD.top} y2={baseY} />
            <circle className="dot" cx={x(active)} cy={y(values[active] as number)} r="5" />
            <g transform={`translate(${tipX} ${PAD.top})`}>
              <rect className="tip-bg" width="120" height="38" rx="6" />
              <text className="tip-value" x="8" y="17">{shown.rate}</text>
              <text className="tip-sub" x="8" y="31">{shown.date}</text>
            </g>
          </g>
        ) : null}
        {points.map((p, i) => (
          <rect key={p.date} className="hit" x={x(i) - plotW / (n - 1) / 2} y={0} width={plotW / (n - 1)} height={H} />
        ))}
      </svg>
      <span id="spark-live" className="sr-only" aria-live="polite">
        {shown ? `${shown.date}: ${shown.rate}` : ""}
      </span>
      <details>
        <summary>Show the {n} values as a table</summary>
        <div className="table-wrap" tabIndex={0} role="region" aria-label="Rate history data table">
          <table>
            <thead><tr><th>Date</th><th className="num">BDT per 1 {currency} (synthetic)</th></tr></thead>
            <tbody>
              {[...points].reverse().map((p) => (
                <tr key={p.date}><td>{p.date}</td><td className="num">{p.rate}</td></tr>
              ))}
            </tbody>
          </table>
        </div>
      </details>
    </div>
  );
}
