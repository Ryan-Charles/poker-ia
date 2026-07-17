import { useState } from 'react';
import type { ViewName } from '../types';
import { useAppStore } from '../store';

const NAVIGATION: Array<{ view: ViewName; label: string; icon: string }> = [
  { view: 'table', label: 'Table', icon: '♠' },
  { view: 'historique', label: 'Historique', icon: '↺' },
  { view: 'adversaires', label: 'Adversaires', icon: '◎' },
  { view: 'parametres', label: 'Données', icon: '⚙' },
];

export function Header() {
  const view = useAppStore((state) => state.view);
  const sessionId = useAppStore((state) => state.sessionId);
  const saveStatus = useAppStore((state) => state.saveStatus);
  const table = useAppStore((state) => state.table);
  const setView = useAppStore((state) => state.setView);
  const saveSession = useAppStore((state) => state.saveSession);
  const exitSession = useAppStore((state) => state.exitSession);
  const [exitConfirmationOpen, setExitConfirmationOpen] = useState(false);
  const handInProgress = Boolean(
    table && ['playing', 'awaiting_cards', 'showdown'].includes(table.hand.phase),
  );

  return (
    <header className="app-header">
      <button type="button" className="brand" onClick={() => setView(sessionId ? 'table' : 'configuration')}>
        <img src="/assets/poker-ia-logo.png" alt="" />
        <span>
          <strong>Poker IA</strong>
          <small>Entraînement local</small>
        </span>
      </button>
      {sessionId ? (
        <>
          <nav aria-label="Navigation principale">
            {NAVIGATION.map((item) => (
              <button
                type="button"
                key={item.view}
                className={view === item.view ? 'active' : ''}
                onClick={() => setView(item.view)}
                aria-current={view === item.view ? 'page' : undefined}
              >
                <span aria-hidden="true">{item.icon}</span>
                {item.label}
              </button>
            ))}
          </nav>
          <div className="header-actions">
            <span className={`save-indicator ${saveStatus}`} aria-live="polite">
              <span aria-hidden="true">●</span>{' '}
              {saveStatus === 'saved'
                ? 'Sauvegardé'
                : saveStatus === 'saving'
                  ? 'Sauvegarde…'
                  : 'À resauvegarder'}
            </span>
            <button type="button" className="ghost" onClick={() => void saveSession()}>
              Sauvegarder
            </button>
            <button
              type="button"
              className="danger-ghost"
              onClick={() => {
                if (handInProgress) setExitConfirmationOpen(true);
                else void exitSession();
              }}
            >
              Sortir de la table
            </button>
          </div>
        </>
      ) : (
        <span className="fictional-badge">100 % jetons fictifs</span>
      )}
      {exitConfirmationOpen ? (
        <div className="drawer-backdrop" role="presentation">
          <section
            className="edit-drawer exit-confirmation"
            role="dialog"
            aria-modal="true"
            aria-labelledby="exit-confirmation-title"
          >
            <header>
              <div>
                <p className="eyebrow">Main en cours</p>
                <h2 id="exit-confirmation-title">Que souhaitez-vous faire ?</h2>
              </div>
              <button
                type="button"
                className="icon-button"
                aria-label="Fermer"
                onClick={() => setExitConfirmationOpen(false)}
              >
                ×
              </button>
            </header>
            <p>
              La session n’est jamais abandonnée silencieusement. Sortir sauvegarde la session, remet la table
              à zéro et vous ramène aux réglages de configuration. Vous pouvez aussi revenir terminer la main.
            </p>
            <footer>
              <button type="button" className="ghost" onClick={() => setExitConfirmationOpen(false)}>
                Annuler
              </button>
              <button
                type="button"
                className="ghost"
                onClick={() => {
                  setExitConfirmationOpen(false);
                  setView('table');
                }}
              >
                Terminer la main
              </button>
              <button
                type="button"
                className="primary"
                onClick={() => {
                  setExitConfirmationOpen(false);
                  void exitSession();
                }}
              >
                Sauvegarder et sortir
              </button>
            </footer>
          </section>
        </div>
      ) : null}
    </header>
  );
}
