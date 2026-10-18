"use client";

import { zodResolver } from "@hookform/resolvers/zod";
import { ChevronRight } from "lucide-react";
import { useState } from "react";
import { useForm } from "react-hook-form";
import { toast } from "sonner";
import { z } from "zod";

import { KV, KVList } from "@/components/app/key-value";
import { ErrorNotice, Notice } from "@/components/app/notice";
import { Chip, type Tone } from "@/components/app/status";
import { MfaDialog, type MfaScope } from "@/components/payment/mfa-dialog";
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
  Form,
  FormControl,
  FormField,
  FormItem,
  FormLabel,
  FormMessage,
} from "@/components/ui/form";
import { Input } from "@/components/ui/input";
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
import { get, post } from "@/lib/api/client";
import type {
  AnchorVerdict,
  ChainAnchor,
  ChainEscrowStatus,
  ChainStatus,
  EscrowTranche,
  EscrowView,
  TrancheState,
} from "@/lib/api/types";
import { formatDateTime } from "@/lib/format";

const CHAIN_LABEL: Record<ChainEscrowStatus, { tone: Tone; text: string }> = {
  ACTIVE: { tone: "ok", text: "Active on the chain" },
  FROZEN: { tone: "danger", text: "Frozen by the bank's reviewer" },
  COMPLETED: { tone: "ok", text: "Completed" },
  CANCELLED: { tone: "neutral", text: "Cancelled" },
};

function StatusChip({ escrow }: { escrow: EscrowView }) {
  if (escrow.chain_status) {
    const label = CHAIN_LABEL[escrow.chain_status];
    return <Chip tone={label.tone}>{label.text}</Chip>;
  }
  if (escrow.status === "ABANDONED") return <Chip tone="neutral">Plan dropped</Chip>;
  return <Chip tone="warn">Waiting for MFA confirmation</Chip>;
}

const TRANCHE_LABEL: Record<TrancheState, { tone: Tone; text: string }> = {
  PLANNED: { tone: "neutral", text: "Planned" },
  LOCKED: { tone: "info", text: "Locked" },
  RELEASED: { tone: "ok", text: "Paid" },
  REFUNDED: { tone: "warn", text: "Returned to the parent" },
};

