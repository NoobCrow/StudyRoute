import type { Quote, QuoteResult } from "../api/types";
import { formatDate } from "../lib/format";
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

function rowClass(result: QuoteResult, bestInTime: string | null | undefined): string | undefined {
  if (bestInTime !== undefined) {
    if (result.provider_id === bestInTime) return "best";
  } else if (result.rank === 1) {
    return "best";
  }
  return result.shortfall_foreign_minor > 0 ? "fail" : undefined;
}

function nameOf(quote: Quote, providerId: string | null): string {
  return quote.results.find((r) => r.provider_id === providerId)?.provider_name ?? "";
}

/** One sentence that says what the deadline changed, built from the engine's answer. */
function DeadlineNote({ quote }: { quote: Quote }) {
  const fit = quote.deadline_fit;
  if (!fit) return null;
  if (fit.best_in_time === null) {
    return (
      <p className="small error-text" role="alert">
        No provider can arrive by {formatDate(fit.due_date)} if the money is sent on {formatDate(fit.send_date)}.
        The fastest is {nameOf(quote, fit.fastest)}. Ask the university whether it can wait.
      </p>
    );
  }
  if (fit.cheapest_misses_deadline) {
    return (
      <p className="small error-text" role="alert">
        {nameOf(quote, fit.cheapest_overall)} has the lowest cost but would arrive after {formatDate(fit.due_date)}.
        The cheapest provider that arrives in time is {nameOf(quote, fit.best_in_time)}.
      </p>
    );
  }
  return (
    <p className="small muted" role="status">
      The lowest-cost provider also arrives by {formatDate(fit.due_date)}. {fit.indicative}
    </p>
  );
}

/** F1 provider comparator: ranked by true total cost percentage, hidden margin included. */
export function QuoteTable({ quote, selected, onSelect }: Props) {
  const fit = quote.deadline_fit ?? null;
  const arrival = new Map((fit?.providers ?? []).map((p) => [p.provider_id, p]));
  return (
    <>
    <DeadlineNote quote={quote} />
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
            <tr key={r.provider_id} className={rowClass(r, fit ? fit.best_in_time : undefined)}>
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
                {fit && fit.best_in_time === r.provider_id && r.rank !== 1 ? <> <Badge tone="ok">Best in time</Badge></> : null}
              </td>
              <td className="provider-cell">
                <strong>{r.provider_name}</strong>
                <div className="small muted">
                  Charge code {r.charge_code}
                  {r.charge_code !== r.requested_charge_code ? ` (you asked for ${r.requested_charge_code})` : ""}
                </div>
                {arrival.get(r.provider_id) ? (
                  <div className="small">
                    Arrives {formatDate(arrival.get(r.provider_id)?.arrives_on)}{" "}
                    <Badge tone={arrival.get(r.provider_id)?.meets_deadline ? "ok" : "danger"}>
                      {arrival.get(r.provider_id)?.meets_deadline ? "In time" : "Too late"}
                    </Badge>
                  </div>
                ) : null}
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
    </>
  );
}
