import { ChevronLeft, ChevronRight, MoreHorizontal } from "lucide-react";
import * as React from "react";

import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";

function Pagination({ className, ...props }: React.ComponentProps<"nav">) {
  return (
    <nav
      role="navigation"
      aria-label="pagination"
      data-slot="pagination"
      className={cn("mx-auto flex w-full justify-center", className)}
      {...props}
    />
  );
}

function PaginationContent({ className, ...props }: React.ComponentProps<"ul">) {
  return (
    <ul
      data-slot="pagination-content"
      className={cn("flex flex-row items-center gap-1", className)}
      {...props}
    />
  );
}

function PaginationItem(props: React.ComponentProps<"li">) {
  return <li data-slot="pagination-item" {...props} />;
}

/** A page button. The pager changes the view in place (and the address), so these are buttons, not links. */
function PaginationLink({
  isActive,
  size = "icon",
  className,
  ...props
}: { isActive?: boolean } & Omit<React.ComponentProps<typeof Button>, "variant">) {
  return (
    <Button
      type="button"
      data-slot="pagination-link"
      data-active={isActive}
      aria-current={isActive ? "page" : undefined}
      variant={isActive ? "outline" : "ghost"}
      size={size}
      className={cn(isActive && "bg-card", className)}
      {...props}
    />
  );
}

function PaginationPrevious({ className, ...props }: React.ComponentProps<typeof PaginationLink>) {
  return (
    <PaginationLink
      aria-label="Go to the previous page"
      size="sm"
      className={cn("gap-1 px-2.5", className)}
      {...props}
    >
      <ChevronLeft aria-hidden="true" />
      <span>Previous</span>
    </PaginationLink>
  );
}

function PaginationNext({ className, ...props }: React.ComponentProps<typeof PaginationLink>) {
  return (
    <PaginationLink
      aria-label="Go to the next page"
      size="sm"
      className={cn("gap-1 px-2.5", className)}
      {...props}
    >
      <span>Next</span>
      <ChevronRight aria-hidden="true" />
    </PaginationLink>
  );
}

function PaginationEllipsis({ className, ...props }: React.ComponentProps<"span">) {
  return (
    <span
      aria-hidden="true"
      data-slot="pagination-ellipsis"
      className={cn("flex size-9 items-center justify-center", className)}
      {...props}
    >
      <MoreHorizontal className="size-4" />
      <span className="sr-only">More pages</span>
    </span>
  );
}

export {
  Pagination,
  PaginationContent,
  PaginationEllipsis,
  PaginationItem,
  PaginationLink,
  PaginationNext,
  PaginationPrevious,
};
