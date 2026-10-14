import { useState } from "react";

import { get } from "../api/client";
import type { Corridor, PlanView } from "../api/types";
import { formatDate } from "../lib/format";
import { addDaysIso } from "../lib/format";
import { useAsync } from "../hooks";
import { Badge, ErrorNotice, Field, Loading, Notice } from "./Ui";

const STATUS = {
  ON_TRACK: { tone: "ok", text: "On track" },
  TIGHT: { tone: "warn", text: "Tight: using the buffer" },
  AT_RISK: { tone: "warn", text: "At risk: buffer used up" },
  LATE: { tone: "danger", text: "Too late for normal settlement" },
} as const;

/** F3 deadline planner: works back from the university due date over both countries' calendars. */
export function PlannerCard({ corridors }: { corridors: Corridor[] }) {
  const [due, setDue] = useState(() => addDaysIso(14));
  const [country, setCountry] = useState("GB");
  const plan = useAsync(
    () => (due ? get<PlanView>(`/planner/deadline?due_date=${due}&country=${country}`) : Promise.resolve(null)),
    [due, country],
  );
  const data = plan.data;
  const badge = data ? STATUS[data.status] : null;

  return (
    <section className="card" aria-labelledby="planner-title">
      <h2 id="planner-title">Deadline planner</h2>
      <div className="form-grid">
        <Field label="University due date" htmlFor="due-date" hint="The date the university must have the money.">
          <input id="due-date" type="date" value={due} onChange={(e) => setDue(e.target.value)} />
        </Field>
        <Field label="Destination" htmlFor="plan-country">
          <select id="plan-country" value={country} onChange={(e) => setCountry(e.target.value)}>
            {corridors.map((c) => <option key={c.country} value={c.country}>{c.name}</option>)}
          </select>
        </Field>
      </div>
      <ErrorNotice error={plan.error} />
      {plan.loading && !data ? <Loading what="Planning" /> : null}
      {data && badge ? (
        <>
          <p className="row">
            <Badge tone={badge.tone}>{badge.text}</Badge>
            <span className="muted small">{data.days_until_latest_send} calendar days until the latest send date</span>
          </p>
          <dl className="kv">
            <dt>Latest send date</dt><dd><strong>{formatDate(data.latest_send_date)}</strong></dd>
            <dt>Recommended</dt><dd>{formatDate(data.recommended_send_date)}</dd>
            <dt>Earliest if sent now</dt><dd>{formatDate(data.earliest_send_date)} (after the {data.bank_cutoff_local} Dhaka cut-off a payment counts the next business day)</dd>
            <dt>Assumes</dt><dd>{data.settlement_business_days} business days to settle plus {data.buffer_days} days of buffer</dd>
          </dl>
          {data.warnings.map((w) => (
            <Notice key={w.code} tone={w.code === "HOLIDAY_OVERLAP" || w.code === "KYC_PENDING" ? "info" : "warn"}>{w.message}</Notice>
          ))}
          {data.skipped_days.length > 0 ? (
            <details>
              <summary>{data.skipped_days.length} non-working days skipped</summary>
              <ul className="small">
                {data.skipped_days.map((d) => <li key={d.date}>{formatDate(d.date)}: {d.reasons.join(", ")}</li>)}
              </ul>
            </details>
          ) : null}
          <p className="small muted">{data.indicative}</p>
        </>
      ) : null}
    </section>
  );
}
