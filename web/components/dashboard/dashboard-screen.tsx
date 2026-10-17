"use client";

import { ArrowRight } from "lucide-react";
import Link from "next/link";
import { useEffect, useState } from "react";

import { CurrencySelect } from "@/components/app/country-select";
import { Field } from "@/components/app/field";
import { ErrorNotice, Notice } from "@/components/app/notice";
import { PageHead } from "@/components/app/page-head";
import { CardSkeleton } from "@/components/app/skeletons";
import { KycCard } from "@/components/dashboard/kyc-card";
import { PlannerCard } from "@/components/dashboard/planner-card";
import { RateCard } from "@/components/dashboard/rate-card";
import { RecentPaymentsCard } from "@/components/dashboard/recent-payments-card";
import { RunwayCard } from "@/components/dashboard/runway-card";
import { SendPlanCard } from "@/components/dashboard/send-plan-card";
import { YourDataCard } from "@/components/dashboard/your-data-card";
import { useAuth } from "@/components/providers/auth-provider";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { loadHealth } from "@/lib/api/health";
import type { CorridorList } from "@/lib/api/types";
import { useApi } from "@/lib/api/use-api";

function ReviewerPanel() {
  const [payerId, setPayerId] = useState("");
  useEffect(() => {
    loadHealth()
      .then((h) => h.demo && setPayerId((current) => current || h.demo?.parent_id || ""))
      .catch(() => undefined);
  }, []);
  return (
    <>
      <Card aria-labelledby="reviewer-title">
        <CardHeader>
          <CardTitle id="reviewer-title" className="text-base">
            Reviewer tools
          </CardTitle>
        </CardHeader>
        <CardContent className="space-y-4">
          <p className="text-muted-foreground text-sm">
            You can read the audit log, verify its hash chain and manage the rules. You cannot
            approve a family&apos;s payment.
          </p>
          <div className="flex flex-wrap gap-2">
            <Button asChild>
              <Link href="/audit/">Open the audit log</Link>
            </Button>
            <Button asChild variant="outline">
              <Link href="/rules/">Manage rules</Link>
            </Button>
            <Button asChild variant="outline">
              <Link href="/payments/">All payments</Link>
            </Button>
          </div>
          <Field
            label="Payer user id"
            htmlFor="payer-id"
            hint="Sandbox helper: the demo parent id is filled in for you."
          >
            <Input
              id="payer-id"
              value={payerId}
              className="font-mono"
              onChange={(e) => setPayerId(e.target.value.trim())}
            />
          </Field>
        </CardContent>
      </Card>
      <KycCard payerId={payerId || undefined} />
    </>
  );
}

export function DashboardScreen() {
  const { user } = useAuth();
  const corridors = useApi<CorridorList>("/corridors");
  const [currency, setCurrency] = useState("GBP");
  if (!user) return null;

  const items = corridors.data?.items ?? [];
  const isAdmin = user.role === "admin";
  const canCompare = user.permissions.includes("quotes:create");
  const canPlan = user.permissions.includes("planner:read");

  return (
    <div className="space-y-6">
      <PageHead
        title={`Hello, ${user.display_name}`}
        actions={
          canCompare ? (
            <Button asChild size="lg" className="h-10 gap-2 px-5">
              <Link href="/compare/">
                Compare providers
                <ArrowRight aria-hidden="true" />
              </Link>
            </Button>
          ) : null
        }
      >
        Pay tuition and living costs abroad from Bangladesh with clear costs, a safe checklist and a
        human in control.
      </PageHead>
      {user.payer && user.role === "student" ? (
        <Notice tone="info" title={`Household of ${user.payer.display_name}`}>
          As the student you can look and prepare, but only the paying parent can approve.
        </Notice>
      ) : null}
      <ErrorNotice error={corridors.error} onRetry={corridors.reload} />
      <div className="grid grid-cols-[minmax(0,1fr)] gap-6 lg:grid-cols-2">
        <div className="flex min-w-0 flex-col gap-6">
          {isAdmin ? <ReviewerPanel /> : <KycCard />}
          {!isAdmin ? <RecentPaymentsCard canCompare={canCompare} /> : null}
        </div>
        {canPlan && items.length > 0 ? <PlannerCard corridors={items} /> : null}
        {canPlan && items.length === 0 && !corridors.error ? (
          <CardSkeleton lines={8} label="Loading corridors" />
        ) : null}
      </div>
      {canPlan && items.length > 0 ? (
        <div className="grid grid-cols-[minmax(0,1fr)] items-start gap-6 lg:grid-cols-[1.3fr_1fr]">
          <RateCard
            currency={currency}
            selector={
              <div className="flex items-center gap-2">
                <label htmlFor="rate-currency" className="text-muted-foreground text-xs">
                  Rate card currency
                </label>
                <CurrencySelect
                  id="rate-currency"
                  corridors={items}
                  value={currency}
                  onValueChange={setCurrency}
                  className="w-24"
                />
              </div>
            }
          />
          <div className="space-y-6">
            <RunwayCard corridors={items} />
            {user.permissions.includes("data:reset") ? <YourDataCard /> : null}
          </div>
        </div>
      ) : null}
      {canPlan && items.length > 0 ? <SendPlanCard corridors={items} /> : null}
    </div>
  );
}
