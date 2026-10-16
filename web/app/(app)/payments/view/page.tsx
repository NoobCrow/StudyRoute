import type { Metadata } from "next";
import { Suspense } from "react";

import { PaymentScreen } from "@/components/payment/payment-screen";

export const metadata: Metadata = { title: "Payment" };

/** The payment id travels in the query string (?id=) so the static export needs no dynamic routes. */
export default function PaymentPage() {
  return (
    <Suspense>
      <PaymentScreen />
    </Suspense>
  );
}
