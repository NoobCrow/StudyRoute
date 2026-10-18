"use client";

import { useState } from "react";

import { KV, KVList } from "@/components/app/key-value";
import { ErrorNotice, Notice } from "@/components/app/notice";
import { PageHead } from "@/components/app/page-head";
import { CardSkeleton } from "@/components/app/skeletons";
import { Chip, StateBadge } from "@/components/app/status";
import { useAuth } from "@/components/providers/auth-provider";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { post } from "@/lib/api/client";
import type { Page, PaymentBrief, SandboxInfo } from "@/lib/api/types";
import { useApi } from "@/lib/api/use-api";

type Outcome = "settle" | "fail";

/** Reviewer control: bring the simulated provider's signed webhook forward. */
function ProviderControl() {
  const flights = useApi<Page<PaymentBrief>>("/payments?limit=50", { refetchInterval: 3000 });
  const [error, setError] = useState<Error | null>(null);
  const [message, setMessage] = useState<string | null>(null);
  const [busy, setBusy] = useState<string | null>(null);
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
    <Card aria-labelledby="control-title">
      <CardHeader>
        <CardTitle id="control-title" className="text-base">
          Simulated provider control
        </CardTitle>
      </CardHeader>
      <CardContent className="space-y-3">
        <p className="text-muted-foreground text-sm">
          Settle or fail a payment that is in flight. The simulator still sends a real HMAC-signed
          webhook, so the same verification and state machine run. The action is written to the
          audit log.
        </p>
        <ErrorNotice error={error ?? flights.error} />
        {message ? <Notice tone="ok">{message}</Notice> : null}
        {inFlight.length === 0 ? (
          <p className="text-muted-foreground text-sm">
            No payment is in flight right now. Approve one as the parent; a recipient named
            SLOW_TEST keeps it in flight long enough to try this.
          </p>
        ) : (
          <ul className="space-y-2">
            {inFlight.map((p) => (
              <li
                key={p.payment_id}
                className="flex flex-wrap items-center justify-between gap-2 rounded-lg border p-3"
              >
                <span>
                  <strong className="font-medium">{p.recipient_label}</strong> {p.target.formatted}{" "}
                  <StateBadge state={p.state} />
                </span>
                <span className="flex gap-2">
                  <Button
                    type="button"
                    variant="outline"
                    size="sm"
                    disabled={busy !== null}
                    onClick={() => void trigger(p.payment_id, "settle")}
                  >
                    Settle now
                  </Button>
                  <Button
                    type="button"
                    variant="destructive-outline"
                    size="sm"
                    disabled={busy !== null}
                    onClick={() => void trigger(p.payment_id, "fail")}
                  >
                    Fail now
                  </Button>
                </span>
              </li>
            ))}
          </ul>
        )}
      </CardContent>
    </Card>
  );
}

