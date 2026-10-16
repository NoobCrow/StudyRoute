import type { Metadata } from "next";
import { Suspense } from "react";

import { CompareScreen } from "@/components/compare/compare-screen";

export const metadata: Metadata = { title: "Compare providers" };

export default function ComparePage() {
  return (
    <Suspense>
      <CompareScreen />
    </Suspense>
  );
}
