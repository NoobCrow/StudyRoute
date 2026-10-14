import { useState } from "react";
import type { FormEvent } from "react";

import { get } from "../api/client";
import type { ChargeCode, Corridor, SendPlan } from "../api/types";
import { corridorForCurrency, exponentFor, formDefaults } from "../lib/corridors";
import { parseMajorToMinor } from "../lib/money";
import { CurrencyOptions } from "./CountryOptions";
import { SendPlanTable } from "./SendPlanTable";
import { Badge, ErrorNotice, Field } from "./Ui";

/** Smart send plan: how often to send living costs. Fixed fees are paid on every transfer. */
export function SendPlanCard({ corridors }: { corridors: Corridor[] }) {
  const start = corridors.some((c) => c.currency === "GBP") ? "GBP" : (corridors[0]?.currency ?? "GBP");
  const [currency, setCurrency] = useState(start);
  const [monthly, setMonthly] = useState(() => formDefaults(corridorForCurrency(corridors, start)).sendPlanMonthly);
  const [months, setMonths] = useState("12");
  const [charge, setCharge] = useState<ChargeCode>("OUR");
  const [plan, setPlan] = useState<SendPlan | null>(null);
  const [error, setError] = useState<Error | null>(null);
  const [problem, setProblem] = useState<string | null>(null);

  /** Another currency is a different size of money, so the monthly amount starts again in proportion. */
  function chooseCurrency(next: string) {
    setCurrency(next);
    setMonthly(formDefaults(corridorForCurrency(corridors, next)).sendPlanMonthly);
  }

  async function submit(event: FormEvent) {
    event.preventDefault();
    setError(null);
    const amount = parseMajorToMinor(monthly, exponentFor(corridors, currency));
    const count = Number(months);
    if (!amount.ok) return setProblem(`Monthly amount: ${amount.error}`);
    if (!Number.isInteger(count) || count < 1 || count > 60) return setProblem("Months: enter a whole number from 1 to 60.");
    setProblem(null);
    try {
      setPlan(
        await get<SendPlan>(
          `/planner/send-plan?monthly_minor=${amount.minor}&months=${count}&currency=${currency}&charge_code=${charge}`,
        ),
      );
    } catch (e) {
      setError(e as Error);
    }
  }

  return (
    <section className="card" aria-labelledby="sendplan-title">
      <div className="row between">
        <h2 id="sendplan-title">Smart send plan</h2>
        <Badge tone="neutral">Indicative</Badge>
      </div>
      <p className="muted">
        Monthly or all at once? Fixed and SWIFT fees are paid on every transfer, so how often you send changes the real cost.
      </p>
      <form onSubmit={submit}>
        <div className="form-grid">
          <Field label="Currency" htmlFor="sp-currency">
            <select id="sp-currency" value={currency} onChange={(e) => chooseCurrency(e.target.value)}>
              <CurrencyOptions corridors={corridors} />
            </select>
          </Field>
          <Field label="Needed each month" htmlFor="sp-monthly">
            <input id="sp-monthly" inputMode="decimal" value={monthly} onChange={(e) => setMonthly(e.target.value)} />
          </Field>
          <Field label="Months to cover" htmlFor="sp-months">
            <input id="sp-months" inputMode="numeric" value={months} onChange={(e) => setMonths(e.target.value)} />
          </Field>
          <Field label="Charge code" htmlFor="sp-charge">
            <select id="sp-charge" value={charge} onChange={(e) => setCharge(e.target.value as ChargeCode)}>
              <option value="OUR">OUR (sender pays all)</option>
              <option value="SHA">SHA (shared)</option>
              <option value="BEN">BEN (beneficiary pays all)</option>
            </select>
          </Field>
        </div>
        {problem ? <p className="error-text" role="alert">{problem}</p> : null}
        <button type="submit" className="btn">Compare ways to send</button>
      </form>
      <ErrorNotice error={error} />
      {plan ? <SendPlanTable plan={plan} /> : null}
    </section>
  );
}
