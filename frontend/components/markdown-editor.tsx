"use client";

import * as React from "react";
import CodeMirror from "@uiw/react-codemirror";
import { markdown, markdownLanguage } from "@codemirror/lang-markdown";
import { languages } from "@codemirror/language-data";
import { EditorView } from "@codemirror/view";
import { useTheme } from "next-themes";

interface MarkdownEditorProps {
  value: string;
  onChange: (value: string) => void;
  readOnly?: boolean;
  height?: string;
}

export function MarkdownEditor({ value, onChange, readOnly, height = "100%" }: MarkdownEditorProps) {
  const { resolvedTheme } = useTheme();
  const dark = resolvedTheme === "dark";

  const extensions = React.useMemo(
    () => [
      markdown({ base: markdownLanguage, codeLanguages: languages }),
      EditorView.lineWrapping,
      EditorView.theme({
        "&": { fontSize: "13.5px", backgroundColor: "transparent" },
        ".cm-content": { fontFamily: "ui-monospace, SFMono-Regular, Menlo, Consolas, monospace", padding: "12px 16px" },
        ".cm-gutters": { backgroundColor: "transparent", borderRight: "1px solid var(--border)", color: "var(--muted-foreground)" },
        ".cm-activeLine": { backgroundColor: "transparent" },
        "&.cm-focused": { outline: "none" },
        ".cm-selectionBackground, &.cm-focused .cm-selectionBackground": {
          backgroundColor: dark ? "rgba(255,255,255,0.12)" : "rgba(0,0,0,0.08)",
        },
      }),
    ],
    [dark]
  );

  return (
    <CodeMirror
      value={value}
      onChange={(value) => onChange(value)}
      extensions={extensions}
      readOnly={readOnly}
      height={height}
      theme={dark ? "dark" : "light"}
      basicSetup={{
        lineNumbers: true,
        foldGutter: true,
        highlightActiveLine: true,
        highlightSelectionMatches: true,
      }}
      className="h-full overflow-hidden text-left"
      aria-label="Markdown editor"
    />
  );
}
