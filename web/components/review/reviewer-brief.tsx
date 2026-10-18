"use client";

import { useState } from "react";

import { Field } from "@/components/app/field";
import { KV, KVList } from "@/components/app/key-value";
import { ErrorNotice, Notice } from "@/components/app/notice";
import { Chip } from "@/components/app/status";
import { MfaDialog } from "@/components/payment/mfa-dialog";
import {
  AiReadingCard,
  ClockChip,
  PriorityChip,
  ReviewStatusChip,
  clockText,
} from "@/components/review/review-bits";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Textarea } from "@/components/ui/textarea";
import { useIdempotencyKey } from "@/hooks/use-idempotency-key";
import { ApiError, post } from "@/lib/api/client";
import type { ReviewerBrief } from "@/lib/api/types";
import { useApi, useInvalidateApi } from "@/lib/api/use-api";

type Choice = "CLEAR" | "ASK_INFO" | "DECLINE";

const CHOICES: { value: Choice; label: string; help: string }[] = [
  { value: "CLEAR", label: "Yes, clear it", help: "The parent can then approve with MFA." },
  {
    value: "ASK_INFO",
    label: "Ask for more",
    help: "The parent is asked a question; the clock stops.",
  },
  {
    value: "DECLINE",
    label: "No, decline it",
    help: "The payment is rejected and the parent sees why.",
  },
];

const HINT_WORDS: Record<Choice, string> = {
  CLEAR: "this looks routine",
  ASK_INFO: "ask for more first",
  DECLINE: "this may need a no",
};

const REASONS: Record<string, string> = {
  UNCLEAR_PURPOSE: "The purpose is not clear",
  DOCUMENTS_MISSING: "A document is missing",
  NAME_MISMATCH: "The name does not match the invoice",
  OVER_BANK_POLICY: "Above what this bank allows",
  OTHER: "Another reason (explain below)",
};

/**
 * One page for the bank's reviewer: the facts, why it was flagged, what to ask, and three buttons.
 * The yes / no needs a fresh MFA code for this payment; the hint and the priority are only aids.
 */
