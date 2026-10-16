"use client";

import { ShieldCheck } from "lucide-react";
import Link from "next/link";

import { EmptyState } from "@/components/app/empty-state";
import { ErrorNotice, Notice } from "@/components/app/notice";
import { PageHead } from "@/components/app/page-head";
import { CardSkeleton } from "@/components/app/skeletons";
import { KycCard } from "@/components/dashboard/kyc-card";
import { EscrowPlanForm } from "@/components/escrow/escrow-plan-form";
import { AnchorCard, ChainCard, EscrowCard, TimeControl } from "@/components/escrow/escrow-panels";
import { useAuth } from "@/components/providers/auth-provider";
import { usePolling } from "@/hooks/use-polling";
import type {
  ChainAnchor,
  ChainStatus,
  CorridorList,
  EscrowView,
  Recipient,
} from "@/lib/api/types";
import { loadHealth } from "@/lib/api/health";
import { useApi, useLoader } from "@/lib/api/use-api";

export function EscrowScreen() {
  const { user } = useAuth();
  const can = (permission: string) => user?.permissions.includes(permission) ?? false;
  const canWrite = can("escrow:write");
  const escrows = useApi<{ items: EscrowView[] }>("/escrows");
  const chain = useApi<ChainStatus>("/chain/status");
  const anchors = useApi<{ items: ChainAnchor[] }>("/chain/anchors");
  const recipients = useApi<{ items: Recipient[] }>(canWrite ? "/recipients" : null);
  const corridors = useApi<CorridorList>("/corridors");
  const health = useLoader(["health"], () => loadHealth());

  const items = escrows.data?.items ?? [];
  // Keep refreshing while something can change by itself: a schedule paying out, or a plan waiting
  // for KYC to be verified.
  const live = items.some(
    (e) =>
      e.chain_status === "ACTIVE" ||
      e.chain_status === "FROZEN" ||
      (e.status === "PENDING_CONFIRMATION" && (e.blockers?.length ?? 0) > 0),
  );
  const { reload: reloadEscrows } = escrows;
  const { reload: reloadChain } = chain;
  const { reload: reloadAnchors } = anchors;
  const refresh = () => {
    reloadEscrows();
    reloadChain();
    reloadAnchors();
  };
  usePolling(refresh, 3000, live);

  const people = recipients.data?.items ?? [];

  return (
    <div className="space-y-6">
      <PageHead title="Smart escrow">
        Tuition and living costs locked in a smart contract that pays on the dates you choose, with
        a bank-style safety net.
      </PageHead>
      <Notice tone="info" title="A simulated chain">
        The contracts are real Solidity, run on an in-memory EVM inside the sandbox: no network, no
        real tokens, nothing is money. The parent decides (with MFA), the contract enforces, the
        bank&apos;s reviewer can freeze but never move funds, and the AI has no access at all. Only
        amounts, dates and hashes go on the chain.
      </Notice>
      <ErrorNotice error={escrows.error ?? chain.error ?? anchors.error} onRetry={refresh} />
      {user?.role === "parent" && user.kyc_status !== "VERIFIED" ? <KycCard /> : null}
      {canWrite && recipients.data && corridors.data ? (
        people.length > 0 ? (
          <EscrowPlanForm recipients={people} corridors={corridors.data} onPlanned={refresh} />
        ) : (
          <Notice tone="warn" title="Add a recipient first">
            An escrow pays someone.{" "}
            <Link href="/recipients/" className="font-medium underline">
              Add the university or the student
            </Link>
            , then plan an escrow.
          </Notice>
        )
      ) : null}
      <section className="space-y-4" aria-labelledby="escrows-title">
        <h2 id="escrows-title" className="text-lg font-semibold tracking-tight">
          Escrows
        </h2>
        {escrows.loading && !escrows.data ? (
          <CardSkeleton lines={4} label="Loading escrows" />
        ) : null}
        {escrows.data && items.length === 0 ? (
          <EmptyState
            icon={ShieldCheck}
            title="No escrows yet."
            description="Plan one above to see the schedule and its proof on the chain."
          />
        ) : null}
        {items.map((escrow) => (
          <EscrowCard
            key={escrow.escrow_id}
            escrow={escrow}
            canWrite={canWrite}
            canFreeze={can("escrow:freeze")}
            canControl={can("sandbox:control")}
            sandboxCode={health.data?.demo?.mfa_code}
            onChanged={refresh}
          />
        ))}
      </section>
      <AnchorCard
        anchors={anchors.data?.items ?? []}
        canAnchor={can("chain:anchor")}
        canVerify={can("audit:verify")}
        onChanged={refresh}
      />
      {can("sandbox:control") ? <TimeControl onChanged={refresh} /> : null}
      {chain.data ? <ChainCard status={chain.data} /> : null}
    </div>
  );
}