export function SandboxScreen() {
  const { user } = useAuth();
  const info = useApi<SandboxInfo>("/sandbox");
  const data = info.data;
  const canControl = user?.permissions.includes("sandbox:control") ?? false;

  return (
    <div className="space-y-6">
      <PageHead title="Sandbox">
        What is simulated, how to try the edge cases, and the timings behind the demo.
      </PageHead>
      <ErrorNotice error={info.error} onRetry={info.reload} />
      {info.loading && !data ? (
        <CardSkeleton lines={5} label="Loading the sandbox description" />
      ) : null}
      {data ? (
        <>
          <Notice tone="info" title={data.banner}>
            {data.disclaimer}
          </Notice>
          <Card aria-labelledby="sim-title">
            <CardHeader>
              <CardTitle id="sim-title" className="text-base">
                What is simulated
              </CardTitle>
            </CardHeader>
            <CardContent>
              <div
                className="overflow-x-auto rounded-md border"
                tabIndex={0}
                role="region"
                aria-label="What is simulated table"
              >
                <Table>
                  <TableHeader>
                    <TableRow>
                      <TableHead>Part</TableHead>
                      <TableHead>What it does here</TableHead>
                    </TableRow>
                  </TableHeader>
                  <TableBody>
                    {data.simulated.map((s) => (
                      <TableRow key={s.component}>
                        <TableCell className="align-top">
                          <strong className="font-medium">{s.component}</strong>
                        </TableCell>
                        <TableCell className="whitespace-normal">{s.what}</TableCell>
                      </TableRow>
                    ))}
                  </TableBody>
                </Table>
              </div>
            </CardContent>
          </Card>
          <Card aria-labelledby="scenario-title">
            <CardHeader>
              <CardTitle id="scenario-title" className="text-base">
                Test scenarios
              </CardTitle>
            </CardHeader>
            <CardContent>
              <div
                className="overflow-x-auto rounded-md border"
                tabIndex={0}
                role="region"
                aria-label="Test scenarios table"
              >
                <Table>
                  <TableHeader>
                    <TableRow>
                      <TableHead>Type this</TableHead>
                      <TableHead>Where</TableHead>
                      <TableHead>What happens</TableHead>
                    </TableRow>
                  </TableHeader>
                  <TableBody>
                    {data.scenarios.map((s) => (
                      <TableRow key={s.token}>
                        <TableCell className="align-top">
                          <code className="font-mono text-xs">{s.token}</code>
                        </TableCell>
                        <TableCell className="align-top whitespace-normal">{s.where}</TableCell>
                        <TableCell className="whitespace-normal">{s.effect}</TableCell>
                      </TableRow>
                    ))}
                  </TableBody>
                </Table>
              </div>
            </CardContent>
          </Card>
          <div className="grid items-start gap-6 md:grid-cols-2">
            <Card aria-labelledby="timing-title">
              <CardHeader>
                <CardTitle id="timing-title" className="text-base">
                  Timings and caps
                </CardTitle>
              </CardHeader>
              <CardContent className="space-y-3">
                <KVList>
                  <KV label="Quote is valid" wide>
                    {data.timings.quote_ttl_seconds} seconds
                  </KV>
                  <KV label="MFA proof is valid" wide>
                    {data.timings.mfa_proof_ttl_seconds} seconds
                  </KV>
                  <KV label="Simulated KYC review" wide>
                    {data.timings.kyc_review_seconds} seconds
                  </KV>
                  <KV label="Submitted after approval" wide>
                    {data.timings.submit_delay_seconds} seconds
                  </KV>
                  <KV label="Settles after submit" wide>
                    {data.timings.settle_delay_seconds} seconds (
                    {data.timings.slow_settle_delay_seconds} for SLOW_TEST)
                  </KV>
                  <KV label="Per-payment cap" wide>
                    USD {data.limits.per_transaction_usd_equivalent.toLocaleString("en-US")}{" "}
                    equivalent
                  </KV>
                  <KV label="Daily cap" wide>
                    USD {data.limits.daily_usd_equivalent.toLocaleString("en-US")} equivalent
                  </KV>
                </KVList>
                <p className="text-muted-foreground text-xs">
                  {data.limits.indicative} Indicative. Confirm with your AD bank.
                </p>
              </CardContent>
            </Card>
            <Card aria-labelledby="providers-title">
              <CardHeader>
                <CardTitle id="providers-title" className="text-base">
                  Providers and assistant
                </CardTitle>
              </CardHeader>
              <CardContent className="space-y-3">
                <ul className="list-disc space-y-1 pl-5">
                  {data.providers.map((p) => (
                    <li key={p.provider_id}>
                      {p.name} <code className="font-mono text-xs">{p.provider_id}</code>
                    </li>
                  ))}
                </ul>
                <p>
                  Assistant mode:{" "}
                  <Chip tone={data.ai_mode === "llm" ? "info" : "warn"}>
                    {data.ai_mode === "llm" ? "Model" : "Template mode"}
                  </Chip>
                </p>
                {data.demo ? (
                  <p className="text-sm">
                    Demo password <code className="font-mono">{data.demo.password}</code>, MFA code{" "}
                    <code className="font-mono">{data.demo.mfa_code}</code>.
                  </p>
                ) : null}
              </CardContent>
            </Card>
          </div>
        </>
      ) : null}
      {canControl ? <ProviderControl /> : null}
    </div>
  );
}
