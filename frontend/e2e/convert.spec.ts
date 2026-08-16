import { expect, test } from "@playwright/test";
import { join } from "node:path";

const fixturePath = (name: string) =>
  join(process.cwd(), "e2e", "fixtures", name);

test("dashboard loads and shows the dropzone", async ({ page }) => {
  await page.goto("/");
  await expect(page.getByRole("heading", { name: /Convert documents/ })).toBeVisible();
  await expect(page.getByText("Drop files here")).toBeVisible();
});

test("upload -> convert -> preview -> edit -> download flow", async ({ page }) => {
  await page.goto("/");
  await page.setInputFiles('input[type="file"]', fixturePath("report.pdf"));
  await expect(page.getByText("report.pdf")).toBeVisible();

  await page.getByRole("button", { name: "Convert to Markdown" }).click();
  await page.waitForURL(/\/jobs\//, { timeout: 30_000 });

  await expect(page.getByText("report.pdf")).toBeVisible();
  await expect(page.getByText("Converted", { exact: false })).toBeVisible({ timeout: 30_000 });

  await expect(page.getByRole("tab", { name: "Preview" })).toBeVisible();
  await page.getByRole("tab", { name: "Preview" }).click();

  await expect(page.locator(".markdown-body h1").first()).toBeVisible();

  await page.getByRole("tab", { name: "Edit" }).click();
  const editor = page.locator(".cm-content");
  await expect(editor).toBeVisible();
  await editor.click();
  await page.keyboard.press("ControlOrMeta+End");
  await page.keyboard.type("\n\n# Appended by e2e test");
  await page.getByRole("button", { name: "Save", exact: true }).click();
  await expect(page.getByText("Unsaved changes")).toBeHidden();
  await expect(page.getByText("Markdown saved")).toBeVisible();

  const downloadPromise = page.waitForEvent("download");
  await page.getByRole("button", { name: "Download .md" }).click();
  const download = await downloadPromise;
  expect(download.suggestedFilename()).toBe("report.md");

  const zipPromise = page.waitForEvent("download");
  await page.getByRole("button", { name: "Download ZIP" }).click();
  const zip = await zipPromise;
  expect(zip.suggestedFilename()).toMatch(/\.zip$/);
});

test("history shows the job and can be deleted", async ({ page }) => {
  await page.goto("/");
  await page.setInputFiles('input[type="file"]', fixturePath("notes.docx"));
  await page.getByRole("button", { name: "Convert to Markdown" }).click();
  await page.waitForURL(/\/jobs\//, { timeout: 30_000 });
  await expect(page.getByText("Converted", { exact: false })).toBeVisible({ timeout: 30_000 });

  await page.getByRole("link", { name: "History" }).click();
  await expect(page.getByRole("link", { name: "notes.docx" })).toBeVisible();
  await expect(page.getByRole("link", { name: "notes.docx" })).toHaveAttribute("href", /\/jobs\//);

  await page.getByRole("button", { name: "Delete notes.docx" }).click();
  await expect(page.getByRole("link", { name: "notes.docx" })).toHaveCount(0);
  await expect(page.getByText("Deleted", { exact: false })).toBeVisible();
});

test("batch conversion of all four formats", async ({ page }) => {
  await page.goto("/");
  await page.setInputFiles('input[type="file"]', [
    fixturePath("report.pdf"),
    fixturePath("notes.docx"),
    fixturePath("deck.pptx"),
    fixturePath("grades.xlsx"),
  ]);
  await expect(page.getByText("report.pdf")).toBeVisible();
  await expect(page.getByText("grades.xlsx")).toBeVisible();

  await page.getByRole("button", { name: /Convert all/ }).click();
  await page.waitForURL(/\/jobs\//, { timeout: 30_000 });

  for (const name of ["report.pdf", "notes.docx", "deck.pptx", "grades.xlsx"]) {
    await expect(page.locator(`text=${name}`).first()).toBeVisible();
  }
  await expect(page.getByText("Converted", { exact: false }).first()).toBeVisible({ timeout: 60_000 });
});
