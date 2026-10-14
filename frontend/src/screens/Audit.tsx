import { useState } from "react";
import { useSearchParams } from "react-router-dom";

import { get } from "../api/client";
import type { AuditEventView, Page, VerifyView } from "../api/types";
import { useAuth } from "../auth/AuthContext";
import { Badge, ErrorNotice, Field, Loading, Notice, PageHead } from "../components/Ui";
import { useAsync } from "../hooks";
import { formatDateTime, shortHash } from "../lib/format";

type AuditPage = Page<AuditEventView> & { scope: string };

function decisionTone(decision: string | null): "ok" | "danger" | "warn" | "neutral" {
  if (decision === "approved") return "ok";
  if (decision === "blocked" || decision === "rejected") return "danger";
  if (decision === "suggested") return "warn";
  return "neutral";
}

function VerifyResult({ result }: { result: VerifyView }) {
  if (result.status === "PASS") {
    return (
      <Notice tone="ok" title="Chain verified: PASS">
        {result.events_checked} events recomputed. Each hash matches and each link points at the one before it.
        Latest event {result.head.seq}: <code>{shortHash(result.head.hash, 16)}</code>.
      </Notice>
    );
  }
  return (
    <Notice tone="danger" title={`Chain verification FAILED at event ${result.failed_seq ?? "?"}`}>
      {result.reason ?? "An event no longer matches its hash."} The log was changed after it was written.
    </Notice>
  );
}

export function AuditScreen() {
  const { user } = useAuth();
  const [params, setParams] = useSearchParams();
  const paymentId = params.get("payment_id") ?? "";
  const action = params.get("action") ?? "";
  const query = new URLSearchParams({ limit: "25" });
  if (paymentId) query.set("payment_id", paymentId);
  if (action) query.set("action", action);

  const first = useAsync(() => get<AuditPage>(`/audit/events?${query.toString()}`), [paymentId, action]);
  const [more, setMore] = useState<AuditEventView[]>([]);
  const [cursor, setCursor] = useState<number | string | null | undefined>(undefined);
  const [verify, setVerify] = useState<VerifyView | null>(null);
  const [error, setError] = useState<Error | null>(null);
  const [busy, setBusy] = useState(false);

  const events = [...(first.data?.items ?? []), ...more];
  const next = cursor === undefined ? (first.data?.next_cursor ?? null) : cursor;
  const canVerify = user?.permissions.includes("audit:verify") ?? false;

  function setFilter(key: string, value: string) {
    const copy = new URLSearchParams(params);
    if (value) copy.set(key, value);
    else copy.delete(key);
    setParams(copy);
    setMore([]);
    setCursor(undefined);
  }

  async function loadMore() {
    if (next === null) return;
    setBusy(true);
    try {
      const page = await get<AuditPage>(`/audit/events?${query.toString()}&cursor=${next}`);
      setMore((m) => [...m, ...page.items]);
      setCursor(page.next_cursor);
    } catch (e) {
      setError(e as Error);
    } finally {
      setBusy(false);
    }
  }

  async function runVerify() {
    setBusy(true);
    setError(null);
    try {
      setVerify(await get<VerifyView>("/audit/verify"));
    } catch (e) {
      setError(e as Error);
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="stack">
      <PageHead
        title="Audit log"
        actions={
          canVerify ? (
            <button type="button" className="btn primary" disabled={busy} onClick={() => void runVerify()}>
              Verify the hash chain
            </button>
          ) : null
        }
      >
        Every state change is written once, in the same transaction, to an append-only log. Each event includes the hash of the one before it.
      </PageHead>
      {!canVerify ? (
        <Notice tone="info">You see {first.data?.scope ?? "your events"}. Only a reviewer can verify the whole chain.</Notice>
      ) : null}
      {verify ? <VerifyResult result={verify} /> : null}
      <ErrorNotice error={first.error ?? error} />
      <div className="form-grid">
        <Field label="Payment id" htmlFor="a-payment">
          <input id="a-payment" value={paymentId} onChange={(e) => setFilter("payment_id", e.target.value.trim())} placeholder="pay_... or btr_..." />
        </Field>
        <Field label="Action" htmlFor="a-action" hint="For example approval.granted or webhook.rejected.">
          <input id="a-action" value={action} onChange={(e) => setFilter("action", e.target.value.trim())} />
        </Field>
      </div>
      {first.loading && !first.data ? <Loading /> : null}
      {events.length > 0 ? (
        <div className="table-wrap" tabIndex={0} role="region" aria-label="Audit events table">
          <table>
            <thead>
              <tr>
                <th scope="col" className="num">Seq</th>
                <th scope="col">When</th>
                <th scope="col">Actor</th>
                <th scope="col">Action</th>
                <th scope="col">Decision</th>
                <th scope="col">Detail</th>
                <th scope="col">Hash</th>
              </tr>
            </thead>
            <tbody>
              {events.map((e) => (
                <tr key={e.event_id} className={verify?.failed_seq === e.seq ? "fail" : undefined}>
                  <td className="num">{e.seq}</td>
                  <td className="nowrap">{formatDateTime(e.timestamp)}</td>
                  <td>{e.actor_type}<div className="small muted mono">{e.actor_id}</div></td>
                  <td><code>{e.action}</code>{e.payment_id ? <div className="small muted mono">{e.payment_id}</div> : null}</td>
                  <td>{e.decision ? <Badge tone={decisionTone(e.decision)}>{e.decision}</Badge> : null}{e.reason_code ? <div className="small muted">{e.reason_code}</div> : null}</td>
                  <td className="small">
                    {e.amount_display ? <div>{e.amount_display}</div> : null}
                    {e.detail}
                    {e.model_version ? <div className="muted">model {e.model_version}</div> : null}
                  </td>
                  <td className="mono small" title={`prev ${e.prev_event_hash}`}>{shortHash(e.this_event_hash, 8)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ) : null}
      {first.data && events.length === 0 ? <p className="muted">No events match.</p> : null}
      {next !== null && events.length > 0 ? (
        <div><button type="button" className="btn" disabled={busy} onClick={() => void loadMore()}>Load older events</button></div>
      ) : null}
      <p className="small muted">
        Tamper-evident, not tamper-proof. For extra strength, publish the latest hash outside the database.
      </p>
    </div>
  );
}
