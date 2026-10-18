"use client";

import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { useState } from "react";

import { KV, KVList } from "@/components/app/key-value";
import { ErrorNotice, Notice } from "@/components/app/notice";
import { PageHead } from "@/components/app/page-head";
import { CardSkeleton } from "@/components/app/skeletons";
import { Chip, StateBadge, type Tone } from "@/components/app/status";
import { Button } from "@/components/ui/button";
import { Card, CardAction, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import type { ComplianceReport, ControlResult } from "@/lib/api/types";
import { useApi } from "@/lib/api/use-api";
import { reportIsIntact } from "@/lib/canonical";
import { formatDate, formatDateTime, shortHash } from "@/lib/format";

const TONE: Record<ControlResult, Tone> = {
  PASS: "ok",
  PENDING: "warn",
  NOT_YET: "neutral",
  BLOCKED: "danger",
  FAIL: "danger",
};
const WORDS: Record<ControlResult, string> = {
  PASS: "Pass",
  PENDING: "Pending",
  NOT_YET: "Not yet",
  BLOCKED: "Blocked",
  FAIL: "Fail",
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
  const paymentId = useSearchParams().get("id") ?? "";
  const result = useApi<ComplianceReport>(
    paymentId ? `/payments/${paymentId}/compliance-report` : null,
  );
  const [intact, setIntact] = useState<boolean | null>(null);
  const report = result.data;
  const back = `/payments/view/?id=${encodeURIComponent(paymentId)}`;

  async function verify() {
    if (report)
      setIntact(
        await reportIsIntact(
          report as unknown as { report_hash: string } & Record<string, unknown>,
        ),
      );
  }

  if (result.loading && !report) return <CardSkeleton lines={6} label="Building the report" />;
  if (!report) {
    return (
      <div className="space-y-4">
        <ErrorNotice error={result.error} onRetry={result.reload} />
        <Link href={back} className="text-primary hover:underline">
          Back to the payment
        </Link>
      </div>
    );
  }
  const { payment, amount, parties, approval, audit } = report;
  return (
    <div className="space-y-6">
      <PageHead
        title="Compliance report"
        actions={
          <span className="flex gap-2 print:hidden">
            <Button type="button" variant="outline" onClick={() => window.print()}>
              Print or save as PDF
            </Button>
            <Button type="button" variant="outline" onClick={() => download(report)}>
              Download JSON
            </Button>
          </span>
        }
      >
        Evidence for one payment: who is involved, every control and its result, the approval proof
        and the audit trail.
      </PageHead>
      <Notice tone="info" title="Sandbox report">
        {report.disclaimer}
      </Notice>

      <Card aria-labelledby="rep-payment">
        <CardHeader>
          <CardTitle id="rep-payment" className="text-base">
            Payment {payment.payment_id}
          </CardTitle>
          <CardAction>
            <StateBadge state={payment.state} />
          </CardAction>
        </CardHeader>
        <CardContent className="space-y-3">
          <KVList>
            <KV label="Reference">{payment.reference}</KV>
            <KV label="Provider">{payment.provider_name}</KV>
            <KV label="Beneficiary receives">
              <strong className="font-semibold">{amount.beneficiary_receives}</strong>
            </KV>
            <KV label="Rate and charge code">
              {amount.rate} BDT, {amount.charge_code}
            </KV>
            <KV label="Total cost">
              {amount.total_cost} ({amount.cost_pct}%)
            </KV>
            <KV label="Parent pays">{amount.parent_pays}</KV>
            <KV label="UETR">
              <span className="font-mono text-xs break-all">
                {payment.uetr ?? "Not assigned yet"}
              </span>
            </KV>
            <KV label="Due and latest send">
              {formatDate(payment.due_date)} and {formatDate(payment.latest_send_date)}
            </KV>
            <KV label="Created, settled">
              {formatDateTime(payment.created_at)}, {formatDateTime(payment.settled_at)}
            </KV>
          </KVList>
          {payment.failure_reason ? (
            <Notice tone="danger" title="Did not complete">
              {payment.failure_reason}
            </Notice>
          ) : null}
        </CardContent>
      </Card>

      <div className="grid gap-6 md:grid-cols-2">
        <Card aria-labelledby="rep-orig">
          <CardHeader>
            <CardTitle id="rep-orig" className="text-base">
              Originator
            </CardTitle>
          </CardHeader>
          <CardContent>
            <KVList>
              <KV label="Name">{parties.originator.name}</KV>
              <KV label="Address">{parties.originator.address}</KV>
              <KV label="Country">{parties.originator.country}</KV>
            </KVList>
          </CardContent>
        </Card>
        <Card aria-labelledby="rep-benef">
          <CardHeader>
            <CardTitle id="rep-benef" className="text-base">
              Beneficiary
            </CardTitle>
          </CardHeader>
          <CardContent>
            <KVList>
              <KV label="Name">{parties.beneficiary.name}</KV>
              <KV label="Account">
                <span className="font-mono">{parties.beneficiary.account_masked}</span>
              </KV>
              <KV label="BIC">
                <span className="font-mono">{parties.beneficiary.bic}</span>
              </KV>
              <KV label="Country">{parties.beneficiary.country}</KV>
            </KVList>
          </CardContent>
        </Card>
      </div>

      <Card aria-labelledby="rep-controls">
        <CardHeader>
          <CardTitle id="rep-controls" className="text-base">
            Controls
          </CardTitle>
        </CardHeader>
        <CardContent>
          <div
            className="overflow-x-auto rounded-md border"
            tabIndex={0}
            role="region"
            aria-label="Controls table"
          >
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Control</TableHead>
                  <TableHead>Result</TableHead>
                  <TableHead>Evidence</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {report.controls.map((c) => (
                  <TableRow key={c.key}>
                    <TableCell className="align-top whitespace-normal">
                      <strong className="font-medium">{c.label}</strong>
                    </TableCell>
                    <TableCell className="align-top">
                      <Chip tone={TONE[c.result]}>{WORDS[c.result]}</Chip>
                    </TableCell>
                    <TableCell className="text-xs whitespace-normal">{c.evidence}</TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </div>
        </CardContent>
      </Card>

      <Card aria-labelledby="rep-approval">
        <CardHeader>
          <CardTitle id="rep-approval" className="text-base">
            Approval
          </CardTitle>
        </CardHeader>
        <CardContent>
          {approval.approved ? (
            <KVList>
              <KV label="Approved by">
                <span className="font-mono text-xs">{approval.approved_by}</span>
              </KV>
              <KV label="Approved at">{formatDateTime(approval.approved_at)}</KV>
              <KV label="MFA proof">
                <span className="font-mono text-xs">{approval.mfa_proof_reference}</span>
              </KV>
              <KV label="Summary hash">
                <span className="font-mono text-xs break-all">{approval.summary_hash}</span>
              </KV>
            </KVList>
          ) : (
            <p className="text-muted-foreground">
              Not approved yet. Only a human parent can approve, with a fresh MFA code.
            </p>
          )}
        </CardContent>
      </Card>

      <Card aria-labelledby="rep-audit">
        <CardHeader>
          <CardTitle id="rep-audit" className="text-base">
            Audit trail for this payment
          </CardTitle>
        </CardHeader>
        <CardContent className="space-y-3">
          <p className="text-sm">
            Chain check:{" "}
            <Chip tone={audit.chain.status === "PASS" ? "ok" : "danger"}>{audit.chain.status}</Chip>{" "}
            {audit.chain.events_checked} events verified, head event {audit.chain.head.seq}{" "}
            <code className="font-mono text-xs">{shortHash(audit.chain.head.hash, 12)}</code>
          </p>
          <div
            className="overflow-x-auto rounded-md border"
            tabIndex={0}
            role="region"
            aria-label="Audit events for this payment table"
          >
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead className="text-right">Seq</TableHead>
                  <TableHead>When</TableHead>
                  <TableHead>Actor</TableHead>
                  <TableHead>Action</TableHead>
                  <TableHead>Hash</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {audit.events.map((e) => (
                  <TableRow key={e.event_id}>
                    <TableCell className="text-right font-mono tabular-nums">{e.seq}</TableCell>
                    <TableCell className="text-xs whitespace-nowrap">
                      {formatDateTime(e.timestamp)}
                    </TableCell>
                    <TableCell>{e.actor_type}</TableCell>
                    <TableCell>
                      <code className="font-mono text-xs">{e.action}</code>
                      {e.reason_code ? (
                        <div className="text-muted-foreground text-xs">{e.reason_code}</div>
                      ) : null}
                    </TableCell>
                    <TableCell className="font-mono text-xs">
                      {shortHash(e.this_event_hash, 8)}
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </div>
        </CardContent>
      </Card>

      <Card aria-labelledby="rep-hash">
        <CardHeader>
          <CardTitle id="rep-hash" className="text-base">
            Report integrity
          </CardTitle>
        </CardHeader>
        <CardContent className="space-y-3">
          <p className="text-sm">
            Generated {formatDateTime(report.generated_at)}. The hash below is the SHA-256 of this
            report as JSON with sorted keys and no whitespace, without the hash field itself. Any
            edit to a copy changes it.
          </p>
          <p className="font-mono text-xs break-all">{report.report_hash}</p>
          <div className="flex flex-wrap items-center gap-2 print:hidden">
            <Button type="button" variant="outline" onClick={() => void verify()}>
              Verify this report in my browser
            </Button>
            {intact === true ? <Chip tone="ok">Matches: not changed</Chip> : null}
            {intact === false ? <Chip tone="danger">Does not match</Chip> : null}
          </div>
          <p className="print:hidden">
            <Link href={back} className="text-primary hover:underline">
              Back to the payment
            </Link>
          </p>
        </CardContent>
      </Card>
    </div>
  );
}
