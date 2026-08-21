import { describe, expect, it, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { SettingsPanel } from "@/components/settings-panel";
import type { UserSettings } from "@/lib/types";

const defaults: UserSettings = {
  output_mode: "fidelity",
  ocr_mode: "auto",
  preserve_boundaries: true,
  convert_tables: true,
  preserve_links: true,
  extract_images: false,
};

function setup(overrides: Partial<UserSettings> = {}, props = {}) {
  const onChange = vi.fn();
  const onSave = vi.fn();
  const result = render(
    <SettingsPanel settings={{ ...defaults, ...overrides }} onChange={onChange} onSave={onSave} {...props} />,
  );
  return { onChange, onSave, ...result };
}

describe("SettingsPanel", () => {
  it("renders the heading", () => {
    setup();
    expect(screen.getByText("Conversion settings")).toBeInTheDocument();
  });

  it("calls onChange when output mode is selected", async () => {
    const user = userEvent.setup();
    const { onChange } = setup();
    // The radio accessible name includes both label and description.
    const clean = screen.getByRole("radio", { name: /Clean Markdown/ });
    await user.click(clean);
    expect(onChange).toHaveBeenCalledWith(
      expect.objectContaining({ output_mode: "clean" }),
    );
  });

  it("calls onChange when OCR mode is selected", async () => {
    const user = userEvent.setup();
    const { onChange } = setup();
    await user.click(screen.getByRole("radio", { name: /Always/ }));
    expect(onChange).toHaveBeenCalledWith(
      expect.objectContaining({ ocr_mode: "always" }),
    );
  });

  it("advanced section is collapsed by default", () => {
    setup();
    expect(screen.queryByRole("button", { name: "Page / slide / sheet boundaries" })).not.toBeInTheDocument();
  });

  it("expands advanced section and shows toggles", async () => {
    const user = userEvent.setup();
    setup();
    await user.click(screen.getByRole("button", { name: /Advanced/ }));
    // Toggles are <button role="switch"> with aria-label.
    expect(screen.getByRole("switch", { name: "Page / slide / sheet boundaries" })).toBeInTheDocument();
    expect(screen.getByRole("switch", { name: "Extract figures" })).toBeInTheDocument();
  });

  it("calls onChange when a toggle is flipped", async () => {
    const user = userEvent.setup();
    const { onChange } = setup();
    await user.click(screen.getByRole("button", { name: /Advanced/ }));
    await user.click(screen.getByRole("switch", { name: "Extract figures" }));
    expect(onChange).toHaveBeenCalledWith(
      expect.objectContaining({ extract_images: true }),
    );
  });

  it("renders save button when onSave is provided", () => {
    setup();
    expect(screen.getByRole("button", { name: "Save as default" })).toBeInTheDocument();
  });

  it("hides save button when onSave is absent", () => {
    render(
      <SettingsPanel settings={defaults} onChange={vi.fn()} />,
    );
    expect(screen.queryByRole("button", { name: "Save as default" })).not.toBeInTheDocument();
  });
});
