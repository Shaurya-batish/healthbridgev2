// Copies the canonical rule table (repo root: rules/imnci-rules.v1.json) into
// apps/web/lib so it can be imported as a JSON module. The root file is the
// only place clinical rules are authored — this script must never transform
// content, only copy it byte-for-byte.
import { copyFileSync, mkdirSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const __dirname = dirname(fileURLToPath(import.meta.url));
const repoRoot = join(__dirname, "..", "..", "..");
const source = join(repoRoot, "rules", "imnci-rules.v1.json");
const destDir = join(__dirname, "..", "lib");
const dest = join(destDir, "imnci-rules.v1.json");

mkdirSync(destDir, { recursive: true });
copyFileSync(source, dest);
console.log(`[sync-rules] copied ${source} -> ${dest}`);
