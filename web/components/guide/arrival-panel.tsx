"use client";

import { useMemo, useState } from "react";

import { CountrySelect } from "@/components/app/country-select";
import { Field } from "@/components/app/field";
import { ErrorNotice, Notice } from "@/components/app/notice";
import { CardSkeleton } from "@/components/app/skeletons";
import { Chip, NotVerifiedBadge } from "@/components/app/status";
import { Button } from "@/components/ui/button";
import { Card, CardAction, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Checkbox } from "@/components/ui/checkbox";
import { Label } from "@/components/ui/label";
import { Progress } from "@/components/ui/progress";
import type { ArrivalGuide, CorridorList } from "@/lib/api/types";
import { useApi } from "@/lib/api/use-api";
import { doneCount, readTicks, writeTicks } from "@/lib/domain/arrival-ticks";
import type { GuideParams } from "@/lib/schemas/guide-params";
import { cn } from "@/lib/utils";

/** What to do before flying and in the first weeks, for one country, with steps that can be ticked off. */
export function ArrivalPanel({
  params,
  onChange,
}: {
  params: GuideParams;
  onChange: (patch: Partial<GuideParams>) => void;
}) {
  const corridors = useApi<CorridorList>("/corridors");
  const guide = useApi<ArrivalGuide>(`/planner/arrival-guide?country=${params.arrival}`, {
    keepPrevious: true,
  });
  // Each country keeps its own ticks. What was ticked in this visit is held here; before that, and for
  // another country, they are read from the browser.
  const [session, setSession] = useState<{ country: string; keys: string[] } | null>(null);
  const ticks = session?.country === params.arrival ? session.keys : readTicks(params.arrival);

  const view = guide.data;
  const stepKeys = useMemo(
    () => (view ? view.stages.flatMap((stage) => stage.items.map((item) => item.key)) : []),
    [view],
  );
  const done = doneCount(ticks, stepKeys);
  const total = view?.item_count ?? 0;
  const percent = total === 0 ? 0 : Math.round((done / total) * 100);

  function toggle(key: string, checked: boolean) {
    const next = checked ? [...ticks, key] : ticks.filter((tick) => tick !== key);
    setSession({ country: params.arrival, keys: next });
    writeTicks(params.arrival, next);
  }
  function clear() {
    setSession({ country: params.arrival, keys: [] });
    writeTicks(params.arrival, []);
  }

  return (
    <div className="space-y-6">
      <div className="max-w-sm">
        <Field label="Country you are going to" htmlFor="g-arrival">
          <CountrySelect
            id="g-arrival"
            corridors={corridors.data?.items ?? []}
            value={params.arrival}
            onValueChange={(arrival) => onChange({ arrival })}
          />
        </Field>
      </div>
      <ErrorNotice error={guide.error} onRetry={guide.reload} />
      {!view && guide.loading ? <CardSkeleton lines={6} label="Loading the checklist" /> : null}
      {view ? (
        <Card aria-labelledby="arrival-title" aria-busy={guide.loading}>
          <CardHeader>
            <CardTitle id="arrival-title" className="text-base">
              Your arrival checklist: {view.country_name}
            </CardTitle>
            <CardAction className="flex items-center gap-2">
              {view.verified ? <Chip tone="ok">Verified</Chip> : <NotVerifiedBadge />}
              <Chip tone={total > 0 && done === total ? "ok" : "info"}>
                {done} of {total} done
              </Chip>
            </CardAction>
          </CardHeader>
          <CardContent className="space-y-6">
            <div className="flex items-center gap-3">
              <Progress
                value={percent}
                aria-label="Steps done"
                aria-valuetext={`${done} of ${total} steps done`}
                className="bg-muted"
              />
              <Button type="button" variant="ghost" size="sm" disabled={done === 0} onClick={clear}>
                Clear ticks
              </Button>
            </div>
            {view.general ? (
              <Notice tone="info">
                This is a general list. Steps specific to {params.arrival} are not loaded; pick one
                of the six main countries for its own steps.
              </Notice>
            ) : null}
            {view.stages.map((stage) => (
              <section key={stage.key} aria-labelledby={`stage-${stage.key}`} className="space-y-3">
                <h2 id={`stage-${stage.key}`} className="text-sm font-semibold">
                  {stage.label}
                </h2>
                <ul className="divide-y rounded-lg border">
                  {stage.items.map((step) => {
                    const checked = ticks.includes(step.key);
                    return (
                      <li key={step.key} className="flex items-start gap-3 px-4 py-3">
                        <Checkbox
                          id={`step-${step.key}`}
                          className="mt-0.5"
                          checked={checked}
                          onCheckedChange={(value) => toggle(step.key, value === true)}
                          aria-describedby={`step-${step.key}-hint`}
                        />
                        <div className="min-w-0 space-y-0.5">
                          <Label
                            htmlFor={`step-${step.key}`}
                            className={cn("font-medium", checked && "text-muted-foreground")}
                          >
                            {step.label}
                          </Label>
                          <p id={`step-${step.key}-hint`} className="text-muted-foreground text-xs">
                            {step.hint}
                          </p>
                        </div>
                      </li>
                    );
                  })}
                </ul>
              </section>
            ))}
            <div className="text-muted-foreground space-y-1 text-xs">
              <p>
                {view.indicative} {view.note}
              </p>
              <p>Your ticks are saved in this browser only.</p>
              {view.source_url ? (
                <p>
                  Source to confirm: <code className="font-mono">{view.source_url}</code> (last
                  checked {view.last_checked ?? "never"}).
                </p>
              ) : null}
            </div>
          </CardContent>
        </Card>
      ) : null}
    </div>
  );
}
