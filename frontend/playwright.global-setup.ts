import { execSync } from "node:child_process";
import { rmSync } from "node:fs";
import { join } from "node:path";

export default function globalSetup() {
  const e2eData = process.env.MARKFORGE_E2E_DATA;
  if (e2eData) {
    try {
      rmSync(e2eData, { recursive: true, force: true });
    } catch {
      /* dir may be locked by a previous run; the unique per-run dir makes this best-effort */
    }
  }

  const script = join(process.cwd(), "e2e", "generate-fixtures.mjs");
  execSync(`node "${script}"`, { stdio: "inherit" });
}
