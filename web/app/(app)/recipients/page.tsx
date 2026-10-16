import type { Metadata } from "next";

import { RecipientsScreen } from "@/components/recipients/recipients-screen";

export const metadata: Metadata = { title: "Recipients" };

export default function RecipientsPage() {
  return <RecipientsScreen />;
}
