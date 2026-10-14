import { useState } from "react";
import { Link } from "react-router-dom";

import { get } from "../api/client";
import type { Page, PaymentBrief } from "../api/types";
import { useAuth } from "../auth/AuthContext";
import { ErrorNotice, Loading, PageHead, StateBadge } from "../components/Ui";
import { useAsync } from "../hooks";
import { formatDate, formatDateTime } from "../lib/format";

export function PaymentsScreen() {
  const { user } = useAuth();
  const first = useAsync(() => get<Page<PaymentBrief>>("/payments?limit=20"), []);
  const [more, setMore] = useState<PaymentBrief[]>([]);
  const [cursor, setCursor] = useState<string | number | null | undefined>(undefined);
  const [error, setError] = useState<Error | null>(null);
  const [busy, setBusy] = useState(false);

  const items = [...(first.data?.items ?? []), ...more];
  const next = cursor === undefined ? (first.data?.next_cursor ?? null) : cursor;

  async function loadMore() {
    if (next === null) return;
    setBusy(true);
    setError(null);
    try {
      const page = await get<Page<PaymentBrief>>(`/payments?limit=20&cursor=${encodeURIComponent(String(next))}`);
      setMore((m) => [...m, ...page.items]);
      setCursor(page.next_cursor);
    } catch (e) {
      setError(e as Error);
    } finally {
      setBusy(false);
    }
  }

  const canCompare = user?.permissions.includes("quotes:create") ?? false;
  return (
    <div className="stack">
      <PageHead
        title="Payments"
        actions={canCompare ? <Link className="btn primary" to="/compare">New comparison</Link> : null}
      >
        Every payment here is simulated. Nothing is sent to a real bank.
      </PageHead>
      <ErrorNotice error={first.error ?? error} />
      {first.loading && !first.data ? <Loading /> : null}
      {first.data && items.length === 0 ? (
        <div className="card">
          <p>No payments yet.</p>
          {canCompare ? <Link to="/compare">Compare providers to start one.</Link> : null}
        </div>
      ) : null}
      {items.length > 0 ? (
        <div className="table-wrap" tabIndex={0} role="region" aria-label="Payments table">
          <table>
            <thead>
              <tr>
                <th scope="col">Recipient and reference</th>
                <th scope="col">Provider</th>
                <th scope="col">State</th>
                <th scope="col" className="num">Beneficiary gets</th>
                <th scope="col" className="num">You pay</th>
                <th scope="col">Due</th>
                <th scope="col">Updated</th>
              </tr>
            </thead>
            <tbody>
              {items.map((p) => (
                <tr key={p.payment_id}>
                  <td>
                    <Link to={`/payments/${p.payment_id}`}>{p.recipient_label}</Link>
                    <div className="small muted">{p.reference}</div>
                  </td>
                  <td>{p.provider_name}</td>
                  <td><StateBadge state={p.state} /></td>
                  <td className="num">{p.target.formatted}</td>
                  <td className="num">{p.parent_pays}</td>
                  <td className="nowrap">{formatDate(p.due_date)}</td>
                  <td className="nowrap">{formatDateTime(p.updated_at)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ) : null}
      {next !== null && items.length > 0 ? (
        <div>
          <button type="button" className="btn" disabled={busy} onClick={() => void loadMore()}>
            {busy ? "Loading" : "Load more"}
          </button>
        </div>
      ) : null}
    </div>
  );
}
