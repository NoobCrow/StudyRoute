"use client";

import { zodResolver } from "@hookform/resolvers/zod";
import { useEffect, useRef, useState } from "react";
import { useForm, type Resolver, useWatch } from "react-hook-form";
import { z } from "zod";

import { CurrencySelect } from "@/components/app/country-select";
import { ErrorNotice } from "@/components/app/notice";
import { SendPlanTable } from "@/components/app/send-plan-table";
import { Chip } from "@/components/app/status";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import {
  Form,
  FormControl,
  FormField,
  FormItem,
  FormLabel,
  FormMessage,
} from "@/components/ui/form";
import { Input } from "@/components/ui/input";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { get } from "@/lib/api/client";
import type { ChargeCode, Corridor, SendPlan } from "@/lib/api/types";
import { corridorForCurrency, exponentFor, formDefaults } from "@/lib/corridors";
import { parseMajorToMinor } from "@/lib/money";
import { chargeCodes, moneyText, wholeMonths } from "@/lib/schemas/money";

function schemaFor(exponent: number) {
  return z.object({
    currency: z.string().min(1),
    monthly: moneyText("Monthly amount", () => exponent),
    months: wholeMonths,
    charge: z.enum(chargeCodes),
  });
}
type Values = z.infer<ReturnType<typeof schemaFor>>;

const CHARGE_LABEL: Record<ChargeCode, string> = {
  OUR: "OUR (sender pays all)",
  SHA: "SHA (shared)",
  BEN: "BEN (beneficiary pays all)",
};

/** Smart send plan: how often to send living costs. Fixed fees are paid on every transfer. */
export function SendPlanCard({ corridors }: { corridors: Corridor[] }) {
  const start = corridors.some((c) => c.currency === "GBP")
    ? "GBP"
    : (corridors[0]?.currency ?? "GBP");
  const [plan, setPlan] = useState<SendPlan | null>(null);
  const [error, setError] = useState<Error | null>(null);
  const [revealed, setRevealed] = useState(false);
  const resolver: Resolver<Values> = (values, context, options) =>
    zodResolver(schemaFor(exponentFor(corridors, values.currency)))(values, context, options);
  const form = useForm<Values>({
    resolver,
    mode: "onBlur",
    defaultValues: {
      currency: start,
      monthly: formDefaults(corridorForCurrency(corridors, start)).sendPlanMonthly,
      months: "12",
      charge: "OUR",
    },
  });
  const currency = useWatch({ control: form.control, name: "currency" });
  const monthsText = useWatch({ control: form.control, name: "months" });
  const transfers = /^[0-9]+$/.test(monthsText.trim()) ? Number(monthsText) : null;

  async function run(values: Values) {
    setError(null);
    const amount = parseMajorToMinor(values.monthly, exponentFor(corridors, values.currency));
    if (!amount.ok) return;
    try {
      setPlan(
        await get<SendPlan>(
          `/planner/send-plan?monthly_minor=${amount.minor}&months=${Number(values.months)}&currency=${values.currency}&charge_code=${values.charge}`,
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

  /** Another currency is a different size of money, so the monthly amount starts again in proportion. */
  function chooseCurrency(next: string) {
    form.setValue("currency", next);
    form.setValue("monthly", formDefaults(corridorForCurrency(corridors, next)).sendPlanMonthly, {
      shouldValidate: true,
    });
  }

  return (
    <Card aria-labelledby="sendplan-title">
      <CardHeader>
        <div className="flex items-center justify-between">
          <CardTitle id="sendplan-title" className="text-base">
            Smart send plan
          </CardTitle>
          <Chip tone="neutral" title="Rules are not verified against an official source.">
            Indicative
          </Chip>
        </div>
        <CardDescription>
          Monthly or all at once? Fixed and SWIFT fees are paid on every transfer, so how often you
          send changes the real cost.
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-5">
        <Form {...form}>
          <form
            onSubmit={form.handleSubmit(async (values) => {
              setRevealed(true);
              await run(values);
            })}
            className="space-y-4"
            noValidate
          >
            <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
              <FormItem>
                <FormLabel htmlFor="sp-currency">Currency</FormLabel>
                <CurrencySelect
                  id="sp-currency"
                  corridors={corridors}
                  value={currency}
                  onValueChange={chooseCurrency}
                />
              </FormItem>
              <FormField
                control={form.control}
                name="monthly"
                render={({ field }) => (
                  <FormItem>
                    <FormLabel>Needed each month</FormLabel>
                    <FormControl>
                      <Input inputMode="decimal" className="font-mono" {...field} />
                    </FormControl>
                    <FormMessage />
                  </FormItem>
                )}
              />
              <FormField
                control={form.control}
                name="months"
                render={({ field }) => (
                  <FormItem>
                    <FormLabel>Months to cover</FormLabel>
                    <FormControl>
                      <Input inputMode="numeric" className="font-mono" {...field} />
                    </FormControl>
                    <FormMessage />
                  </FormItem>
                )}
              />
              <FormField
                control={form.control}
                name="charge"
                render={({ field }) => (
                  <FormItem>
                    <FormLabel htmlFor="sp-charge">Charge code</FormLabel>
                    <Select value={field.value} onValueChange={field.onChange}>
                      <SelectTrigger id="sp-charge" className="w-full">
                        <SelectValue />
                      </SelectTrigger>
                      <SelectContent>
                        {chargeCodes.map((code) => (
                          <SelectItem key={code} value={code}>
                            {CHARGE_LABEL[code]}
                          </SelectItem>
                        ))}
                      </SelectContent>
                    </Select>
                  </FormItem>
                )}
              />
            </div>
            <div className="flex flex-wrap items-center gap-4">
              <Button type="submit" variant="outline" loading={form.formState.isSubmitting}>
                Compare ways to send
              </Button>
              {plan ? (
                <span className="text-muted-foreground text-sm">
                  To cover:{" "}
                  <span className="text-foreground font-mono tabular-nums">
                    {plan.total.formatted}
                  </span>
                </span>
              ) : null}
            </div>
          </form>
        </Form>
        <ErrorNotice error={error} />
        <div className="grid gap-4 sm:grid-cols-2">
          <div className="bg-card rounded-lg border p-4">
            <p className="text-muted-foreground text-xs">Send monthly</p>
            <p className="mt-1 text-xl font-semibold">{transfers ?? "N"} transfers</p>
            <p className="text-muted-foreground mt-1 text-xs">
              Fixed and SWIFT fees paid {transfers ?? "N"} times
            </p>
          </div>
          <div className="bg-card rounded-lg border p-4">
            <p className="text-muted-foreground text-xs">Send all at once</p>
            <p className="mt-1 text-xl font-semibold">1 transfer</p>
            <p className="text-muted-foreground mt-1 text-xs">Fixed and SWIFT fees paid once</p>
          </div>
        </div>
        {plan && revealed ? <SendPlanTable plan={plan} /> : null}
      </CardContent>
    </Card>
  );
}
