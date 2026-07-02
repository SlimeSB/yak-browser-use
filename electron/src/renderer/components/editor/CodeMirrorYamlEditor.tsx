import React, { useMemo } from 'react';
import CodeMirror from '@uiw/react-codemirror';
import { yaml } from '@codemirror/lang-yaml';
import { unifiedMergeView } from '@codemirror/merge';
import { EditorState } from '@codemirror/state';
import { EditorView } from '@codemirror/view';

interface CodeMirrorYamlEditorProps {
  value: string;
  original?: string;
  modified?: string;
  onChange?: (text: string) => void;
  theme?: string;
  wrap?: boolean;
  onWrapChange?: (wrap: boolean) => void;
}

const fontFamily = "'Cascadia Code', 'Fira Code', 'JetBrains Mono', 'Consolas', monospace";

const baseTheme = EditorView.theme({
  '&': {
    fontSize: '13px',
    fontFamily: fontFamily,
  },
  '.cm-scroller': {
    fontFamily: fontFamily,
  },
  '.cm-content': {
    fontFamily: fontFamily,
    caretColor: '#528bff',
  },
  '.cm-gutters': {
    fontFamily: fontFamily,
    fontSize: '12px',
  },
  '.cm-activeLineGutter': {
    backgroundColor: 'var(--bg-hover)',
  },
  '&.cm-editor.cm-focused': {
    outline: 'none',
  },
});

const darkThemeOverrides = EditorView.theme({
  '&': {
    backgroundColor: 'var(--bg-surface)',
  },
  '&.cm-focused .cm-cursor': {
    borderLeftColor: '#aeafad',
  },
  '.cm-activeLine': {
    backgroundColor: 'var(--bg-hover)',
  },
}, { dark: true });

export default function CodeMirrorYamlEditor({
  value,
  original,
  modified,
  onChange,
  theme,
  wrap = true,
  onWrapChange,
}: CodeMirrorYamlEditorProps) {
  const hasDiff = original !== undefined && modified !== undefined && original !== modified;
  const isDark = theme !== 'light';

  const cmTheme = isDark ? 'dark' : 'light';

  const extensions = useMemo(() => {
    const base = [yaml(), baseTheme];
    if (isDark) base.push(darkThemeOverrides);
    if (hasDiff) {
      return [
        ...base,
        unifiedMergeView({ original: original! }),
        EditorState.readOnly.of(true),
        EditorView.editable.of(false),
      ];
    }
    return wrap ? [...base, EditorView.lineWrapping] : base;
  }, [hasDiff, original, isDark, wrap]);

  return (
    <div style={{ flex: 1, minHeight: 0, overflow: 'auto' }}>
      <CodeMirror
        value={value}
        onChange={onChange}
        extensions={extensions}
        theme={cmTheme}
        basicSetup={{
          lineNumbers: true,
          tabSize: 2,
          indentUnit: 2,
          bracketMatching: true,
          foldGutter: true,
        }}
      />
    </div>
  );
}
