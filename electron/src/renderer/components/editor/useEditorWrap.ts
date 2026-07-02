import { useState, useEffect, useCallback } from 'react';
import { readStorage, writeStorage } from '../../utils/storage';

type Listener = () => void;

const key = 'editor-wrap';
const listeners = new Set<Listener>();

function notifyListeners() {
  listeners.forEach(fn => fn());
}

export function useEditorWrap(defaults: boolean = true): [boolean, (v: boolean) => void] {
  const [wrap, setWrap] = useState(() => readStorage<boolean>(key, defaults));

  useEffect(() => {
    const listener = () => setWrap(readStorage<boolean>(key, defaults));
    listeners.add(listener);
    return () => { listeners.delete(listener); };
  }, [defaults]);

  const updateWrap = useCallback((v: boolean) => {
    writeStorage(key, v);
    setWrap(v);
    notifyListeners();
  }, []);

  return [wrap, updateWrap];
}
