import type { Metadata } from "next";

import { RulesScreen } from "@/components/rules/rules-screen";

export const metadata: Metadata = { title: "Rules" };

export default function RulesPage() {
  return <RulesScreen />;
}
