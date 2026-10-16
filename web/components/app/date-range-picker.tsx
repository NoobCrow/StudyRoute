"use client";

import { format, parseISO } from "date-fns";
import { CalendarIcon } from "lucide-react";
import { useState } from "react";
import type { DateRange } from "react-day-picker";

import { Button } from "@/components/ui/button";
import { Calendar } from "@/components/ui/calendar";
import { Popover, PopoverContent, PopoverTrigger } from "@/components/ui/popover";
import { parseRange, rangeValue } from "@/lib/schemas/payments-params";

const PRESETS = [
  { value: "7d", label: "Last 7 days" },
  { value: "30d", label: "Last 30 days" },
  { value: "year", label: "This year" },
  { value: "all", label: "All time" },
] as const;

function labelFor(value: string, today: string): string {
  const preset = PRESETS.find((p) => p.value === value);
  if (preset) return preset.label;
  const range = parseRange(value, today);
  if (!range) return "Choose dates";
  const day = (iso: string) => format(parseISO(iso), "d MMM yyyy");
  return `${day(range.from)} - ${day(range.to)}`;
}

/**
 * A date range for a list: presets, or two days picked in a calendar. The value is a preset name or
 * "FROM..TO" (days on the Dhaka calendar), the same text the address carries.
 */
export function DateRangePicker({
  value,
  onChange,
  today,
}: {
  value: string;
  onChange: (value: string) => void;
  /** Today on the Dhaka calendar (ISO). */
  today: string;
}) {
  const [open, setOpen] = useState(false);
  const range = parseRange(value, today);
  const selected: DateRange | undefined = range
    ? { from: parseISO(range.from), to: parseISO(range.to) }
    : undefined;

  function pick(next: DateRange | undefined) {
    if (!next?.from || !next.to) return;
    onChange(
      rangeValue({ from: format(next.from, "yyyy-MM-dd"), to: format(next.to, "yyyy-MM-dd") }),
    );
    setOpen(false);
  }

  return (
    <Popover open={open} onOpenChange={setOpen}>
      <PopoverTrigger asChild>
        <Button type="button" variant="outline" className="bg-card gap-2 font-normal">
          <CalendarIcon aria-hidden="true" className="text-muted-foreground" />
          <span className="sr-only">Date range: </span>
          {labelFor(value, today)}
        </Button>
      </PopoverTrigger>
      <PopoverContent className="w-auto p-0" align="start" aria-label="Choose dates">
        <div className="flex flex-col sm:flex-row">
          <ul className="flex gap-1 border-b p-2 sm:w-36 sm:flex-col sm:border-r sm:border-b-0">
            {PRESETS.map((preset) => (
              <li key={preset.value}>
                <Button
                  type="button"
                  variant={value === preset.value ? "secondary" : "ghost"}
                  size="sm"
                  className="w-full justify-start"
                  onClick={() => {
                    onChange(preset.value);
                    setOpen(false);
                  }}
                >
                  {preset.label}
                </Button>
              </li>
            ))}
          </ul>
          <Calendar
            mode="range"
            selected={selected}
            defaultMonth={selected?.to ?? parseISO(today)}
            onSelect={pick}
            disabled={{ after: parseISO(today) }}
            autoFocus
          />
        </div>
      </PopoverContent>
    </Popover>
  );
}
