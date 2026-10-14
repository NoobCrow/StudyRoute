import { useState } from "react";

import { get } from "../api/client";
import type { RateHistory } from "../api/types";
import { useAsync } from "../hooks";
import { Sparkline } from "./Sparkline";
import { Badge, ErrorNotice, Loading } from "./Ui";

const TONE = { SEND_NOW: "ok", WAIT_MAY_HELP: "warn", NEUTRAL: "info" } as const;
const WORDS = {
  SEND_NOW: "Today looks better",
  WAIT_MAY_HELP: "Waiting may help",
  NEUTRAL: "About average",
} as const;
const ALERT_KEY = "sr.rate-alert";

function readAlert(currency: string): string {
  try {
    return localStorage.getItem(`${ALERT_KEY}.${currency}`) ?? "";
  } catch {
    return "";
  }
}

/** F10: synthetic rate history, a best-day hint (never a forecast) and a local rate alert. */
export function RateCard({ currency }: { currency: string }) {
  const history = useAsync(() => get<RateHistory>(`/rates/history?currency=${currency}`), [currency]);
  const [target, setTarget] = useState(() => readAlert(currency));
  const data = history.data;

  function saveTarget(value: string) {
    setTarget(value);
    try {
      localStorage.setItem(`${ALERT_KEY}.${currency}`, value);
    } catch {
      /* alerts are a per-browser convenience; losing one is harmless */
    }
  }

  const triggered = data !== null && target !== "" && Number(data.hint.today) <= Number(target);

  return (
    <section className="card" aria-labelledby="rate-title">
      <div className="row between">
        <h2 id="rate-title">{currency} rate and best-day hint</h2>
        <Badge tone="neutral">Synthetic data</Badge>
      </div>
      <ErrorNotice error={history.error} />
      {history.loading && !data ? <Loading what="Loading rates" /> : null}
      {data ? (
        <>
          <p className="row">
            <Badge tone={TONE[data.hint.kind]}>{WORDS[data.hint.kind]}</Badge>
            <span className="small muted">
              {data.hint.gap_pct}% vs the {data.hint.days}-day average
            </span>
          </p>
          <p>{data.hint.message}</p>
          <Sparkline points={data.points} average={data.hint.average} currency={currency} />
          <div className="field">
            <label htmlFor={`alert-${currency}`}>
              Rate alert: tell me when the synthetic rate is at or below
            </label>
            <input
              id={`alert-${currency}`}
              inputMode="decimal"
              value={target}
              onChange={(e) => saveTarget(e.target.value)}
              placeholder={data.hint.average}
            />
            <span className="hint">Saved in this browser only. A lower rate is better for you.</span>
          </div>
          {triggered ? (
            <div className="notice ok" role="status">
              Alert: today's synthetic rate {data.hint.today} is at or below your {target}.
            </div>
          ) : null}
          <p className="small muted">{data.disclaimer}</p>
        </>
      ) : null}
    </section>
  );
}
