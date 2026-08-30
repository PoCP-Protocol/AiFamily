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
if (
  !bundle.includes("SANDBOX_SYNTHETIC") ||
  !bundle.includes("fixture_only") ||
  !bundle.includes("DEV_ONLY") ||
  !bundle.includes("LOCKED") ||
  !bundle.includes("WAITING_AUTHORIZATION") ||
  !bundle.includes("视频暂不可用") ||
  !bundle.includes("问题搜索") ||
  !bundle.includes("直播中") ||
  !bundle.includes("已结束 / 回看受限") ||
  !bundle.includes("NO_MEDIA") ||
  !bundle.includes("MEDIA_READY") ||
  !bundle.includes("PLAYBACK_AUTHORIZED") ||
  !bundle.includes("SCHEDULED") ||
  !bundle.includes("ENDED")
) {
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
  !catalogSource.includes('audience_scope: "FAMILY"') ||
  !catalogSource.includes('favorite: "LOCKED"') ||
  !catalogSource.includes('replay: "LOCKED"') ||
  !catalogSource.includes('playback_state: "WAITING_AUTHORIZATION"') ||
  !catalogSource.includes('VITE_MEDIA_PLAYBACK_DTO') ||
  !catalogSource.includes('playback_url')
) {
  fail("artifact source map does not retain sandbox-only fixture provenance");
}

const detailIndex = sourceMap.sources.findIndex((source) => source.endsWith("src/components/LiveDetailPage.tsx"));
const detailSource = sourceMap.sourcesContent?.[detailIndex];
if (!detailSource) fail("detail page source is not traceable from the production artifact");
if (!detailSource.includes("<video") || !detailSource.includes("playback.playback_url") || !detailSource.includes("playsInline")) {
  fail("artifact source map does not retain the authorized video surface");
}

console.log(`build audit: PASS (${relativeScriptPath}; sandbox fixture explicit; DEV:false resolves HTTP; fake guarded)`);
console.log("preview: pnpm run preview -- --host 127.0.0.1 -> http://127.0.0.1:4173/");
