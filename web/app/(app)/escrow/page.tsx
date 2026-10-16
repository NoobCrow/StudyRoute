import type { Metadata } from "next";

import { EscrowScreen } from "@/components/escrow/escrow-screen";

export const metadata: Metadata = { title: "Smart escrow" };

export default function EscrowPage() {
  return <EscrowScreen />;
}
