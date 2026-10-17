"use client";

import { ChevronRight } from "lucide-react";
import { useMemo, useState } from "react";

import { CountrySelect } from "@/components/app/country-select";
import { DatePicker } from "@/components/app/date-picker";
import { Field } from "@/components/app/field";
import { Notice, ErrorNotice } from "@/components/app/notice";
import { CardSkeleton } from "@/components/app/skeletons";
import { Chip } from "@/components/app/status";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Collapsible, CollapsibleContent, CollapsibleTrigger } from "@/components/ui/collapsible";
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip";
import type { Corridor, PlanView } from "@/lib/api/types";
import { useApi } from "@/lib/api/use-api";
import { MARKER_LABEL, buildStrip, describeDay, type Marker } from "@/lib/domain/calendar-strip";
import { PLAN_STATUS } from "@/lib/domain/plan-status";
import { addDaysIso, dhakaToday, formatDate } from "@/lib/format";
import { cn } from "@/lib/utils";

const DAY_STYLE: Record<Marker, string> = {
  today: "border-foreground",
  earliest: "border-dashed border-foreground/60",
  recommended: "border-primary bg-primary text-primary-foreground",
  latest: "border-warning-soft-foreground/30 bg-warning-soft text-warning-soft-foreground",
  due: "border-foreground bg-foreground text-background",
};
/** When a day has more than one marker, the filled ones win over the outlined ones. */
const PRECEDENCE: Marker[] = ["earliest", "today", "latest", "recommended", "due"];

const SWATCH: [Marker, string][] = [
  ["today", "border border-foreground"],
  ["earliest", "border border-dashed border-foreground/60"],
  ["recommended", "bg-primary"],
  ["latest", "border border-warning-soft-foreground/40 bg-warning-soft"],
  ["due", "bg-foreground"],
];

function CalendarStrip({ plan }: { plan: PlanView }) {
  const days = useMemo(
    () =>
      buildStrip({
        today: dhakaToday(),
        earliest: plan.earliest_send_date,
        recommended: plan.recommended_send_date,
        latest: plan.latest_send_date,
        due: plan.due_date,
      }),
    [plan],
  );
  return (
    <div className="space-y-3">
      <ol className="grid grid-cols-15 gap-1.5" aria-label="Fifteen days around the deadline">
        {days.map((day) => {
          const styles = PRECEDENCE.filter((m) => day.markers.includes(m)).map((m) => DAY_STYLE[m]);
          return (
            <li key={day.iso} className="flex flex-col items-center gap-1.5">
              <span className="text-muted-foreground text-[10px] font-medium" aria-hidden="true">
                {day.weekday}
              </span>
              <Tooltip>
                <TooltipTrigger asChild>
                  <span
                    role="img"
                    aria-label={describeDay(day)}
                    className={cn(
                      "flex aspect-square w-full max-w-8 items-center justify-center rounded-md border border-transparent font-mono text-[10px] tabular-nums sm:text-xs",
                      day.markers.length === 0 && "text-muted-foreground",
                      day.markers.length > 0 && "font-semibold",
                      ...styles,
                    )}
                  >
                    {day.day}
                  </span>
                </TooltipTrigger>
                <TooltipContent>{describeDay(day)}</TooltipContent>
              </Tooltip>
            </li>
          );
        })}
      </ol>
      <ul
        className="text-muted-foreground flex flex-wrap gap-x-3 gap-y-1 text-[11px]"
        aria-label="Legend"
      >
        {SWATCH.map(([marker, swatch]) => (
          <li key={marker} className="flex items-center gap-1.5">
            <span className={cn("size-3 rounded-[3px]", swatch)} aria-hidden="true" />
            {MARKER_LABEL[marker]}
          </li>
        ))}
      </ul>
    </div>
  );
}

function Row({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="grid grid-cols-[9.5rem_1fr] gap-4 border-t py-3 text-sm first:border-t-0">
      <dt className="text-muted-foreground">{label}</dt>
      <dd className="min-w-0">{children}</dd>
    </div>
  );
}

