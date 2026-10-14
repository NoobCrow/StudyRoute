import { useState } from "react";
import { Link, useParams } from "react-router-dom";

import { get } from "../api/client";
import type { ComplianceReport, ControlResult } from "../api/types";
import { Badge, ErrorNotice, Loading, Notice, PageHead, StateBadge } from "../components/Ui";
import { useAsync } from "../hooks";
import { reportIsIntact } from "../lib/canonical";
import { formatDate, formatDateTime, shortHash } from "../lib/format";

const TONE: Record<ControlResult, "ok" | "warn" | "danger" | "neutral"> = {
  PASS: "ok", PENDING: "warn", NOT_YET: "neutral", BLOCKED: "danger", FAIL: "danger",
};
const WORDS: Record<ControlResult, string> = {
  PASS: "Pass", PENDING: "Pending", NOT_YET: "Not yet", BLOCKED: "Blocked", FAIL: "Fail",
};

function download(report: ComplianceReport): void {
  const blob = new Blob([JSON.stringify(report, null, 2)], { type: "application/json" });
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = `compliance-report-${report.payment.payment_id}.json`;
  link.click();
  URL.revokeObjectURL(url);
}

/** A regulator-style evidence pack for one payment. Synthetic data; reading it changes nothing. */
export function ReportScreen() {
  const { paymentId = "" } = useParams();
  const result = useAsync(() => get<ComplianceReport>(`/payments/${paymentId}/compliance-report`), [paymentId]);
  const [intact, setIntact] = useState<boolean | null>(null);
  const report = result.data;

  async function verify() {
    if (report) setIntact(await reportIsIntact(report as unknown as { report_hash: string } & Record<string, unknown>));
  }

  if (result.loading && !report) return <Loading what="Building the report" />;
  if (!report) {
    return (
      <div className="stack">
        <ErrorNotice error={result.error} />
        <Link to={`/payments/${paymentId}`}>Back to the payment</Link>
      </div>
    );
  }
  const { payment, amount, parties, approval, audit } = report;
  return (
    <div className="stack report">
      <PageHead
        title="Compliance report"
        actions={
          <span className="row no-print">
            <button type="button" className="btn" onClick={() => window.print()}>Print or save as PDF</button>
            <button type="button" className="btn" onClick={() => download(report)}>Download JSON</button>
          </span>
        }
      >
        Evidence for one payment: who is involved, every control and its result, the approval proof and the audit trail.
      </PageHead>
      <Notice tone="info" title="Sandbox report">{report.disclaimer}</Notice>

      <section className="card" aria-labelledby="rep-payment">
        <div className="row between">
          <h2 id="rep-payment">Payment {payment.payment_id}</h2>
          <StateBadge state={payment.state} />
        </div>
        <dl className="kv">
          <dt>Reference</dt><dd>{payment.reference}</dd>
          <dt>Provider</dt><dd>{payment.provider_name}</dd>
          <dt>Beneficiary receives</dt><dd><strong>{amount.beneficiary_receives}</strong></dd>
          <dt>Rate and charge code</dt><dd>{amount.rate} BDT, {amount.charge_code}</dd>
          <dt>Total cost</dt><dd>{amount.total_cost} ({amount.cost_pct}%)</dd>
          <dt>Parent pays</dt><dd>{amount.parent_pays}</dd>
          <dt>UETR</dt><dd className="mono mono-wrap">{payment.uetr ?? "Not assigned yet"}</dd>
          <dt>Due and latest send</dt><dd>{formatDate(payment.due_date)} and {formatDate(payment.latest_send_date)}</dd>
          <dt>Created, settled</dt><dd>{formatDateTime(payment.created_at)}, {formatDateTime(payment.settled_at)}</dd>
        </dl>
        {payment.failure_reason ? <Notice tone="danger" title="Did not complete">{payment.failure_reason}</Notice> : null}
      </section>

      <div className="grid two">
        <section className="card" aria-labelledby="rep-orig">
          <h2 id="rep-orig">Originator</h2>
          <dl className="kv">
            <dt>Name</dt><dd>{parties.originator.name}</dd>
            <dt>Address</dt><dd>{parties.originator.address}</dd>
            <dt>Country</dt><dd>{parties.originator.country}</dd>
          </dl>
        </section>
        <section className="card" aria-labelledby="rep-benef">
          <h2 id="rep-benef">Beneficiary</h2>
          <dl className="kv">
            <dt>Name</dt><dd>{parties.beneficiary.name}</dd>
            <dt>Account</dt><dd className="mono">{parties.beneficiary.account_masked}</dd>
            <dt>BIC</dt><dd className="mono">{parties.beneficiary.bic}</dd>
            <dt>Country</dt><dd>{parties.beneficiary.country}</dd>
          </dl>
        </section>
      </div>

      <section className="card" aria-labelledby="rep-controls">
        <h2 id="rep-controls">Controls</h2>
        <div className="table-wrap" tabIndex={0} role="region" aria-label="Controls table">
          <table className="controls">
            <thead><tr><th scope="col">Control</th><th scope="col">Result</th><th scope="col">Evidence</th></tr></thead>
            <tbody>
              {report.controls.map((c) => (
                <tr key={c.key}>
                  <td><strong>{c.label}</strong></td>
                  <td><Badge tone={TONE[c.result]}>{WORDS[c.result]}</Badge></td>
                  <td className="small">{c.evidence}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>

      <section className="card" aria-labelledby="rep-approval">
        <h2 id="rep-approval">Approval</h2>
        {approval.approved ? (
          <dl className="kv">
            <dt>Approved by</dt><dd className="mono">{approval.approved_by}</dd>
            <dt>Approved at</dt><dd>{formatDateTime(approval.approved_at)}</dd>
            <dt>MFA proof</dt><dd className="mono">{approval.mfa_proof_reference}</dd>
            <dt>Summary hash</dt><dd className="mono mono-wrap">{approval.summary_hash}</dd>
          </dl>
        ) : (
          <p className="muted">Not approved yet. Only a human parent can approve, with a fresh MFA code.</p>
        )}
      </section>

      <section className="card" aria-labelledby="rep-audit">
        <h2 id="rep-audit">Audit trail for this payment</h2>
        <p className="small">
          Chain check: <Badge tone={audit.chain.status === "PASS" ? "ok" : "danger"}>{audit.chain.status}</Badge>{" "}
          {audit.chain.events_checked} events verified, head event {audit.chain.head.seq}{" "}
          <code>{shortHash(audit.chain.head.hash, 12)}</code>
        </p>
        <div className="table-wrap" tabIndex={0} role="region" aria-label="Audit events for this payment table">
          <table>
            <thead><tr><th scope="col" className="num">Seq</th><th scope="col">When</th><th scope="col">Actor</th><th scope="col">Action</th><th scope="col">Hash</th></tr></thead>
            <tbody>
              {audit.events.map((e) => (
                <tr key={e.event_id}>
                  <td className="num">{e.seq}</td>
                  <td className="nowrap">{formatDateTime(e.timestamp)}</td>
                  <td>{e.actor_type}</td>
                  <td><code>{e.action}</code>{e.reason_code ? <div className="small muted">{e.reason_code}</div> : null}</td>
                  <td className="mono small">{shortHash(e.this_event_hash, 8)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>

      <section className="card" aria-labelledby="rep-hash">
        <h2 id="rep-hash">Report integrity</h2>
        <p className="small">
          Generated {formatDateTime(report.generated_at)}. The hash below is the SHA-256 of this report as JSON with sorted
          keys and no whitespace, without the hash field itself. Any edit to a copy changes it.
        </p>
        <p className="mono mono-wrap">{report.report_hash}</p>
        <div className="row no-print">
          <button type="button" className="btn" onClick={() => void verify()}>Verify this report in my browser</button>
          {intact === true ? <Badge tone="ok">Matches: not changed</Badge> : null}
          {intact === false ? <Badge tone="danger">Does not match</Badge> : null}
        </div>
        <p className="no-print"><Link to={`/payments/${payment.payment_id}`}>Back to the payment</Link></p>
      </section>
    </div>
  );
}
