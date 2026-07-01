import React, { useRef, useEffect, useCallback } from 'react';
import * as monaco from 'monaco-editor';

interface MonacoYamlEditorProps {
  value: string;
  original?: string;
  modified?: string;
  onChange?: (text: string) => void;
  theme?: string;
}

const monacoTheme = (t: string) => t === 'light' ? 'vs' : 'vs-dark';

export default function MonacoYamlEditor({
  value,
  original,
  modified,
  onChange,
  theme,
}: MonacoYamlEditorProps) {
  const containerRef = useRef<HTMLDivElement>(null);
  const editorRef = useRef<monaco.editor.IStandaloneDiffEditor | null>(null);
  const originalModelRef = useRef<monaco.editor.ITextModel | null>(null);
  const modifiedModelRef = useRef<monaco.editor.ITextModel | null>(null);
  const debounceRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const disposedRef = useRef(false);
  const applyingDiffRef = useRef(false);
  const onChangeRef = useRef(onChange);
  onChangeRef.current = onChange;

  const hasDiff = original !== undefined && modified !== undefined && original !== modified;

  useEffect(() => {
    if (!containerRef.current) return;
    disposedRef.current = false;

    const safeValue = value ?? '';

    originalModelRef.current = monaco.editor.createModel(
      safeValue,
      'yaml',
      monaco.Uri.parse('file:///pipeline-original.yaml')
    );
    modifiedModelRef.current = monaco.editor.createModel(
      safeValue,
      'yaml',
      monaco.Uri.parse('file:///pipeline-modified.yaml')
    );

    const editor = monaco.editor.createDiffEditor(containerRef.current, {
      theme: monacoTheme(theme || 'dark'),
      renderSideBySide: false,
      readOnly: false,
      automaticLayout: true,
      minimap: { enabled: false },
      scrollBeyondLastLine: false,
    });

    editor.updateOptions({
      fontSize: 12,
      fontFamily: "'Cascadia Code', 'Fira Code', 'JetBrains Mono', monospace",
    });

    editor.setModel({
      original: originalModelRef.current,
      modified: modifiedModelRef.current,
    });

    const innerOptions: monaco.editor.IStandaloneEditorConstructionOptions = {
      fontSize: 12,
      fontFamily: "'Cascadia Code', 'Fira Code', 'JetBrains Mono', monospace",
      lineNumbers: 'on',
      lineNumbersMinChars: 3,
      glyphMargin: false,
      lineDecorationsWidth: 4,
      tabSize: 2,
      insertSpaces: true,
      folding: true,
      guides: { indentation: true },
      matchBrackets: 'always',
      autoClosingBrackets: 'always',
      wordWrap: 'on',
      padding: { top: 8, bottom: 8 },
    };
    editor.getModifiedEditor().updateOptions(innerOptions);
    editor.getOriginalEditor().updateOptions({
      ...innerOptions,
      lineNumbers: 'off',
      glyphMargin: false,
      lineDecorationsWidth: 0,
    });

    editorRef.current = editor;

    const disposable = modifiedModelRef.current.onDidChangeContent(() => {
      if (applyingDiffRef.current) return;
      if (debounceRef.current) clearTimeout(debounceRef.current);
      debounceRef.current = setTimeout(() => {
        if (disposedRef.current) return;
        const text = modifiedModelRef.current?.getValue() ?? '';
        if (originalModelRef.current && text !== originalModelRef.current.getValue()) {
          originalModelRef.current.setValue(text);
        }
        onChangeRef.current?.(text);
      }, 300);
    });

    return () => {
      disposedRef.current = true;
      if (debounceRef.current) clearTimeout(debounceRef.current);
      disposable.dispose();
      try {
        const model = editor.getModel();
        if (model) editor.setModel(null);
        editor.dispose();
      } catch { /* dispose may cancel pending async ops */ }
      try { originalModelRef.current?.dispose(); } catch { /* ok */ }
      try { modifiedModelRef.current?.dispose(); } catch { /* ok */ }
      editorRef.current = null;
      originalModelRef.current = null;
      modifiedModelRef.current = null;
    };
  }, []);

  const setModels = useCallback(
    (orig: string, mod: string) => {
      if (!originalModelRef.current || !modifiedModelRef.current || disposedRef.current) return;
      applyingDiffRef.current = true;
      originalModelRef.current.setValue(orig ?? '');
      modifiedModelRef.current.setValue(mod ?? '');
      applyingDiffRef.current = false;
    },
    []
  );

  useEffect(() => {
    if (!editorRef.current || disposedRef.current) return;
    monaco.editor.setTheme(monacoTheme(theme || 'dark'));
  }, [theme]);

  useEffect(() => {
    if (!editorRef.current || disposedRef.current) return;
    if (hasDiff && original !== undefined && modified !== undefined) {
      setModels(original, modified);
      editorRef.current.updateOptions({ readOnly: true });
    } else {
      editorRef.current.updateOptions({ readOnly: false });
    }
  }, [original, modified, hasDiff, setModels]);

  useEffect(() => {
    if (!modifiedModelRef.current || disposedRef.current || hasDiff) return;
    const currentValue = modifiedModelRef.current.getValue();
    if (currentValue !== value) {
      applyingDiffRef.current = true;
      modifiedModelRef.current.setValue(value ?? '');
      if (originalModelRef.current) {
        originalModelRef.current.setValue(value ?? '');
      }
      applyingDiffRef.current = false;
    }
  }, [value, hasDiff]);

  return (
    <div
      ref={containerRef}
      className="monaco-yaml-editor"
      style={{ flex: 1, minHeight: 0 }}
    />
  );
}
