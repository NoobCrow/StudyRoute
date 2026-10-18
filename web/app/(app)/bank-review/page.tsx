import type { Metadata } from "next";

import { ReviewDesk } from "@/components/review/review-desk";

export const metadata: Metadata = { title: "Bank review desk" };

export default function BankReviewPage() {
  return <ReviewDesk />;
}
