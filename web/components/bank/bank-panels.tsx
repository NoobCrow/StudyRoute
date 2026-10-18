"use client";

import { ChevronRight } from "lucide-react";
import { useState } from "react";

import { KV, KVList } from "@/components/app/key-value";
import { ErrorNotice, Notice } from "@/components/app/notice";
import { Chip, type Tone } from "@/components/app/status";
import { MfaDialog } from "@/components/payment/mfa-dialog";
import { Button } from "@/components/ui/button";
import {
  Card,
  CardAction,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Collapsible, CollapsibleContent, CollapsibleTrigger } from "@/components/ui/collapsible";
import {
  Table,
  TableBody,
  TableCaption,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { useIdempotencyKey } from "@/hooks/use-idempotency-key";
import { post } from "@/lib/api/client";
import type {
  BankEvent,
  BankJournal,
  BankNetwork,
  BankStatus,
  BankTransfer,
  Money,
} from "@/lib/api/types";
import { cn } from "@/lib/utils";

const STATUS_TONE: Record<BankStatus, Tone> = {
  PENDING_CONFIRMATION: "warn",
  ACCEPTED: "info",
  IN_TRANSIT: "info",
  SETTLED: "ok",
  RETURNED: "danger",
  CANCELLED: "neutral",
};
const STATUS_LABEL: Record<BankStatus, string> = {
  PENDING_CONFIRMATION: "Waiting for your confirmation",
  ACCEPTED: "Accepted",
  IN_TRANSIT: "In transit",
  SETTLED: "Settled",
  RETURNED: "Returned in full",
  CANCELLED: "Cancelled",
};

export function BankStatusBadge({ status }: { status: BankStatus }) {
  return <Chip tone={STATUS_TONE[status]}>{STATUS_LABEL[status]}</Chip>;
}

export const isOpen = (status: BankStatus) => status === "ACCEPTED" || status === "IN_TRANSIT";

function formatted(figures: Record<string, unknown>, key: string): string | null {
  const value = figures[key] as Partial<Money> | undefined;
  return value && typeof value.formatted === "string" ? value.formatted : null;
}

function Disclosure({ summary, children }: { summary: string; children: React.ReactNode }) {
  return (
    <Collapsible>
      <CollapsibleTrigger className="group text-muted-foreground hover:text-foreground flex items-center gap-1 text-sm">
        <ChevronRight
          className="size-4 transition-transform group-data-[state=open]:rotate-90"
          aria-hidden="true"
        />
        {summary}
      </CollapsibleTrigger>
      <CollapsibleContent className="mt-2 space-y-3">{children}</CollapsibleContent>
    </Collapsible>
  );
}

function Figures({ transfer }: { transfer: BankTransfer }) {
  const f = transfer.figures;
  const international = transfer.kind === "INTERNATIONAL";
  const rows: [string, string | null][] = international
    ? [
        ["You pay", formatted(f, "you_pay")],
        ["Beneficiary receives", formatted(f, "beneficiary_receives")],
        ["Charge code", String(f.charge_code ?? "")],
        ["Bank rate (BDT per unit)", String(f.provider_rate ?? "")],
        ["Originating bank fees", formatted(f, "bank_fees")],
        ["Correspondent fee", formatted(f, "intermediary_fee")],
        ["Receiving bank fee", formatted(f, "receiving_fee")],
        [
          "Total cost of sending",
          formatted(f, "total_cost")
            ? `${formatted(f, "total_cost")} (${String(f.cost_pct)}%)`
            : null,
        ],
      ]
    : [
        ["You pay", formatted(f, "you_pay")],
        ["Beneficiary receives", formatted(f, "beneficiary_receives")],
        ["Fee", formatted(f, "fee")],
        ["Way of sending", String(f.rail_label ?? transfer.rail)],
      ];
  return (
    <KVList>
      {rows
        .filter(([, value]) => value)
        .map(([label, value]) => (
          <KV key={label} label={label} wide>
            {value}
          </KV>
        ))}
    </KVList>
  );
}

function Steps({ transfer }: { transfer: BankTransfer }) {
  const returned = transfer.status === "RETURNED";
  return (
    <ol className="relative space-y-4 border-l pl-5" aria-label="Where the money is">
      {transfer.steps.map((step) => (
        <li key={step.stage} className="relative">
          <span
            className={cn(
              "border-card absolute top-1.5 -left-[1.6rem] size-2.5 rounded-full border-2",
              returned ? "bg-destructive" : step.done ? "bg-primary" : "bg-muted-foreground/40",
            )}
            aria-hidden="true"
          />
          <strong className="font-medium">{step.bank_name}</strong>{" "}
          <span className="text-muted-foreground">({step.bank})</span>
          <div className="text-sm">{step.summary}</div>
          <div className="text-muted-foreground text-xs">
            {returned
              ? "Not completed, returned"
              : step.done
                ? "Done"
                : `Waits about ${step.delay_seconds} seconds`}
          </div>
        </li>
      ))}
    </ol>
  );
}

function Messages({ events }: { events: BankEvent[] }) {
  return (
    <Disclosure summary={`Messages and history (${events.length})`}>
      <ul className="space-y-3 text-sm">
        {events.map((event, index) => (
          <li key={`${event.at}-${index}`} className="space-y-2">
            <div>
              <span className="text-muted-foreground font-mono text-xs">
                {new Date(event.at).toLocaleTimeString()}
              </span>{" "}
              {event.bank_name ? (
                <strong className="font-medium">{event.bank_name}: </strong>
              ) : null}
              {event.note}
            </div>
            {event.message?.fields ? (
              <div
                className="overflow-x-auto rounded-md border"
                tabIndex={0}
                role="region"
                aria-label={`${event.message.type ?? "Message"} fields`}
              >
                <Table>
                  <TableCaption className="sr-only">
                    Simulated {event.message.type} message
                  </TableCaption>
                  <TableHeader>
                    <TableRow>
                      <TableHead>Tag</TableHead>
                      <TableHead>Field</TableHead>
                      <TableHead>Value</TableHead>
                    </TableRow>
                  </TableHeader>
                  <TableBody>
                    {event.message.fields.map((field) => (
                      <TableRow key={field.tag}>
                        <TableCell>
                          <code className="font-mono text-xs">{field.tag}</code>
                        </TableCell>
                        <TableCell>{field.name}</TableCell>
                        <TableCell className="font-mono text-xs whitespace-normal">
                          {field.value}
                        </TableCell>
                      </TableRow>
                    ))}
                  </TableBody>
                </Table>
              </div>
            ) : null}
          </li>
        ))}
      </ul>
    </Disclosure>
  );
}

function Ledger({ journals }: { journals: BankJournal[] }) {
  return (
    <Disclosure summary={`Ledger entries, double entry (${journals.length} journals)`}>
      {journals.map((journal) => (
        <div
          key={journal.id}
          className="overflow-x-auto rounded-md border"
          tabIndex={0}
          role="region"
          aria-label={`Journal: ${journal.memo}`}
        >
          <Table>
            <TableCaption className="mb-2 text-left text-xs">
              {journal.kind}: {journal.memo}
            </TableCaption>
            <TableHeader>
              <TableRow>
                <TableHead>Side</TableHead>
                <TableHead>Bank</TableHead>
                <TableHead>Account</TableHead>
                <TableHead className="text-right">Amount</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {journal.lines.map((line, index) => (
                <TableRow key={index}>
                  <TableCell>{line.side === "DEBIT" ? "Debit" : "Credit"}</TableCell>
                  <TableCell>{line.bank}</TableCell>
                  <TableCell>{line.account}</TableCell>
                  <TableCell className="text-right font-mono tabular-nums">
                    {line.amount.formatted}
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </div>
      ))}
    </Disclosure>
  );
}

interface DetailProps {
  transfer: BankTransfer;
  canTransfer: boolean;
  canControl: boolean;
  sandboxCode?: string;
  onChanged: () => void;
}

/** One transfer: the plan, the hops, the messages and the ledger, with the actions the viewer may take. */
export function TransferDetail({
  transfer,
  canTransfer,
  canControl,
  sandboxCode,
  onChanged,
}: DetailProps) {
  const [asking, setAsking] = useState(false);
  const [error, setError] = useState<Error | null>(null);
  const [busy, setBusy] = useState(false);
  const confirmKey = useIdempotencyKey(`confirm|${transfer.id}`);
  const cancelKey = useIdempotencyKey(`cancel|${transfer.id}`);
  const pending = transfer.status === "PENDING_CONFIRMATION";

  async function run(action: () => Promise<unknown>) {
    setBusy(true);
    setError(null);
    try {
      await action();
    } catch (e) {
      setError(e as Error);
    } finally {
      setBusy(false);
      onChanged();
    }
  }

  const confirm = (proof: string) => {
    setAsking(false);
    return run(() =>
      post(`/bank/transfers/${transfer.id}/confirm`, undefined, {
        idempotencyKey: confirmKey,
        mfaProof: proof,
      }),
    );
  };

  return (
    <Card aria-labelledby={`transfer-${transfer.id}`} className="border-primary/40">
      <CardHeader>
        <CardTitle id={`transfer-${transfer.id}`} className="text-base">
          {transfer.debit.formatted} to {transfer.destination.holder}
        </CardTitle>
        <CardAction>
          <BankStatusBadge status={transfer.status} />
        </CardAction>
        <CardDescription>
          {transfer.kind === "INTERNATIONAL"
            ? "International (SWIFT via a correspondent)"
            : "National"}{" "}
          · from {transfer.source.bank_name} to {transfer.destination.bank_name} · reference{" "}
          {transfer.reference}
          {transfer.uetr ? (
            <>
              {" "}
              · UETR <code className="font-mono text-xs">{transfer.uetr}</code>
            </>
          ) : null}
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-4">
        <ErrorNotice error={error} />
        {transfer.status === "RETURNED" || transfer.status === "CANCELLED" ? (
          <p className="text-muted-foreground text-sm">
            These were the planned figures. Nothing was charged.
          </p>
        ) : null}
        <Figures transfer={transfer} />
        {transfer.failure_reason ? (
          <Notice tone="danger" title="Returned">
            {transfer.failure_reason}
          </Notice>
        ) : null}
        {pending && transfer.blockers.length > 0 ? (
          <Notice tone="warn" title="This cannot be confirmed yet">
            <ul className="list-disc pl-5">
              {transfer.blockers.map((b) => (
                <li key={b.code}>{b.message}</li>
              ))}
            </ul>
          </Notice>
        ) : null}
        <Steps transfer={transfer} />
        {transfer.events ? <Messages events={transfer.events} /> : null}
        {transfer.journals && transfer.journals.length > 0 ? (
          <Ledger journals={transfer.journals} />
        ) : null}
        <div className="flex flex-wrap items-center gap-2">
          {pending && canTransfer ? (
            <>
              <Button
                type="button"
                disabled={busy || transfer.blockers.length > 0}
                onClick={() => setAsking(true)}
              >
                Confirm with MFA
              </Button>
              <Button
                type="button"
                variant="outline"
                disabled={busy}
                onClick={() =>
                  void run(() =>
                    post(`/bank/transfers/${transfer.id}/cancel`, undefined, {
                      idempotencyKey: cancelKey,
                    }),
                  )
                }
              >
                Cancel this transfer
              </Button>
            </>
          ) : null}
          {isOpen(transfer.status) && canControl ? (
            <>
              <Button
                type="button"
                variant="outline"
                size="sm"
                disabled={busy}
                onClick={() =>
                  void run(() =>
                    post(`/bank/transfers/${transfer.id}/sandbox-step`, { outcome: "advance" }),
                  )
                }
              >
                Run next hop now
              </Button>
              <Button
                type="button"
                variant="destructive-outline"
                size="sm"
                disabled={busy}
                onClick={() =>
                  void run(() =>
                    post(`/bank/transfers/${transfer.id}/sandbox-step`, { outcome: "fail" }),
                  )
                }
              >
                Make it fail
              </Button>
            </>
          ) : null}
        </div>
        <p className="text-muted-foreground text-xs">{transfer.note}</p>
        {asking ? (
          <MfaDialog
            title="Confirm this transfer"
            scope="confirm_bank_transfer"
            subjectId={transfer.id}
            sandboxCode={sandboxCode}
            onProof={(proof) => void confirm(proof)}
            onCancel={() => setAsking(false)}
          />
        ) : null}
      </CardContent>
    </Card>
  );
}

/** Do the books balance, and does every nostro agree with the liability the other bank keeps? */
export function NetworkCard({ network }: { network: BankNetwork }) {
  if (!network.ready) {
    return (
      <Notice tone="warn" title="The bank network is not set up">
        Run <code className="font-mono">python -m app.scripts.seed</code> (in Docker:{" "}
        <code className="font-mono">docker compose exec backend python -m app.scripts.seed</code>).
      </Notice>
    );
  }
  const totals = Object.entries(network.trial_balance ?? {});
  return (
    <Card aria-labelledby="books-title">
      <CardHeader>
        <CardTitle id="books-title" className="text-base">
          Do the books balance?
        </CardTitle>
        <CardAction>
          <Chip tone={network.all_ok ? "ok" : "danger"}>
            {network.all_ok ? "All books balance" : "Mismatch found"}
          </Chip>
        </CardAction>
        <CardDescription>
          Every transfer is double entry: for each currency the debits equal the credits, and each
          nostro account equals the liability the other bank keeps for it. This is checked from the
          ledger on every refresh. The banks are invented.
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-3">
        <div
          className="overflow-x-auto rounded-md border"
          tabIndex={0}
          role="region"
          aria-label="Trial balance by currency"
        >
          <Table>
            <TableCaption className="sr-only">Total debits and credits by currency</TableCaption>
            <TableHeader>
              <TableRow>
                <TableHead>Currency</TableHead>
                <TableHead className="text-right">Debits (minor units)</TableHead>
                <TableHead className="text-right">Credits (minor units)</TableHead>
                <TableHead>Balanced</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {totals.map(([currency, t]) => (
                <TableRow key={currency}>
                  <TableCell>{currency}</TableCell>
                  <TableCell className="text-right font-mono tabular-nums">
                    {t.debits.toLocaleString("en-US")}
                  </TableCell>
                  <TableCell className="text-right font-mono tabular-nums">
                    {t.credits.toLocaleString("en-US")}
                  </TableCell>
                  <TableCell>{t.balanced ? "Yes" : "No"}</TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </div>
        <Disclosure
          summary={`Nostro and reserve accounts against their mirror (${network.mirror_accounts?.length ?? 0})`}
        >
          <div
            className="overflow-x-auto rounded-md border"
            tabIndex={0}
            role="region"
            aria-label="Mirror accounts"
          >
            <Table>
              <TableCaption className="sr-only">
                Each bank&apos;s account at another institution and whether it agrees
              </TableCaption>
              <TableHeader>
                <TableRow>
                  <TableHead>Held by</TableHead>
                  <TableHead>At</TableHead>
                  <TableHead>Kind</TableHead>
                  <TableHead className="text-right">Balance</TableHead>
                  <TableHead>Agrees</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {(network.mirror_accounts ?? []).map((m, index) => (
                  <TableRow
                    key={index}
                    className={cn(!m.reconciled && "bg-danger-soft hover:bg-danger-soft")}
                  >
                    <TableCell>{m.holder_bank_name}</TableCell>
                    <TableCell>{m.other_name}</TableCell>
                    <TableCell>{m.kind === "NOSTRO" ? "Nostro" : "Reserve"}</TableCell>
                    <TableCell className="text-right font-mono tabular-nums">
                      {m.balance.formatted}
                    </TableCell>
                    <TableCell>{m.reconciled ? "Yes" : "No"}</TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </div>
        </Disclosure>
      </CardContent>
    </Card>
  );
}
