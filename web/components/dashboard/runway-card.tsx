"use client";

import { zodResolver } from "@hookform/resolvers/zod";
import { useEffect, useRef, useState } from "react";
import { useForm, type Resolver, useWatch } from "react-hook-form";
import { z } from "zod";

import { CurrencySelect } from "@/components/app/country-select";
import { ErrorNotice } from "@/components/app/notice";
import { Chip, NotVerifiedBadge } from "@/components/app/status";
import { Button } from "@/components/ui/button";
import { Card, CardAction, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import {
  Form,
  FormControl,
  FormField,
  FormItem,
  FormLabel,
  FormMessage,
} from "@/components/ui/form";
import { Input } from "@/components/ui/input";
import { get } from "@/lib/api/client";
import type { Corridor, RunwayView } from "@/lib/api/types";
import { corridorForCurrency, exponentFor, formDefaults } from "@/lib/corridors";
import { parseMajorToMinor } from "@/lib/money";
import { moneyText } from "@/lib/schemas/money";
import { cn } from "@/lib/utils";

const CELLS = 12;

function schemaFor(exponent: number) {
  return z.object({
    currency: z.string().min(1),
    amount: moneyText("Amount", () => exponent),
    monthly: moneyText("Monthly cost", () => exponent),
  });
}
type Values = z.infer<ReturnType<typeof schemaFor>>;

/** Twelve cells, one per month; the last filled cell is partly filled for the fraction. */
function RunwayBar({ months }: { months: number }) {
  const whole = Math.min(CELLS, Math.floor(months));
  const fraction = months >= CELLS ? 0 : months - whole;
  return (
    <div className="flex gap-1.5" aria-hidden="true">
      {Array.from({ length: CELLS }, (_, index) => (
        <div key={index} className="bg-border h-2 flex-1 overflow-hidden rounded-full">
          {index < whole ? <div className="bg-primary h-full w-full rounded-full" /> : null}
          {index === whole && fraction > 0 ? (
            <div
              className="bg-primary h-full rounded-full"
              style={{ width: `${Math.round(fraction * 100)}%` }}
            />
          ) : null}
        </div>
      ))}
    </div>
  );
}

/** F9 living-cost runway: how many months an amount covers. The engine does the arithmetic. */
export function RunwayCard({ corridors }: { corridors: Corridor[] }) {
  const start = corridors.some((c) => c.currency === "GBP")
    ? "GBP"
    : (corridors[0]?.currency ?? "GBP");
  const defaults = formDefaults(corridorForCurrency(corridors, start));
  const [result, setResult] = useState<RunwayView | null>(null);
  const [error, setError] = useState<Error | null>(null);
  const resolver: Resolver<Values> = (values, context, options) =>
    zodResolver(schemaFor(exponentFor(corridors, values.currency)))(values, context, options);
  const form = useForm<Values>({
    resolver,
    mode: "onBlur",
    defaultValues: {
      currency: start,
      amount: defaults.runwayAmount,
      monthly: defaults.runwayMonthly,
    },
  });
  const currency = useWatch({ control: form.control, name: "currency" });

  async function run(values: Values) {
    setError(null);
    const exponent = exponentFor(corridors, values.currency);
    const total = parseMajorToMinor(values.amount, exponent);
    const cost = parseMajorToMinor(values.monthly, exponent);
    if (!total.ok || !cost.ok) return;
    try {
      setResult(
        await get<RunwayView>(
          `/planner/runway?amount_minor=${total.minor}&monthly_cost_minor=${cost.minor}&currency=${values.currency}`,
        ),
      );
    } catch (e) {
      setError(e as Error);
    }
  }

  const started = useRef(false);
  useEffect(() => {
    if (started.current) return;
    started.current = true;
    void run(form.getValues());
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  /** Another currency is a different size of money, so the amounts start again in proportion. */
  function chooseCurrency(next: string) {
    form.setValue("currency", next);
    const d = formDefaults(corridorForCurrency(corridors, next));
    form.setValue("amount", d.runwayAmount, { shouldValidate: true });
    form.setValue("monthly", d.runwayMonthly, { shouldValidate: true });
  }

  const months = result ? Number(result.display.covers.split(" ")[0]) : 0;

  return (
    <Card aria-labelledby="runway-title">
      <CardHeader>
        <CardTitle id="runway-title" className="text-base">
          Living-cost runway
        </CardTitle>
        <CardAction>
          <Chip tone="neutral" title="Rules are not verified against an official source.">
            Indicative
          </Chip>
        </CardAction>
      </CardHeader>
      <CardContent className="space-y-4">
        <Form {...form}>
          <form onSubmit={form.handleSubmit(run)} className="space-y-4" noValidate>
            <div className="grid gap-4 sm:grid-cols-2">
              <FormItem>
                <FormLabel htmlFor="rw-currency">Currency</FormLabel>
                <CurrencySelect
                  id="rw-currency"
                  corridors={corridors}
                  value={currency}
                  onValueChange={chooseCurrency}
                />
              </FormItem>
              <FormField
                control={form.control}
                name="amount"
                render={({ field }) => (
                  <FormItem>
                    <FormLabel>Amount sent</FormLabel>
                    <FormControl>
                      <Input inputMode="decimal" className="font-mono" {...field} />
                    </FormControl>
                    <FormMessage />
                  </FormItem>
                )}
              />
            </div>
            <FormField
              control={form.control}
              name="monthly"
              render={({ field }) => (
                <FormItem>
                  <FormLabel>Monthly living cost</FormLabel>
                  <FormControl>
                    <Input inputMode="decimal" className="font-mono" {...field} />
                  </FormControl>
                  <FormMessage />
                </FormItem>
              )}
            />
            <Button type="submit" variant="outline" loading={form.formState.isSubmitting}>
              Calculate runway
            </Button>
          </form>
        </Form>
        <ErrorNotice error={error} />
        {result ? (
          <div className="bg-muted space-y-3 rounded-lg p-4" aria-live="polite">
            <p className="flex items-baseline gap-2">
              <span className={cn("font-mono text-4xl font-semibold tabular-nums")}>{months}</span>
              <span className="text-muted-foreground">months of living costs covered</span>
            </p>
            <RunwayBar months={months} />
            <p className="text-muted-foreground text-xs">
              Based on {result.display.amount} sent and {result.display.monthly_cost} a month.
              Indicative.
            </p>
            <dl className="grid grid-cols-[auto_1fr] gap-x-4 gap-y-1 border-t pt-3 text-xs">
              <dt className="text-muted-foreground">Full months</dt>
              <dd>{result.display.full_months}</dd>
              <dt className="text-muted-foreground">Left over</dt>
              <dd>{result.display.leftover}</dd>
              <dt className="text-muted-foreground">Monthly cost in USD</dt>
              <dd>{result.monthly_cost_usd_equivalent}</dd>
              <dt className="text-muted-foreground">Reference</dt>
              <dd>
                {result.reference.value} per month{" "}
                {result.reference.badge ? <NotVerifiedBadge /> : null}
                <div className="text-muted-foreground">{result.reference.note}</div>
              </dd>
            </dl>
          </div>
        ) : null}
      </CardContent>
    </Card>
  );
}
