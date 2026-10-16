import type { Metadata } from "next";

import { PaymentsScreen } from "@/components/payment/payments-screen";

export const metadata: Metadata = { title: "Payments" };

export default function PaymentsPage() {
  return <PaymentsScreen />;
}
