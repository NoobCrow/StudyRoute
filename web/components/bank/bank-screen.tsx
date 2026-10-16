"use client";

import { useState } from "react";

import { Landmark } from "lucide-react";

import { EmptyState } from "@/components/app/empty-state";
import { ErrorNotice, Notice } from "@/components/app/notice";
import { PageHead } from "@/components/app/page-head";
import { CardSkeleton } from "@/components/app/skeletons";
import {
  BankStatusBadge,
  NetworkCard,
  TransferDetail,
  isOpen,
} from "@/components/bank/bank-panels";
import { PlanForm } from "@/components/bank/plan-form";
import { KycCard } from "@/components/dashboard/kyc-card";
import { useAuth } from "@/components/providers/auth-provider";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import {
  Table,
  TableBody,
  TableCaption,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { get } from "@/lib/api/client";
import { loadHealth } from "@/lib/api/health";
import type {
  BankAccountView,
  BankNetwork,
  BankTotals,
  BankTransfer,
  Beneficiary,
} from "@/lib/api/types";
import { useApi, useLoader } from "@/lib/api/use-api";
import { usePolling } from "@/hooks/use-polling";
import { cn } from "@/lib/utils";

function Totals({ totals }: { totals: BankTotals }) {
  return (
    <Card aria-labelledby="totals-title">
      <CardHeader>
        <CardTitle id="totals-title" className="text-base">
          Your money in every currency
        </CardTitle>
      </CardHeader>
      <CardContent className="space-y-3">
        <div
          className="overflow-x-auto rounded-md border"
          tabIndex={0}
          role="region"
          aria-label="Money by currency table"
        >
          <Table>
            <TableCaption className="sr-only">
              Household balances by currency with an indicative BDT value
            </TableCaption>
            <TableHeader>
              <TableRow>
                <TableHead>Currency</TableHead>
                <TableHead className="text-right">Balance</TableHead>
                <TableHead className="text-right">About, in BDT</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {totals.by_currency.map((line) => (
                <TableRow key={line.currency}>
                  <TableCell>
                    <strong className="font-medium">{line.currency}</strong>
                    <div className="text-muted-foreground text-xs">
                      {line.accounts} account{line.accounts === 1 ? "" : "s"}
                    </div>
                  </TableCell>
                  <TableCell className="text-right font-mono tabular-nums">
                    {line.balance.formatted}
                  </TableCell>
                  <TableCell className="text-right font-mono tabular-nums">
                    {line.bdt_equivalent.formatted}
                  </TableCell>
                </TableRow>
              ))}
              <TableRow className="bg-success-soft/60 hover:bg-success-soft/60">
                <TableCell colSpan={2}>
                  <strong className="font-medium">Total, about</strong>
                </TableCell>
                <TableCell className="text-right font-mono font-semibold tabular-nums">
                  {totals.bdt_total.formatted}
                </TableCell>
              </TableRow>
            </TableBody>
          </Table>
        </div>
        <p className="text-muted-foreground text-xs">{totals.note}</p>
      </CardContent>
    </Card>
  );
}

function AccountsTable({ accounts }: { accounts: BankAccountView[] }) {
  return (
    <Card aria-labelledby="accounts-title">
      <CardHeader>
        <CardTitle id="accounts-title" className="text-base">
          Accounts
        </CardTitle>
      </CardHeader>
      <CardContent>
        <div
          className="overflow-x-auto rounded-md border"
          tabIndex={0}
          role="region"
          aria-label="Bank accounts table"
        >
          <Table>
            <TableCaption className="sr-only">Simulated bank accounts and balances</TableCaption>
            <TableHeader>
              <TableRow>
                <TableHead>Account</TableHead>
                <TableHead>Bank</TableHead>
                <TableHead className="hidden md:table-cell">Number</TableHead>
                <TableHead className="text-right">Balance</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {accounts.map((a) => (
                <TableRow key={a.id}>
                  <TableCell>
                    <strong className="font-medium">{a.label}</strong>
                    <div className="text-muted-foreground text-xs">{a.holder}</div>
                  </TableCell>
                  <TableCell>{a.bank_name}</TableCell>
                  <TableCell className="hidden font-mono text-xs md:table-cell">
                    {a.number}
                  </TableCell>
                  <TableCell className="text-right font-mono tabular-nums">
                    {a.balance.formatted}
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </div>
      </CardContent>
    </Card>
  );
}

export function BankScreen() {
  const { user } = useAuth();
  const canTransfer = user?.permissions.includes("bank:transfer") ?? false;
  const canControl = user?.permissions.includes("sandbox:control") ?? false;
  const network = useApi<BankNetwork>("/bank/network");
  const accounts = useApi<{ items: BankAccountView[]; totals: BankTotals | null }>(
    "/bank/accounts",
  );
  const people = useApi<{ items: Beneficiary[] }>("/bank/beneficiaries");
  const transfers = useApi<{ items: BankTransfer[] }>("/bank/transfers?limit=20");
  const health = useLoader(["health"], () => loadHealth());
  const [openId, setOpenId] = useState<string | null>(null);
  const [active, setActive] = useState<BankTransfer | null>(null);

  const list = transfers.data?.items ?? [];
  const live = list.some((t) => isOpen(t.status)) || (active !== null && isOpen(active.status));
  const { reload: reloadNetwork } = network;
  const { reload: reloadAccounts } = accounts;
  const { reload: reloadTransfers } = transfers;

  const refresh = () => {
    reloadNetwork();
    reloadAccounts();
    reloadTransfers();
    if (openId) {
      void get<BankTransfer>(`/bank/transfers/${openId}`)
        .then(setActive)
        .catch(() => undefined);
    }
  };

  // Open transfers move by themselves; look again every two seconds while one is in flight.
  usePolling(refresh, 2000, live);

  function open(transfer: BankTransfer) {
    setOpenId(transfer.id);
    void get<BankTransfer>(`/bank/transfers/${transfer.id}`).then(setActive);
  }

  const ready = network.data?.ready ?? false;
  const mine = accounts.data?.items ?? [];

  return (
    <div className="space-y-6">
      <PageHead title="Bank network">
        Invented banks that pass simulated money to each other, inside Bangladesh and across
        borders. No real bank is contacted.
      </PageHead>
      <Notice tone="info" title="Everything here is simulated">
        The banks, accounts, fees and timings are made up for the sandbox. Try the names{" "}
        <code className="font-mono">FAIL_TEST</code>, <code className="font-mono">SLOW_TEST</code>{" "}
        and <code className="font-mono">SANCTION_TEST</code> as beneficiaries to see the edge cases.
        International transfers need KYC to be verified; the identity check is below.
      </Notice>
      <ErrorNotice error={network.error ?? accounts.error ?? transfers.error} onRetry={refresh} />
      {network.loading && !network.data ? (
        <CardSkeleton lines={4} label="Opening the bank network" />
      ) : null}
      {network.data && !ready ? <NetworkCard network={network.data} /> : null}
      {ready ? (
        <>
          {user?.role === "parent" && user.kyc_status !== "VERIFIED" ? <KycCard /> : null}
          {accounts.data?.totals ? <Totals totals={accounts.data.totals} /> : null}
          <AccountsTable accounts={mine} />
          {canTransfer && network.data && people.data && accounts.data ? (
            <PlanForm
              accounts={mine}
              beneficiaries={people.data.items}
              network={network.data}
              onPlanned={(transfer) => {
                setOpenId(transfer.id);
                setActive(transfer);
                transfers.reload();
              }}
            />
          ) : null}
          {active ? (
            <TransferDetail
              transfer={active}
              canTransfer={canTransfer}
              canControl={canControl}
              sandboxCode={health.data?.demo?.mfa_code}
              onChanged={refresh}
            />
          ) : null}
          <Card aria-labelledby="transfers-title">
            <CardHeader>
              <CardTitle id="transfers-title" className="text-base">
                Transfers
              </CardTitle>
              <CardDescription className="sr-only">
                Simulated transfers, newest first
              </CardDescription>
            </CardHeader>
            <CardContent>
              {list.length === 0 ? (
                <EmptyState
                  icon={Landmark}
                  title="No transfers yet."
                  description="Plan one above to see the hops and the ledger."
                />
              ) : (
                <div
                  className="overflow-x-auto rounded-md border"
                  tabIndex={0}
                  role="region"
                  aria-label="Transfers table"
                >
                  <Table>
                    <TableCaption className="sr-only">
                      Simulated transfers, newest first
                    </TableCaption>
                    <TableHeader>
                      <TableRow>
                        <TableHead>To</TableHead>
                        <TableHead className="hidden md:table-cell">Kind</TableHead>
                        <TableHead className="text-right">You paid</TableHead>
                        <TableHead>Status</TableHead>
                        <TableHead>
                          <span className="sr-only">Open</span>
                        </TableHead>
                      </TableRow>
                    </TableHeader>
                    <TableBody>
                      {list.map((t) => (
                        <TableRow
                          key={t.id}
                          className={cn(
                            t.id === openId && "bg-success-soft/60 hover:bg-success-soft/60",
                          )}
                        >
                          <TableCell>
                            {t.destination.holder}
                            <div className="text-muted-foreground text-xs">
                              {t.destination.bank_name}
                            </div>
                          </TableCell>
                          <TableCell className="hidden md:table-cell">
                            {t.kind === "INTERNATIONAL" ? "International" : `National (${t.rail})`}
                          </TableCell>
                          <TableCell className="text-right font-mono tabular-nums">
                            {t.debit.formatted}
                          </TableCell>
                          <TableCell>
                            <BankStatusBadge status={t.status} />
                          </TableCell>
                          <TableCell>
                            <Button
                              type="button"
                              variant="outline"
                              size="sm"
                              onClick={() => open(t)}
                              aria-label={`Open transfer to ${t.destination.holder}`}
                            >
                              Open
                            </Button>
                          </TableCell>
                        </TableRow>
                      ))}
                    </TableBody>
                  </Table>
                </div>
              )}
            </CardContent>
          </Card>
          {network.data ? <NetworkCard network={network.data} /> : null}
        </>
      ) : null}
    </div>
  );
}
