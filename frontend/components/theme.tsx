"use client";

import { createContext, useCallback, useContext, useEffect, useState } from "react";
import { Monitor, Moon, Sun } from "lucide-react";
import { cn } from "@/lib/utils";

/**
 * Theme control.
 *
 * Dark mode is a selected theme, not an inversion: `globals.css` redefines the
 * tokens, including chart slots re-stepped for the dark surface. Three modes,
 * because "follow the system" is the right default and a hard override is the
 * right escape hatch.
 */

export type ThemeMode = "light" | "dark" | "system";
const STORAGE_KEY = "biflow-theme";

/**
 * Runs before first paint to stamp the class on <html>, so the page never
 * renders light and then flips. Inlined in the document head.
 */
export const THEME_SCRIPT = `(function(){try{var m=localStorage.getItem('${STORAGE_KEY}')||'system';var d=m==='dark'||(m==='system'&&window.matchMedia('(prefers-color-scheme: dark)').matches);document.documentElement.classList.toggle('dark',d);document.documentElement.style.colorScheme=d?'dark':'light';}catch(e){}})();`;

const ThemeContext = createContext<{ mode: ThemeMode; setMode: (mode: ThemeMode) => void }>({
  mode: "system",
  setMode: () => {},
});

export function ThemeProvider({ children }: { children: React.ReactNode }) {
  const [mode, setModeState] = useState<ThemeMode>("system");

  useEffect(() => {
    const stored = (localStorage.getItem(STORAGE_KEY) as ThemeMode | null) ?? "system";
    setModeState(stored);
  }, []);

  const apply = useCallback((next: ThemeMode) => {
    const dark =
      next === "dark" ||
      (next === "system" && window.matchMedia("(prefers-color-scheme: dark)").matches);
    document.documentElement.classList.toggle("dark", dark);
    document.documentElement.style.colorScheme = dark ? "dark" : "light";
  }, []);

  const setMode = useCallback(
    (next: ThemeMode) => {
      setModeState(next);
      try {
        localStorage.setItem(STORAGE_KEY, next);
      } catch {
        // Private browsing: the choice just does not persist.
      }
      apply(next);
    },
    [apply],
  );

  // Track the OS setting while following it.
  useEffect(() => {
    if (mode !== "system") return;
    const query = window.matchMedia("(prefers-color-scheme: dark)");
    const onChange = () => apply("system");
    query.addEventListener("change", onChange);
    return () => query.removeEventListener("change", onChange);
  }, [mode, apply]);

  return <ThemeContext.Provider value={{ mode, setMode }}>{children}</ThemeContext.Provider>;
}

export function useTheme() {
  return useContext(ThemeContext);
}

const OPTIONS: { mode: ThemeMode; icon: typeof Sun; label: string }[] = [
  { mode: "light", icon: Sun, label: "Light" },
  { mode: "dark", icon: Moon, label: "Dark" },
  { mode: "system", icon: Monitor, label: "System" },
];

export function ThemeToggle({ className }: { className?: string }) {
  const { mode, setMode } = useTheme();
  return (
    <div
      className={cn("inline-flex rounded-lg bg-inset p-0.5", className)}
      role="group"
      aria-label="Colour theme"
    >
      {OPTIONS.map((option) => {
        const Icon = option.icon;
        const active = mode === option.mode;
        return (
          <button
            key={option.mode}
            type="button"
            onClick={() => setMode(option.mode)}
            aria-pressed={active}
            title={option.label}
            className={cn(
              "grid size-7 place-items-center rounded-md transition-[background-color,color,box-shadow] duration-[--duration-fast]",
              active
                ? "bg-surface text-ink shadow-sm ring-1 ring-line"
                : "text-ink-faint hover:text-ink-soft",
            )}
          >
            <Icon className="size-3.5" aria-hidden />
            <span className="sr-only">{option.label}</span>
          </button>
        );
      })}
    </div>
  );
}
