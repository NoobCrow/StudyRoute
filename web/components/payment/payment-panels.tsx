import { Chip, StateBadge } from "@/components/app/status";
import { Notice } from "@/components/app/notice";
import { Countdown } from "@/components/compare/countdown";
import { Card, CardAction, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import type { Mt103Preview, Payment, Summary, Tracker } from "@/lib/api/types";
import { formatDate, formatDateTime } from "@/lib/format";
import { cn } from "@/lib/utils";

function Row({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="grid grid-cols-[11rem_1fr] gap-4 border-t py-2.5 text-sm first:border-t-0">
      <dt className="text-muted-foreground">{label}</dt>
      <dd className="min-w-0">{children}</dd>
    </div>
  );
}

/** The facts a human must read before approving. Its hash binds the approval to them. */
export function SummaryCard({ payment }: { payment: Payment }) {
  const summary: Summary | null = payment.summary ?? payment.summary_preview;
  const frozen = payment.summary !== null;
  if (!summary) return null;
  const open = ["QUOTED", "PENDING_APPROVAL", "DRAFT"].includes(payment.state);
  return (
    <Card aria-labelledby="summary-title">
      <CardHeader>
        <CardTitle id="summary-title" className="text-base">
          {frozen ? "Approval summary" : "Preview of the approval summary"}
        </CardTitle>
        <CardAction>
          {open && payment.quote_status === "ACTIVE" ? (
            <Countdown expiresAt={payment.quote_expires_at} />
          ) : null}
          {open && payment.quote_status === "EXPIRED" ? (
            <Chip tone="danger">Quote expired</Chip>
          ) : null}
        </CardAction>
      </CardHeader>
      <CardContent className="space-y-3">
        {summary.shortfall_foreign_minor > 0 ? (
          <Notice tone="danger" title="Shortfall risk">
            Fees will be taken from the amount, so the university may receive less than the invoice.
            A charge code of OUR avoids this.
          </Notice>
        ) : null}
        <dl>
          <Row label="Recipient">{summary.recipient}</Row>
          <Row label="Provider">{summary.provider_name}</Row>
          <Row label="Reference">{summary.reference}</Row>
          <Row label="Beneficiary receives">
            <strong className="font-semibold">{summary.display.beneficiary_receives}</strong>
          </Row>
          <Row label="Rate">
            {summary.rate} BDT per {summary.beneficiary_receives.currency}
          </Row>
          <Row label="Charge code">{summary.charge_code}</Row>
          <Row label="Total cost">
            {summary.display.total_cost} ({summary.display.cost_pct})
          </Row>
          <Row label="You pay">
            <strong className="font-semibold">{summary.display.parent_pays}</strong>
          </Row>
          <Row label="Latest send date">{formatDate(summary.latest_send_date)}</Row>
          <Row label="Quote expires">{formatDateTime(summary.quote_expires_at)}</Row>
        </dl>
        <p className="text-muted-foreground text-xs">
          {summary.disclaimer} Indicative. Confirm with your AD bank.
        </p>
      </CardContent>
    </Card>
  );
}

/** Payment instruction preview: shows the originator and beneficiary data (the travel rule). */
export function Mt103Card({ preview }: { preview: Mt103Preview }) {
  return (
    <Card aria-labelledby="mt103-title">
      <CardHeader>
        <CardTitle id="mt103-title" className="text-base">
          Payment instruction preview
        </CardTitle>
        <CardAction>
          <Chip tone="neutral">{preview.format} - simulated</Chip>
        </CardAction>
      </CardHeader>
      <CardContent className="space-y-3">
        <div
          className="overflow-x-auto rounded-md border"
          tabIndex={0}
          role="region"
          aria-label="Instruction preview fields table"
        >
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Tag</TableHead>
                <TableHead>Field</TableHead>
                <TableHead>Value</TableHead>
                <TableHead>Note</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {preview.fields.map((f) => (
                <TableRow key={f.tag}>
                  <TableCell>
                    <code className="font-mono text-xs">{f.tag}</code>
                  </TableCell>
                  <TableCell className="whitespace-normal">{f.name}</TableCell>
                  <TableCell className="font-mono text-xs whitespace-normal">{f.value}</TableCell>
                  <TableCell className="text-muted-foreground text-xs whitespace-normal">
                    {f.note}
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </div>
        <p className="text-sm">
          ISO 20022 equivalent: <code className="font-mono">ChrgBr = {preview.pacs008.ChrgBr}</code>
          , <code className="font-mono">RmtInf = {preview.pacs008.RmtInf}</code>.
        </p>
        <ul className="text-muted-foreground list-disc space-y-1 pl-5 text-xs">
          {preview.notes.map((note) => (
            <li key={note}>{note}</li>
          ))}
        </ul>
      </CardContent>
    </Card>
  );
}

/** Status timeline with the UETR. */
export function TrackerCard({ tracker }: { tracker: Tracker }) {
  return (
    <Card aria-labelledby="tracker-title">
      <CardHeader>
        <CardTitle id="tracker-title" className="text-base">
          Status tracker
        </CardTitle>
        <CardAction>
          <StateBadge state={tracker.state} />
        </CardAction>
      </CardHeader>
      <CardContent className="space-y-4">
        <dl>
          <Row label="UETR">
            <span className="font-mono text-xs break-all">
              {tracker.uetr ?? "Assigned when the payment is submitted"}
            </span>
          </Row>
          <Row label="Host-country rail">{tracker.host_rail}</Row>
        </dl>
        <ol className="relative space-y-4 border-l pl-5" aria-label="Payment timeline">
          {tracker.timeline.map((step, index) => (
            <li key={`${step.state}-${index}`} className="relative">
              <span
                className={cn(
                  "border-card absolute top-1.5 -left-[1.6rem] size-2.5 rounded-full border-2",
                  step.state === "FAILED" || step.state === "REJECTED"
                    ? "bg-destructive"
                    : "bg-primary",
                )}
                aria-hidden="true"
              />
              <StateBadge state={step.state} />
              <div className="text-muted-foreground mt-1 text-xs">
                {formatDateTime(step.at)} by {step.actor_type}
              </div>
              {step.note ? <div className="text-sm">{step.note}</div> : null}
            </li>
          ))}
        </ol>
        <p className="text-muted-foreground text-xs">
          Simulated. No real bank or SWIFT network is contacted.
        </p>
      </CardContent>
    </Card>
  );
}