/** F3 deadline planner: works back from the university due date over both countries' calendars. */
export function PlannerCard({ corridors }: { corridors: Corridor[] }) {
  const [due, setDue] = useState(() => addDaysIso(14));
  const [country, setCountry] = useState("GB");
  const plan = useApi<PlanView>(
    due ? `/planner/deadline?due_date=${due}&country=${country}` : null,
  );
  const data = plan.data;
  const badge = data ? PLAN_STATUS[data.status] : null;

  return (
    <Card aria-labelledby="planner-title">
      <CardHeader>
        <CardTitle id="planner-title" className="text-base">
          Deadline planner
        </CardTitle>
      </CardHeader>
      <CardContent className="space-y-5">
        <div className="grid gap-4 sm:grid-cols-2">
          <Field
            label="University due date"
            htmlFor="due-date"
            hint="The date the university must have the money."
          >
            <DatePicker
              id="due-date"
              value={due}
              onChange={setDue}
              aria-describedby="due-date-hint"
            />
          </Field>
          <Field label="Destination" htmlFor="plan-country">
            <CountrySelect
              id="plan-country"
              corridors={corridors}
              value={country}
              onValueChange={setCountry}
            />
          </Field>
        </div>
        <ErrorNotice error={plan.error} onRetry={plan.reload} />
        {plan.loading && !data ? <CardSkeleton lines={4} label="Planning" /> : null}
        {data && badge ? (
          <>
            <p className="flex flex-wrap items-center gap-x-3 gap-y-1">
              <Chip tone={badge.tone}>{badge.text}</Chip>
              <span className="text-muted-foreground text-sm">
                {data.days_until_latest_send} calendar days until the latest send date
              </span>
            </p>
            <CalendarStrip plan={data} />
            <dl>
              <Row label="Latest send date">
                <strong className="font-semibold">{formatDate(data.latest_send_date)}</strong>
              </Row>
              <Row label="Recommended">{formatDate(data.recommended_send_date)}</Row>
              <Row label="Earliest if sent now">
                {formatDate(data.earliest_send_date)} (after the {data.bank_cutoff_local} Dhaka
                cut-off a payment counts the next business day)
              </Row>
              <Row label="Assumes">
                {data.settlement_business_days} business days to settle plus {data.buffer_days} days
                of buffer
              </Row>
            </dl>
            {data.warnings.map((w) => (
              <Notice
                key={w.code}
                tone={w.code === "HOLIDAY_OVERLAP" || w.code === "KYC_PENDING" ? "info" : "warn"}
              >
                {w.message}
              </Notice>
            ))}
            {data.skipped_days.length > 0 ? (
              <Collapsible>
                <CollapsibleTrigger className="group text-muted-foreground hover:text-foreground flex items-center gap-1 text-sm">
                  <ChevronRight
                    className="size-4 transition-transform group-data-[state=open]:rotate-90"
                    aria-hidden="true"
                  />
                  {data.skipped_days.length} non-working days skipped
                </CollapsibleTrigger>
                <CollapsibleContent>
                  <ul className="text-muted-foreground mt-2 space-y-1 pl-5 text-sm">
                    {data.skipped_days.map((s) => (
                      <li key={s.date}>
                        {formatDate(s.date)}: {s.reasons.join(", ")}
                      </li>
                    ))}
                  </ul>
                </CollapsibleContent>
              </Collapsible>
            ) : null}
            <p className="text-muted-foreground text-xs">
              <Tooltip>
                <TooltipTrigger className="underline decoration-dotted underline-offset-2">
                  Indicative.
                </TooltipTrigger>
                <TooltipContent>Rules are not verified against an official source.</TooltipContent>
              </Tooltip>{" "}
              Confirm with your AD bank.
            </p>
          </>
        ) : null}
      </CardContent>
    </Card>
  );
}
