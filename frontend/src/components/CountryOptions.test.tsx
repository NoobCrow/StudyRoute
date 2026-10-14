import { render, screen, within } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { corridor } from "../test/fixtures";
import { CountryOptions, CurrencyOptions } from "./CountryOptions";

const UK = corridor();
const JAPAN = corridor({ country: "JP", name: "Japan", currency: "JPY", exponent: 0, featured: false });
const NORTH_KOREA = corridor({ country: "KP", name: "North Korea", currency: "KPW", exponent: 0, featured: false, restricted: true });
const ITEMS = [UK, JAPAN, NORTH_KOREA];

function texts(group: HTMLElement): (string | null)[] {
  return within(group).getAllByRole("option").map((option) => option.textContent);
}

describe("destination options", () => {
  it("groups the main destinations first and then every country", () => {
    render(<select aria-label="Destination"><CountryOptions corridors={ITEMS} withCurrency /></select>);
    expect(texts(screen.getByRole("group", { name: "Popular study destinations" }))).toEqual(["United Kingdom (GBP)"]);
    expect(texts(screen.getByRole("group", { name: "All countries" }))).toEqual(["Japan (JPY)", "North Korea (KPW) - not available"]);
  });

  it("lists a restricted country but does not let anyone pick it", () => {
    render(<select aria-label="Destination"><CountryOptions corridors={ITEMS} /></select>);
    expect(screen.getByRole("option", { name: /North Korea/ })).toBeDisabled();
    expect(screen.getByRole("option", { name: "Japan" })).toBeEnabled();
  });

  it("shows a plain list when only the main destinations exist", () => {
    render(<select aria-label="Destination"><CountryOptions corridors={[UK]} /></select>);
    expect(screen.queryByRole("group")).toBeNull();
    expect(screen.getByRole("option", { name: "United Kingdom" })).toBeInTheDocument();
  });

  it("groups currencies too", () => {
    render(<select aria-label="Currency"><CurrencyOptions corridors={ITEMS} /></select>);
    expect(texts(screen.getByRole("group", { name: "Popular study destinations" }))).toEqual(["GBP"]);
    expect(texts(screen.getByRole("group", { name: "All currencies" }))).toEqual(["JPY", "KPW"]);
  });
});
