import { useAppStore } from '../store';
import { formatAmount } from '../utils';

export function ExitReportView() {
  const report = useAppStore((state) => state.exitReport);
  const sessionId = useAppStore((state) => state.sessionId);
  const setView = useAppStore((state) => state.setView);
  const loadHistory = useAppStore((state) => state.loadHistory);
  if (!report)
    return (
      <main className="empty-page">
        <h1>Aucun bilan de session disponible.</h1>
        <button
          type="button"
          className="primary"
          onClick={() => setView(sessionId ? 'table' : 'configuration')}
        >
          {sessionId ? 'Retour à la table' : 'Nouvelle table'}
        </button>
      </main>
    );
  const duration = Math.max(0, new Date(report.ended_at).getTime() - new Date(report.started_at).getTime());
  const minutes = Math.round(duration / 60_000);
  return (
    <main className="exit-page content-page">
      <section className="exit-hero">
        <span className="result-icon" aria-hidden="true">
          ✓
        </span>
        <p className="eyebrow">Session sauvegardée</p>
        <h1>Bilan de Ryanchl</h1>
        <p>
          {report.hands_played} mains en {minutes} min · toutes les décisions et explications restent
          consultables.
        </p>
        <strong className={report.net_result >= 0 ? 'positive-text' : 'negative-text'}>
          {report.net_result > 0 ? '+' : ''}
          {formatAmount(report.net_result, report.unit, report.big_blind)}{' '}
          <small>
            ({report.net_result_bb > 0 ? '+' : ''}
            {report.net_result_bb.toFixed(2)} BB)
          </small>
        </strong>
      </section>
      <section className="exit-kpis">
        <article>
          <span>Tapis initial</span>
          <strong>{formatAmount(report.initial_stack, report.unit, report.big_blind)}</strong>
        </article>
        <article>
          <span>Tapis final</span>
          <strong>{formatAmount(report.final_stack, report.unit, report.big_blind)}</strong>
        </article>
        <article>
          <span>Décisions</span>
          <strong>{report.decisions}</strong>
        </article>
        <article>
          <span>Suivi du conseil</span>
          <strong>{Math.round(report.advice_follow_rate * 100)} %</strong>
        </article>
      </section>
      <section className="exit-kpis outcome-kpis" aria-label="Résultats des mains">
        <article>
          <span>Mains gagnées</span>
          <strong>{report.hands_won}</strong>
        </article>
        <article>
          <span>Mains perdues</span>
          <strong>{report.hands_lost}</strong>
        </article>
        <article>
          <span>Pots partagés</span>
          <strong>{report.split_pots}</strong>
        </article>
        <article>
          <span>Gains sans showdown</span>
          <strong>{report.wins_without_showdown}</strong>
        </article>
        <article>
          <span>Gains au showdown</span>
          <strong>{report.showdown_wins}</strong>
        </article>
        <article>
          <span>Plus gros pot gagné</span>
          <strong>{formatAmount(report.biggest_pot_won, report.unit, report.big_blind)}</strong>
        </article>
        <article>
          <span>Plus gros pot perdu</span>
          <strong>{formatAmount(report.biggest_pot_lost, report.unit, report.big_blind)}</strong>
        </article>
      </section>
      <div className="exit-grid">
        <section className="panel quality-breakdown">
          <h2>Qualité des décisions</h2>
          <div
            className="quality-ring"
            style={
              {
                '--score': `${report.decisions ? ((report.excellent + report.acceptable) / report.decisions) * 100 : 0}%`,
              } as React.CSSProperties
            }
          >
            <strong>
              {report.decisions
                ? Math.round(((report.excellent + report.acceptable) / report.decisions) * 100)
                : 0}{' '}
              %
            </strong>
            <span>solides</span>
          </div>
          <dl>
            <div>
              <dt>
                <i className="excellent" />
                Excellentes
              </dt>
              <dd>{report.excellent}</dd>
            </div>
            <div>
              <dt>
                <i className="acceptable" />
                Acceptables
              </dt>
              <dd>{report.acceptable}</dd>
            </div>
            <div>
              <dt>
                <i className="mistake" />
                Erreurs
              </dt>
              <dd>{report.mistakes}</dd>
            </div>
          </dl>
        </section>
        <section className="panel street-errors">
          <h2>Erreurs par rue</h2>
          {Object.entries(report.street_mistakes).map(([street, count]) => (
            <div key={street}>
              <span>{street}</span>
              <span className="horizontal-bar">
                <i style={{ width: `${report.mistakes ? (count / report.mistakes) * 100 : 0}%` }} />
              </span>
              <strong>{count}</strong>
            </div>
          ))}
        </section>
        <section className="panel session-insights">
          <h2>Axes de révision</h2>
          <ul>
            {report.insights.map((insight) => (
              <li key={insight}>
                <span>→</span>
                {insight}
              </li>
            ))}
          </ul>
        </section>
      </div>
      <footer className="exit-actions">
        <button
          type="button"
          className="ghost"
          onClick={() => {
            void loadHistory('quality=mistake');
            setView('historique');
          }}
        >
          Revoir les erreurs
        </button>
        <button type="button" className="ghost" onClick={() => setView('historique')}>
          Tous les conseils et explications
        </button>
        <button
          type="button"
          className="primary large"
          onClick={() => {
            localStorage.removeItem('poker-ia-session');
            useAppStore.setState({ sessionId: null, table: null, exitReport: null, view: 'configuration' });
          }}
        >
          Nouvelle session
        </button>
      </footer>
    </main>
  );
}
