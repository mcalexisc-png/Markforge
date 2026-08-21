import { describe, expect, it, vi } from "vitest";
import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { UploadDropzone } from "@/components/upload-dropzone";
import type { UploadedFile } from "@/lib/types";

const makeFile = (overrides: Partial<UploadedFile> = {}): UploadedFile => ({
  id: "file-1",
  name: "report.pdf",
  size: 204800,
  format: "pdf",
  sha256: "abc123",
  duplicate_of: null,
  ...overrides,
});

function setup(files: UploadedFile[] = []) {
  const onFilesAdded = vi.fn();
  const onRemove = vi.fn();
  const onClear = vi.fn();
  const result = render(
    <UploadDropzone files={files} onFilesAdded={onFilesAdded} onRemove={onRemove} onClear={onClear} />,
  );
  return { onFilesAdded, onRemove, onClear, ...result };
}

describe("UploadDropzone — file list", () => {
  it("renders nothing when there are no files", () => {
    setup();
    expect(screen.queryByRole("list")).not.toBeInTheDocument();
  });

  it("renders each file name and format label", () => {
    setup([
      makeFile({ id: "a", name: "report.pdf", format: "pdf" }),
      makeFile({ id: "b", name: "notes.docx", format: "docx" }),
    ]);
    expect(screen.getByText("report.pdf")).toBeInTheDocument();
    expect(screen.getByText("notes.docx")).toBeInTheDocument();
  });

  it("shows the format label in the file list", () => {
    setup([makeFile({ format: "xlsx" })]);
    // Scope to the file list to avoid matching the dropzone's format badges.
    const list = screen.getByRole("list", { name: "Files ready for conversion" });
    expect(within(list).getByText(/XLSX/)).toBeInTheDocument();
  });

  it("marks duplicate files", () => {
    setup([makeFile({ duplicate_of: "existing-id" })]);
    expect(screen.getByText(/duplicate/)).toBeInTheDocument();
  });

  it("has accessible remove button per file", () => {
    setup([makeFile({ name: "report.pdf" })]);
    expect(screen.getByRole("button", { name: "Remove report.pdf" })).toBeInTheDocument();
  });

  it("calls onRemove when remove button is clicked", async () => {
    const user = userEvent.setup();
    const { onRemove } = setup([makeFile({ id: "file-1", name: "report.pdf" })]);
    await user.click(screen.getByRole("button", { name: "Remove report.pdf" }));
    expect(onRemove).toHaveBeenCalledWith("file-1");
  });

  it("shows clear all button", async () => {
    const user = userEvent.setup();
    const { onClear } = setup([makeFile()]);
    await user.click(screen.getByRole("button", { name: "Clear all" }));
    expect(onClear).toHaveBeenCalled();
  });

  it("file list has accessible label", () => {
    setup([makeFile()]);
    expect(screen.getByRole("list", { name: "Files ready for conversion" })).toBeInTheDocument();
  });
});
