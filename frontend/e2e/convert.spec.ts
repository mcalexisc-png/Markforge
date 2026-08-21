import { expect, test, type Page } from "@playwright/test";
import { readFileSync } from "node:fs";
import { join } from "node:path";

const fixturePath = (name: string) =>
  join(process.cwd(), "e2e", "fixtures", name);

// Uploads are deduplicated by SHA-256, so every test needs bytes no other
// test has used. The project name is part of the salt because the desktop and
// mobile projects share one backend and one data directory: without it, the
// second project's upload is detected as a duplicate and never staged.
const uniqueCopy = (name: string, salt = "batch", project = "") => ({
  name,
  mimeType: "",
  buffer: Buffer.concat([
    readFileSync(fixturePath(name)),
    Buffer.from(`\ne2e-${project}-${salt}-${name}\n`),
  ]),
});

const stagedFiles = (page: Page) =>
  page.getByRole("list", { name: "Files ready for conversion" });

test("dashboard loads and shows the dropzone", async ({ page }) => {
  await page.goto("/");
  await expect(page.getByRole("heading", { name: /Convert documents/ })).toBeVisible();
  await expect(page.getByText("Drop files here")).toBeVisible();
});

test("upload -> convert -> preview -> edit -> download flow", async ({ page }, testInfo) => {
  await page.goto("/");
  await page.setInputFiles('input[type="file"]', uniqueCopy("notes.docx", "single-flow", testInfo.project.name));
  await expect(stagedFiles(page).getByText("notes.docx")).toBeVisible();

  await page.getByRole("button", { name: "Convert to Markdown" }).click();
  await page.waitForURL(/\/jobs\//, { timeout: 30_000 });

  await expect(page.getByText("notes.docx").first()).toBeVisible();
  await expect(page.getByText("Converted", { exact: false }).first()).toBeVisible({ timeout: 30_000 });

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
  await expect(page.getByText("Markdown saved")).toBeVisible({ timeout: 15_000 });
  await expect(page.getByText("Unsaved changes")).toBeHidden({ timeout: 15_000 });

  const downloadPromise = page.waitForEvent("download");
  await page.getByRole("button", { name: "Download .md" }).click();
  const download = await downloadPromise;
  expect(download.suggestedFilename()).toBe("notes.md");

  const zipPromise = page.waitForEvent("download");
  await page.getByRole("button", { name: "Download ZIP" }).click();
  const zip = await zipPromise;
  expect(zip.suggestedFilename()).toMatch(/\.zip$/);
});

test("history shows the job and can be deleted", async ({ page }, testInfo) => {
  await page.goto("/");
  await page.setInputFiles('input[type="file"]', uniqueCopy("notes.docx", "history", testInfo.project.name));
  await expect(stagedFiles(page).getByText("notes.docx")).toBeVisible();
  await page.getByRole("button", { name: "Convert to Markdown" }).click();
  await page.waitForURL(/\/jobs\//, { timeout: 30_000 });
  await expect(page.getByText("Converted", { exact: false })).toBeVisible({ timeout: 30_000 });

  await page.getByRole("link", { name: "History" }).click();
  const notesLinks = page.getByRole("link", { name: "notes.docx" });
  await expect(notesLinks.first()).toBeVisible();
  await expect(notesLinks.first()).toHaveAttribute("href", /\/jobs\//);

  const notesLinksBefore = await notesLinks.count();
  await page.getByRole("button", { name: "Delete notes.docx" }).first().click();
  await expect(page.getByRole("heading", { name: "Delete this conversion?" })).toBeVisible();
  await page.getByRole("button", { name: "Delete", exact: true }).click();
  await expect(notesLinks).toHaveCount(notesLinksBefore - 1);
  await expect(page.getByText("Deleted", { exact: false })).toBeVisible();
});

test("batch conversion of all four formats", async ({ page }, testInfo) => {
  await page.goto("/");
  await page.setInputFiles('input[type="file"]', [
    uniqueCopy("report.pdf", "batch", testInfo.project.name),
    uniqueCopy("notes.docx", "batch", testInfo.project.name),
    uniqueCopy("deck.pptx", "batch", testInfo.project.name),
    uniqueCopy("grades.xlsx", "batch", testInfo.project.name),
  ]);
  await expect(stagedFiles(page).getByText("report.pdf")).toBeVisible();
  await expect(stagedFiles(page).getByText("grades.xlsx")).toBeVisible();

  await page.getByRole("button", { name: /Convert all/ }).click();
  await page.waitForURL(/\/jobs\//, { timeout: 30_000 });

  for (const name of ["report.pdf", "notes.docx", "deck.pptx", "grades.xlsx"]) {
    await expect(page.locator(`text=${name}`).first()).toBeVisible();
  }
  await expect(page.getByText("Converted", { exact: false }).first()).toBeVisible({ timeout: 60_000 });
});
