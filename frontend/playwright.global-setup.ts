import { execSync } from "node:child_process";
import { existsSync, rmSync } from "node:fs";
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
  try {
    execSync(`node "${script}"`, { stdio: "inherit" });
  } catch {
    const fixturesDir = join(process.cwd(), "e2e", "fixtures");
    const names = ["report.pdf", "notes.docx", "deck.pptx", "grades.xlsx"];
    if (names.every((name) => existsSync(join(fixturesDir, name)))) {
      console.warn(
        "Fixture regeneration failed (backend venv missing?); using committed fixtures."
      );
    } else {
      throw new Error(
        "Fixture generation failed and no committed fixtures are available. " +
          "Install the backend venv or run `node e2e/generate-fixtures.mjs`."
      );
    }
  }
}