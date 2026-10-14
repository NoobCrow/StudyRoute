import { useState } from "react";

import { get, post } from "../api/client";
import type { Page, PaymentBrief, SandboxInfo } from "../api/types";
import { useAuth } from "../auth/AuthContext";
import { Badge, ErrorNotice, Loading, Notice, PageHead, StateBadge } from "../components/Ui";
import { useAsync, usePolling } from "../hooks";

type Outcome = "settle" | "fail";

/** Reviewer control: bring the simulated provider's signed webhook forward. */
function ProviderControl() {
  const flights = useAsync(() => get<Page<PaymentBrief>>("/payments?limit=50"), []);
  const [error, setError] = useState<Error | null>(null);
  const [message, setMessage] = useState<string | null>(null);
  const [busy, setBusy] = useState<string | null>(null);
  usePolling(flights.reload, 3000, true);
  const inFlight = (flights.data?.items ?? []).filter((p) => p.state === "SUBMITTED");

  async function trigger(paymentId: string, outcome: Outcome) {
    setBusy(paymentId);
    setError(null);
    try {
      const reply = await post<{ event: string; note: string }>(
        `/sandbox/payments/${paymentId}/provider-event`,
        { outcome },
      );
      setMessage(`${reply.event} scheduled. ${reply.note}`);
    } catch (e) {
      setError(e as Error);
    } finally {
      setBusy(null);
      flights.reload();
    }
  }

  return (
    <section className="card" aria-labelledby="control-title">
      <h2 id="control-title">Simulated provider control</h2>
      <p className="muted">
        Settle or fail a payment that is in flight. The simulator still sends a real HMAC-signed
        webhook, so the same verification and state machine run. The action is written to the audit log.
      </p>
      <ErrorNotice error={error ?? flights.error} />
      {message ? <Notice tone="ok">{message}</Notice> : null}
      {inFlight.length === 0 ? (
        <p className="muted">
          No payment is in flight right now. Approve one as the parent; a recipient named
          SLOW_TEST keeps it in flight long enough to try this.
        </p>
      ) : (
        <ul className="stack">
          {inFlight.map((p) => (
            <li key={p.payment_id} className="row between">
              <span>
                <strong>{p.recipient_label}</strong> {p.target.formatted} <StateBadge state={p.state} />
              </span>
              <span className="row">
                <button type="button" className="btn small" disabled={busy !== null} onClick={() => void trigger(p.payment_id, "settle")}>
                  Settle now
                </button>
                <button type="button" className="btn small danger" disabled={busy !== null} onClick={() => void trigger(p.payment_id, "fail")}>
                  Fail now
                </button>
              </span>
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}

export function SandboxScreen() {
  const { user } = useAuth();
  const info = useAsync(() => get<SandboxInfo>("/sandbox", { auth: false }), []);
  const data = info.data;
  const canControl = user?.permissions.includes("sandbox:control") ?? false;

  return (
    <div className="stack">
      <PageHead title="Sandbox">
        What is simulated, how to try the edge cases, and the timings behind the demo.
      </PageHead>
      <ErrorNotice error={info.error} />
      {info.loading && !data ? <Loading /> : null}
      {data ? (
        <>
          <Notice tone="info" title={data.banner}>{data.disclaimer}</Notice>
          <section className="card" aria-labelledby="sim-title">
            <h2 id="sim-title">What is simulated</h2>
            <div className="table-wrap">
              <table>
                <thead><tr><th scope="col">Part</th><th scope="col">What it does here</th></tr></thead>
                <tbody>
                  {data.simulated.map((s) => (
                    <tr key={s.component}><td><strong>{s.component}</strong></td><td>{s.what}</td></tr>
                  ))}
                </tbody>
              </table>
            </div>
          </section>
          <section className="card" aria-labelledby="scenario-title">
            <h2 id="scenario-title">Test scenarios</h2>
            <div className="table-wrap">
              <table>
                <thead><tr><th scope="col">Type this</th><th scope="col">Where</th><th scope="col">What happens</th></tr></thead>
                <tbody>
                  {data.scenarios.map((s) => (
                    <tr key={s.token}><td><code>{s.token}</code></td><td>{s.where}</td><td>{s.effect}</td></tr>
                  ))}
                </tbody>
              </table>
            </div>
          </section>
          <div className="grid two">
            <section className="card" aria-labelledby="timing-title">
              <h2 id="timing-title">Timings and caps</h2>
              <dl className="kv">
                <dt>Quote is valid</dt><dd>{data.timings.quote_ttl_seconds} seconds</dd>
                <dt>MFA proof is valid</dt><dd>{data.timings.mfa_proof_ttl_seconds} seconds</dd>
                <dt>Simulated KYC review</dt><dd>{data.timings.kyc_review_seconds} seconds</dd>
                <dt>Submitted after approval</dt><dd>{data.timings.submit_delay_seconds} seconds</dd>
                <dt>Settles after submit</dt><dd>{data.timings.settle_delay_seconds} seconds ({data.timings.slow_settle_delay_seconds} for SLOW_TEST)</dd>
                <dt>Per-payment cap</dt><dd>USD {data.limits.per_transaction_usd_equivalent.toLocaleString("en-US")} equivalent</dd>
                <dt>Daily cap</dt><dd>USD {data.limits.daily_usd_equivalent.toLocaleString("en-US")} equivalent</dd>
              </dl>
              <p className="small muted">{data.limits.indicative} Indicative. Confirm with your AD bank.</p>
            </section>
            <section className="card" aria-labelledby="providers-title">
              <h2 id="providers-title">Providers and assistant</h2>
              <ul>
                {data.providers.map((p) => <li key={p.provider_id}>{p.name} <code>{p.provider_id}</code></li>)}
              </ul>
              <p>
                Assistant mode:{" "}
                <Badge tone={data.ai_mode === "llm" ? "info" : "warn"}>
                  {data.ai_mode === "llm" ? "Model" : "Template mode"}
                </Badge>
              </p>
              {data.demo ? (
                <p className="small">
                  Demo password <code>{data.demo.password}</code>, MFA code <code>{data.demo.mfa_code}</code>.
                </p>
              ) : null}
            </section>
          </div>
        </>
      ) : null}
      {canControl ? <ProviderControl /> : null}
    </div>
  );
}
