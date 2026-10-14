import type { Corridor } from "../api/types";
import { ALL_LABEL, POPULAR_LABEL, currencyGroups, splitCorridors } from "../lib/corridors";

function optionLabel(c: Corridor, withCurrency: boolean): string {
  const currency = withCurrency ? ` (${c.currency})` : "";
  return `${c.name}${currency}${c.restricted ? " - not available" : ""}`;
}

/** The <option>s for a destination select: the main six first, then every country by name. */
export function CountryOptions({ corridors, withCurrency = false }: { corridors: Corridor[]; withCurrency?: boolean }) {
  const { featured, others } = splitCorridors(corridors);
  const option = (c: Corridor) => (
    <option key={c.country} value={c.country} disabled={c.restricted}>{optionLabel(c, withCurrency)}</option>
  );
  if (others.length === 0) return <>{featured.map(option)}</>;
  return (
    <>
      <optgroup label={POPULAR_LABEL}>{featured.map(option)}</optgroup>
      <optgroup label={ALL_LABEL}>{others.map(option)}</optgroup>
    </>
  );
}

/** The <option>s for a currency select, grouped the same way. */
export function CurrencyOptions({ corridors }: { corridors: Corridor[] }) {
  const { featured, others } = currencyGroups(corridors);
  const option = (code: string) => <option key={code} value={code}>{code}</option>;
  if (others.length === 0) return <>{featured.map(option)}</>;
  return (
    <>
      <optgroup label={POPULAR_LABEL}>{featured.map(option)}</optgroup>
      <optgroup label="All currencies">{others.map(option)}</optgroup>
    </>
  );
}
