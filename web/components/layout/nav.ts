import {
  ArrowLeftRight,
  CreditCard,
  FileText,
  FlaskConical,
  GraduationCap,
  Landmark,
  LayoutDashboard,
  ListChecks,
  ShieldCheck,
  SlidersHorizontal,
  Users,
  type LucideIcon,
} from "lucide-react";

export interface NavItem {
  href: string;
  label: string;
  icon: LucideIcon;
  roles: readonly string[];
}

/** The same screens and the same roles as before; only the look changed. */
export const NAV: readonly NavItem[] = [
  { href: "/", label: "Dashboard", icon: LayoutDashboard, roles: ["parent", "student", "admin"] },
  { href: "/compare/", label: "Compare", icon: ArrowLeftRight, roles: ["parent", "student"] },
  {
    href: "/payments/",
    label: "Payments",
    icon: CreditCard,
    roles: ["parent", "student", "admin"],
  },
  { href: "/recipients/", label: "Recipients", icon: Users, roles: ["parent", "student"] },
  { href: "/documents/", label: "Documents", icon: FileText, roles: ["parent", "student"] },
  { href: "/guide/", label: "Student guide", icon: GraduationCap, roles: ["parent", "student"] },
  { href: "/audit/", label: "Audit log", icon: ListChecks, roles: ["parent", "admin"] },
  {
    href: "/rules/",
    label: "Rules",
    icon: SlidersHorizontal,
    roles: ["parent", "student", "admin"],
  },
  { href: "/bank/", label: "Bank network", icon: Landmark, roles: ["parent", "student", "admin"] },
  {
    href: "/escrow/",
    label: "Smart escrow",
    icon: ShieldCheck,
    roles: ["parent", "student", "admin"],
  },
  {
    href: "/sandbox/",
    label: "Sandbox",
    icon: FlaskConical,
    roles: ["parent", "student", "admin"],
  },
];

function bare(path: string): string {
  return path.replace(/\/+$/, "") || "/";
}

export function isActive(pathname: string, href: string): boolean {
  const here = bare(pathname);
  const target = bare(href);
  return target === "/" ? here === "/" : here === target || here.startsWith(`${target}/`);
}

/** The breadcrumb trail for a path, e.g. ["Payments", "Payment"]. */
export function trailFor(pathname: string): string[] {
  const here = bare(pathname);
  if (here === "/") return ["Dashboard"];
  const item = NAV.find((entry) => entry.href !== "/" && isActive(here, entry.href));
  const trail = [item?.label ?? "StudyRoute"];
  if (here.startsWith("/payments/")) {
    trail.push(here.endsWith("/report") ? "Compliance report" : "Payment");
  }
  return trail;
}
