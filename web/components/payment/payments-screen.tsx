"use client";

import { Download, Inbox, Plus, Search } from "lucide-react";
import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { useEffect, useMemo, useState } from "react";

import { DateRangePicker } from "@/components/app/date-range-picker";
import { EmptyState } from "@/components/app/empty-state";
import { ErrorNotice } from "@/components/app/notice";
import { PageHead } from "@/components/app/page-head";
import { CancelPaymentDialog } from "@/components/payment/cancel-payment-dialog";
import { PaymentSheet } from "@/components/payment/payment-sheet";
import { PaymentsTable } from "@/components/payment/payments-table";
import { useAuth } from "@/components/providers/auth-provider";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardAction, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
  Pagination,
  PaginationContent,
  PaginationEllipsis,
  PaginationItem,
  PaginationLink,
  PaginationNext,
  PaginationPrevious,
} from "@/components/ui/pagination";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip";
import { loadAllPayments } from "@/lib/api/payments";
import type { PaymentBrief } from "@/lib/api/types";
import { useInvalidateApi, useLoader } from "@/lib/api/use-api";
import {
  STATUS_FILTERS,
  STATUS_LABEL,
  currenciesOf,
  filterExceptStatus,
  filterPayments,
  pageNumbers,
  paginate,
  paymentsToCsv,
  sortPayments,
  statusCounts,
  type SortKey,
  type StatusFilter,
} from "@/lib/domain/payments";
import { dhakaToday } from "@/lib/format";
import {
  DEFAULT_PAYMENTS_PARAMS,
  parseRange,
  readPaymentsParams,
  writePaymentsParams,
  type PaymentsParams,
} from "@/lib/schemas/payments-params";

const PAGE_SIZE = 10;
const ALL_CURRENCIES = "__all__";
const TAB_LABEL: Record<StatusFilter, string> = { all: "All", ...STATUS_LABEL };

function download(payments: PaymentBrief[], today: string): void {
  const blob = new Blob([paymentsToCsv(payments)], { type: "text/csv;charset=utf-8" });
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = `studyroute-payments-${today}.csv`;
  link.click();
  URL.revokeObjectURL(url);
}

const STEPS = [
  { title: "Compare", text: "Rank providers by the true total cost." },
  { title: "Check", text: "Work through the safe checklist, with a human in control." },
  { title: "Send", text: "Simulated only. Nothing reaches a real bank." },
];

