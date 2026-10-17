import { get } from "@/lib/api/client";
import type { Page, PaymentBrief } from "@/lib/api/types";

const PAGE_SIZE = 100;
const MAX_PAGES = 20;

/**
 * Every payment of the signed-in family, read page by page. A family has a handful, so the list is held
 * whole and filtered, counted and sorted in the browser; the cap only stops a runaway loop.
 */
export async function loadAllPayments(): Promise<PaymentBrief[]> {
  const all: PaymentBrief[] = [];
  let cursor: string | number | null = null;
  for (let page = 0; page < MAX_PAGES; page += 1) {
    const suffix: string = cursor === null ? "" : `&cursor=${encodeURIComponent(String(cursor))}`;
    const result: Page<PaymentBrief> = await get<Page<PaymentBrief>>(
      `/payments?limit=${PAGE_SIZE}${suffix}`,
    );
    all.push(...result.items);
    cursor = result.next_cursor;
    if (cursor === null) break;
  }
  return all;
}
