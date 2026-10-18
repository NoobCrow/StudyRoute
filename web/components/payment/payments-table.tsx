"use client";

import { formatDistanceToNowStrict } from "date-fns";
import { ArrowDown, ArrowUp, ChevronsUpDown, MoreHorizontal } from "lucide-react";
import Link from "next/link";
import type { KeyboardEvent } from "react";

import { Avatar, AvatarFallback } from "@/components/ui/avatar";
import { Button } from "@/components/ui/button";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { Skeleton } from "@/components/ui/skeleton";
import {
  Table,
  TableBody,
  TableCaption,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip";
import { PaymentStatusBadge } from "@/components/payment/payment-status";
import type { PaymentBrief } from "@/lib/api/types";
import { canCancel, type SortDir, type SortKey } from "@/lib/domain/payments";
import { formatDateTime } from "@/lib/format";

const HEAD = "text-muted-foreground text-[11px] font-medium tracking-wider uppercase";

function initials(label: string): string {
  return label
    .split(/\s+/)
    .filter((part) => /^[A-Za-z]/.test(part))
    .slice(0, 2)
    .map((part) => part[0]?.toUpperCase() ?? "")
    .join("");
}

function SortHead({
  label,
  column,
  sort,
  dir,
  onSort,
  align = "left",
}: {
  label: string;
  column: SortKey;
  sort: SortKey;
  dir: SortDir;
  onSort: (key: SortKey) => void;
  align?: "left" | "right";
}) {
  const active = sort === column;
  const Icon = !active ? ChevronsUpDown : dir === "asc" ? ArrowUp : ArrowDown;
  return (
    <TableHead
      aria-sort={active ? (dir === "asc" ? "ascending" : "descending") : "none"}
      className={align === "right" ? "text-right" : undefined}
    >
      <button
        type="button"
        onClick={() => onSort(column)}
        className={`${HEAD} hover:text-foreground focus-visible:ring-ring/50 inline-flex items-center gap-1 rounded-sm outline-none focus-visible:ring-[3px]`}
      >
        {label}
        <Icon className="size-3" aria-hidden="true" />
      </button>
    </TableHead>
  );
}

/** Three grey rows with the shape of the table, shown while the list loads. */
function LoadingRows() {
  return (
    <TableBody role="status" aria-label="Loading payments" aria-busy="true">
      {[0, 1, 2].map((row) => (
        <TableRow key={row} className="hover:bg-transparent">
          <TableCell>
            <Skeleton className="h-4 w-24" />
          </TableCell>
          <TableCell>
            <div className="flex items-center gap-3">
              <Skeleton className="size-8 rounded-md" />
              <Skeleton className="h-4 w-36" />
            </div>
          </TableCell>
          {[0, 1, 2, 3].map((cell) => (
            <TableCell key={cell}>
              <Skeleton className="h-4 w-20" />
            </TableCell>
          ))}
          <TableCell />
        </TableRow>
      ))}
    </TableBody>
  );
}

interface Props {
  rows: PaymentBrief[];
  loading: boolean;
  sort: SortKey;
  dir: SortDir;
  onSort: (key: SortKey) => void;
  onOpen: (payment: PaymentBrief) => void;
  mayCancel: boolean;
  onCancel: (payment: PaymentBrief) => void;
}

/** The payments of one page. A row opens the detail sheet by click, Enter or Space; its menu has the rest. */
export function PaymentsTable({
  rows,
  loading,
  sort,
  dir,
  onSort,
  onOpen,
  mayCancel,
  onCancel,
}: Props) {
  const head = { sort, dir, onSort };
  return (
    <div
      className="overflow-x-auto rounded-md border"
      tabIndex={0}
      role="region"
      aria-label="Payments table"
    >
      <Table>
        <TableCaption className="sr-only">
          Your simulated payments. Press Enter on a row to see its details.
        </TableCaption>
        <TableHeader>
          <TableRow>
            <SortHead label="Reference" column="reference" {...head} />
            <SortHead label="Recipient" column="recipient" {...head} />
            <SortHead label="Beneficiary receives" column="amount" align="right" {...head} />
            <SortHead label="Provider" column="provider" {...head} />
            <SortHead label="Status" column="status" {...head} />
            <SortHead label="Created" column="created" {...head} />
            <TableHead className="w-10">
              <span className="sr-only">Actions</span>
            </TableHead>
          </TableRow>
        </TableHeader>
        {loading ? (
          <LoadingRows />
        ) : (
          <TableBody>
            {rows.map((payment) => {
              const open = () => onOpen(payment);
              const onKey = (event: KeyboardEvent<HTMLTableRowElement>) => {
                if (event.target !== event.currentTarget) return;
                if (event.key === "Enter" || event.key === " ") {
                  event.preventDefault();
                  open();
                }
              };
              return (
                <TableRow
                  key={payment.payment_id}
                  tabIndex={0}
                  onClick={open}
                  onKeyDown={onKey}
                  aria-label={`${payment.reference}, ${payment.recipient_label}`}
                  className="focus-visible:ring-ring/50 cursor-pointer outline-none focus-visible:ring-[3px] focus-visible:ring-inset"
                >
                  <TableCell className="font-mono text-xs">{payment.reference}</TableCell>
                  <TableCell className="min-w-64 whitespace-normal">
                    <div className="flex items-center gap-3">
                      <Avatar className="size-8 rounded-md">
                        <AvatarFallback className="rounded-md text-xs font-medium">
                          {initials(payment.recipient_label)}
                        </AvatarFallback>
                      </Avatar>
                      {/* Plain text: the UI never injects a recipient name as HTML. */}
                      <span className="min-w-0 font-medium">{payment.recipient_label}</span>
                    </div>
                  </TableCell>
                  <TableCell className="text-right font-mono text-sm tabular-nums">
                    {payment.target.formatted}
                  </TableCell>
                  <TableCell>{payment.provider_name}</TableCell>
                  <TableCell>
                    <PaymentStatusBadge state={payment.state} />
                  </TableCell>
                  <TableCell className="text-muted-foreground text-xs whitespace-nowrap">
                    <Tooltip>
                      <TooltipTrigger asChild>
                        <time dateTime={payment.created_at}>
                          {formatDistanceToNowStrict(new Date(payment.created_at), {
                            addSuffix: true,
                          })}
                        </time>
                      </TooltipTrigger>
                      <TooltipContent>{formatDateTime(payment.created_at)}</TooltipContent>
                    </Tooltip>
                  </TableCell>
                  <TableCell onClick={(event) => event.stopPropagation()}>
                    <DropdownMenu>
                      <DropdownMenuTrigger asChild>
                        <Button
                          type="button"
                          variant="ghost"
                          size="icon"
                          aria-label={`Actions for ${payment.reference}`}
                        >
                          <MoreHorizontal aria-hidden="true" />
                        </Button>
                      </DropdownMenuTrigger>
                      <DropdownMenuContent align="end">
                        <DropdownMenuItem onSelect={open}>View details</DropdownMenuItem>
                        <DropdownMenuItem asChild>
                          <Link
                            href={`/payments/report/?id=${encodeURIComponent(payment.payment_id)}`}
                          >
                            Compliance report
                          </Link>
                        </DropdownMenuItem>
                        {mayCancel && canCancel(payment.state) ? (
                          <>
                            <DropdownMenuSeparator />
                            <DropdownMenuItem
                              variant="destructive"
                              onSelect={() => onCancel(payment)}
                            >
                              Cancel payment
                            </DropdownMenuItem>
                          </>
                        ) : null}
                      </DropdownMenuContent>
                    </DropdownMenu>
                  </TableCell>
                </TableRow>
              );
            })}
          </TableBody>
        )}
      </Table>
    </div>
  );
}