export function ReviewerBriefCard({
  paymentId,
  sandboxCode,
  onDecided,
}: {
  paymentId: string;
  sandboxCode?: string;
  onDecided?: () => void;
}) {
  const brief = useApi<ReviewerBrief>(`/payments/${paymentId}/bank-review`);
  const invalidate = useInvalidateApi();
  const [choice, setChoice] = useState<Choice | null>(null); // no default: the reviewer chooses
  const [reason, setReason] = useState("");
  const [note, setNote] = useState("");
  const [mfaOpen, setMfaOpen] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<Error | null>(null);
  const data = brief.data;
  const key = useIdempotencyKey(
    `review-decide:${paymentId}:${data?.status}:${choice}:${reason}:${note}`,
  );

  if (brief.error instanceof ApiError && brief.error.status === 404) return null;
  if (!data) return null;

  const needsWords = choice !== null && choice !== "CLEAR";
  const ready = choice !== null && (!needsWords || (reason !== "" && note.trim().length >= 5));

  async function decide(proof: string) {
    if (choice === null) return;
    setMfaOpen(false);
    setBusy(true);
    setError(null);
    try {
      await post(
        `/payments/${paymentId}/bank-review/decision`,
        { decision: choice, reason_code: needsWords ? reason : null, note: note.trim() || null },
        { idempotencyKey: key, mfaProof: proof },
      );
      await invalidate();
      onDecided?.();
    } catch (e) {
      setError(e as Error);
    } finally {
      setBusy(false);
    }
  }

  const clock = clockText(data.clock);
  return (
    <Card aria-labelledby="review-brief-title">
      <CardHeader className="flex flex-row flex-wrap items-center justify-between gap-2">
        <CardTitle id="review-brief-title" className="text-base">
          Bank review brief
        </CardTitle>
        <div className="flex flex-wrap items-center gap-1.5">
          <ReviewStatusChip status={data.status} />
          <ClockChip clock={data.clock} />
          <PriorityChip priority={data.priority} />
        </div>
      </CardHeader>
      <CardContent className="space-y-5">
        {clock ? <p className="text-sm">{clock}</p> : null}
        <KVList>
          <KV label="Payer">
            {data.payer.name}{" "}
            <Chip tone={data.payer.kyc_status === "VERIFIED" ? "ok" : "warn"}>
              KYC {data.payer.kyc_status.replace("_", " ").toLowerCase()} (simulated)
            </Chip>
          </KV>
          <KV label="Receiver">
            {data.recipient.label}{" "}
            <Chip tone={data.recipient.allowlisted ? "ok" : "warn"}>
              {data.recipient.allowlisted ? "allowlisted" : "not allowlisted"}
            </Chip>
          </KV>
          <KV label="Amount">
            {data.amount.formatted} for {data.purpose.toLowerCase()} to {data.destination_country}
          </KV>
          <KV label="Reference">{data.reference}</KV>
          <KV label="Documents on file">
            {data.documents_on_file.length > 0 ? data.documents_on_file.join(", ") : "none yet"}
          </KV>
        </KVList>

        {data.ai ? (
          <AiReadingCard reading={data.ai} audience="reviewer" />
        ) : (
          <Notice tone="warn" title="No AI reading">
            The risk model is not loaded here, so plain rules decided that a person must look.
          </Notice>
        )}

        <div className="space-y-2">
          <h3 className="text-sm font-medium">Why it was flagged and what to check</h3>
          <ul className="space-y-2">
            {data.signals.map((signal) => (
              <li key={signal.code} className="rounded-md border p-3 text-sm">
                <p className="font-medium">
                  {signal.title}{" "}
                  {signal.needs_human ? (
                    <Chip tone="warn">needs a person</Chip>
                  ) : (
                    <Chip>context</Chip>
                  )}
                </p>
                {Object.keys(signal.figures).length > 0 ? (
                  <p className="text-muted-foreground">
                    {Object.entries(signal.figures)
                      .map(([name, value]) => `${name}: ${value}`)
                      .join(" · ")}
                  </p>
                ) : null}
                <p>{signal.check}</p>
              </li>
            ))}
          </ul>
        </div>

        {data.parent_reply ? (
          <Notice tone="info" title="The parent answered">
            {data.parent_reply}
          </Notice>
        ) : null}

        <Notice tone="info" title={`Hint: ${HINT_WORDS[data.hint.suggested]}`}>
          {data.hint.why} {data.hint.note}
        </Notice>

        {data.can_decide ? (
          <form
            className="space-y-4"
            onSubmit={(event) => {
              event.preventDefault();
              if (ready) setMfaOpen(true);
            }}
          >
            <fieldset className="space-y-2">
              <legend className="text-sm font-medium">Your decision</legend>
              {CHOICES.map((entry) => (
                <label key={entry.value} className="flex items-start gap-2 text-sm">
                  <input
                    type="radio"
                    name="review-choice"
                    value={entry.value}
                    checked={choice === entry.value}
                    onChange={() => setChoice(entry.value)}
                    className="mt-1"
                  />
                  <span>
                    <span className="font-medium">{entry.label}</span>
                    <span className="text-muted-foreground block">{entry.help}</span>
                  </span>
                </label>
              ))}
            </fieldset>
            {needsWords ? (
              <>
                <Field label="Reason" htmlFor="review-reason">
                  <select
                    id="review-reason"
                    value={reason}
                    onChange={(event) => setReason(event.target.value)}
                    className="border-input bg-background h-9 w-full rounded-md border px-3 text-sm"
                  >
                    <option value="">Choose a reason</option>
                    {data.reason_codes.map((code) => (
                      <option key={code} value={code}>
                        {REASONS[code] ?? code}
                      </option>
                    ))}
                  </select>
                </Field>
                <Field
                  label="Note for the parent"
                  htmlFor="review-note"
                  hint="Plain words. The parent reads this."
                >
                  <Textarea
                    id="review-note"
                    value={note}
                    maxLength={500}
                    onChange={(event) => setNote(event.target.value)}
                  />
                </Field>
              </>
            ) : null}
            <Button type="submit" loading={busy} disabled={busy || !ready}>
              Sign with MFA and send
            </Button>
          </form>
        ) : data.decided_at ? (
          <p className="text-muted-foreground text-sm">
            Decided {data.decided_at}. {data.reviewer_note ?? ""}
          </p>
        ) : null}
        <ErrorNotice error={error} />
        <p className="text-muted-foreground text-xs">{data.disclaimer}</p>
      </CardContent>
      {mfaOpen ? (
        <MfaDialog
          title="Sign this decision"
          scope="review_payment"
          subjectId={paymentId}
          sandboxCode={sandboxCode}
          onProof={(proof) => void decide(proof)}
          onCancel={() => setMfaOpen(false)}
        />
      ) : null}
    </Card>
  );
}
