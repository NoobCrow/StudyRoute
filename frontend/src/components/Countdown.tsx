import { useNow } from "../hooks";
import { clock, secondsUntil } from "../lib/format";
import { Badge } from "./Ui";

/** Live validity of a quote. The server is still the judge: this only tells the user. */
export function Countdown({ expiresAt }: { expiresAt: string }) {
  const now = useNow(1000);
  const left = secondsUntil(expiresAt, now);
  if (left <= 0) return <Badge tone="danger">Quote expired</Badge>;
  return (
    <Badge tone={left <= 60 ? "warn" : "info"} title="Every sandbox quote has an expiry time.">
      Valid for {clock(left)}
    </Badge>
  );
}
