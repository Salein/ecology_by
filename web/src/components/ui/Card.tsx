import type { HTMLAttributes } from "react";

export type CardProps = HTMLAttributes<HTMLDivElement> & {
  /** Внутренние отступы */
  padding?: "none" | "sm" | "md" | "lg";
};

const pad: Record<NonNullable<CardProps["padding"]>, string> = {
  none: "",
  sm: "p-3",
  md: "p-4 sm:p-5",
  lg: "p-6 sm:p-8",
};

const shell =
  "rounded-2xl border border-emerald-200/50 bg-white shadow-md shadow-emerald-950/[0.06]";

export function Card({ className = "", padding = "md", children, ...rest }: CardProps) {
  return (
    <div className={`${shell} ${pad[padding]} ${className}`.trim()} {...rest}>
      {children}
    </div>
  );
}
