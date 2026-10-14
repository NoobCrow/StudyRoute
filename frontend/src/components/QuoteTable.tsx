import type { Quote, QuoteResult } from "../api/types";
import { Badge } from "./Ui";

interface Props {
  quote: Quote;
  selected: string | null;
  onSelect?: (providerId: string) => void;
}

function Shortfall({ result }: { result: QuoteResult }) {
  if (result.shortfall_foreign_minor <= 0) return <span className="muted">None</span>;
  return (
    <span className="badge danger" role="alert">
      Short by {result.display.shortfall}
    </span>
  );
}

function rowClass(result: QuoteResult): string | undefined {
  if (result.rank === 1) return "best";
  return result.shortfall_foreign_minor > 0 ? "fail" : undefined;
}

/** F1 provider comparator: ranked by true total cost percentage, hidden margin included. */
export function QuoteTable({ quote, selected, onSelect }: Props) {
  return (
    <div className="table-wrap" tabIndex={0} role="region" aria-label="Provider comparison table">
      <table>
        <caption className="sr-only">Providers ranked by true total cost percentage</caption>
        <thead>
          <tr>
            {onSelect ? <th scope="col"><span className="sr-only">Choose</span></th> : null}
            <th scope="col">Rank</th>
            <th scope="col">Provider</th>
            <th scope="col" className="num">Rate (BDT per {quote.target.currency})</th>
            <th scope="col" className="num">Hidden margin</th>
            <th scope="col">Shortfall risk</th>
            <th scope="col" className="num">Total cost</th>
            <th scope="col" className="num">Cost %</th>
            <th scope="col" className="num">You pay</th>
            <th scope="col" className="num">Days</th>
          </tr>
        </thead>
        <tbody>
          {quote.results.map((r) => (
            <tr key={r.provider_id} className={rowClass(r)}>
              {onSelect ? (
                <td>
                  <input
                    type="radio"
                    name="provider"
                    aria-label={`Choose ${r.provider_name}`}
                    checked={selected === r.provider_id}
                    onChange={() => onSelect(r.provider_id)}
                  />
                </td>
              ) : null}
              <td>
                {r.rank}
                {r.rank === 1 ? <> <Badge tone="ok">Lowest cost</Badge></> : null}
              </td>
              <td className="provider-cell">
                <strong>{r.provider_name}</strong>
                <div className="small muted">
                  Charge code {r.charge_code}
                  {r.charge_code !== r.requested_charge_code ? ` (you asked for ${r.requested_charge_code})` : ""}
                </div>
                {r.warnings.map((w) => (
                  <div key={w.code} className="small error-text">{w.message}</div>
                ))}
              </td>
              <td className="num">{r.display.provider_rate}</td>
              <td className="num">{r.display.margin_pct}</td>
              <td><Shortfall result={r} /></td>
              <td className="num">{r.display.total_cost}</td>
              <td className="num"><strong>{r.display.cost_pct}</strong></td>
              <td className="num">{r.display.parent_pays}</td>
              <td className="num">{r.eta_business_days}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
