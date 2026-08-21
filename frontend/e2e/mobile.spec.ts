import { expect, test } from "@playwright/test";
import { readFileSync } from "node:fs";
import { join } from "node:path";

// Salted per project for the same dedupe reason as convert.spec.ts.
const fixture = (name: string, salt: string, project: string) => ({
  name,
  mimeType: "",
  buffer: Buffer.concat([
    readFileSync(join(process.cwd(), "e2e", "fixtures", name)),
    Buffer.from(`\ne2e-${project}-${salt}-${name}\n`),
  ]),
});

test.describe("small screens", () => {
  test("dashboard fits the viewport without sideways scrolling", async ({ page }) => {
    await page.goto("/");
    await expect(page.getByText("Drop files here")).toBeVisible();

    const overflow = await page.evaluate(
      () => document.documentElement.scrollWidth - document.documentElement.clientWidth,
    );
    // A couple of pixels of rounding is fine; a real horizontal scrollbar is not.
    expect(overflow).toBeLessThanOrEqual(2);
  });

  test("the editor has usable height on a phone", async ({ page }, testInfo) => {
    await page.goto("/");
    await page.setInputFiles('input[type="file"]', fixture("notes.docx", "mobile", testInfo.project.name));
    await page.getByRole("button", { name: "Convert to Markdown" }).click();
    await page.waitForURL(/\/jobs\//, { timeout: 30_000 });
    await expect(page.getByText("Converted", { exact: false })).toBeVisible({
      timeout: 30_000,
    });

    await page.getByRole("tab", { name: "Edit" }).click();
    const editor = page.locator(".cm-editor");
    await expect(editor).toBeVisible();

    // CodeMirror at height:100% inside a flex child collapses to zero unless
    // the chain has an explicit basis. Assert it is actually usable.
    const box = await editor.boundingBox();
    expect(box).not.toBeNull();
    expect(box!.height).toBeGreaterThan(200);
  });
});
