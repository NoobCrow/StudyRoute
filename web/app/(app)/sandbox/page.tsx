import type { Metadata } from "next";

import { SandboxScreen } from "@/components/sandbox/sandbox-screen";

export const metadata: Metadata = { title: "Sandbox" };

export default function SandboxPage() {
  return <SandboxScreen />;
}
