"use client";

import { zodResolver } from "@hookform/resolvers/zod";
import { Info } from "lucide-react";
import { useSearchParams } from "next/navigation";
import { useEffect, useMemo, useRef, useState } from "react";
import { useForm, type Resolver, useWatch } from "react-hook-form";
import { toast } from "sonner";

import { CountrySelect } from "@/components/app/country-select";
import { DatePicker } from "@/components/app/date-picker";
import { Notice } from "@/components/app/notice";
import { PageHead } from "@/components/app/page-head";
import { ChargeCodeCards } from "@/components/compare/charge-code-cards";
import { DraftForm } from "@/components/compare/draft-form";
import { QuotesCard } from "@/components/compare/quotes-card";
import { RequestSummary } from "@/components/compare/request-summary";
import { StressCard } from "@/components/compare/stress-card";
import { useAuth } from "@/components/providers/auth-provider";
import { Alert, AlertDescription } from "@/components/ui/alert";
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
import { InputGroup, InputGroupAddon, InputGroupInput } from "@/components/ui/input-group";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { useChatScope } from "@/hooks/use-chat-scope";
import { get, post } from "@/lib/api/client";
import type { CorridorList, Quote, Recipient } from "@/lib/api/types";
import { useApi } from "@/lib/api/use-api";
import { formDefaults } from "@/lib/corridors";
import { addDaysIso, dhakaToday } from "@/lib/format";
import {
  amountToMinor,
  quoteRequestSchema,
  readCompareParams,
  writeCompareParams,
  type CompareValues,
} from "@/lib/schemas/compare";

const NONE = "__none__";

const DEFAULTS: CompareValues = {
  country: "GB",
  amount: "10000",
  purpose: "TUITION",
  charge: "OUR",
  dueDate: addDaysIso(14),
  recipientId: "",
};

function reducedMotion(): boolean {
  return window.matchMedia("(prefers-reduced-motion: reduce)").matches;
}