export function shortHash(hash: string, keep = 10): string {
  return hash.length <= keep * 2 + 1 ? hash : `${hash.slice(0, keep)}...${hash.slice(-4)}`;
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

interface TrancheRowProps {
  tranche: EscrowTranche;
  canPay: boolean;
  canControl: boolean;
  frozen: boolean;
  busy: boolean;
  onPay: (index: number) => void;
  onReturn: (index: number) => void;
}

function TrancheRow({
  tranche,
  canPay,
  canControl,
  frozen,
  busy,
  onPay,
  onReturn,
}: TrancheRowProps) {
  const label = TRANCHE_LABEL[tranche.state];
  const locked = tranche.state === "LOCKED";
  return (
    <TableRow>
      <TableCell>{tranche.index + 1}</TableCell>
      <TableCell className="font-mono text-xs whitespace-nowrap">{tranche.release_on}</TableCell>
      <TableCell className="text-right font-mono tabular-nums">
        {tranche.amount.formatted}
      </TableCell>
      <TableCell>
        <span className="flex flex-wrap gap-1">
          <Chip tone={label.tone}>{label.text}</Chip>
          {locked && tranche.due ? <Chip tone="info">Due now</Chip> : null}
        </span>
      </TableCell>
      <TableCell>
        <div className="flex flex-wrap gap-2">
          {locked && canPay ? (
            <Button
              type="button"
              variant="outline"
              size="sm"
              disabled={busy || frozen}
              onClick={() => onPay(tranche.index)}
              aria-label={`Pay tranche ${tranche.index + 1} now`}
            >
              Pay now
            </Button>
          ) : null}
          {locked && canControl ? (
            <Button
              type="button"
              variant="ghost"
              size="sm"
              disabled={busy || frozen}
              onClick={() => onReturn(tranche.index)}
              aria-label={`University returns tranche ${tranche.index + 1} (simulated)`}
            >
              University returns it
            </Button>
          ) : null}
        </div>
      </TableCell>
    </TableRow>
  );
}

function ProofPanel({ escrow }: { escrow: EscrowView }) {
  const chain = escrow.chain;
  const tag = escrow.escrow_id.slice(-6);
  if (!chain) return null;
  return (
    <Disclosure summary={`On-chain proof (${escrow.transactions?.length ?? 0} transactions)`}>
      <KVList>
        <KV label="Escrow number" wide>
          #{chain.escrow_id} in the escrow contract
        </KV>
        <KV label="Escrow contract" wide>
          <span className="font-mono text-xs break-all">{chain.contract}</span>
        </KV>
        <KV label="Deposit token" wide>
          <span className="font-mono text-xs break-all">{chain.token}</span>
        </KV>
        <KV label="Parent's wallet" wide>
          <span className="font-mono text-xs break-all">{chain.payer_wallet}</span>
        </KV>
        <KV label="University's wallet" wide>
          <span className="font-mono text-xs break-all">{chain.beneficiary_wallet}</span>
        </KV>
        <KV label="Plan hash" wide>
          <span className="font-mono text-xs break-all">{escrow.plan_hash}</span>
        </KV>
        <KV label="Still locked" wide>
          {chain.locked.formatted}
        </KV>
      </KVList>
      <p className="text-muted-foreground text-xs">
        Only amounts, dates and hashes are on the chain. The payment reference is stored as a hash;
        no name, account number or BIC ever is.
      </p>
      {escrow.transactions && escrow.transactions.length > 0 ? (
        <div
          className="overflow-x-auto rounded-md border"
          tabIndex={0}
          role="region"
          aria-label={`Chain transactions of ${tag}`}
        >
          <Table>
            <TableCaption className="sr-only">
              Transactions on the simulated chain for this escrow
            </TableCaption>
            <TableHeader>
              <TableRow>
                <TableHead className="text-right">#</TableHead>
                <TableHead>Call</TableHead>
                <TableHead>Sent by</TableHead>
                <TableHead>Transaction id</TableHead>
                <TableHead className="hidden md:table-cell">Time</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {escrow.transactions.map((tx) => (
                <TableRow key={tx.seq}>
                  <TableCell className="text-right font-mono tabular-nums">{tx.seq}</TableCell>
                  <TableCell>
                    <code className="font-mono text-xs">
                      {tx.contract}.{tx.function}
                    </code>
                  </TableCell>
                  <TableCell>{tx.sender.split(":")[0]}</TableCell>
                  <TableCell>
                    <code className="font-mono text-xs" title={tx.tx_hash}>
                      {shortHash(tx.tx_hash)}
                    </code>
                  </TableCell>
                  <TableCell className="hidden text-xs whitespace-nowrap md:table-cell">
                    {formatDateTime(tx.time)}
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </div>
      ) : null}
    </Disclosure>
  );
}

type Asking =
  | { scope: "confirm_escrow" }
  | { scope: "release_escrow"; index: number }
  | { scope: "cancel_escrow" };

const reasonSchema = z.object({
  reason: z.string().trim().min(3, "Give a reason of at least 3 characters.").max(120),
});
type ReasonValues = z.infer<typeof reasonSchema>;

interface EscrowCardProps {
  escrow: EscrowView;
  canWrite: boolean;
  canFreeze: boolean;
  canControl: boolean;
  sandboxCode?: string;
  onChanged: () => void;
}

/** One escrow: its schedule, the human steps (MFA), the reviewer's freeze, and the proof on the chain. */
export function EscrowCard({
  escrow,
  canWrite,
  canFreeze,
  canControl,
  sandboxCode,
  onChanged,
}: EscrowCardProps) {
  const [asking, setAsking] = useState<Asking | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<Error | null>(null);
  const reasonForm = useForm<ReasonValues>({
    resolver: zodResolver(reasonSchema),
    mode: "onChange",
    defaultValues: { reason: "" },
  });
  const states = escrow.tranches.map((t) => t.state).join();
  const confirmKey = useIdempotencyKey(`confirm|${escrow.escrow_id}`);
  const cancelKey = useIdempotencyKey(`cancel|${escrow.escrow_id}|${states}`);
  const dropKey = useIdempotencyKey(`drop|${escrow.escrow_id}`);
  const [releaseIndex, setReleaseIndex] = useState(0);
  const releaseKey = useIdempotencyKey(`release|${escrow.escrow_id}|${releaseIndex}|${states}`);
  const id = escrow.escrow_id;
  const tag = id.slice(-6);
  const pending = escrow.status === "PENDING_CONFIRMATION";
  const live = escrow.chain_status === "ACTIVE";
  const frozen = escrow.chain_status === "FROZEN";
  const hasLocked = escrow.tranches.some((t) => t.state === "LOCKED");
  const blockers = escrow.blockers ?? [];

  async function run(work: () => Promise<unknown>, success?: string) {
    setBusy(true);
    setError(null);
    try {
      await work();
      if (success) toast.success(success);
      onChanged();
    } catch (e) {
      setError(e as Error);
    } finally {
      setBusy(false);
    }
  }

  function withProof(proof: string) {
    const step = asking;
    setAsking(null);
    if (!step) return;
    if (step.scope === "confirm_escrow") {
      void run(
        () =>
          post(`/escrows/${id}/confirm`, undefined, {
            idempotencyKey: confirmKey,
            mfaProof: proof,
          }),
        "Funds locked",
      );
    } else if (step.scope === "release_escrow") {
      void run(
        () =>
          post(`/escrows/${id}/tranches/${step.index}/release`, undefined, {
            idempotencyKey: releaseKey,
            mfaProof: proof,
          }),
        "Tranche paid",
      );
    } else {
      void run(
        () =>
          post(`/escrows/${id}/cancel`, undefined, { idempotencyKey: cancelKey, mfaProof: proof }),
        "Escrow cancelled",
      );
    }
  }

  async function freezeOrThaw(values: ReasonValues, action: "freeze" | "unfreeze") {
    await run(
      async () => {
        await post(`/escrows/${id}/${action}`, { reason: values.reason.trim() });
        reasonForm.reset({ reason: "" });
      },
      action === "freeze" ? "Escrow frozen" : "Escrow unfrozen",
    );
  }

  const dialogTitle =
    asking?.scope === "confirm_escrow"
      ? "Lock these funds in the escrow"
      : asking?.scope === "release_escrow"
        ? "Pay this tranche now"
        : "Cancel the tranches that are not yet due";

  return (
    <Card aria-label={`Escrow ${escrow.reference} (${tag})`}>
      <CardHeader>
        <CardTitle className="text-base">
          {escrow.purpose === "TUITION" ? "Tuition" : "Living costs"}: {escrow.total.formatted}
        </CardTitle>
        <CardAction>
          <StatusChip escrow={escrow} />
        </CardAction>
        <CardDescription>
          To {escrow.recipient.label || "the beneficiary"}. Reference{" "}
          <strong>{escrow.reference}</strong>.{" "}
          {escrow.tranches.length === 1
            ? "One payment."
            : `${escrow.tranches.length} tranches, one a month.`}
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-4">
        <ErrorNotice error={error} />
        {frozen ? (
          <Notice tone="danger" title="Frozen">
            The bank&apos;s reviewer has stopped all movement. The funds stay locked in the
            contract. Nobody can pay, return or cancel until it is unfrozen.
          </Notice>
        ) : null}
        {pending && blockers.length > 0 ? (
          <Notice tone="warn" title="Not ready to lock funds">
            <ul className="list-disc pl-5">
              {blockers.map((b) => (
                <li key={b.code}>{b.message}</li>
              ))}
            </ul>
          </Notice>
        ) : null}
        <div
          className="overflow-x-auto rounded-md border"
          tabIndex={0}
          role="region"
          aria-label={`Tranches of ${escrow.reference} (${tag})`}
        >
          <Table>
            <TableCaption className="sr-only">Release schedule</TableCaption>
            <TableHeader>
              <TableRow>
                <TableHead>#</TableHead>
                <TableHead>Releases on</TableHead>
                <TableHead className="text-right">Amount</TableHead>
                <TableHead>State</TableHead>
                <TableHead>
                  <span className="sr-only">Actions</span>
                </TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {escrow.tranches.map((tranche) => (
                <TrancheRow
                  key={tranche.index}
                  tranche={tranche}
                  canPay={canWrite && live}
                  canControl={canControl && (live || frozen)}
                  frozen={frozen}
                  busy={busy}
                  onPay={(index) => {
                    setReleaseIndex(index);
                    setAsking({ scope: "release_escrow", index });
                  }}
                  onReturn={(index) =>
                    void run(() => post(`/escrows/${id}/tranches/${index}/sandbox-refund`))
                  }
                />
              ))}
            </TableBody>
          </Table>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          {pending && canWrite ? (
            <>
              <Button
                type="button"
                disabled={busy || blockers.length > 0}
                onClick={() => setAsking({ scope: "confirm_escrow" })}
              >
                Lock funds with MFA
              </Button>
              <Button
                type="button"
                variant="outline"
                disabled={busy}
                onClick={() =>
                  void run(() =>
                    post(`/escrows/${id}/abandon`, undefined, { idempotencyKey: dropKey }),
                  )
                }
              >
                Drop this plan
              </Button>
            </>
          ) : null}
          {live && canWrite && hasLocked ? (
            <Button
              type="button"
              variant="destructive-outline"
              disabled={busy}
              onClick={() => setAsking({ scope: "cancel_escrow" })}
            >
              Cancel what is not yet due
            </Button>
          ) : null}
        </div>
        {canFreeze && (live || frozen) ? (
          <Form {...reasonForm}>
            <form
              onSubmit={reasonForm.handleSubmit((values) =>
                freezeOrThaw(values, frozen ? "unfreeze" : "freeze"),
              )}
              className="flex flex-wrap items-end gap-3"
              aria-label={`Reviewer control for ${tag}`}
              noValidate
            >
              <FormField
                control={reasonForm.control}
                name="reason"
                render={({ field }) => (
                  <FormItem className="min-w-60 flex-1">
                    <FormLabel>{frozen ? "Reason to unfreeze" : "Reason to freeze"}</FormLabel>
                    <FormControl>
                      <Input maxLength={120} placeholder="Written in the audit log" {...field} />
                    </FormControl>
                    <FormMessage />
                  </FormItem>
                )}
              />
              <Button
                type="submit"
                variant={frozen ? "outline" : "destructive-outline"}
                loading={busy}
              >
                {frozen ? "Unfreeze" : "Freeze this escrow"}
              </Button>
            </form>
          </Form>
        ) : null}
        <ProofPanel escrow={escrow} />
        <p className="text-muted-foreground text-xs">
          Simulated. The tokens are not money, no bank is contacted, and the chain is an in-memory
          sandbox.
        </p>
        {asking ? (
          <MfaDialog
            title={dialogTitle}
            scope={asking.scope as MfaScope}
            subjectId={id}
            sandboxCode={sandboxCode}
            onProof={withProof}
            onCancel={() => setAsking(null)}
          />
        ) : null}
      </CardContent>
    </Card>
  );
}

/** Local audit consistency check. The simulated chain replay log shares SQLite. */
export function AnchorCard({
  anchors,
  canAnchor,
  canVerify,
  onChanged,
}: {
  anchors: ChainAnchor[];
  canAnchor: boolean;
  canVerify: boolean;
  onChanged: () => void;
}) {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<Error | null>(null);
  const [verdict, setVerdict] = useState<AnchorVerdict | null>(null);

  async function run(work: () => Promise<void>) {
    setBusy(true);
    setError(null);
    try {
      await work();
    } catch (e) {
      setError(e as Error);
    } finally {
      setBusy(false);
    }
  }

  return (
    <Card aria-labelledby="anchor-title">
      <CardHeader>
        <CardTitle id="anchor-title" className="text-base">
          Audit anchor
        </CardTitle>
        <CardAction>
          {verdict ? (
            <Chip
              tone={
                verdict.status === "PASS" ? "ok" : verdict.status === "FAIL" ? "danger" : "warn"
              }
            >
              {verdict.status === "PASS"
                ? "Database matches the chain"
                : verdict.status === "FAIL"
                  ? "Does NOT match the chain"
                  : "Nothing anchored yet"}
            </Chip>
          ) : null}
        </CardAction>
        <CardDescription>
          The audit log is a SHA-256 hash chain, which catches an edited event unless the attacker
          also recomputes every hash after it. The simulated chain catches audit-only rewrites, but
          its replay log shares the same database. A database owner can rewrite both logs.
          Independent protection requires a checkpoint stored and protected outside this database.
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-3">
        <ErrorNotice error={error} />
        {anchors.length === 0 ? (
          <p className="text-muted-foreground text-sm">Nothing is anchored yet.</p>
        ) : (
          <div
            className="overflow-x-auto rounded-md border"
            tabIndex={0}
            role="region"
            aria-label="Audit anchors table"
          >
            <Table>
              <TableCaption className="sr-only">
                Audit log hashes written on the sandbox chain
              </TableCaption>
              <TableHeader>
                <TableRow>
                  <TableHead className="text-right">#</TableHead>
                  <TableHead className="text-right">Audit event</TableHead>
                  <TableHead>Hash on the chain</TableHead>
                  <TableHead className="hidden md:table-cell">Anchored</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {anchors.map((a) => (
                  <TableRow key={a.index}>
                    <TableCell className="text-right font-mono tabular-nums">
                      {a.index + 1}
                    </TableCell>
                    <TableCell className="text-right font-mono tabular-nums">{a.seq}</TableCell>
                    <TableCell>
                      <code className="font-mono text-xs" title={a.head}>
                        {shortHash(a.head)}
                      </code>
                    </TableCell>
                    <TableCell className="hidden text-xs whitespace-nowrap md:table-cell">
                      {formatDateTime(a.time)}
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </div>
        )}
        {verdict && verdict.anchors.length > 0 ? (
          <ul className="list-disc space-y-1 pl-5 text-sm">
            {verdict.anchors.map((a) => (
              <li key={a.index}>
                Anchor {a.index + 1} (audit event {a.seq}):{" "}
                <strong>
                  {a.state === "MATCH"
                    ? "matches"
                    : a.state === "MISMATCH"
                      ? "does not match"
                      : "event is missing"}
                </strong>
              </li>
            ))}
            <li>
              Hash chain on its own:{" "}
              <strong>
                {verdict.audit_chain.status === "PASS"
                  ? "passes"
                  : `fails at event ${verdict.audit_chain.failed_seq ?? "?"}`}
              </strong>
            </li>
          </ul>
        ) : null}
        <div className="flex flex-wrap items-center gap-2">
          {canAnchor ? (
            <Button
              type="button"
              loading={busy}
              onClick={() =>
                void run(async () => {
                  await post("/chain/anchor");
                  setVerdict(null);
                  onChanged();
                  toast.success("Audit log anchored on the chain");
                })
              }
            >
              Anchor the audit log now
            </Button>
          ) : null}
          {canVerify ? (
            <Button
              type="button"
              variant="outline"
              disabled={busy}
              onClick={() =>
                void run(async () => setVerdict(await get<AnchorVerdict>("/chain/verify")))
              }
            >
              Verify against the chain
            </Button>
          ) : null}
        </div>
      </CardContent>
    </Card>
  );
}

/** The contracts, where they are, and whether the replayable log is intact. */
export function ChainCard({ status }: { status: ChainStatus }) {
  return (
    <Card aria-labelledby="chain-title">
      <CardHeader>
        <CardTitle id="chain-title" className="text-base">
          The simulated chain
        </CardTitle>
        <CardAction>
          <Chip tone={status.integrity.ok ? "ok" : "danger"}>
            {status.integrity.ok ? "Log intact" : "Log failed its check"}
          </Chip>
        </CardAction>
        <CardDescription>
          {status.engine} Solidity contracts, compiled and run for real; the money is not.
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-3">
        {status.integrity.problem ? (
          <Notice tone="danger" title="Integrity problem">
            {status.integrity.problem}
          </Notice>
        ) : null}
        <KVList>
          <KV label="Blocks">{status.block}</KV>
          <KV label="Chain time">
            {formatDateTime(status.chain_time)}
            {status.time_offset_seconds > 0
              ? ` (moved ${Math.round(status.time_offset_seconds / 86400)} days ahead by a reviewer)`
              : ""}
          </KV>
          <KV label="Log head">
            <span className="font-mono text-xs break-all">{status.log.head}</span>
          </KV>
        </KVList>
        {status.contracts.length > 0 ? (
          <div
            className="overflow-x-auto rounded-md border"
            tabIndex={0}
            role="region"
            aria-label="Deployed contracts table"
          >
            <Table>
              <TableCaption className="sr-only">
                Contracts deployed on the simulated chain
              </TableCaption>
              <TableHeader>
                <TableRow>
                  <TableHead>Contract</TableHead>
                  <TableHead>Address</TableHead>
                  <TableHead className="hidden md:table-cell">Source SHA-256</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {status.contracts.map((c) => (
                  <TableRow key={c.label}>
                    <TableCell>
                      <strong className="font-medium">{c.contract}</strong>
                      <div className="text-muted-foreground text-xs">{c.label}</div>
                    </TableCell>
                    <TableCell>
                      <code className="font-mono text-xs" title={c.address}>
                        {shortHash(c.address, 12)}
                      </code>
                    </TableCell>
                    <TableCell className="hidden md:table-cell">
                      <code className="font-mono text-xs" title={c.source_sha256}>
                        {shortHash(c.source_sha256, 8)}
                      </code>
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </div>
        ) : (
          <p className="text-muted-foreground text-sm">
            The contracts are deployed the first time an escrow is locked.
          </p>
        )}
      </CardContent>
    </Card>
  );
}

const daysSchema = z.object({
  days: z
    .string()
    .regex(/^[0-9]{1,3}$/, "Use a whole number of days, 1 to 999.")
    .refine((v) => Number(v) >= 1, "At least 1 day."),
});
type DaysValues = z.infer<typeof daysSchema>;

/** Sandbox control for the reviewer: let days pass so scheduled tranches can be seen paying out. */
export function TimeControl({ onChanged }: { onChanged: () => void }) {
  const [error, setError] = useState<Error | null>(null);
  const [result, setResult] = useState<string | null>(null);
  const form = useForm<DaysValues>({
    resolver: zodResolver(daysSchema),
    mode: "onChange",
    defaultValues: { days: "15" },
  });

  async function onSubmit(values: DaysValues) {
    setError(null);
    try {
      const reply = await post<{ released: number }>("/chain/sandbox/advance", {
        days: Number(values.days),
      });
      setResult(`${reply.released} tranche${reply.released === 1 ? "" : "s"} paid.`);
      onChanged();
    } catch (e) {
      setError(e as Error);
    }
  }

  return (
    <Card aria-labelledby="time-title">
      <CardHeader>
        <CardTitle id="time-title" className="text-base">
          Sandbox clock
        </CardTitle>
        <CardDescription>
          Let days pass on the chain, then the schedule pays whatever is due. Reviewer only.
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-3">
        <ErrorNotice error={error} />
        <Form {...form}>
          <form
            onSubmit={form.handleSubmit(onSubmit)}
            className="flex flex-wrap items-end gap-3"
            noValidate
          >
            <FormField
              control={form.control}
              name="days"
              render={({ field }) => (
                <FormItem>
                  <FormLabel>Days to move forward</FormLabel>
                  <FormControl>
                    <Input inputMode="numeric" className="w-32 font-mono" {...field} />
                  </FormControl>
                  <FormMessage />
                </FormItem>
              )}
            />
            <Button type="submit" variant="outline" loading={form.formState.isSubmitting}>
              Move time forward
            </Button>
          </form>
        </Form>
        {result ? <p role="status">{result}</p> : null}
      </CardContent>
    </Card>
  );
}
