import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import App from "./App";
import { ProductFactoryComposer } from "./productStudio/ProductFactoryComposer";
import { MarketEvidenceWorkbench } from "./productStudio/MarketEvidenceWorkbench";
import { ProductStudio } from "./productStudio/ProductStudio";
import { sandboxProductStudioState } from "./productStudio/sandboxFixture";
import "./styles.css";

export function WebRoot() {
  const path = window.location.pathname.replace(/\/+$/, "") || "/";
  if (path === "/product-studio") {
    return (
      <main>
        <ProductFactoryComposer />
        <MarketEvidenceWorkbench />
        <ProductStudio initialState={sandboxProductStudioState} environmentLabel="Sandbox · Product Studio · API seam" />
      </main>
    );
  }
  return <App />;
}

const root = document.getElementById("root");
if (root) createRoot(root).render(
  <StrictMode>
    <WebRoot />
  </StrictMode>,
);
