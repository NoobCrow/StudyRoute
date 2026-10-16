"use client";

import { Check, Circle } from "lucide-react";
import Link from "next/link";

import { SendPlanTable } from "@/components/app/send-plan-table";
import { Chip, type Tone } from "@/components/app/status";
import { Button } from "@/components/ui/button";
import type { PaymentPlanCard, SendPlanCardData, TaskCard } from "@/lib/api/types";
import { formatDate } from "@/lib/format";
import { appHref } from "@/lib/links";

const STATUS: Record<string, Tone> = {
  ON_TRACK: "ok",
  TIGHT: "warn",
  AT_RISK: "warn",
  LATE: "danger",
};

function Row({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="grid grid-cols-[9rem_1fr] gap-2 py-1 text-xs">
      <dt className="text-muted-foreground">{label}</dt>
      <dd>{children}</dd>
    </div>
  );
}

/** What the assistant prepared from one sentence. Built by the engine; the person still decides. */
export function PlanCard({ card }: { card: PaymentPlanCard }) {
  const { best, deadline, request, steps } = card;
  const draft = steps.find((s) => s.key === "draft");
  return (
    <section
      className="bg-card text-card-foreground mb-3 space-y-2 rounded-lg border p-3"
      aria-label="Payment plan"
    >
      <h3 className="text-sm font-semibold">
        Payment plan: {request.amount.formatted} to {request.country_name}
      </h3>
      <dl>
        <Row label={card.deadline_fit ? "Lowest cost that arrives in time" : "Lowest true cost"}>
          <strong className="font-semibold">{best.provider_name}</strong> at {best.cost_pct}
        </Row>
        {best.arrives_on ? (
          <Row label="Arrives">
            {formatDate(best.arrives_on)}{" "}
            <Chip tone={best.meets_deadline ? "ok" : "danger"}>
              {best.meets_deadline ? "in time" : "too late"}
            </Chip>
          </Row>
        ) : null}
        <Row label="You would pay">{best.parent_pays}</Row>
        <Row label="Send by">
          {deadline ? (
            <>
              <strong className="font-semibold">{formatDate(deadline.latest_send_date)}</strong>{" "}
              <Chip tone={STATUS[deadline.status] ?? "neutral"}>
                {deadline.status.replace("_", " ").toLowerCase()}
              </Chip>
            </>
          ) : (
            "Add a due date to plan the deadline"
          )}
        </Row>
      </dl>
      {card.cheapest_misses_deadline ? (
        <p className="text-destructive text-xs" role="alert">
          {card.alternatives
            .filter((a) => a.meets_deadline === false)
            .map((a) => `${a.provider_name} would arrive after the due date.`)
            .join(" ")}
        </p>
      ) : null}
      {card.alternatives.some((a) => a.has_shortfall) ? (
        <p className="text-destructive text-xs" role="alert">
          {card.alternatives
            .filter((a) => a.has_shortfall)
            .map((a) => `${a.provider_name} may leave the university ${a.shortfall} short.`)
            .join(" ")}
        </p>
      ) : null}
      <ol className="space-y-1.5" aria-label="What is done and what is left">
        {steps.map((step) => (
          <li key={step.key} className="flex items-start gap-2 text-xs">
            {step.state === "done" ? (
              <Check className="text-primary mt-0.5 size-3.5 shrink-0" aria-hidden="true" />
            ) : (
              <Circle
                className="text-muted-foreground mt-0.5 size-3.5 shrink-0"
                aria-hidden="true"
              />
            )}
            <span>
              <strong className="font-medium">{step.label}</strong>
              <span className="sr-only">{step.state === "done" ? " (done)" : " (to do)"}</span>
              <span className="text-muted-foreground"> {step.detail}</span>
              {step.link && step.key !== "draft" && step.state === "todo" ? (
                <>
                  {" "}
                  <Link href={appHref(step.link)} className="text-primary underline">
                    Open
                  </Link>
                </>
              ) : null}
            </span>
          </li>
        ))}
      </ol>
      {draft?.link ? (
        <Button asChild size="sm">
          <Link href={appHref(draft.link)}>Review and create the draft</Link>
        </Button>
      ) : null}
      <p className="text-muted-foreground text-xs">
        The assistant proposes. You create the draft and approve it with a fresh MFA code.
      </p>
    </section>
  );
}

export function TaskView({ task }: { task: TaskCard | null }) {
  if (!task || task.status !== "ready") return null;
  if (task.kind === "payment_plan") return <PlanCard card={task as PaymentPlanCard} />;
  return (
    <section className="bg-card mb-3 space-y-2 rounded-lg border p-3" aria-label="Send plan">
      <h3 className="text-sm font-semibold">Smart send plan</h3>
      <SendPlanTable plan={(task as SendPlanCardData).plan} compact />
    </section>
  );
}
