import { execSync } from "node:child_process";
import { existsSync } from "node:fs";
import { join } from "node:path";

export default function globalSetup() {
  // The data directory is deliberately NOT wiped here. Playwright starts
  // `webServer` before globalSetup, so the backend has already created and
  // opened its SQLite database by this point; deleting the directory leaves
  // the server holding a handle to an unlinked inode, and the next connection
  // it opens silently creates an empty database ("no such table: jobs").
  // The wipe was also redundant: MARKFORGE_E2E_DATA is unique per run
  // (`markforge-e2e-${Date.now()}`), so there is never stale state to clear.

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