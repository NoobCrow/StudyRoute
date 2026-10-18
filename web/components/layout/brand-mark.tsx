/** The StudyRoute mark: a green tile with a route line and a dot (the same shapes as the favicon). */
export function BrandMark({ className }: { className?: string }) {
  return (
    <svg className={className} viewBox="0 0 32 32" aria-hidden="true" focusable="false">
      <rect width="32" height="32" rx="9" className="fill-primary" />
      <path
        d="M8 21l5-8 4 5 3-4 4 7"
        pathLength="1"
        fill="none"
        strokeWidth="2.4"
        strokeLinecap="round"
        strokeLinejoin="round"
        className="animate-draw stroke-primary-foreground [stroke-dasharray:1]"
      />
      <circle
        cx="25"
        cy="8"
        r="2.6"
        className="animate-pop fill-primary-foreground [transform-origin:center] [animation-delay:0.9s] [transform-box:fill-box]"
      />
    </svg>
  );
}
