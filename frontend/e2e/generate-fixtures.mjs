import { spawnSync } from "node:child_process";
import { existsSync, mkdirSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const here = dirname(fileURLToPath(import.meta.url));
const root = dirname(dirname(here));
const backendDir = join(root, "backend");
const outDir = join(here, "fixtures");
mkdirSync(outDir, { recursive: true });

const venvPython =
  process.platform === "win32"
    ? join(backendDir, ".venv", "Scripts", "python.exe")
    : join(backendDir, ".venv", "bin", "python");
const python = existsSync(venvPython) ? venvPython : "python";

const code = `
import sys
sys.path.insert(0, "tests")
from fixtures.make_fixtures import make_pdf, make_docx, make_pptx, make_xlsx
from pathlib import Path
out = Path(${JSON.stringify(outDir)})
make_pdf(out / "report.pdf")
make_docx(out / "notes.docx")
make_pptx(out / "deck.pptx")
make_xlsx(out / "grades.xlsx")
print("fixtures written to", out)
`;

const result = spawnSync(
  python,
  ["-c", code],
  { cwd: backendDir, encoding: "utf-8" }
);

if (result.status !== 0) {
  console.error("Failed to generate e2e fixtures:", result.stderr || result.stdout);
  process.exit(result.status ?? 1);
}
console.log(result.stdout.trim());
