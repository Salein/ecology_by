type WasteTypeFieldProps = {
  value: string;
};

export function WasteTypeField({ value }: WasteTypeFieldProps) {
  return (
    <div className="flex min-w-0 flex-1 flex-col gap-2">
      <span className="text-xs font-medium uppercase tracking-wide text-black">Вид отхода</span>
      <div
        className="flex min-w-0 flex-wrap items-stretch gap-2 rounded-2xl border border-emerald-100/80 bg-emerald-50/80 px-4 py-3 shadow-sm shadow-emerald-900/5"
        aria-live="polite"
      >
        <div
          className="flex min-w-[12rem] flex-1 items-center rounded-xl border border-emerald-100/90 bg-white/95 px-3 py-2.5 text-sm leading-snug text-stone-900"
          title="Полное наименование вида отходов"
        >
          {value}
        </div>
      </div>
    </div>
  );
}
