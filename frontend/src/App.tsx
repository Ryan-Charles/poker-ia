import { Component, useEffect, useState, type ErrorInfo, type ReactNode } from 'react';
import { api } from './api';
import { Header } from './components/Header';
import { Notification } from './components/Notification';
import { useAppStore } from './store';
import { ConfigurationView } from './views/ConfigurationView';
import { ExitReportView } from './views/ExitReportView';
import { HistoryView } from './views/HistoryView';
import { OpponentsView } from './views/OpponentsView';
import { SettingsView } from './views/SettingsView';
import { TableView } from './views/TableView';

class ErrorBoundary extends Component<{ children: ReactNode }, { failed: boolean }> {
  override state = { failed: false };
  static getDerivedStateFromError() {
    return { failed: true };
  }
  override componentDidCatch(error: Error, info: ErrorInfo) {
    console.error('Erreur d’interface Poker IA', error, info.componentStack);
  }
  override render() {
    if (this.state.failed)
      return (
        <main className="fatal-error">
          <img src="/assets/poker-ia-logo.png" alt="" />
          <h1>L’interface a rencontré un problème.</h1>
          <p>La session locale n’a pas été effacée. Rechargez la fenêtre pour la reprendre.</p>
          <button type="button" className="primary" onClick={() => window.location.reload()}>
            Recharger Poker IA
          </button>
        </main>
      );
    return this.props.children;
  }
}

export default function App() {
  const view = useAppStore((state) => state.view);
  const selectedDecision = useAppStore((state) => state.selectedDecision);
  const closeDecision = useAppStore((state) => state.closeDecision);
  const setNotification = useAppStore((state) => state.setNotification);
  const [engineOnline, setEngineOnline] = useState<boolean | null>(null);

  useEffect(() => {
    void api
      .health()
      .then(() => setEngineOnline(true))
      .catch(() => setEngineOnline(false));
  }, []);

  useEffect(() => {
    const escape = (event: KeyboardEvent) => {
      if (event.key !== 'Escape') return;
      if (selectedDecision) closeDecision();
      else setNotification(null);
    };
    window.addEventListener('keydown', escape);
    return () => window.removeEventListener('keydown', escape);
  }, [closeDecision, selectedDecision, setNotification]);

  return (
    <ErrorBoundary>
      <div className="app-shell">
        <Header />
        {engineOnline === false ? (
          <div className="engine-offline" role="alert">
            <span>!</span> Le moteur local est hors ligne. Démarrez Poker IA pour créer ou reprendre une
            session.
          </div>
        ) : null}
        {view === 'configuration' ? <ConfigurationView /> : null}
        {view === 'table' ? <TableView /> : null}
        {view === 'historique' ? <HistoryView /> : null}
        {view === 'adversaires' ? <OpponentsView /> : null}
        {view === 'parametres' ? <SettingsView /> : null}
        {view === 'bilan' ? <ExitReportView /> : null}
        <Notification />
      </div>
    </ErrorBoundary>
  );
}
