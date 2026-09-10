import { useColorScheme } from "./ThemeProvider";

/** Small fixed corner toggle — web had no dark-mode entry point before this. */
export function ColorSchemeToggle() {
  const { colorScheme, setColorScheme } = useColorScheme();
  const next = colorScheme === "light" ? "dark" : "light";
  return (
    <button
      type="button"
      className="color-scheme-toggle"
      onClick={() => setColorScheme(next)}
      aria-label={colorScheme === "light" ? "切换到深色模式" : "切换到浅色模式"}
    >
      {colorScheme === "light" ? "🌙" : "☀️"}
    </button>
  );
}
