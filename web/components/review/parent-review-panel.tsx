"use client";

import { useState } from "react";

import { ErrorNotice, Notice } from "@/components/app/notice";
import { Field } from "@/components/app/field";
import { AiReadingCard, ReviewStatusChip, clockText } from "@/components/review/review-bits";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Textarea } from "@/components/ui/textarea";
import { useIdempotencyKey } from "@/hooks/use-idempotency-key";
import { ApiError, post } from "@/lib/api/client";
import type { ParentReview } from "@/lib/api/types";
import { useApi, useInvalidateApi } from "@/lib/api/use-api";

const WAITING = new Set(["OPEN", "INFO_REQUESTED"]);

/**
 * The bank's check in plain words, for a parent who has never dealt with an AD bank: what is
 * happening, how long it should take, what to prepare, and a way to answer or to nudge. Nothing here
 * accuses anyone: a "reason" is only why the bank looks closer. The bank decides, not this screen.
 */
export function ParentReviewPanel({ paymentId }: { paymentId: string }) {
  const review = useApi<ParentReview>(`/payments/${paymentId}/bank-review`, {
    refetchInterval: (data) =>
      WAITING.has((data as ParentReview | undefined)?.status ?? "") ? 5000 : false,
  });
  const invalidate = useInvalidateApi();
  const [reply, setReply] = useState("");
  const [busy, setBusy] = useState<"reply" | "remind" | null>(null);
  const [error, setError] = useState<Error | null>(null);
  const data = review.data;
  const replyKey = useIdempotencyKey(`review-reply:${paymentId}:${reply}`);
  const remindKey = useIdempotencyKey(`review-remind:${paymentId}:${data?.reminders_sent ?? 0}`);

  if (review.error instanceof ApiError && review.error.status === 404) return null;
  if (!data) return null;

  async function send(kind: "reply" | "remind") {
    setBusy(kind);
    setError(null);
    try {
      if (kind === "reply") {
        await post(
          `/payments/${paymentId}/bank-review/reply`,
          { message: reply },
          { idempotencyKey: replyKey },
        );
        setReply("");
      } else {
        await post(`/payments/${paymentId}/bank-review/remind`, undefined, {
          idempotencyKey: remindKey,
        });
      }
      await invalidate();
    } catch (e) {
      setError(e as Error);
    } finally {
      setBusy(null);
    }
  }

  const clock = clockText(data.clock);
  return (
    <Card aria-labelledby="bank-check-title">
      <CardHeader className="flex flex-row flex-wrap items-center justify-between gap-2">
        <CardTitle id="bank-check-title" className="text-base">
          The bank&apos;s check
        </CardTitle>
        <ReviewStatusChip status={data.status} />
      </CardHeader>
      <CardContent className="space-y-4">
        <div>
          <p className="font-medium">{data.headline}</p>
          <p className="text-muted-foreground text-sm">{data.plain}</p>
          {clock ? (
            <p className={data.clock.state === "overdue" ? "text-sm font-medium" : "text-sm"}>
              {clock}
            </p>
          ) : null}
        </div>

        {data.ai ? <AiReadingCard reading={data.ai} audience="parent" /> : null}

        {data.reviewer_asked ? (
          <Notice tone="info" title="The bank asks">
            {data.reviewer_asked}
          </Notice>
        ) : null}
        {data.decision_reason ? (
          <Notice tone="danger" title="Why the bank said no">
            {data.decision_reason} {data.decision_note ?? ""}
          </Notice>
        ) : null}

        {data.signals.length > 0 ? (
          <div className="space-y-3">
            <h3 className="text-sm font-medium">Why the bank looks closer</h3>
            <ul className="space-y-3">
              {data.signals.map((signal) => (
                <li key={signal.code} className="rounded-md border p-3 text-sm">
                  <p className="font-medium">{signal.title}</p>
                  <p>{signal.means}</p>
                  <p className="text-muted-foreground">{signal.why}</p>
                  <p className="mt-2 font-medium">What to have ready</p>
                  <ul className="list-disc pl-5">
                    {signal.prepare.map((item) => (
                      <li key={item}>{item}</li>
                    ))}
                  </ul>
                </li>
              ))}
            </ul>
          </div>
        ) : null}

        {data.can_reply ? (
          <form
            className="space-y-2"
            onSubmit={(event) => {
              event.preventDefault();
              void send("reply");
            }}
          >
            <Field
              label="Your answer to the bank"
              htmlFor="bank-reply"
              hint="A few words. Do not type passwords or full account numbers."
            >
              <Textarea
                id="bank-reply"
                value={reply}
                maxLength={500}
                onChange={(event) => setReply(event.target.value)}
              />
            </Field>
            <Button
              type="submit"
              loading={busy === "reply"}
              disabled={busy !== null || reply.trim().length < 5}
            >
              Send my answer
            </Button>
          </form>
        ) : null}
        {data.your_reply ? (
          <p className="text-muted-foreground text-sm">
            You answered: <q>{data.your_reply}</q>
          </p>
        ) : null}

        {data.can_remind ? (
          <div className="space-y-1">
            <Button
              type="button"
              variant="outline"
              loading={busy === "remind"}
              disabled={busy !== null}
              onClick={() => void send("remind")}
            >
              Remind the bank
            </Button>
            <p className="text-muted-foreground text-xs">
              This puts the payment higher in the bank&apos;s queue once the target time has passed.
              You can send one every few hours.
            </p>
          </div>
        ) : data.reminders_sent > 0 ? (
          <p className="text-muted-foreground text-sm">
            Reminder sent ({data.reminders_sent}). You can send another in a few hours.
          </p>
        ) : null}
        <ErrorNotice error={error} />

        <details className="text-sm">
          <summary className="cursor-pointer font-medium">Words the bank uses</summary>
          <dl className="mt-2 space-y-1">
            {data.glossary.map((entry) => (
              <div key={entry.term}>
                <dt className="inline font-medium">{entry.term}: </dt>
                <dd className="inline">{entry.plain}</dd>
              </div>
            ))}
          </dl>
        </details>
        <p className="text-muted-foreground text-xs">{data.disclaimer}</p>
      </CardContent>
    </Card>
  );
}
