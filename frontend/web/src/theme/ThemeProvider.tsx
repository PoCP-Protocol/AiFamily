import { createContext, useCallback, useContext, useEffect, useMemo, useState } from "react";
import type { ReactNode } from "react";

import { type ColorScheme, paletteFor } from "./tokens";

const STORAGE_KEY = "aifamily-web-color-scheme";

type ThemeContextValue = {
  colorScheme: ColorScheme;
  setColorScheme: (scheme: ColorScheme) => void;
};

const ThemeContext = createContext<ThemeContextValue | null>(null);

function systemPreferredScheme(): ColorScheme {
  if (typeof window === "undefined" || !window.matchMedia) return "light";
  return window.matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light";
}

function storedScheme(): ColorScheme | null {
  if (typeof window === "undefined") return null;
  const stored = window.localStorage.getItem(STORAGE_KEY);
  return stored === "light" || stored === "dark" ? stored : null;
}

function applyScheme(scheme: ColorScheme): void {
  if (typeof document === "undefined") return;
  const root = document.documentElement;
  root.dataset.theme = scheme;
  root.classList.toggle("dark", scheme === "dark");
  const palette = paletteFor(scheme);
  Object.entries(palette).forEach(([token, value]) => {
    root.style.setProperty(`--color-${token}`, value);
  });
}

export function ThemeProvider({ children }: { children: ReactNode }) {
  const [colorScheme, setColorSchemeState] = useState<ColorScheme>(
    () => storedScheme() ?? systemPreferredScheme(),
  );

  const setColorScheme = useCallback((scheme: ColorScheme) => {
    setColorSchemeState(scheme);
    if (typeof window !== "undefined") {
      window.localStorage.setItem(STORAGE_KEY, scheme);
    }
  }, []);

  useEffect(() => {
    applyScheme(colorScheme);
  }, [colorScheme]);

  const value = useMemo(() => ({ colorScheme, setColorScheme }), [colorScheme, setColorScheme]);

  return <ThemeContext.Provider value={value}>{children}</ThemeContext.Provider>;
}

export function useColorScheme(): ThemeContextValue {
  const ctx = useContext(ThemeContext);
  if (!ctx) {
    throw new Error("useColorScheme must be used within ThemeProvider");
  }
  return ctx;
}
