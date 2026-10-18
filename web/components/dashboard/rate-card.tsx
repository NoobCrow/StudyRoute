"use client";

import { zodResolver } from "@hookform/resolvers/zod";
import { ChevronRight } from "lucide-react";
import { useEffect, useMemo } from "react";
import { useForm, useWatch } from "react-hook-form";
import { Area, AreaChart, ReferenceDot, ReferenceLine, XAxis, YAxis } from "recharts";
import { z } from "zod";

import { Field } from "@/components/app/field";
import { ErrorNotice, Notice } from "@/components/app/notice";
import { CardSkeleton } from "@/components/app/skeletons";
import { Chip, type Tone } from "@/components/app/status";
import { Card, CardAction, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import {
  ChartContainer,
  ChartTooltip,
  ChartTooltipContent,
  type ChartConfig,
} from "@/components/ui/chart";
import { Collapsible, CollapsibleContent, CollapsibleTrigger } from "@/components/ui/collapsible";
import { Input } from "@/components/ui/input";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import type { RateHistory } from "@/lib/api/types";
import { useApi } from "@/lib/api/use-api";

const TONE: Record<RateHistory["hint"]["kind"], Tone> = {
  SEND_NOW: "ok",
  WAIT_MAY_HELP: "warn",
  NEUTRAL: "info",
};
const WORDS: Record<RateHistory["hint"]["kind"], string> = {
  SEND_NOW: "Today looks better",
  WAIT_MAY_HELP: "Waiting may help",
  NEUTRAL: "About average",
};
const ALERT_KEY = "sr.rate-alert";

const alertSchema = z.object({
  target: z
    .string()
    .refine(
      (value) => value === "" || /^[0-9]{1,6}([.][0-9]{1,6})?$/.test(value.trim()),
      "Use digits and one decimal point.",
    ),
});
type AlertValues = z.infer<typeof alertSchema>;

function readAlert(currency: string): string {
  try {
    return localStorage.getItem(`${ALERT_KEY}.${currency}`) ?? "";
  } catch {
    return "";
  }
}

function saveAlert(currency: string, value: string): void {
  try {
    localStorage.setItem(`${ALERT_KEY}.${currency}`, value);
  } catch {
    /* alerts are a per-browser convenience; losing one is harmless */
  }
}

/** Rates keep their exact text; for axis labels we only cut the string, no number formatting. */
function brief(rate: string): string {
  const dot = rate.indexOf(".");
  return dot < 0 ? rate : rate.slice(0, dot + 3);
}

function shortDate(iso: string): string {
  const d = new Date(`${iso}T00:00:00Z`);
  return Number.isNaN(d.getTime())
    ? iso
    : d.toLocaleDateString("en-GB", { day: "numeric", month: "short", timeZone: "UTC" });
}

const config = { rate: { label: "Synthetic rate", color: "var(--chart-1)" } } satisfies ChartConfig;

function RateChart({ history, currency }: { history: RateHistory; currency: string }) {
  const points = useMemo(
    () => history.points.map((p) => ({ date: p.date, rate: Number(p.rate), text: p.rate })),
    [history],
  );
  const last = points[points.length - 1];
  const first = points[0];
  const values = points.map((p) => p.rate);
  const min = Math.min(...values);
  const max = Math.max(...values);
  const average = Number(history.hint.average);
  const minText = points.find((p) => p.rate === min)?.text ?? String(min);
  const maxText = points.find((p) => p.rate === max)?.text ?? String(max);
  if (!last || !first) return null;
  const summary = `${currency} synthetic rate over ${points.length} days, from ${brief(minText)} to ${brief(maxText)}, ${history.hint.gap_pct}% against the average of ${brief(history.hint.average)}. The values are in the table below.`;

  return (
    <div role="img" aria-label={summary}>
      <ChartContainer config={config} className="aspect-auto h-40 w-full justify-start">
        <AreaChart data={points} margin={{ top: 12, right: 8, bottom: 8, left: 4 }}>
          <XAxis dataKey="date" hide />
          <YAxis
            orientation="right"
            domain={[min, max]}
            ticks={[min, average, max]}
            tickFormatter={(v: number) =>
              v === average
                ? `avg ${brief(history.hint.average)}`
                : brief(v === min ? minText : maxText)
            }
            axisLine={false}
            tickLine={false}
            width={78}
            interval={0}
            className="font-mono"
          />
          <ChartTooltip
            cursor={{ strokeDasharray: "3 3" }}
            content={
              <ChartTooltipContent
                hideLabel={false}
                formatter={(value) => <span className="font-mono">{String(value)}</span>}
              />
            }
          />
          <ReferenceLine
            y={average}
            strokeDasharray="4 4"
            stroke="var(--muted-foreground)"
            strokeOpacity={0.7}
          />
          <Area
            dataKey="rate"
            type="monotone"
            stroke="var(--color-rate)"
            strokeWidth={2}
            fill="var(--color-rate)"
            fillOpacity={0.1}
            dot={false}
            isAnimationActive={false}
          />
          <ReferenceDot
            x={last.date}
            y={last.rate}
            r={5}
            fill="var(--color-rate)"
            stroke="var(--card)"
            strokeWidth={2}
          />
        </AreaChart>
      </ChartContainer>
      <div
        className="text-muted-foreground flex justify-between pr-[78px] pl-1 font-mono text-xs"
        aria-hidden="true"
      >
        <span>{shortDate(first.date)}</span>
        <span>today</span>
      </div>
    </div>
  );
}

/** F10: synthetic rate history, a best-day hint (never a forecast) and a local rate alert. */
export function RateCard({ currency, selector }: { currency: string; selector: React.ReactNode }) {
  const history = useApi<RateHistory>(`/rates/history?currency=${currency}`);
  const data = history.data;
  const form = useForm<AlertValues>({
    resolver: zodResolver(alertSchema),
    mode: "onChange",
    defaultValues: { target: "" },
  });
  const target = useWatch({ control: form.control, name: "target" });

  useEffect(() => {
    form.reset({ target: readAlert(currency) });
  }, [currency, form]);

  useEffect(() => {
    if (form.formState.isDirty && form.formState.isValid) saveAlert(currency, target.trim());
  }, [target, currency, form.formState.isDirty, form.formState.isValid]);

  const triggered =
    data !== null && target.trim() !== "" && Number(data.hint.today) <= Number(target);

  return (
    <Card aria-labelledby="rate-title">
      <CardHeader>
        <CardTitle id="rate-title" className="flex flex-wrap items-center gap-2 text-base">
          {currency} rate and best-day hint
          <Chip tone="neutral">Synthetic data</Chip>
        </CardTitle>
        <CardAction>{selector}</CardAction>
      </CardHeader>
      <CardContent className="space-y-4">
        <ErrorNotice error={history.error} onRetry={history.reload} />
        {history.loading && !data ? <CardSkeleton lines={5} label="Loading rates" /> : null}
        {data ? (
          <>
            <p className="flex flex-wrap items-center gap-x-3 gap-y-1">
              <Chip tone={TONE[data.hint.kind]}>{WORDS[data.hint.kind]}</Chip>
              <span className="text-muted-foreground text-sm">
                {data.hint.gap_pct}% vs the {data.hint.days}-day average
              </span>
            </p>
            <p className="leading-relaxed">{data.hint.message}</p>
            <RateChart history={data} currency={currency} />
            <Collapsible>
              <CollapsibleTrigger className="group text-muted-foreground hover:text-foreground flex items-center gap-1 text-sm">
                <ChevronRight
                  className="size-4 transition-transform group-data-[state=open]:rotate-90"
                  aria-hidden="true"
                />
                Show the {data.points.length} values as a table
              </CollapsibleTrigger>
              <CollapsibleContent>
                <Table className="mt-2">
                  <TableHeader>
                    <TableRow>
                      <TableHead>Date</TableHead>
                      <TableHead className="text-right">
                        Synthetic rate (BDT per {currency})
                      </TableHead>
                    </TableRow>
                  </TableHeader>
                  <TableBody>
                    {data.points.map((p) => (
                      <TableRow key={p.date}>
                        <TableCell className="font-mono tabular-nums">{p.date}</TableCell>
                        <TableCell className="text-right font-mono tabular-nums">
                          {p.rate}
                        </TableCell>
                      </TableRow>
                    ))}
                  </TableBody>
                </Table>
              </CollapsibleContent>
            </Collapsible>
            <div className="border-t pt-4">
              <Field
                label="Rate alert: tell me when the synthetic rate is at or below"
                htmlFor={`alert-${currency}`}
                error={form.formState.errors.target?.message}
              >
                <Input
                  id={`alert-${currency}`}
                  inputMode="decimal"
                  placeholder={data.hint.average}
                  className="font-mono"
                  aria-describedby={`alert-${currency}-hint`}
                  {...form.register("target")}
                />
              </Field>
              <p id={`alert-${currency}-hint`} className="text-muted-foreground mt-1.5 text-xs">
                Saved in this browser only. A lower rate is better for you.
              </p>
            </div>
            {triggered ? (
              <Notice tone="ok">
                Alert: today&apos;s synthetic rate {data.hint.today} is at or below your {target}.
              </Notice>
            ) : null}
            <p className="text-muted-foreground text-xs">{data.disclaimer}</p>
          </>
        ) : null}
      </CardContent>
    </Card>
  );
}
