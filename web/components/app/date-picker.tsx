"use client";

import { format, parseISO } from "date-fns";
import { CalendarIcon } from "lucide-react";
import { useState } from "react";

import { Button } from "@/components/ui/button";
import { Calendar } from "@/components/ui/calendar";
import { Popover, PopoverContent, PopoverTrigger } from "@/components/ui/popover";
import { cn } from "@/lib/utils";

/** A date as an ISO string ("2026-10-30"), chosen in a calendar. Empty string means no date. */
export function DatePicker({
  id,
  value,
  onChange,
  minIso,
  className,
  "aria-describedby": describedBy,
}: {
  id?: string;
  value: string;
  onChange: (iso: string) => void;
  /** The earliest day that can be chosen (ISO). */
  minIso?: string;
  className?: string;
  "aria-describedby"?: string;
}) {
  const [open, setOpen] = useState(false);
  const selected = value ? parseISO(value) : undefined;
  return (
    <Popover open={open} onOpenChange={setOpen}>
      <PopoverTrigger asChild>
        <Button
          id={id}
          type="button"
          variant="outline"
          aria-describedby={describedBy}
          className={cn(
            "bg-card w-full justify-between px-3 font-normal",
            !selected && "text-muted-foreground",
            className,
          )}
        >
          <span className="font-mono tabular-nums">
            {selected ? format(selected, "MM/dd/yyyy") : "Pick a date"}
          </span>
          <CalendarIcon aria-hidden="true" className="text-muted-foreground" />
        </Button>
      </PopoverTrigger>
      <PopoverContent className="w-auto p-0" align="start">
        <Calendar
          mode="single"
          selected={selected}
          defaultMonth={selected}
          disabled={minIso ? { before: parseISO(minIso) } : undefined}
          onSelect={(date) => {
            if (!date) return;
            onChange(format(date, "yyyy-MM-dd"));
            setOpen(false);
          }}
          autoFocus
        />
      </PopoverContent>
    </Popover>
  );
}
