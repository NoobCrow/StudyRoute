"use client";

import { Circle, CircleCheck, Plus } from "lucide-react";
import { useState } from "react";

import { Chip, NotVerifiedBadge } from "@/components/app/status";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardAction, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Progress } from "@/components/ui/progress";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import type { Checklist } from "@/lib/api/types";
import {
  CHECKLIST_TABS,
  checklistCounts,
  filterChecklist,
  readiness,
  type ChecklistTab,
} from "@/lib/domain/documents";
import { cn } from "@/lib/utils";

const TAB_LABEL: Record<ChecklistTab, string> = { all: "All", missing: "Missing", ready: "Ready" };
const EMPTY: Record<ChecklistTab, string> = {
  all: "The list is empty.",
  missing: "Nothing is missing.",
  ready: "Nothing is ready yet.",
};

/** The rule's own note, unless it only repeats the indicative line that is already shown. */
function extraNote({ note, indicative }: Checklist): string {
  const text = note?.trim();
  return text && text !== indicative.trim() ? ` ${text}` : "";
}

/** What the bank may ask for, ticked off. The list and its source come from the API's rules. */
export function ChecklistCard({
  checklist,
  canWrite,
  onAdd,
}: {
  checklist: Checklist;
  canWrite: boolean;
  onAdd: (kind: string) => void;
}) {
  const [tab, setTab] = useState<ChecklistTab>("all");
  const { ready, total, percent } = readiness(checklist.items);
  const counts = checklistCounts(checklist.items);
  const shown = filterChecklist(checklist.items, tab);

  return (
    <Card aria-labelledby="checklist-title">
      <CardHeader>
        <CardTitle id="checklist-title" className="text-base">
          What the bank may ask for
        </CardTitle>
        <CardAction className="flex items-center gap-2">
          {checklist.verified ? <Chip tone="ok">Verified</Chip> : <NotVerifiedBadge />}
          <Chip tone={ready === total ? "ok" : "info"}>
            {ready} of {total} ready
          </Chip>
        </CardAction>
      </CardHeader>
      <CardContent className="space-y-4">
        <div className="flex items-center gap-3">
          <Progress
            value={percent}
            aria-label="Documents ready"
            aria-valuetext={`${percent}% ready`}
            className="bg-muted"
          />
          <span className="text-muted-foreground w-10 text-right font-mono text-xs tabular-nums">
            {percent}%
          </span>
        </div>
        <Tabs value={tab} onValueChange={(value) => setTab(value as ChecklistTab)}>
          <TabsList>
            {CHECKLIST_TABS.map((name) => (
              <TabsTrigger key={name} value={name} className="gap-2 px-3">
                {TAB_LABEL[name]}
                <Badge variant="muted" className="bg-background/70 px-1.5 text-[11px]">
                  {counts[name]}
                </Badge>
              </TabsTrigger>
            ))}
          </TabsList>
          <TabsContent value={tab}>
            {shown.length === 0 ? (
              <p className="text-muted-foreground rounded-lg border border-dashed py-6 text-center text-sm">
                {EMPTY[tab]}
              </p>
            ) : (
              <ul aria-label="Document checklist" className="-mx-6 divide-y border-y">
                {shown.map((item) => (
                  <li
                    key={item.key}
                    className="flex flex-col items-start justify-between gap-3 px-6 py-3 sm:flex-row sm:items-center"
                  >
                    <div className="flex gap-3">
                      {item.provided ? (
                        <CircleCheck
                          className="text-primary mt-0.5 size-5 shrink-0"
                          aria-hidden="true"
                        />
                      ) : (
                        <Circle
                          className="text-muted-foreground/60 mt-0.5 size-5 shrink-0"
                          aria-hidden="true"
                        />
                      )}
                      <div>
                        <strong
                          className={cn("font-semibold", item.provided && "text-muted-foreground")}
                        >
                          {item.label}
                        </strong>
                        <span className="sr-only">{item.provided ? " (ready)" : " (missing)"}</span>
                        <div className="text-muted-foreground text-xs">{item.hint}</div>
                      </div>
                    </div>
                    {canWrite && !item.provided ? (
                      <Button
                        type="button"
                        variant="outline"
                        size="sm"
                        className="shrink-0"
                        aria-label={`Add mock file for ${item.label}`}
                        onClick={() => onAdd(item.key)}
                      >
                        <Plus aria-hidden="true" />
                        Add mock file
                      </Button>
                    ) : null}
                  </li>
                ))}
              </ul>
            )}
          </TabsContent>
        </Tabs>
        <div className="text-muted-foreground space-y-1 text-xs">
          <p>
            {checklist.indicative}
            {extraNote(checklist)}
          </p>
          {checklist.source_url ? (
            <p>
              Source to confirm: <code className="font-mono">{checklist.source_url}</code> (last
              checked {checklist.last_checked ?? "never"}).
            </p>
          ) : null}
        </div>
      </CardContent>
    </Card>
  );
}
