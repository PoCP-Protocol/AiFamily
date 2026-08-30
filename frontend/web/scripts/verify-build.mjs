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
if (!/=>\s*["']http["']/.test(bundle)) {
  fail("production bundle does not resolve the default client to HTTP (DEV:false fail-closed)");
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

console.log(`build audit: PASS (${relativeScriptPath}; DEV:false resolves HTTP; fake guarded)`);
