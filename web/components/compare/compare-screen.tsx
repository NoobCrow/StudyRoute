"use client";

import { zodResolver } from "@hookform/resolvers/zod";
import { useSearchParams } from "next/navigation";
import { useEffect, useMemo, useState } from "react";
import { useForm, type Resolver, useWatch } from "react-hook-form";
import { z } from "zod";

import { CountrySelect } from "@/components/app/country-select";
import { DatePicker } from "@/components/app/date-picker";
import { Notice, ErrorNotice } from "@/components/app/notice";
import { PageHead } from "@/components/app/page-head";
import { Loading } from "@/components/app/skeletons";
import { ChargeAdvisor } from "@/components/compare/charge-advisor";
import { Countdown } from "@/components/compare/countdown";
import { DraftForm } from "@/components/compare/draft-form";
import { QuoteTable } from "@/components/compare/quote-table";
import { StressCard } from "@/components/compare/stress-card";
import { useAuth } from "@/components/providers/auth-provider";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
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
import { useChatScope } from "@/hooks/use-chat-scope";
import { get, post } from "@/lib/api/client";
import type { ChargeCode, CorridorList, Quote, Recipient } from "@/lib/api/types";
import { useApi } from "@/lib/api/use-api";
import { formDefaults } from "@/lib/corridors";
import { addDaysIso } from "@/lib/format";
import { parseMajorToMinor } from "@/lib/money";
import { chargeCodes, moneyText } from "@/lib/schemas/money";

const CHARGE_LABEL: Record<ChargeCode, string> = {
  OUR: "OUR (sender pays all)",
  SHA: "SHA (shared)",
  BEN: "BEN (beneficiary pays all)",
};
const NONE = "__none__";

function schemaFor(exponent: number) {
  return z.object({
    country: z.string().min(1, "Choose a destination country."),
    amount: moneyText("Amount", () => exponent),
    purpose: z.enum(["TUITION", "LIVING"]),
    charge: z.enum(chargeCodes),
    dueDate: z.string(),
    recipientId: z.string(),
  });
}
type Values = z.infer<ReturnType<typeof schemaFor>>;

