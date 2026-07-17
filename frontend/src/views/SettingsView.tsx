import { useEffect, useRef, useState } from 'react';
import { api } from '../api';
import { useAppStore } from '../store';
import { downloadBlob, safeJsonParse } from '../utils';

export function SettingsView() {
  const sessionId = useAppStore((state) => state.sessionId);
  const config = useAppStore((state) => state.config);
  const setConfig = useAppStore((state) => state.setConfig);
  const importData = useAppStore((state) => state.importData);
  const deleteAllData = useAppStore((state) => state.deleteAllData);
  const setNotification = useAppStore((state) => state.setNotification);
  const saveSession = useAppStore((state) => state.saveSession);
  const saveStatus = useAppStore((state) => state.saveStatus);
  const fileRef = useRef<HTMLInputElement>(null);
  const [sessions, setSessions] = useState<Array<{ id: string; status: string; updated_at: string }>>([]);
  const [confirmDelete, setConfirmDelete] = useState('');

  useEffect(() => {
    void api
      .listSessions()
      .then(setSessions)
      .catch(() => setSessions([]));
  }, []);

  return (
    <main className="settings-page content-page">
      <header className="page-heading">
        <div>
          <p className="eyebrow">Stockage 100 % local</p>
          <h1>Données et paramètres</h1>
          <p>Gérez les sauvegardes, imports et exports sans compte externe.</p>
        </div>
      </header>
      <section className="integrity-banner">
        <span aria-hidden="true">◈</span>
        <div>
          <strong>Usage fictif uniquement</strong>
          <p>
            Cette application est un simulateur d’entraînement utilisant exclusivement des jetons fictifs.
            Elle n’est pas conçue pour assister un joueur sur une plateforme de poker en direct.
          </p>
        </div>
      </section>
      <div className="settings-grid">
        <section className="panel setting-card">
          <header>
            <span aria-hidden="true">●</span>
            <div>
              <h2>Sauvegarde de session</h2>
              <p>L’écriture backend est asynchrone et ne bloque jamais une action.</p>
            </div>
          </header>
          <dl>
            <div>
              <dt>État actuel</dt>
              <dd className={saveStatus}>
                {saveStatus === 'saved'
                  ? 'Sauvegardé'
                  : saveStatus === 'saving'
                    ? 'Écriture en cours'
                    : 'Nouvelle tentative nécessaire'}
              </dd>
            </div>
            <div>
              <dt>Mode</dt>
              <dd>Automatique + manuel</dd>
            </div>
            <div>
              <dt>Emplacement</dt>
              <dd>Base SQLite locale</dd>
            </div>
          </dl>
          <button
            type="button"
            className="primary"
            disabled={!sessionId || saveStatus === 'saving'}
            onClick={() => void saveSession()}
          >
            Sauvegarder maintenant
          </button>
        </section>
        <section className="panel setting-card">
          <header>
            <span aria-hidden="true">?</span>
            <div>
              <h2>Mode de conseil</h2>
              <p>Ce réglage prend effet dès le prochain tour de Ryanchl.</p>
            </div>
          </header>
          <div className="segmented-control">
            <button
              type="button"
              className={config.advice_mode === 'immediate' ? 'active' : ''}
              onClick={() => setConfig({ ...config, advice_mode: 'immediate' })}
            >
              Conseil immédiat
            </button>
            <button
              type="button"
              className={config.advice_mode === 'quiz' ? 'active' : ''}
              onClick={() => setConfig({ ...config, advice_mode: 'quiz' })}
            >
              Mode quiz
            </button>
          </div>
          <p className="muted">
            En quiz, le conseil est calculé mais masqué jusqu’au choix. La note compare les EV estimées, pas
            le résultat de la main.
          </p>
        </section>
        <section className="panel setting-card export-card">
          <header>
            <span aria-hidden="true">⇩</span>
            <div>
              <h2>Exporter</h2>
              <p>Fichiers portables lisibles hors de l’application.</p>
            </div>
          </header>
          <button
            type="button"
            className="ghost"
            disabled={!sessionId}
            onClick={() =>
              sessionId &&
              void api
                .exportSession(sessionId)
                .then((blob) => downloadBlob(blob, `poker-ia-session-${sessionId}.json`, 'application/json'))
                .catch((error: Error) => setNotification({ kind: 'error', message: error.message }))
            }
          >
            Session complète en JSON
          </button>
          <button
            type="button"
            className="ghost"
            onClick={() =>
              void api
                .exportHistoryCsv()
                .then((blob) => downloadBlob(blob, 'poker-ia-historique.csv', 'text/csv'))
                .catch((error: Error) => setNotification({ kind: 'error', message: error.message }))
            }
          >
            Historique en CSV
          </button>
        </section>
        <section className="panel setting-card import-card">
          <header>
            <span aria-hidden="true">⇧</span>
            <div>
              <h2>Importer</h2>
              <p>Le moteur valide le schéma et refuse les données incompatibles.</p>
            </div>
          </header>
          <input
            ref={fileRef}
            type="file"
            accept="application/json,.json"
            hidden
            onChange={(event) => {
              const file = event.target.files?.[0];
              if (!file) return;
              void file
                .text()
                .then((text) => importData(safeJsonParse(text)))
                .catch((error: Error) => setNotification({ kind: 'error', message: error.message }));
              event.target.value = '';
            }}
          />
          <button type="button" className="ghost" onClick={() => fileRef.current?.click()}>
            Choisir un fichier JSON
          </button>
        </section>
      </div>
      <section className="panel saved-sessions">
        <header>
          <div>
            <h2>Sessions locales</h2>
            <p>Inventaire renvoyé par la base locale.</p>
          </div>
          <strong>{sessions.length}</strong>
        </header>
        {sessions.length ? (
          <table>
            <thead>
              <tr>
                <th>Identifiant</th>
                <th>État</th>
                <th>Dernière mise à jour</th>
              </tr>
            </thead>
            <tbody>
              {sessions.map((session) => (
                <tr key={session.id}>
                  <td>{session.id}</td>
                  <td>{session.status}</td>
                  <td>
                    {new Intl.DateTimeFormat('fr-FR', { dateStyle: 'medium', timeStyle: 'short' }).format(
                      new Date(session.updated_at),
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        ) : (
          <p className="empty-inline">Aucune session enregistrée.</p>
        )}
      </section>
      <section className="panel danger-zone">
        <header>
          <div>
            <h2>Supprimer toutes les données locales</h2>
            <p>Sessions, mains, profils, notes, statistiques et historique seront définitivement effacés.</p>
          </div>
        </header>
        <label className="field">
          <span>Tapez SUPPRIMER pour confirmer</span>
          <input
            value={confirmDelete}
            onChange={(event) => setConfirmDelete(event.target.value)}
            autoComplete="off"
          />
        </label>
        <button
          type="button"
          className="danger"
          disabled={confirmDelete !== 'SUPPRIMER'}
          onClick={() => void deleteAllData()}
        >
          Supprimer définitivement
        </button>
      </section>
    </main>
  );
}
