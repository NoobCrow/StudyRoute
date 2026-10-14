import { useState } from "react";
import type { FormEvent } from "react";

import { get } from "../api/client";
import type { Corridor, RunwayView } from "../api/types";
import { parseMajorToMinor } from "../lib/money";
import { Badge, ErrorNotice, Field, NotVerifiedBadge } from "./Ui";

/** F9 living-cost runway: how many months an amount covers. The engine does the arithmetic. */
export function RunwayCard({ corridors }: { corridors: Corridor[] }) {
  const currencies = [...new Set(corridors.map((c) => c.currency))];
  const [currency, setCurrency] = useState(currencies[0] ?? "GBP");
  const [amount, setAmount] = useState("5000");
  const [monthly, setMonthly] = useState("1200");
  const [result, setResult] = useState<RunwayView | null>(null);
  const [error, setError] = useState<Error | null>(null);
  const [problem, setProblem] = useState<string | null>(null);

  async function submit(event: FormEvent) {
    event.preventDefault();
    setError(null);
    const total = parseMajorToMinor(amount);
    const cost = parseMajorToMinor(monthly);
    if (!total.ok) return setProblem(`Amount: ${total.error}`);
    if (!cost.ok) return setProblem(`Monthly cost: ${cost.error}`);
    setProblem(null);
    try {
      setResult(
        await get<RunwayView>(
          `/planner/runway?amount_minor=${total.minor}&monthly_cost_minor=${cost.minor}&currency=${currency}`,
        ),
      );
    } catch (e) {
      setError(e as Error);
    }
  }

  return (
    <section className="card" aria-labelledby="runway-title">
      <div className="row between">
        <h2 id="runway-title">Living-cost runway</h2>
        <Badge tone="neutral">Indicative</Badge>
      </div>
      <form onSubmit={submit}>
        <div className="form-grid">
          <Field label="Currency" htmlFor="rw-currency">
            <select id="rw-currency" value={currency} onChange={(e) => setCurrency(e.target.value)}>
              {currencies.map((c) => <option key={c} value={c}>{c}</option>)}
            </select>
          </Field>
          <Field label="Amount sent" htmlFor="rw-amount">
            <input id="rw-amount" inputMode="decimal" value={amount} onChange={(e) => setAmount(e.target.value)} />
          </Field>
          <Field label="Monthly living cost" htmlFor="rw-monthly">
            <input id="rw-monthly" inputMode="decimal" value={monthly} onChange={(e) => setMonthly(e.target.value)} />
          </Field>
        </div>
        {problem ? <p className="error-text" role="alert">{problem}</p> : null}
        <button type="submit" className="btn">Calculate runway</button>
      </form>
      <ErrorNotice error={error} />
      {result ? (
        <dl className="kv">
          <dt>Covers</dt><dd><strong>{result.display.covers}</strong></dd>
          <dt>Full months</dt><dd>{result.display.full_months}</dd>
          <dt>Left over</dt><dd>{result.display.leftover}</dd>
          <dt>Monthly cost in USD</dt><dd>{result.monthly_cost_usd_equivalent}</dd>
          <dt>Reference</dt>
          <dd>
            {result.reference.value} per month {result.reference.badge ? <NotVerifiedBadge /> : null}
            <div className="small muted">{result.reference.note}</div>
          </dd>
        </dl>
      ) : null}
    </section>
  );
}
