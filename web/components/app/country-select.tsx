"use client";

import {
  Select,
  SelectContent,
  SelectGroup,
  SelectItem,
  SelectLabel,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import type { Corridor } from "@/lib/api/types";
import { ALL_LABEL, POPULAR_LABEL, currencyGroups, splitCorridors } from "@/lib/corridors";

function optionLabel(corridor: Corridor, withCurrency: boolean): string {
  const currency = withCurrency ? ` (${corridor.currency})` : "";
  return `${corridor.name}${currency}${corridor.restricted ? " - not available" : ""}`;
}

interface CommonProps {
  id?: string;
  value: string;
  onValueChange: (value: string) => void;
  "aria-label"?: string;
  className?: string;
}

/** A destination select: the six main countries first, then every country by name. */
export function CountrySelect({
  corridors,
  withCurrency = false,
  id,
  value,
  onValueChange,
  className,
  ...aria
}: CommonProps & { corridors: Corridor[]; withCurrency?: boolean }) {
  const { featured, others } = splitCorridors(corridors);
  const item = (c: Corridor) => (
    <SelectItem key={c.country} value={c.country} disabled={c.restricted}>
      {optionLabel(c, withCurrency)}
    </SelectItem>
  );
  return (
    <Select value={value} onValueChange={onValueChange}>
      <SelectTrigger id={id} className={className ?? "w-full"} {...aria}>
        <SelectValue placeholder="Choose a country" />
      </SelectTrigger>
      <SelectContent>
        <SelectGroup>
          <SelectLabel>{POPULAR_LABEL}</SelectLabel>
          {featured.map(item)}
        </SelectGroup>
        {others.length > 0 ? (
          <SelectGroup>
            <SelectLabel>{ALL_LABEL}</SelectLabel>
            {others.map(item)}
          </SelectGroup>
        ) : null}
      </SelectContent>
    </Select>
  );
}

/** A currency select, grouped the same way. */
export function CurrencySelect({
  corridors,
  id,
  value,
  onValueChange,
  className,
  ...aria
}: CommonProps & { corridors: Corridor[] }) {
  const { featured, others } = currencyGroups(corridors);
  return (
    <Select value={value} onValueChange={onValueChange}>
      <SelectTrigger id={id} className={className ?? "w-full"} {...aria}>
        <SelectValue placeholder="Currency" />
      </SelectTrigger>
      <SelectContent>
        <SelectGroup>
          <SelectLabel>{POPULAR_LABEL}</SelectLabel>
          {featured.map((code) => (
            <SelectItem key={code} value={code}>
              {code}
            </SelectItem>
          ))}
        </SelectGroup>
        {others.length > 0 ? (
          <SelectGroup>
            <SelectLabel>All currencies</SelectLabel>
            {others.map((code) => (
              <SelectItem key={code} value={code}>
                {code}
              </SelectItem>
            ))}
          </SelectGroup>
        ) : null}
      </SelectContent>
    </Select>
  );
}
