import type { Metadata } from "next";

import { BankScreen } from "@/components/bank/bank-screen";

export const metadata: Metadata = { title: "Bank network" };

export default function BankPage() {
  return <BankScreen />;
}
