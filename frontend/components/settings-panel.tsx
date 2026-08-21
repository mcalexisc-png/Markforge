"use client";

import * as React from "react";
import { ChevronDown, Settings2 } from "lucide-react";
import { cn } from "@/lib/utils";
import type { UserSettings } from "@/lib/types";
import { Switch } from "@/components/ui/switch";

interface Option {
  value: string;
  label: string;
  description: string;
}

function RadioGroup({
  options,
  value,
  onChange,
  name,
  columns = 3,
}: {
  options: Option[];
  value: string;
  onChange: (value: string) => void;
  name: string;
  columns?: number;
}) {
  const refs = React.useRef<(HTMLButtonElement | null)[]>([]);

  // The ARIA radiogroup pattern is arrow-key driven with a roving tabindex:
  // the group occupies one tab stop and the options are moved between with the
  // arrow keys. Declaring the roles without this behaviour is worse than using
  // plain buttons, because it promises navigation that does not work.
  const onKeyDown = (event: React.KeyboardEvent, index: number) => {
    const keys = ["ArrowRight", "ArrowDown", "ArrowLeft", "ArrowUp", "Home", "End"];
    if (!keys.includes(event.key)) return;
    event.preventDefault();

    const last = options.length - 1;
    let next = index;
    if (event.key === "ArrowRight" || event.key === "ArrowDown") next = index === last ? 0 : index + 1;
    else if (event.key === "ArrowLeft" || event.key === "ArrowUp") next = index === 0 ? last : index - 1;
    else if (event.key === "Home") next = 0;
    else if (event.key === "End") next = last;

    onChange(options[next].value);
    refs.current[next]?.focus();
  };

  // When nothing is selected the first option takes the tab stop, so the group
  // is always reachable by keyboard.
  const selectedIndex = options.findIndex((option) => option.value === value);
  const tabStop = selectedIndex === -1 ? 0 : selectedIndex;

  return (
    <div role="radiogroup" aria-label={name} className={cn("grid gap-2", columns === 2 ? "sm:grid-cols-2" : "sm:grid-cols-3")}>
      {options.map((option, index) => {
        const active = option.value === value;
        return (
          <button
            key={option.value}
            ref={(node) => {
              refs.current[index] = node;
            }}
            type="button"
            role="radio"
            aria-checked={active}
            tabIndex={index === tabStop ? 0 : -1}
            onKeyDown={(event) => onKeyDown(event, index)}
            onClick={() => onChange(option.value)}
            className={cn(
              "flex flex-col items-start gap-0.5 rounded-lg border px-3 py-2.5 text-left transition-all duration-150 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring",
              active
                ? "border-primary/60 bg-primary/5 ring-1 ring-primary/30"
                : "border-border hover:border-primary/40 hover:bg-accent/40"
            )}
          >
            <span className={cn("text-sm font-medium", active ? "text-primary" : "")}>{option.label}</span>
            <span className="text-xs text-muted-foreground leading-snug">{option.description}</span>
          </button>
        );
      })}
    </div>
  );
}

interface SettingsPanelProps {
  settings: UserSettings;
  onChange: (settings: UserSettings) => void;
  onSave?: () => void;
  saving?: boolean;
  compact?: boolean;
}

export function SettingsPanel({ settings, onChange, onSave, saving, compact }: SettingsPanelProps) {
  const [advancedOpen, setAdvancedOpen] = React.useState(false);
  const set = <K extends keyof UserSettings>(key: K, value: UserSettings[K]) =>
    onChange({ ...settings, [key]: value });

  const toggles: { key: keyof UserSettings; label: string; description: string }[] = [
    { key: "preserve_boundaries", label: "Page / slide / sheet boundaries", description: "Keep `---` separators between pages, slides and sheets" },
    { key: "convert_tables", label: "Convert tables to Markdown", description: "Render tables as Markdown tables" },
    { key: "preserve_links", label: "Preserve hyperlinks", description: "Keep links as [text](url)" },
    { key: "extract_images", label: "Extract figures", description: "Save embedded images alongside the Markdown" },
  ];

  return (
    <div className={cn("rounded-xl border border-border bg-card p-5 shadow-sm", compact && "p-4")}>
      <div className="mb-4 flex items-center gap-2">
        <Settings2 className="h-4 w-4 text-primary" />
        <h2 className="text-sm font-semibold">Conversion settings</h2>
      </div>

      <div className="space-y-5">
        <fieldset>
          <legend className="mb-2 block text-xs font-medium uppercase tracking-wide text-muted-foreground">
            Output mode
          </legend>
          <RadioGroup
            name="output-mode"
            columns={2}
            value={settings.output_mode}
            onChange={(value) => set("output_mode", value as UserSettings["output_mode"])}
            options={[
              { value: "fidelity", label: "Fidelity", description: "Keeps pages, slides and sheets visible" },
              { value: "clean", label: "Clean Markdown", description: "Flows content, no page/slide/sheet markers" },
            ]}
          />
        </fieldset>

        <fieldset>
          <legend className="mb-2 block text-xs font-medium uppercase tracking-wide text-muted-foreground">
            OCR
          </legend>
          <RadioGroup
            name="ocr-mode"
            value={settings.ocr_mode}
            onChange={(value) => set("ocr_mode", value as UserSettings["ocr_mode"])}
            options={[
              { value: "auto", label: "Automatic", description: "OCR only scanned pages" },
              { value: "always", label: "Always", description: "OCR every page" },
              { value: "never", label: "Never", description: "Text extraction only" },
            ]}
          />
        </fieldset>

        <div>
          <button
            type="button"
            onClick={() => setAdvancedOpen((v) => !v)}
            aria-expanded={advancedOpen}
            className="flex w-full items-center justify-between rounded-md px-1 py-1 text-xs font-medium uppercase tracking-wide text-muted-foreground transition-colors hover:text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
          >
            Advanced
            <ChevronDown className={cn("h-4 w-4 transition-transform duration-200", advancedOpen && "rotate-180")} />
          </button>
          {advancedOpen && (
            <div className="mt-3 animate-fade-in space-y-1">
              {toggles.map((toggle) => (
                <div
                  key={toggle.key}
                  className="flex items-center justify-between gap-3 rounded-lg px-1 py-2"
                >
                  <div className="min-w-0">
                    <p className="text-sm font-medium">{toggle.label}</p>
                    <p className="text-xs text-muted-foreground">{toggle.description}</p>
                  </div>
                  <Switch
                    checked={Boolean(settings[toggle.key])}
                    onCheckedChange={(checked) => set(toggle.key, checked)}
                    aria-label={toggle.label}
                  />
                </div>
              ))}
            </div>
          )}
        </div>

        {onSave && (
          <button
            type="button"
            disabled={saving}
            onClick={onSave}
            className="text-xs font-medium text-primary underline-offset-2 transition-colors hover:underline disabled:opacity-50"
          >
            {saving ? "Saving…" : "Save as default"}
          </button>
        )}
      </div>
    </div>
  );
}
