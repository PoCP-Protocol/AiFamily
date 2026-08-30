import { readFile } from "node:fs/promises";
import { dirname, relative, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const webRoot = resolve(dirname(fileURLToPath(import.meta.url)), "..");
const distRoot = resolve(webRoot, "dist");

const fail = (message) => {
  throw new Error(`build audit failed: ${message}`);
};

const read = async (path) => {
  try {
    return await readFile(path, "utf8");
  } catch {
    fail(`missing artifact ${relative(webRoot, path)}`);
  }
};

const html = await read(resolve(distRoot, "index.html"));
const scriptReference = html.match(
  /<script\b[^>]*\btype="module"[^>]*\bsrc="([^"]+)"[^>]*><\/script>/,
);
if (!scriptReference) fail("index.html has no module entrypoint");

const scriptPath = resolve(distRoot, scriptReference[1].replace(/^\//, ""));
const relativeScriptPath = relative(distRoot, scriptPath);
if (!relativeScriptPath || relativeScriptPath.startsWith("..")) {
  fail("index.html module entrypoint escapes dist/");
}

const bundle = await read(scriptPath);
if (!bundle.includes("SYNTHETIC_TEST")) fail("synthetic test marker is absent from the bundle");
if (!bundle.includes("SANDBOX_SYNTHETIC") || !bundle.includes("fixture_only") || !bundle.includes("DEV_ONLY")) {
  fail("sandbox fixture provenance marker is absent from the bundle");
}
if (
  !bundle.includes('VITE_EXPERIENCE_CLIENT==="fake"&&') ||
  !bundle.includes('.DEV===!0?"fake"') ||
  !bundle.includes('VITE_EXPERIENCE_CLIENT==="http"?"http"') ||
  !bundle.includes('.DEV===!0?"fake":"http"')
) {
  fail("production bundle does not retain the DEV:false HTTP fallback and guarded fake branch");
}

const sourceMap = JSON.parse(await read(`${scriptPath}.map`));
const factoryIndex = sourceMap.sources.findIndex((source) => source.endsWith("src/api/clientFactory.ts"));
const factorySource = sourceMap.sourcesContent?.[factoryIndex];
if (!factorySource) fail("clientFactory source is not traceable from the production artifact");
if (!factorySource.includes('environment.DEV === true ? "fake" : "http"')) {
  fail("artifact source map does not retain the fail-closed client factory branch");
}
if (!factorySource.includes('environment.VITE_EXPERIENCE_CLIENT === "fake" && environment.DEV === true')) {
  fail("artifact source map does not retain the guarded fake-client branch");
}

const catalogIndex = sourceMap.sources.findIndex((source) => source.endsWith("src/live/liveCatalog.ts"));
const catalogSource = sourceMap.sourcesContent?.[catalogIndex];
if (!catalogSource) fail("live catalog source is not traceable from the production artifact");
if (
  !catalogSource.includes('source: "SANDBOX_SYNTHETIC"') ||
  !catalogSource.includes("fixture_only: true") ||
  !catalogSource.includes('approval_status: "APPROVED"') ||
  !catalogSource.includes('expiry_state: "UNEXPIRED"') ||
  !catalogSource.includes('audience_scope: "FAMILY"')
) {
  fail("artifact source map does not retain sandbox-only fixture provenance");
}

console.log(`build audit: PASS (${relativeScriptPath}; sandbox fixture explicit; DEV:false resolves HTTP; fake guarded)`);
