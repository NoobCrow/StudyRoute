/**
 * The API names screens with plain paths ("/compare?quote=qte_1", "/payments/pay_9"). This maps them
 * to this app's routes: every path ends in a slash, and a payment id travels in the query string
 * (the static export has no dynamic routes).
 */
export function appHref(link: string): string {
  const [path = "/", query] = link.split("?");
  const parts = path.split("/").filter(Boolean);
  if (parts[0] === "payments" && parts.length >= 2) {
    const id = encodeURIComponent(parts[1] ?? "");
    return parts[2] === "report" ? `/payments/report/?id=${id}` : `/payments/view/?id=${id}`;
  }
  const base = parts.length === 0 ? "/" : `/${parts.join("/")}/`;
  return query ? `${base}?${query}` : base;
}
