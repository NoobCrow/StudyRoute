import { Link } from "react-router-dom";

import type { PaymentPlanCard, SendPlanCardData, TaskCard } from "../api/types";
import { formatDate } from "../lib/format";
import { SendPlanTable } from "./SendPlanTable";
import { Badge } from "./Ui";

const STATUS = { ON_TRACK: "ok", TIGHT: "warn", AT_RISK: "warn", LATE: "danger" } as const;

/** What the assistant prepared from one sentence. Built by the engine; the person still decides. */
export function PlanCard({ card }: { card: PaymentPlanCard }) {
  const { best, deadline, request, steps } = card;
  const draft = steps.find((s) => s.key === "draft");
  return (
    <section className="plan-card" aria-label="Payment plan">
      <h3>Payment plan: {request.amount.formatted} to {request.country_name}</h3>
      <dl className="kv small">
        <dt>{card.deadline_fit ? "Lowest cost that arrives in time" : "Lowest true cost"}</dt>
        <dd><strong>{best.provider_name}</strong> at {best.cost_pct}</dd>
        {best.arrives_on ? (
          <>
            <dt>Arrives</dt>
            <dd>
              {formatDate(best.arrives_on)}{" "}
              <Badge tone={best.meets_deadline ? "ok" : "danger"}>{best.meets_deadline ? "in time" : "too late"}</Badge>
            </dd>
          </>
        ) : null}
        <dt>You would pay</dt>
        <dd>{best.parent_pays}</dd>
        <dt>Send by</dt>
        <dd>
          {deadline ? (
            <>
              <strong>{formatDate(deadline.latest_send_date)}</strong>{" "}
              <Badge tone={STATUS[deadline.status]}>{deadline.status.replace("_", " ").toLowerCase()}</Badge>
            </>
          ) : (
            "Add a due date to plan the deadline"
          )}
        </dd>
      </dl>
      {card.cheapest_misses_deadline ? (
        <p className="small error-text" role="alert">
          {card.alternatives.filter((a) => a.meets_deadline === false).map((a) => `${a.provider_name} would arrive after the due date.`).join(" ")}
        </p>
      ) : null}
      {card.alternatives.some((a) => a.has_shortfall) ? (
        <p className="small error-text" role="alert">
          {card.alternatives.filter((a) => a.has_shortfall).map((a) => `${a.provider_name} may leave the university ${a.shortfall} short.`).join(" ")}
        </p>
      ) : null}
      <ol className="steps" aria-label="What is done and what is left">
        {steps.map((step) => (
          <li key={step.key} className={step.state}>
            <span className="mark" aria-hidden="true">{step.state === "done" ? "✓" : "○"}</span>
            <span>
              <strong>{step.label}</strong>
              <span className="sr-only">{step.state === "done" ? " (done)" : " (to do)"}</span>
              <span className="small muted"> {step.detail}</span>
              {step.link && step.key !== "draft" && step.state === "todo" ? <> <Link to={step.link}>Open</Link></> : null}
            </span>
          </li>
        ))}
      </ol>
      {draft?.link ? (
        <p>
          <Link className="btn primary small" to={draft.link}>Review and create the draft</Link>
        </p>
      ) : null}
      <p className="small muted">The assistant proposes. You create the draft and approve it with a fresh MFA code.</p>
    </section>
  );
}

export function TaskView({ task }: { task: TaskCard | null }) {
  if (!task || task.status !== "ready") return null;
  if (task.kind === "payment_plan") return <PlanCard card={task as PaymentPlanCard} />;
  return (
    <section className="plan-card" aria-label="Send plan">
      <h3>Smart send plan</h3>
      <SendPlanTable plan={(task as SendPlanCardData).plan} compact />
    </section>
  );
}
