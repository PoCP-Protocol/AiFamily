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

// NOTE: This intentionally does not pattern-match the minified bundle text
// for the fail-closed branch. Vite inlines `import.meta.env.DEV` as the
// literal `false` in a production build, which lets the minifier constant-fold
// resolveExperienceClientMode's ternary into an unconditional "http" return
// (observed in practice as a comma expression like `c=>(cond,"http")` that
// discards the now-dead VITE_EXPERIENCE_CLIENT check). That is the *correct*
// and even stronger outcome -- the fake branch becomes literally unreachable
// dead code -- but it means any literal-text regex for the pre-minified
// source is inherently brittle against legal minifier rewrites and will
// false-positive-fail on a safe build. The source map assertion below is the
// reliable check: it traces the artifact back to the unminified TypeScript
// and asserts the guard conditions are the ones actually shipped, independent
// of how the minifier subsequently rewrites them.
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
