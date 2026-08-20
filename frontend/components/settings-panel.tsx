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
}: {
  options: Option[];
  value: string;
  onChange: (value: string) => void;
  name: string;
}) {
  return (
    <div role="radiogroup" aria-label={name} className="grid gap-2 sm:grid-cols-3">
      {options.map((option) => {
        const active = option.value === value;
        return (
          <button
            key={option.value}
            type="button"
            role="radio"
            aria-checked={active}
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
