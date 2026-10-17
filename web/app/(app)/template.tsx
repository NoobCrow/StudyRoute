import type { ReactNode } from "react";

/** A template (unlike a layout) is made again on every navigation, so each screen eases in. */
export default function Template({ children }: { children: ReactNode }) {
  return <div className="animate-page">{children}</div>;
}
