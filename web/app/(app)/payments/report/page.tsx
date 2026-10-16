import type { Metadata } from "next";
import { Suspense } from "react";

import { ReportScreen } from "@/components/payment/report-screen";

export const metadata: Metadata = { title: "Compliance report" };

export default function ReportPage() {
  return (
    <Suspense>
      <ReportScreen />
    </Suspense>
  );
}
