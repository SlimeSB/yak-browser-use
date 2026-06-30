import React from 'react';
import { createRoot } from 'react-dom/client';
import './i18n';
import { initGateway } from './ws/gateway';
import App from './App';

initGateway();

const root = createRoot(document.getElementById('root')!);
root.render(
  <React.StrictMode>
    <App />
  </React.StrictMode>,
);
