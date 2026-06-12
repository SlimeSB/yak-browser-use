import React from 'react';

export default function TitleBar() {
  return (
    <div className="titlebar">
      <span className="titlebar-title">Learning Browser-Use</span>
      <div className="titlebar-controls">
        <button className="titlebar-btn" onClick={() => window.electronAPI.windowMinimize()}>─</button>
        <button className="titlebar-btn" onClick={() => window.electronAPI.windowMaximize()}>□</button>
        <button className="titlebar-btn titlebar-close" onClick={() => window.electronAPI.windowClose()}>✕</button>
      </div>
    </div>
  );
}
