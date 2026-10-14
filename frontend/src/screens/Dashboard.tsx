import { useEffect, useState } from "react";
import { Link } from "react-router-dom";

import { get } from "../api/client";
import type { CorridorList, Page, PaymentBrief } from "../api/types";
import { useAuth } from "../auth/AuthContext";
import { CurrencyOptions } from "../components/CountryOptions";
import { KycCard } from "../components/KycCard";
import { PlannerCard } from "../components/PlannerCard";
import { RateCard } from "../components/RateCard";
import { ResetCard } from "../components/ResetCard";
import { RunwayCard } from "../components/RunwayCard";
import { SendPlanCard } from "../components/SendPlanCard";
import { ErrorNotice, Field, Loading, Notice, PageHead, StateBadge } from "../components/Ui";
import { loadHealth } from "../health";
import { useAsync } from "../hooks";
import { formatDateTime } from "../lib/format";

function RecentPayments({ items }: { items: PaymentBrief[] }) {
  if (items.length === 0) {
    return <p className="muted">No payments yet. Start by comparing providers.</p>;
  }
  return (
    <div className="table-wrap" tabIndex={0} role="region" aria-label="Recent payments table">
      <table>
        <thead>
          <tr>
            <th scope="col">Payment</th>
            <th scope="col">State</th>
            <th scope="col" className="num">Beneficiary gets</th>
            <th scope="col" className="num">You pay</th>
            <th scope="col">Updated</th>
          </tr>
        </thead>
        <tbody>
          {items.map((p) => (
            <tr key={p.payment_id}>
              <td><Link to={`/payments/${p.payment_id}`}>{p.recipient_label}</Link><div className="small muted">{p.reference}</div></td>
              <td><StateBadge state={p.state} /></td>
              <td className="num">{p.target.formatted}</td>
              <td className="num">{p.parent_pays}</td>
              <td className="nowrap">{formatDateTime(p.updated_at)}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function ReviewerPanel() {
  const [payerId, setPayerId] = useState("");
  useEffect(() => {
    loadHealth().then((h) => h.demo && setPayerId((current) => current || h.demo?.parent_id || "")).catch(() => undefined);
  }, []);
  return (
    <>
      <section className="card" aria-labelledby="reviewer-title">
        <h2 id="reviewer-title">Reviewer tools</h2>
        <p>
          You can read the audit log, verify its hash chain and manage the rules. You cannot approve
          a family's payment.
        </p>
        <div className="row">
          <Link className="btn primary" to="/audit">Open the audit log</Link>
          <Link className="btn" to="/rules">Manage rules</Link>
          <Link className="btn" to="/payments">All payments</Link>
        </div>
        <Field label="Payer user id" htmlFor="payer-id" hint="Sandbox helper: the demo parent id is filled in for you.">
          <input id="payer-id" value={payerId} onChange={(e) => setPayerId(e.target.value.trim())} />
        </Field>
      </section>
      <KycCard payerId={payerId || undefined} />
    </>
  );
}

export function DashboardScreen() {
  const { user } = useAuth();
  const corridors = useAsync(() => get<CorridorList>("/corridors"), []);
  const recent = useAsync(() => get<Page<PaymentBrief>>("/payments?limit=5"), []);
  const [currency, setCurrency] = useState("GBP");
  if (!user) return null;

  const items = corridors.data?.items ?? [];
  const isAdmin = user.role === "admin";
  const canCompare = user.permissions.includes("quotes:create");
  const canPlan = user.permissions.includes("planner:read");

  return (
    <div className="stack">
      <PageHead
        title={`Hello, ${user.display_name}`}
        actions={canCompare ? <Link className="btn primary" to="/compare">Compare providers</Link> : null}
      >
        Pay tuition and living costs abroad from Bangladesh with clear costs, a safe checklist and a human in control.
      </PageHead>
      {user.payer && user.role === "student" ? (
        <Notice tone="info" title={`Household of ${user.payer.display_name}`}>
          As the student you can look and prepare, but only the paying parent can approve.
        </Notice>
      ) : null}
      <ErrorNotice error={corridors.error ?? recent.error} />
      <div className="grid two">
        {isAdmin ? <ReviewerPanel /> : <KycCard />}
        {canPlan && items.length > 0 ? <PlannerCard corridors={items} /> : null}
        {canPlan && items.length === 0 ? <Loading what="Loading corridors" /> : null}
      </div>
      {!isAdmin ? (
        <section className="card" aria-labelledby="recent-title">
          <div className="row between">
            <h2 id="recent-title">Recent payments</h2>
            <Link to="/payments">See all</Link>
          </div>
          {recent.loading && !recent.data ? <Loading /> : null}
          {recent.data ? <RecentPayments items={recent.data.items} /> : null}
        </section>
      ) : null}
      {canPlan && items.length > 0 ? (
        <div className="grid two">
          <div className="stack">
            <div className="row">
              <label className="small" htmlFor="rate-currency">Rate card currency</label>
              <select id="rate-currency" className="auto-width" value={currency} onChange={(e) => setCurrency(e.target.value)}>
                <CurrencyOptions corridors={items} />
              </select>
            </div>
            <RateCard currency={currency} />
          </div>
          <RunwayCard corridors={items} />
        </div>
      ) : null}
      {canPlan && items.length > 0 ? <SendPlanCard corridors={items} /> : null}
      {user.permissions.includes("data:reset") ? <ResetCard onDone={recent.reload} /> : null}
    </div>
  );
}