/** The parent's simulated payments, with filters, counts and a detail sheet. Filters live in the address. */
export function PaymentsScreen() {
  const { user } = useAuth();
  const search = useSearchParams();
  const invalidate = useInvalidateApi();
  const all = useLoader<PaymentBrief[]>(["payments", "all"], loadAllPayments);
  const today = useMemo(() => dhakaToday(), []);
  const [params, setParams] = useState<PaymentsParams>(() => readPaymentsParams(search));
  const [text, setText] = useState(params.q);
  const [opened, setOpened] = useState<PaymentBrief | null>(null);
  const [cancelFor, setCancelFor] = useState<PaymentBrief | null>(null);

  function update(patch: Partial<PaymentsParams>) {
    setParams((current) => ({ ...current, page: 1, ...patch }));
  }

  // Typing in the search box changes the view 300 ms after the last key.
  useEffect(() => {
    const timer = window.setTimeout(() => {
      setParams((current) =>
        current.q === text.trim() ? current : { ...current, q: text.trim(), page: 1 },
      );
    }, 300);
    return () => window.clearTimeout(timer);
  }, [text]);

  const payments = useMemo(() => all.data ?? [], [all.data]);
  const base = useMemo(
    () =>
      filterExceptStatus(payments, {
        q: params.q,
        currency: params.currency,
        range: parseRange(params.range, today) ?? null,
      }),
    [payments, params.q, params.currency, params.range, today],
  );
  const counts = statusCounts(base);
  const filtered = useMemo(
    () =>
      sortPayments(
        filterPayments(payments, {
          status: params.status,
          q: params.q,
          currency: params.currency,
          range: parseRange(params.range, today) ?? null,
        }),
        params.sort,
        params.dir,
      ),
    [
      payments,
      params.status,
      params.q,
      params.currency,
      params.range,
      params.sort,
      params.dir,
      today,
    ],
  );
  const slice = paginate(filtered, params.page, PAGE_SIZE);
  const currencies = useMemo(() => currenciesOf(payments), [payments]);

  // The address always describes the view, so it can be shared and survives a reload.
  const query = writePaymentsParams({ ...params, page: slice.page });
  useEffect(() => {
    window.history.replaceState(null, "", `${window.location.pathname}${query ? `?${query}` : ""}`);
  }, [query]);

  if (!user) return null;
  const canCompare = user.permissions.includes("quotes:create");
  const mayCancel = user.permissions.includes("payments:cancel");
  const loading = all.loading && !all.data;
  const none = !loading && !all.error && payments.length === 0;
  const noMatch = !loading && !none && filtered.length === 0;

  function sortBy(key: SortKey) {
    setParams((current) => ({
      ...current,
      page: 1,
      sort: key,
      dir: current.sort === key && current.dir === "asc" ? "desc" : "asc",
    }));
  }

  function clearFilters() {
    setText("");
    setParams({ ...DEFAULT_PAYMENTS_PARAMS, range: "all" });
  }

  const exportButton = (
    <Button
      type="button"
      variant="outline"
      className="bg-card gap-2"
      disabled={filtered.length === 0}
      onClick={() => download(filtered, today)}
    >
      <Download aria-hidden="true" />
      Export
    </Button>
  );

  return (
    <div className="space-y-6">
      <PageHead
        title="Payments"
        actions={
          canCompare ? (
            <Button asChild>
              <Link href="/compare/">
                <Plus aria-hidden="true" />
                New comparison
              </Link>
            </Button>
          ) : null
        }
      >
        Every payment here is simulated. Nothing is sent to a real bank.
      </PageHead>

      <Card className="gap-4">
        <CardContent className="space-y-4">
          <Tabs
            value={params.status}
            onValueChange={(value) => update({ status: value as StatusFilter })}
          >
            <TabsList className="flex-wrap justify-start group-data-[orientation=horizontal]/tabs:h-auto">
              {STATUS_FILTERS.map((status) => (
                <TabsTrigger key={status} value={status} className="gap-2 px-3 py-1.5">
                  {TAB_LABEL[status]}
                  <Badge variant="muted" className="bg-background/70 px-1.5 text-[11px]">
                    {counts[status]}
                  </Badge>
                </TabsTrigger>
              ))}
            </TabsList>
            <div className="flex flex-wrap items-center gap-2">
              <div className="relative min-w-52 flex-1 sm:max-w-xs">
                <Label htmlFor="payments-search" className="sr-only">
                  Search by reference or recipient
                </Label>
                <Search
                  className="text-muted-foreground pointer-events-none absolute top-1/2 left-3 size-4 -translate-y-1/2"
                  aria-hidden="true"
                />
                <Input
                  id="payments-search"
                  type="search"
                  autoComplete="off"
                  placeholder="Search by reference or recipient"
                  className="pl-9"
                  value={text}
                  onChange={(event) => setText(event.target.value)}
                  maxLength={80}
                />
              </div>
              <Select
                value={params.currency || ALL_CURRENCIES}
                onValueChange={(value) =>
                  update({ currency: value === ALL_CURRENCIES ? "" : value })
                }
              >
                <SelectTrigger aria-label="Currency" className="bg-card w-40">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value={ALL_CURRENCIES}>All currencies</SelectItem>
                  {currencies.map((code) => (
                    <SelectItem key={code} value={code}>
                      {code}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
              <DateRangePicker
                value={params.range}
                today={today}
                onChange={(value) => update({ range: value })}
              />
              {filtered.length === 0 ? (
                <Tooltip>
                  <TooltipTrigger asChild>
                    <span tabIndex={0} className="inline-flex rounded-md">
                      {exportButton}
                    </span>
                  </TooltipTrigger>
                  <TooltipContent>Nothing to export yet</TooltipContent>
                </Tooltip>
              ) : (
                exportButton
              )}
            </div>
            <TabsContent value={params.status} className="space-y-4">
              <ErrorNotice error={all.error} onRetry={all.reload} />
              {none ? (
                <EmptyState
                  icon={Inbox}
                  title="No payments yet."
                  action={
                    canCompare ? (
                      <Link
                        href="/compare/"
                        className="text-primary text-sm underline underline-offset-4"
                      >
                        Compare providers to start one.
                      </Link>
                    ) : undefined
                  }
                />
              ) : noMatch ? (
                <EmptyState
                  icon={Search}
                  title="No payments match these filters."
                  action={
                    <Button type="button" variant="outline" size="sm" onClick={clearFilters}>
                      Clear filters
                    </Button>
                  }
                />
              ) : all.error && !all.data ? null : (
                <PaymentsTable
                  rows={slice.items}
                  loading={loading}
                  sort={params.sort}
                  dir={params.dir}
                  onSort={sortBy}
                  onOpen={setOpened}
                  mayCancel={mayCancel}
                  onCancel={setCancelFor}
                />
              )}
              <div className="flex flex-wrap items-center justify-between gap-3">
                <p role="status" className="text-muted-foreground text-xs">
                  {loading
                    ? "Loading payments"
                    : `${slice.total} ${slice.total === 1 ? "payment" : "payments"}`}
                </p>
                <Pagination className="mx-0 w-auto">
                  <PaginationContent>
                    <PaginationItem>
                      <PaginationPrevious
                        disabled={slice.page <= 1}
                        onClick={() => setParams((c) => ({ ...c, page: slice.page - 1 }))}
                      />
                    </PaginationItem>
                    {slice.pages > 1
                      ? pageNumbers(slice.page, slice.pages).map((entry, index) => (
                          <PaginationItem key={`${entry}-${index}`}>
                            {entry === "gap" ? (
                              <PaginationEllipsis />
                            ) : (
                              <PaginationLink
                                isActive={entry === slice.page}
                                aria-label={`Page ${entry}`}
                                onClick={() => setParams((c) => ({ ...c, page: entry }))}
                              >
                                {entry}
                              </PaginationLink>
                            )}
                          </PaginationItem>
                        ))
                      : null}
                    <PaginationItem>
                      <PaginationNext
                        disabled={slice.page >= slice.pages}
                        onClick={() => setParams((c) => ({ ...c, page: slice.page + 1 }))}
                      />
                    </PaginationItem>
                  </PaginationContent>
                </Pagination>
              </div>
            </TabsContent>
          </Tabs>
        </CardContent>
      </Card>

      <Card aria-labelledby="how-title">
        <CardHeader>
          <CardTitle id="how-title" className="text-sm">
            How a payment works here
          </CardTitle>
          <CardAction>
            <Badge variant="muted">Simulated</Badge>
          </CardAction>
        </CardHeader>
        <CardContent>
          <ol className="grid gap-3 sm:grid-cols-3">
            {STEPS.map((step, index) => (
              <li key={step.title} className="flex gap-3 rounded-lg border p-3.5">
                <span
                  className="bg-muted text-muted-foreground flex size-5 shrink-0 items-center justify-center rounded-full text-[11px] font-medium"
                  aria-hidden="true"
                >
                  {index + 1}
                </span>
                <span>
                  <span className="block text-sm font-semibold">{step.title}</span>
                  <span className="text-muted-foreground block text-[13px]">{step.text}</span>
                </span>
              </li>
            ))}
          </ol>
        </CardContent>
      </Card>

      <PaymentSheet
        payment={opened}
        mayCancel={mayCancel}
        onClose={() => setOpened(null)}
        onCancel={(payment) => {
          setOpened(null);
          setCancelFor(payment);
        }}
      />
      <CancelPaymentDialog
        payment={cancelFor}
        onClose={() => setCancelFor(null)}
        onCancelled={() => {
          setCancelFor(null);
          void invalidate();
        }}
      />
    </div>
  );
}
