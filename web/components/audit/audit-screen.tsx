"use client";

import { useRouter, useSearchParams } from "next/navigation";
import { useState } from "react";

import { Field } from "@/components/app/field";
import { ErrorNotice, Notice } from "@/components/app/notice";
import { PageHead } from "@/components/app/page-head";
import { CardSkeleton } from "@/components/app/skeletons";
import { Chip, type Tone } from "@/components/app/status";
import { useAuth } from "@/components/providers/auth-provider";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { get } from "@/lib/api/client";
import type { AuditEventView, Page, VerifyView } from "@/lib/api/types";
import { useApi } from "@/lib/api/use-api";
import { formatDateTime, shortHash } from "@/lib/format";
import { cn } from "@/lib/utils";

type AuditPage = Page<AuditEventView> & { scope: string };

function decisionTone(decision: string | null): Tone {
  if (decision === "approved") return "ok";
  if (decision === "blocked" || decision === "rejected") return "danger";
  if (decision === "suggested") return "warn";
  return "neutral";
}

function VerifyResult({ result }: { result: VerifyView }) {
  if (result.status === "PASS") {
    return (
      <Notice tone="ok" title="Chain verified: PASS">
        {result.events_checked} events recomputed. Each hash matches and each link points at the one
        before it. Latest event {result.head.seq}:{" "}
        <code className="font-mono">{shortHash(result.head.hash, 16)}</code>.
      </Notice>
    );
  }
  return (
    <Notice tone="danger" title={`Chain verification FAILED at event ${result.failed_seq ?? "?"}`}>
      {result.reason ?? "An event no longer matches its hash."} The log was changed after it was
      written.
    </Notice>
  );
}

export function AuditScreen() {
  const { user } = useAuth();
  const params = useSearchParams();
  const router = useRouter();
  const paymentId = params.get("payment_id") ?? "";
  const action = params.get("action") ?? "";
  const query = new URLSearchParams({ limit: "25" });
  if (paymentId) query.set("payment_id", paymentId);
  if (action) query.set("action", action);

  const first = useApi<AuditPage>(`/audit/events?${query.toString()}`);
  const [more, setMore] = useState<AuditEventView[]>([]);
  const [cursor, setCursor] = useState<number | string | null | undefined>(undefined);
  const [verify, setVerify] = useState<VerifyView | null>(null);
  const [error, setError] = useState<Error | null>(null);
  const [busy, setBusy] = useState(false);

  const events = [...(first.data?.items ?? []), ...more];
  const next = cursor === undefined ? (first.data?.next_cursor ?? null) : cursor;
  const canVerify = user?.permissions.includes("audit:verify") ?? false;

  function setFilter(key: string, value: string) {
    const copy = new URLSearchParams(params.toString());
    if (value) copy.set(key, value);
    else copy.delete(key);
    router.replace(`/audit/${copy.size ? `?${copy.toString()}` : ""}`);
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
    <div className="space-y-6">
      <PageHead
        title="Audit log"
        actions={
          canVerify ? (
            <Button type="button" loading={busy} onClick={() => void runVerify()}>
              Verify the hash chain
            </Button>
          ) : null
        }
      >
        Every state change is written once, in the same transaction, to an append-only log. Each
        event includes the hash of the one before it.
      </PageHead>
      {!canVerify ? (
        <Notice tone="info">
          You see {first.data?.scope ?? "your events"}. Only a reviewer can verify the whole chain.
        </Notice>
      ) : null}
      {verify ? <VerifyResult result={verify} /> : null}
      <ErrorNotice error={first.error ?? error} onRetry={first.reload} />
      <div className="grid gap-4 sm:max-w-2xl sm:grid-cols-2">
        <Field label="Payment id" htmlFor="a-payment">
          <Input
            id="a-payment"
            value={paymentId}
            className="font-mono"
            onChange={(e) => setFilter("payment_id", e.target.value.trim())}
            placeholder="pay_... or btr_..."
          />
        </Field>
        <Field
          label="Action"
          htmlFor="a-action"
          hint="For example approval.granted or webhook.rejected."
        >
          <Input
            id="a-action"
            value={action}
            className="font-mono"
            onChange={(e) => setFilter("action", e.target.value.trim())}
          />
        </Field>
      </div>
      {first.loading && !first.data ? <CardSkeleton lines={5} label="Loading events" /> : null}
      {events.length > 0 ? (
        <div
          className="bg-card overflow-x-auto rounded-xl border"
          tabIndex={0}
          role="region"
          aria-label="Audit events table"
        >
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead className="text-right">Seq</TableHead>
                <TableHead>When</TableHead>
                <TableHead>Actor</TableHead>
                <TableHead>Action</TableHead>
                <TableHead>Decision</TableHead>
                <TableHead>Detail</TableHead>
                <TableHead>Hash</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {events.map((e) => (
                <TableRow
                  key={e.event_id}
                  className={cn(
                    verify?.failed_seq === e.seq && "bg-danger-soft hover:bg-danger-soft",
                  )}
                >
                  <TableCell className="text-right align-top font-mono tabular-nums">
                    {e.seq}
                  </TableCell>
                  <TableCell className="align-top text-xs whitespace-nowrap">
                    {formatDateTime(e.timestamp)}
                  </TableCell>
                  <TableCell className="align-top">
                    {e.actor_type}
                    <div className="text-muted-foreground font-mono text-xs">{e.actor_id}</div>
                  </TableCell>
                  <TableCell className="align-top">
                    <code className="font-mono text-xs">{e.action}</code>
                    {e.payment_id ? (
                      <div className="text-muted-foreground font-mono text-xs">{e.payment_id}</div>
                    ) : null}
                  </TableCell>
                  <TableCell className="align-top">
                    {e.decision ? <Chip tone={decisionTone(e.decision)}>{e.decision}</Chip> : null}
                    {e.reason_code ? (
                      <div className="text-muted-foreground text-xs">{e.reason_code}</div>
                    ) : null}
                  </TableCell>
                  <TableCell className="max-w-72 align-top text-xs whitespace-normal">
                    {e.amount_display ? <div>{e.amount_display}</div> : null}
                    {e.detail}
                    {e.model_version ? (
                      <div className="text-muted-foreground">model {e.model_version}</div>
                    ) : null}
                  </TableCell>
                  <TableCell
                    className="align-top font-mono text-xs"
                    title={`prev ${e.prev_event_hash}`}
                  >
                    {shortHash(e.this_event_hash, 8)}
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </div>
      ) : null}
      {first.data && events.length === 0 ? (
        <p className="text-muted-foreground">No events match.</p>
      ) : null}
      {next !== null && events.length > 0 ? (
        <div>
          <Button type="button" variant="outline" loading={busy} onClick={() => void loadMore()}>
            Load older events
          </Button>
        </div>
      ) : null}
      <p className="text-muted-foreground text-xs">
        Tamper-evident, not tamper-proof. For extra strength, publish the latest hash outside the
        database.
      </p>
    </div>
  );
}
