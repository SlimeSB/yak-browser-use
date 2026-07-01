import React, { useState } from 'react';
import { useTranslation } from 'react-i18next';
import { useConnectionStore } from '../stores/connectionStore';

export default function ConnectionBar() {
  const { t } = useTranslation();
  const connected = useConnectionStore(s => s.connected);
  const wsUrl = useConnectionStore(s => s.wsUrl);
  const connectionError = useConnectionStore(s => s.connectionError);
  const connectMode = useConnectionStore(s => s.connectMode);
  const selectedProfile = useConnectionStore(s => s.selectedProfile);
  const profiles = useConnectionStore(s => s.profiles);
  const restartDialog = useConnectionStore(s => s.restartDialog);
  const restarting = useConnectionStore(s => s.restarting);
  const connect = useConnectionStore(s => s.connect);
  const disconnect = useConnectionStore(s => s.disconnect);
  const restartConfirm = useConnectionStore(s => s.restartConfirm);
  const restartCancel = useConnectionStore(s => s.restartCancel);
  const setConnectMode = useConnectionStore(s => s.setConnectMode);
  const setConnectionError = useConnectionStore(s => s.setConnectionError);
  const setSelectedProfile = useConnectionStore(s => s.setSelectedProfile);
  const createProfile = useConnectionStore(s => s.createProfile);

  const [showNewProfileInput, setShowNewProfileInput] = useState(false);
  const [newProfileName, setNewProfileName] = useState('');

  const handleNewProfile = () => {
    setShowNewProfileInput(true);
    setNewProfileName('');
  };

  const handleCreateConfirm = async (name: string) => {
    const trimmed = name.trim();
    if (!trimmed) return;
    await createProfile(trimmed);
    setShowNewProfileInput(false);
    setNewProfileName('');
  };

  const handleCreateKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter') handleCreateConfirm(newProfileName);
    if (e.key === 'Escape') { setShowNewProfileInput(false); setNewProfileName(''); }
  };

  return (
    <>
      {restartDialog && (
        <div className="modal-overlay" onClick={restartCancel}>
          <div className="modal-box" onClick={e => e.stopPropagation()}>
            <div className="modal-header">
              <span className="modal-icon">⚠</span>
              <span>{t('restartDialog.title')}</span>
            </div>
            <div className="modal-body">
              <p><strong>{restartDialog.browserName}</strong> is running but debug mode is not enabled.</p>
              <p>To connect to a user browser, close and restart {restartDialog.browserName} (with debug port).</p>
              {restarting && <p className="modal-loading">{t('restartDialog.restarting', { browserName: restartDialog.browserName })}</p>}
            </div>
            <div className="modal-footer">
              <button className="btn btn-secondary" onClick={restartCancel} disabled={restarting}>{t('restartDialog.cancel')}</button>
              <button className="btn btn-secondary" onClick={() => { restartCancel(); connect('isolated', selectedProfile); }} disabled={restarting}>{t('restartDialog.useIsolated')}</button>
              <button className="btn btn-primary" onClick={restartConfirm} disabled={restarting}>
                {restarting ? t('restartDialog.restarting', { browserName: restartDialog.browserName }) : t('restartDialog.closeAndRestart')}
              </button>
            </div>
          </div>
        </div>
      )}
      <div className="connection-bar">
        <span className={`conn-dot ${connected ? 'ok' : ''}`} />
        <span className="conn-label">
          {connected ? t('connection.connected') : t('connection.disconnected')}
        </span>
        {connected && wsUrl && (
          <span className="conn-url" title={wsUrl}>{wsUrl}</span>
        )}

        {!connected && (
          <>
            {connectionError && (
              <span className="conn-error" title={connectionError}>{connectionError}</span>
            )}

            <div className="conn-segment">
              <span className="conn-status-text">{t('connection.mode')}:</span>
              <div className="mode-switch">
                <label className={connectMode === 'user' ? 'active' : ''}>
                  <input type="radio" checked={connectMode === 'user'} onChange={() => { setConnectMode('user'); setConnectionError(null); }} />
                  <span className="radio-dot" /> {t('connection.userBrowser')}
                </label>
                <label className={connectMode === 'isolated' ? 'active' : ''}>
                  <input type="radio" checked={connectMode === 'isolated'} onChange={() => { setConnectMode('isolated'); setConnectionError(null); }} />
                  <span className="radio-dot" /> {t('connection.isolatedBrowser')}
                </label>
              </div>
            </div>

            {connectMode === 'user' ? (
              <div className="conn-segment">
                <button className={'btn btn-primary btn-sm' + (!connected ? ' btn-breathe' : '')} onClick={() => connect('user')}>
                  {t('connection.connectToChrome')}
                </button>
                <span className="conn-status-text">{t('connection.autoDiscover')}</span>
              </div>
            ) : (
              <div className="conn-segment">
                <div className="profile-select">
                  <span className="conn-status-text">{t('connection.profile')}</span>
                  <select value={selectedProfile} onChange={e => setSelectedProfile(e.target.value)}>
                    {profiles.map(p => (
                      <option key={p} value={p}>{p}</option>
                    ))}
                  </select>
                  {showNewProfileInput ? (
                    <span className="new-profile-input">
                      <input
                        autoFocus
                        value={newProfileName}
                        onChange={e => setNewProfileName(e.target.value)}
                        onKeyDown={handleCreateKeyDown}
                        placeholder="Enter name and press Enter"
                        className="input-sm"
                      />
                      <button className="btn btn-secondary btn-sm" onClick={() => handleCreateConfirm(newProfileName)}>{t('connection.ok')}</button>
                      <button className="btn btn-secondary btn-sm" onClick={() => { setShowNewProfileInput(false); setNewProfileName(''); }}>{t('connection.cancel')}</button>
                    </span>
                  ) : (
                    <button className="btn btn-secondary btn-sm" onClick={handleNewProfile}>{t('connection.newConnection')}</button>
                  )}
                </div>
                <button className={'btn btn-primary btn-sm' + (!connected ? ' btn-breathe' : '')} onClick={() => connect('isolated', selectedProfile)}>
                  {t('connection.startConnect')}
                </button>
              </div>
            )}
          </>
        )}

        {connected && (
          <div className="conn-actions">
            <button className="btn btn-danger btn-sm" onClick={disconnect}>{t('connection.disconnect')}</button>
          </div>
        )}
      </div>
    </>
  );
}
