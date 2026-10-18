"use client";

import type { ReactNode } from "react";

import { ErrorNotice } from "@/components/app/notice";
import { Chip } from "@/components/app/status";
import { Card, CardAction, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Separator } from "@/components/ui/separator";
import { Skeleton } from "@/components/ui/skeleton";
import type { Corridor, PlanView } from "@/lib/api/types";
import { useApi } from "@/lib/api/use-api";
import { chargeCodeLabel } from "@/lib/domain/charge-code";
import { PLAN_STATUS } from "@/lib/domain/plan-status";
import { dhakaToday, formatDate } from "@/lib/format";
import { formatMinorCompact } from "@/lib/money";
import { amountToMinor, isIsoDate, type CompareValues } from "@/lib/schemas/compare";
import { cn } from "@/lib/utils";

const PURPOSE_LABEL: Record<CompareValues["purpose"], string> = {
  TUITION: "Tuition",
  LIVING: "Living costs",
};

function Row({ label, children }: { label: string; children: ReactNode }) {
  return (
    <div className="flex items-baseline justify-between gap-4 py-2.5 text-sm">
      <dt className="text-muted-foreground">{label}</dt>
      <dd className="min-w-0 text-right">{children}</dd>
    </div>
  );
}

/**
 * The request in words, updating as the form changes. The dates and the status come from the engine's
 * deadline planner (GET /planner/deadline); this card only shows what the form and the API say.
 */
export function RequestSummary({
  values,
  corridor,
  className,
}: {
  values: CompareValues;
  corridor: Corridor | undefined;
  className?: string;
}) {
  const due = values.dueDate;
  const usable = corridor !== undefined && isIsoDate(due) && due >= dhakaToday();
  const plan = useApi<PlanView>(
    usable ? `/planner/deadline?due_date=${due}&country=${values.country}` : null,
  );
  const minor = corridor ? amountToMinor(values.amount, corridor.exponent) : null;
  const badge = plan.data ? PLAN_STATUS[plan.data.status] : null;

  return (
    <Card aria-labelledby="summary-title" className={cn("min-w-0", className)}>
      <CardHeader>
        <CardTitle id="summary-title" className="text-base">
          Your request
        </CardTitle>
        <CardAction>{badge ? <Chip tone={badge.tone}>{badge.text}</Chip> : null}</CardAction>
      </CardHeader>
      <CardContent className="space-y-3" aria-live="polite">
        <div className="bg-muted rounded-lg p-4">
          <p className="text-muted-foreground text-xs">The university receives</p>
          <p className="mt-1 font-mono text-2xl font-semibold tracking-tight tabular-nums">
            {corridor && minor !== null ? (
              `${corridor.currency} ${formatMinorCompact(minor, corridor.exponent)}`
            ) : (
              <span className="text-muted-foreground text-base font-normal">Enter an amount</span>
            )}
          </p>
        </div>
        <dl className="divide-y">
          <Row label="Destination">{corridor?.name ?? "-"}</Row>
          <Row label="Purpose">{PURPOSE_LABEL[values.purpose]}</Row>
          <Row label="Charge code">{chargeCodeLabel(values.charge)}</Row>
          <Row label="University due date">{formatDate(isIsoDate(due) ? due : null)}</Row>
          <Row label="Latest send date">
            {plan.loading && usable ? (
              <Skeleton className="ml-auto h-4 w-28" />
            ) : plan.data ? (
              <strong className="font-semibold">{formatDate(plan.data.latest_send_date)}</strong>
            ) : (
              "-"
            )}
          </Row>
        </dl>
        <ErrorNotice error={usable ? plan.error : null} onRetry={plan.reload} />
        <Separator />
        <p className="text-muted-foreground text-xs">Indicative. Confirm with your AD bank.</p>
      </CardContent>
    </Card>
  );
}
