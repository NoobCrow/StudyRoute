"use client";

import { Check, CircleAlert } from "lucide-react";
import { useEffect, useState } from "react";

import { Field } from "@/components/app/field";
import { ErrorNotice } from "@/components/app/notice";
import { CardSkeleton } from "@/components/app/skeletons";
import { Chip, NotVerifiedBadge } from "@/components/app/status";
import { CitySheet } from "@/components/guide/city-sheet";
import { Button } from "@/components/ui/button";
import { Card, CardAction, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { InputGroup, InputGroupAddon, InputGroupInput } from "@/components/ui/input-group";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import type { BudgetCity, Housing, StudentBudget } from "@/lib/api/types";
import { useApi } from "@/lib/api/use-api";
import { parseMajorToMinor } from "@/lib/money";
import type { GuideParams } from "@/lib/schemas/guide-params";

const ALL = "__all__";
const HOUSING: Record<Housing, string> = {
  shared: "A room in a shared flat",
  studio: "Your own studio",
};

function budgetPath(params: GuideParams): string {
  const query = new URLSearchParams({ housing: params.housing });
  const applied = params.budget === "" ? null : parseMajorToMinor(params.budget, 2);
  if (applied?.ok) query.set("budget_bdt_minor", String(applied.minor));
  if (params.country) query.set("country", params.country);
  return `/planner/student-budget?${query.toString()}`;
}

function FitChip({ row }: { row: BudgetCity }) {
  if (row.fits === null) return null;
  return row.fits ? (
    <Chip tone="ok">
      <Check aria-hidden="true" className="size-3" />
      Fits, {row.spare_bdt?.formatted} to spare
    </Chip>
  ) : (
    <Chip tone="warn">
      <CircleAlert aria-hidden="true" className="size-3" />
      Short by {row.gap_bdt?.formatted}
    </Chip>
  );
}

/** Which student cities a monthly budget in taka covers: the engine's figures, cheapest first. */
export function BudgetPanel({
  params,
  onChange,
}: {
  params: GuideParams;
  onChange: (patch: Partial<GuideParams>) => void;
}) {
  const answer = useApi<StudentBudget>(budgetPath(params), { keepPrevious: true });
  const [text, setText] = useState(params.budget);
  const [opened, setOpened] = useState<BudgetCity | null>(null);

  // The budget changes the list 300 ms after the last key, and only when it is a valid amount.
  useEffect(() => {
    const timer = window.setTimeout(() => {
      const cleaned = text.trim().replace(/[,\s]/g, "");
      if (cleaned === params.budget) return;
      if (cleaned === "" || parseMajorToMinor(cleaned, 2).ok) onChange({ budget: cleaned });
    }, 300);
    return () => window.clearTimeout(timer);
  }, [text, params.budget, onChange]);

  const cleaned = text.trim().replace(/[,\s]/g, "");
  const typed = cleaned === "" ? null : parseMajorToMinor(cleaned, 2);
  const budgetError = typed && !typed.ok ? typed.error : null;
  const view = answer.data;
  const judged = view?.budget != null;

  return (
    <div className="space-y-6">
      <Card aria-labelledby="budget-form-title">
        <CardHeader>
          <CardTitle id="budget-form-title" className="text-base">
            Find a city that fits your budget
          </CardTitle>
        </CardHeader>
        <CardContent>
          <div className="grid gap-4 sm:grid-cols-3">
            <Field
              label="Monthly budget"
              htmlFor="g-budget"
              hint="What you can send each month. Leave it empty to see every city."
              error={budgetError}
            >
              <InputGroup>
                <InputGroupAddon>BDT</InputGroupAddon>
                <InputGroupInput
                  id="g-budget"
                  inputMode="decimal"
                  autoComplete="off"
                  className="font-mono tabular-nums"
                  aria-invalid={budgetError ? true : undefined}
                  aria-describedby={budgetError ? undefined : "g-budget-hint"}
                  value={text}
                  onChange={(event) => setText(event.target.value.replace(/[^0-9.,\s]/g, ""))}
                />
              </InputGroup>
            </Field>
            <Field label="Where you would live" htmlFor="g-housing">
              <Select
                value={params.housing}
                onValueChange={(value) => onChange({ housing: value as Housing })}
              >
                <SelectTrigger id="g-housing" className="w-full">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  {(Object.keys(HOUSING) as Housing[]).map((key) => (
                    <SelectItem key={key} value={key}>
                      {HOUSING[key]}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </Field>
            <Field label="Country" htmlFor="g-country">
              <Select
                value={params.country || ALL}
                onValueChange={(value) => onChange({ country: value === ALL ? "" : value })}
              >
                <SelectTrigger id="g-country" className="w-full">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value={ALL}>All countries</SelectItem>
                  {(view?.countries ?? []).map((c) => (
                    <SelectItem key={c.country} value={c.country}>
                      {c.name}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </Field>
          </div>
        </CardContent>
      </Card>

      <ErrorNotice error={answer.error} onRetry={answer.reload} />
      {!view && answer.loading ? <CardSkeleton lines={6} label="Loading the cities" /> : null}
      {view ? (
        <Card aria-labelledby="budget-results-title" aria-busy={answer.loading}>
          <CardHeader>
            <CardTitle id="budget-results-title" className="text-base">
              {view.housing_label}, a month
            </CardTitle>
            <CardAction className="flex items-center gap-2">
              {view.source.verified ? null : <NotVerifiedBadge />}
              <Chip tone="neutral">Invented figures</Chip>
            </CardAction>
          </CardHeader>
          <CardContent className="space-y-4">
            <p role="status" aria-live="polite" className="text-sm">
              {judged ? (
                <>
                  <strong>
                    {view.summary.fitting} of {view.summary.cities} cities
                  </strong>{" "}
                  fit {view.budget?.formatted} a month.{" "}
                </>
              ) : (
                <>
                  {view.summary.cities} cities, cheapest first. Enter a monthly budget to see which
                  fit.{" "}
                </>
              )}
              {view.summary.cheapest ? (
                <span className="text-muted-foreground">
                  Cheapest: {view.summary.cheapest.city},{" "}
                  {view.summary.cheapest.total_bdt.formatted}.
                </span>
              ) : null}
            </p>
            <Table aria-label="Student cities, cheapest month first">
              <TableHeader>
                <TableRow>
                  <TableHead>City</TableHead>
                  <TableHead className="text-right">Rent</TableHead>
                  <TableHead className="text-right">A month</TableHead>
                  <TableHead className="text-right">A month in taka</TableHead>
                  <TableHead className="text-right">Rent share</TableHead>
                  {judged ? <TableHead>Your budget</TableHead> : null}
                  <TableHead>
                    <span className="sr-only">Details</span>
                  </TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {view.items.map((row) => (
                  <TableRow key={`${row.country}-${row.city}`}>
                    <TableCell>
                      <span className="font-medium">{row.city}</span>
                      <div className="text-muted-foreground text-xs">{row.country_name}</div>
                    </TableCell>
                    <TableCell className="text-right font-mono tabular-nums">
                      {row.lines[0]?.formatted}
                    </TableCell>
                    <TableCell className="text-right font-mono tabular-nums">
                      {row.total.formatted}
                    </TableCell>
                    <TableCell className="text-right font-mono font-semibold tabular-nums">
                      {row.total_bdt.formatted}
                    </TableCell>
                    <TableCell className="text-right font-mono tabular-nums">
                      {row.rent_share_pct}%
                    </TableCell>
                    {judged ? (
                      <TableCell>
                        <FitChip row={row} />
                      </TableCell>
                    ) : null}
                    <TableCell className="text-right">
                      <Button
                        type="button"
                        variant="outline"
                        size="sm"
                        aria-label={`Details for ${row.city}`}
                        onClick={() => setOpened(row)}
                      >
                        Details
                      </Button>
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
            <div className="text-muted-foreground space-y-1 text-xs">
              <p>{view.disclaimer}</p>
              {view.source.source_url ? (
                <p>
                  Source to confirm: <code className="font-mono">{view.source.source_url}</code>{" "}
                  (last checked {view.source.last_checked ?? "never"}).
                </p>
              ) : null}
            </div>
          </CardContent>
        </Card>
      ) : null}
      <CitySheet
        city={opened}
        housingLabel={view?.housing_label ?? ""}
        budget={view?.budget ?? null}
        disclaimer={view?.disclaimer ?? ""}
        onClose={() => setOpened(null)}
      />
    </div>
  );
}