export function CompareScreen() {
  const { user } = useAuth();
  const params = useSearchParams();
  const corridors = useApi<CorridorList>("/corridors");
  const recipients = useApi<{ items: Recipient[] }>("/recipients");
  const [quote, setQuote] = useState<Quote | null>(null);
  const [selected, setSelected] = useState<string | null>(null);
  const [error, setError] = useState<Error | null>(null);
  const [startCount, setStartCount] = useState(0);
  const [resultsCount, setResultsCount] = useState(0);
  const headingRef = useRef<HTMLDivElement>(null);
  const draftRef = useRef<HTMLDivElement>(null);
  const items = useMemo(() => corridors.data?.items ?? [], [corridors.data]);
  const today = useMemo(() => dhakaToday(), []);

  const resolver: Resolver<CompareValues> = (values, context, options) => {
    const exponent = items.find((c) => c.country === values.country)?.exponent ?? 2;
    return zodResolver(quoteRequestSchema(exponent, today))(values, context, options);
  };
  const form = useForm<CompareValues>({
    resolver,
    mode: "onTouched", // errors appear after the first blur, then follow every change
    defaultValues: readCompareParams(params, { ...DEFAULTS, dueDate: addDaysIso(14) }),
  });
  // Read unconditionally: React Hook Form only tracks a state value that is read on the first render.
  const { isDirty, isSubmitting, isValid } = form.formState;
  const watched = useWatch({ control: form.control }) as CompareValues;
  const { country, charge, purpose } = watched;
  const corridor = items.find((c) => c.country === country);
  const countryRecipients = useMemo(
    () => (recipients.data?.items ?? []).filter((r) => r.country === country),
    [recipients.data, country],
  );
  useChatScope({ quoteId: quote?.quote_id });

  // A link may name a destination this server does not list: fall back to the default one.
  useEffect(() => {
    if (items.length > 0 && !items.some((c) => c.country === form.getValues("country"))) {
      form.setValue("country", DEFAULTS.country);
    }
  }, [items, form]);

  // The address always describes the form once the person has changed it, so a comparison can be shared.
  const query = writeCompareParams(watched);
  const touched = isDirty || quote !== null;
  useEffect(() => {
    if (!touched || query === "") return;
    window.history.replaceState(null, "", `${window.location.pathname}?${query}`);
  }, [query, touched]);

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

  // After Get quotes: bring the results into view and move focus to their heading.
  useEffect(() => {
    if (resultsCount === 0) return;
    const heading = headingRef.current;
    heading?.scrollIntoView({ behavior: reducedMotion() ? "auto" : "smooth", block: "start" });
    heading?.focus({ preventScroll: true });
  }, [resultsCount]);

  // "Start payment" on a row: the draft form below is for that provider, so take the person there.
  useEffect(() => {
    if (startCount === 0) return;
    const target = draftRef.current;
    if (!target) return;
    target.scrollIntoView({ behavior: reducedMotion() ? "auto" : "smooth", block: "start" });
    target
      .querySelector<HTMLElement>("input, button, [role=combobox]")
      ?.focus({ preventScroll: true });
  }, [startCount]);

  /** A new destination means a new currency, so the amount starts again from a sensible size for it. */
  function chooseCountry(next: string) {
    form.setValue("country", next, { shouldDirty: true });
    form.setValue("recipientId", "", { shouldDirty: true });
    const target = items.find((c) => c.country === next);
    if (target) {
      form.setValue("amount", formDefaults(target).amount, {
        shouldValidate: true,
        shouldDirty: true,
      });
    }
  }

  async function onSubmit(values: CompareValues) {
    setError(null);
    if (!corridor) return;
    const minor = amountToMinor(values.amount, corridor.exponent);
    if (minor === null) return;
    try {
      const created = await post<Quote>("/quotes", {
        target: { amount_minor: minor, currency: corridor.currency },
        purpose: values.purpose,
        destination_country: values.country,
        charge_code: values.charge,
        recipient_id: values.recipientId || undefined,
        due_date: values.dueDate || undefined,
      });
      setQuote(created);
      setSelected(created.deadline_fit?.best_in_time ?? created.results[0]?.provider_id ?? null);
      toast.success("Quotes are ready", {
        description: `${created.results.length} providers ranked by the true total cost.`,
      });
      setResultsCount((count) => count + 1);
    } catch (e) {
      setError(e as Error);
      toast.error("The quotes could not be fetched");
    }
  }

  const canDraft = user?.permissions.includes("payments:draft") ?? false;
  const busy = isSubmitting;

  return (
    <div className="space-y-6">
      <PageHead title="Compare providers">
        Rank providers by the true total cost, including the hidden exchange-rate margin and the
        fees taken on the way.
      </PageHead>
      <Notice tone="warn">
        These are synthetic comparisons, not accepted university payment instructions. Verify the
        institution&apos;s official route before comparing costs. For example, Manchester
        Metropolitan University says it no longer accepts direct bank transfers and directs students
        to Flywire. The server blocks direct-bank tuition for declared or name-recognised MMU
        recipients. Other institutions remain unverified. No Flywire integration or live bank
        quotes.{" "}
        <a
          className="underline"
          href="https://www.mmu.ac.uk/student-life/finance/paying-university-fees"
          target="_blank"
          rel="noreferrer"
        >
          Official MMU guidance
        </a>
      </Notice>
      <div className="grid items-start gap-6 lg:grid-cols-[minmax(0,1fr)_21.25rem]">
        <Card aria-labelledby="quote-title">
          <CardHeader>
            <CardTitle id="quote-title" className="text-base">
              What should arrive?
            </CardTitle>
            <CardDescription>
              Tell us what the university must receive. We work backwards to what you send.
            </CardDescription>
          </CardHeader>
          <CardContent>
            <Form {...form}>
              <form onSubmit={form.handleSubmit(onSubmit)} className="space-y-5" noValidate>
                <div className="grid gap-4 sm:grid-cols-2">
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
                          {corridor ? (
                            <span className="sr-only"> in {corridor.currency}</span>
                          ) : null}
                        </FormLabel>
                        <InputGroup>
                          {corridor ? <InputGroupAddon>{corridor.currency}</InputGroupAddon> : null}
                          <FormControl>
                            <InputGroupInput
                              inputMode="decimal"
                              autoComplete="off"
                              className="font-mono tabular-nums"
                              {...field}
                              onChange={(event) =>
                                field.onChange(event.target.value.replace(/[^0-9.,\s]/g, ""))
                              }
                            />
                          </FormControl>
                        </InputGroup>
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
                    name="dueDate"
                    render={({ field }) => (
                      <FormItem>
                        <FormLabel htmlFor="q-due">University due date</FormLabel>
                        <DatePicker
                          id="q-due"
                          value={field.value}
                          minIso={today}
                          onChange={(value) => {
                            field.onChange(value);
                            void form.trigger("dueDate");
                          }}
                        />
                        <FormMessage />
                      </FormItem>
                    )}
                  />
                  <FormField
                    control={form.control}
                    name="recipientId"
                    render={({ field }) => (
                      <FormItem className="sm:col-span-2">
                        <FormLabel htmlFor="q-recipient">
                          Recipient{" "}
                          <span className="text-muted-foreground font-normal">(optional)</span>
                        </FormLabel>
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
                <FormField
                  control={form.control}
                  name="charge"
                  render={({ field }) => (
                    <ChargeCodeCards
                      value={field.value}
                      onChange={field.onChange}
                      purpose={purpose}
                    />
                  )}
                />
                <Alert className="bg-muted/50">
                  <Info aria-hidden="true" />
                  <AlertDescription>
                    Check the university&apos;s own payment instructions too. Indicative. Confirm
                    with your AD bank.
                  </AlertDescription>
                </Alert>
                <Button type="submit" loading={busy} disabled={!corridor || !isValid}>
                  {busy ? "Asking providers..." : "Get quotes"}
                </Button>
              </form>
            </Form>
          </CardContent>
        </Card>
        <RequestSummary
          values={{ ...watched, charge }}
          corridor={corridor}
          className="lg:sticky lg:top-24"
        />
      </div>

      <QuotesCard
        quote={quote}
        busy={busy}
        error={error}
        currency={corridor?.currency ?? quote?.target.currency ?? ""}
        selected={selected}
        onStart={
          canDraft
            ? (providerId) => {
                setSelected(providerId);
                setStartCount((count) => count + 1);
              }
            : undefined
        }
        onRetry={() => void form.handleSubmit(onSubmit)()}
        headingRef={headingRef}
      />
      {quote ? (
        <StressCard
          quoteId={quote.quote_id}
          providerId={selected ?? quote.results[0]?.provider_id ?? ""}
        />
      ) : null}
      {quote && selected && canDraft ? (
        <div ref={draftRef}>
          <DraftForm
            key={`${quote.quote_id}-${selected}`}
            quote={quote}
            providerId={selected}
            recipients={recipients.data?.items ?? []}
            initialRecipient={quote.recipient_id ?? form.getValues("recipientId")}
          />
        </div>
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
