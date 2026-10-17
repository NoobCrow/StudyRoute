import type { Metadata } from "next";

import { GuideScreen } from "@/components/guide/guide-screen";

export const metadata: Metadata = { title: "Student guide" };

export default function GuidePage() {
  return <GuideScreen />;
}