export function CompareScreen() {
  const { user } = useAuth();
  const params = useSearchParams();
  const corridors = useApi<CorridorList>("/corridors");
  const recipients = useApi<{ items: Recipient[] }>("/recipients");
  const [quote, setQuote] = useState<Quote | null>(null);
  const [selected, setSelected] = useState<string | null>(null);
  const [error, setError] = useState<Error | null>(null);
  const items = corridors.data?.items ?? [];

  const resolver: Resolver<Values> = (values, context, options) => {
    const exponent = items.find((c) => c.country === values.country)?.exponent ?? 2;
    return zodResolver(schemaFor(exponent))(values, context, options);
  };
  const form = useForm<Values>({
    resolver,
    mode: "onBlur",
    defaultValues: {
      country: "GB",
      amount: "10000",
      purpose: "TUITION",
      charge: "OUR",
      dueDate: addDaysIso(14),
      recipientId: "",
    },
  });
  const country = useWatch({ control: form.control, name: "country" });
  const charge = useWatch({ control: form.control, name: "charge" });
  const corridor = items.find((c) => c.country === country);
  const countryRecipients = useMemo(
    () => (recipients.data?.items ?? []).filter((r) => r.country === country),
    [recipients.data, country],
  );
  useChatScope({ quoteId: quote?.quote_id });

  const sharedQuote = params.get("quote");
  const sharedProvider = params.get("provider");
  useEffect(() => {
    if (!sharedQuote) return;
    get<Quote>(`/quotes/${encodeURIComponent(sharedQuote)}`)
      .then((loaded) => {
        setQuote(loaded);
        form.setValue("country", loaded.destination_country);
        setSelected(
          sharedProvider ||
            loaded.deadline_fit?.best_in_time ||
            loaded.results[0]?.provider_id ||
            null,
        );
      })
      .catch((e: unknown) => setError(e as Error));
  }, [sharedQuote, sharedProvider, form]);

  /** A new destination means a new currency, so the amount starts again from a sensible size for it. */
  function chooseCountry(next: string) {
    form.setValue("country", next);
    form.setValue("recipientId", "");
    const target = items.find((c) => c.country === next);
    if (target) form.setValue("amount", formDefaults(target).amount, { shouldValidate: true });
  }

  async function onSubmit(values: Values) {
    setError(null);
    if (!corridor) return;
    const parsed = parseMajorToMinor(values.amount, corridor.exponent);
    if (!parsed.ok) return;
    try {
      const created = await post<Quote>("/quotes", {
        target: { amount_minor: parsed.minor, currency: corridor.currency },
        purpose: values.purpose,
        destination_country: values.country,
        charge_code: values.charge,
        recipient_id: values.recipientId || undefined,
        due_date: values.dueDate || undefined,
      });
      setQuote(created);
      setSelected(created.deadline_fit?.best_in_time ?? created.results[0]?.provider_id ?? null);
    } catch (e) {
      setError(e as Error);
    }
  }

  const canDraft = user?.permissions.includes("payments:draft") ?? false;
  const busy = form.formState.isSubmitting;

  return (
    <div className="space-y-6">
      <PageHead title="Compare providers">
        Rank providers by the true total cost, including the hidden exchange-rate margin and the
        fees taken on the way.
      </PageHead>
      <Card aria-labelledby="quote-title">
        <CardHeader>
          <CardTitle id="quote-title" className="text-base">
            What should arrive?
          </CardTitle>
        </CardHeader>
        <CardContent>
          <Form {...form}>
            <form onSubmit={form.handleSubmit(onSubmit)} className="space-y-4" noValidate>
              <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
                <FormItem>
                  <FormLabel htmlFor="q-country">Destination</FormLabel>
                  <CountrySelect
                    id="q-country"
                    corridors={items}
                    withCurrency
                    value={country}
                    onValueChange={chooseCountry}
                  />
                </FormItem>
                <FormField
                  control={form.control}
                  name="amount"
                  render={({ field }) => (
                    <FormItem>
                      <FormLabel>
                        Amount the beneficiary must receive
                        {corridor ? ` (${corridor.currency})` : ""}
                      </FormLabel>
                      <FormControl>
                        <Input inputMode="decimal" className="font-mono" {...field} />
                      </FormControl>
                      <FormMessage />
                    </FormItem>
                  )}
                />
                <FormField
                  control={form.control}
                  name="purpose"
                  render={({ field }) => (
                    <FormItem>
                      <FormLabel htmlFor="q-purpose">Purpose</FormLabel>
                      <Select value={field.value} onValueChange={field.onChange}>
                        <SelectTrigger id="q-purpose" className="w-full">
                          <SelectValue />
                        </SelectTrigger>
                        <SelectContent>
                          <SelectItem value="TUITION">Tuition</SelectItem>
                          <SelectItem value="LIVING">Living costs</SelectItem>
                        </SelectContent>
                      </Select>
                    </FormItem>
                  )}
                />
                <FormField
                  control={form.control}
                  name="charge"
                  render={({ field }) => (
                    <FormItem>
                      <FormLabel htmlFor="q-charge">Charge code</FormLabel>
                      <Select value={field.value} onValueChange={field.onChange}>
                        <SelectTrigger id="q-charge" className="w-full">
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
                <FormField
                  control={form.control}
                  name="dueDate"
                  render={({ field }) => (
                    <FormItem>
                      <FormLabel htmlFor="q-due">University due date</FormLabel>
                      <DatePicker id="q-due" value={field.value} onChange={field.onChange} />
                    </FormItem>
                  )}
                />
                <FormField
                  control={form.control}
                  name="recipientId"
                  render={({ field }) => (
                    <FormItem>
                      <FormLabel htmlFor="q-recipient">Recipient (optional)</FormLabel>
                      <Select
                        value={field.value || NONE}
                        onValueChange={(v) => field.onChange(v === NONE ? "" : v)}
                      >
                        <SelectTrigger id="q-recipient" className="w-full">
                          <SelectValue />
                        </SelectTrigger>
                        <SelectContent>
                          <SelectItem value={NONE}>Choose later</SelectItem>
                          {countryRecipients.map((r) => (
                            <SelectItem key={r.recipient_id} value={r.recipient_id}>
                              {r.display_name}
                            </SelectItem>
                          ))}
                        </SelectContent>
                      </Select>
                    </FormItem>
                  )}
                />
              </div>
              <ChargeAdvisor value={charge} />
              <ErrorNotice error={error} />
              <Button type="submit" loading={busy} disabled={!corridor}>
                {busy ? "Asking providers..." : "Get quotes"}
              </Button>
            </form>
          </Form>
        </CardContent>
      </Card>

      {busy && !quote ? <Loading what="Asking the synthetic providers" /> : null}
      {quote ? (
        <Card aria-labelledby="results-title">
          <CardHeader className="flex-row flex-wrap items-center justify-between gap-2">
            <CardTitle id="results-title" className="text-base">
              Results for {quote.target.formatted}
            </CardTitle>
            <Countdown expiresAt={quote.expires_at} />
          </CardHeader>
          <CardContent className="space-y-3">
            <p className="text-muted-foreground text-xs">
              Mid-market rate {quote.mid_rate.display} ({quote.mid_rate.source}, as of{" "}
              {quote.mid_rate.as_of}). {quote.disclaimer}
            </p>
            <QuoteTable quote={quote} selected={selected} onSelect={setSelected} />
            <p className="text-muted-foreground text-xs">
              Quote {quote.quote_id}. Input hash {quote.input_hash.slice(0, 18)}...
            </p>
          </CardContent>
        </Card>
      ) : null}
      {quote ? (
        <StressCard
          quoteId={quote.quote_id}
          providerId={selected ?? quote.results[0]?.provider_id ?? ""}
        />
      ) : null}
      {quote && selected && canDraft ? (
        <DraftForm
          key={`${quote.quote_id}-${selected}`}
          quote={quote}
          providerId={selected}
          recipients={recipients.data?.items ?? []}
          initialRecipient={quote.recipient_id ?? form.getValues("recipientId")}
        />
      ) : null}
      {quote && !canDraft ? (
        <Notice tone="info">
          Only the paying parent can create a draft payment. You can share this comparison and ask
          the assistant about it.
        </Notice>
      ) : null}
    </div>
  );
}
