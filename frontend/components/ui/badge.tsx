import { cn } from "@/lib/utils";

const tones: Record<string, string> = {
  success: "bg-emerald-950 text-emerald-300 border-emerald-800",
  warning: "bg-amber-950 text-amber-300 border-amber-800",
  error: "bg-red-950 text-red-300 border-red-800",
  info: "bg-slate-800 text-slate-200 border-slate-700",
  running: "bg-blue-950 text-blue-300 border-blue-800",
};

export function Badge({
  children,
  tone = "info",
  className,
}: {
  children: React.ReactNode;
  tone?: keyof typeof tones | string;
  className?: string;
}) {
  return (
    <span
      className={cn(
        "inline-flex items-center rounded border px-1.5 py-0.5 text-[11px] font-medium uppercase tracking-wide",
        tones[tone] || tones.info,
        tone === "running" && "animate-pulse",
        className,
      )}
    >
      {children}
    </span>
  );
}

export function statusTone(status: string): string {
  const value = status.toLowerCase();
  if (["completed", "computed", "valid", "ready", "published"].includes(value)) return "success";
  if (["running", "queued", "pending"].includes(value)) return "running";
  if (["failed", "invalid", "error"].includes(value)) return "error";
  if (["warning", "open"].includes(value)) return "warning";
  return "info";
}
