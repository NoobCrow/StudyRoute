"use client";

import { useSearchParams } from "next/navigation";
import { useCallback, useEffect, useState } from "react";

import { PageHead } from "@/components/app/page-head";
import { ArrivalPanel } from "@/components/guide/arrival-panel";
import { BudgetPanel } from "@/components/guide/budget-panel";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import {
  readGuideParams,
  writeGuideParams,
  type GuideParams,
  type GuideTab,
} from "@/lib/schemas/guide-params";

/**
 * The student guide: which cities a monthly budget covers, and what to do before flying and in the first
 * weeks. Both are indicative and invented for the sandbox. The view lives in the address, so it can be
 * shared and survives a reload.
 */
export function GuideScreen() {
  const search = useSearchParams();
  const [params, setParams] = useState<GuideParams>(() => readGuideParams(search));
  const update = useCallback(
    (patch: Partial<GuideParams>) => setParams((current) => ({ ...current, ...patch })),
    [],
  );

  const query = writeGuideParams(params);
  useEffect(() => {
    window.history.replaceState(null, "", `${window.location.pathname}${query ? `?${query}` : ""}`);
  }, [query]);

  return (
    <div className="space-y-6">
      <PageHead title="Student guide">
        Find a city that fits your monthly budget, then follow the steps for your first weeks
        abroad. The figures and steps are indicative and invented for the sandbox.
      </PageHead>
      <Tabs value={params.tab} onValueChange={(tab) => update({ tab: tab as GuideTab })}>
        <TabsList>
          <TabsTrigger value="budget">Budget</TabsTrigger>
          <TabsTrigger value="arrival">Arrival checklist</TabsTrigger>
        </TabsList>
        <TabsContent value="budget">
          <BudgetPanel params={params} onChange={update} />
        </TabsContent>
        <TabsContent value="arrival">
          <ArrivalPanel params={params} onChange={update} />
        </TabsContent>
      </Tabs>
    </div>
  );
}
