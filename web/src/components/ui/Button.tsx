"use client";

import { forwardRef } from "react";

export type ButtonVariant = "primary" | "secondary" | "ghost" | "danger" | "warning";
export type ButtonSize = "sm" | "md" | "lg";

export type ButtonProps = React.ButtonHTMLAttributes<HTMLButtonElement> & {
  variant?: ButtonVariant;
  size?: ButtonSize;
};

const variantClass: Record<ButtonVariant, string> = {
  primary:
    "border border-emerald-700/30 bg-emerald-700 text-white shadow-md shadow-emerald-900/20 hover:border-emerald-600 hover:bg-emerald-600 disabled:border-emerald-200/60 disabled:bg-emerald-400/80 disabled:text-white/90 disabled:shadow-none",
  secondary:
    "border border-emerald-200/90 bg-emerald-50/80 text-emerald-950 shadow-sm hover:border-emerald-300 hover:bg-emerald-100/90 disabled:opacity-60",
  ghost:
    "border border-stone-200/90 bg-white text-stone-700 shadow-sm hover:border-stone-300 hover:bg-stone-50 disabled:opacity-60",
  danger:
    "border border-red-200/90 bg-white text-red-800 shadow-sm hover:bg-red-50 disabled:opacity-60",
  warning:
    "border border-amber-200/90 bg-white text-amber-900 shadow-sm hover:bg-amber-50 disabled:opacity-60",
};

const sizeClass: Record<ButtonSize, string> = {
  sm: "rounded-lg px-2.5 py-1.5 text-xs font-medium",
  md: "rounded-xl px-4 py-2 text-sm font-medium",
  lg: "rounded-2xl px-5 py-3 text-[15px] font-semibold",
};

const base =
  "inline-flex items-center justify-center gap-2 transition focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-emerald-400/70 focus-visible:ring-offset-2 focus-visible:ring-offset-[var(--ring-offset)] disabled:cursor-not-allowed";

/** Для `next/link`, стиль как у `Button` variant="secondary" */
export const linkAsButtonSecondaryClass =
  "inline-flex items-center justify-center rounded-xl border border-emerald-200/90 bg-emerald-50/80 px-3 py-2 text-sm font-medium text-emerald-900 shadow-sm transition hover:border-emerald-300 hover:bg-emerald-100/90";

export const Button = forwardRef<HTMLButtonElement, ButtonProps>(function Button(
  { className = "", variant = "primary", size = "md", type = "button", ...rest },
  ref,
) {
  return (
    <button
      ref={ref}
      type={type}
      className={`${base} ${variantClass[variant]} ${sizeClass[size]} ${className}`.trim()}
      {...rest}
    />
  );
});
