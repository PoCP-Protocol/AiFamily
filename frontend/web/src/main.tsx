import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import App from "./App";
import { ProductStudioWorkspace } from "./productStudio/ProductStudioWorkspace";
import { ThemeProvider } from "./theme/ThemeProvider";
import { ColorSchemeToggle } from "./theme/ColorSchemeToggle";
import "./styles.css";

export function WebRoot() {
  const path = window.location.pathname.replace(/\/+$/, "") || "/";
  return (
    <ThemeProvider>
      <ColorSchemeToggle />
      {path === "/product-studio" ? (
        <main>
          <ProductStudioWorkspace />
        </main>
      ) : (
        <App />
      )}
    </ThemeProvider>
  );
}

const root = document.getElementById("root");
if (root) {
  const reactRoot = import.meta.hot?.data.reactRoot ?? createRoot(root);
  if (import.meta.hot) import.meta.hot.data.reactRoot = reactRoot;
  reactRoot.render(
    <StrictMode>
      <WebRoot />
    </StrictMode>,
  );
}
