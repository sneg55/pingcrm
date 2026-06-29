/**
 * Loads the real extension service-worker modules into a Node vm context.
 *
 * The modules are classic scripts meant for importScripts() — they share one
 * global lexical scope and expose functions as globals. We reproduce that by
 * concatenating the sources and running them as a single script in a vm
 * context whose globals are our stubs (chrome, fetch, Date, crypto, ...).
 *
 * importScripts() inside service-worker.js is neutralized (no-op) because we
 * concatenate its dependencies ourselves, in the same order it lists them.
 */
import fs from "node:fs";
import path from "node:path";
import vm from "node:vm";
import { fileURLToPath } from "node:url";

const HERE = path.dirname(fileURLToPath(import.meta.url));
export const EXT_DIR = path.resolve(HERE, "../..");
const BG = path.join(EXT_DIR, "background");
const LIB = path.join(EXT_DIR, "lib");

/** The exact importScripts() order from service-worker.js, then the SW itself. */
export const SERVICE_WORKER_FILES = [
  path.join(LIB, "storage.js"),
  path.join(BG, "voyager-client.js"),
  path.join(BG, "sync-utils.js"),
  path.join(BG, "sync.js"),
  path.join(BG, "pairing.js"),
  path.join(BG, "meta-client.js"),
  path.join(BG, "meta-sync-utils.js"),
  path.join(BG, "sync-facebook.js"),
  path.join(BG, "sync-instagram.js"),
  path.join(BG, "twitter-sync.js"),
  path.join(BG, "service-worker.js"),
];

/** Just the LinkedIn sync pipeline — enough for Layer 1 logic tests. */
export const SYNC_FILES = [
  path.join(LIB, "storage.js"),
  path.join(BG, "voyager-client.js"),
  path.join(BG, "sync-utils.js"),
  path.join(BG, "sync.js"),
  path.join(BG, "pairing.js"),
];

/**
 * @param {object} opts
 * @param {object} opts.chrome      chrome stub from makeChrome()
 * @param {Function} opts.fetchImpl global fetch replacement
 * @param {string[]} opts.files     module paths to concatenate (in order)
 * @param {number} [opts.fixedNow]  freeze Date.now() to this epoch ms (determinism)
 * @param {string[]} [opts.exports] global names to expose on the returned object
 * @returns {object} the vm sandbox; requested exports are also returned at top level
 */
export function loadModules({ chrome, fetchImpl, files, fixedNow, exports = [] }) {
  const RealDate = Date;
  function FixedDate(...a) {
    return a.length ? new RealDate(...a) : new RealDate(fixedNow);
  }
  FixedDate.now = () => fixedNow;
  FixedDate.parse = RealDate.parse;
  FixedDate.UTC = RealDate.UTC;
  FixedDate.prototype = RealDate.prototype;

  // Resolve delays immediately so 1s rate-limit pauses don't slow tests.
  const fastTimeout = (fn) => {
    Promise.resolve().then(fn);
    return 0;
  };

  const sandbox = {
    chrome,
    fetch: fetchImpl,
    console,
    crypto: globalThis.crypto,
    setTimeout: fastTimeout,
    clearTimeout: () => {},
    setInterval: () => 0, // pairing poll loop never fires under test
    clearInterval: () => {},
    Date: fixedNow ? FixedDate : Date,
    TextEncoder,
    TextDecoder,
    URL,
    URLSearchParams,
    structuredClone,
    importScripts: () => {}, // neutralized — we concatenate manually
  };
  sandbox.self = sandbox;
  sandbox.globalThis = sandbox;
  vm.createContext(sandbox);

  let src = files.map((f) => fs.readFileSync(f, "utf8")).join("\n;\n");
  if (exports.length) {
    src += `\n;globalThis.__exports = { ${exports.join(", ")} };`;
  }
  vm.runInContext(src, sandbox, { filename: "sw-bundle.js" });

  return Object.assign(sandbox, sandbox.__exports ?? {});
}
