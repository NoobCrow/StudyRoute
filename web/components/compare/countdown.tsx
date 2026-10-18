"use client";

import { Chip } from "@/components/app/status";
import { useNow } from "@/hooks/use-now";
import { clock, secondsUntil } from "@/lib/format";

/** Live validity of a quote. The server is still the judge: this only tells the user. */
export function Countdown({ expiresAt }: { expiresAt: string }) {
  const now = useNow(1000);
  const left = secondsUntil(expiresAt, now);
  if (left <= 0) return <Chip tone="danger">Quote expired</Chip>;
  return (
    <Chip tone={left <= 60 ? "warn" : "info"} title="Every sandbox quote has an expiry time.">
      Valid for {clock(left)}
    </Chip>
  );
}
