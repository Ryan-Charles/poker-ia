import { useAppStore } from '../store';
import { STREET_LABELS, type ExitReport, type Street } from '../types';
import { formatAmount } from '../utils';

function downloadCoachReport(report: ExitReport) {
  const coach = report.coach;
  const lines = [
    '# Poker IA — Coach de session',
    '',
    `Score de décision : ${coach.session_score}/100`,
    `Décisions analysées : ${coach.decisions_reviewed}`,
    `Écart d’EV cumulé : ${coach.total_ev_loss_bb.toFixed(2)} BB`,
    `Confiance moyenne : ${Math.round(coach.average_confidence * 100)} %`,
    '',
    '## Diagnostic',
    coach.summary,
    '',
    '## Points forts',
    ...coach.strengths.map((strength) => `- ${strength}`),
    '',
    '## Décisions prioritaires',
    ...(coach.top_decisions.length
      ? coach.top_decisions.map(
          (decision) =>
            `- Main #${decision.hand_number}, ${STREET_LABELS[decision.street]} : ${decision.chosen_action} → ${decision.recommended_action} (${decision.ev_loss_bb.toFixed(2)} BB)`,
        )
      : ['- Aucune décision fortement coûteuse détectée.']),
    '',
    '## Plan d’entraînement',
    ...coach.learning_plan.flatMap((item, index) => [
      `${index + 1}. ${item.title}`,
      `   Pourquoi : ${item.reason}`,
      `   Exercice : ${item.drill}`,
    ]),
    '',
    '## Méthode',
    coach.methodology,
    '',
    'Poker IA est un outil local d’entraînement. Les estimations ne garantissent aucun résultat futur.',
  ];
  const blob = new Blob([lines.join('\n')], { type: 'text/markdown;charset=utf-8' });
  const url = URL.createObjectURL(blob);
  const link = document.createElement('a');
  link.href = url;
  link.download = `poker-ia-coach-${report.session_id}.md`;
  link.click();
  URL.revokeObjectURL(url);
}

export function ExitReportView() {
  const report = useAppStore((state) => state.exitReport);
  const sessionId = useAppStore((state) => state.sessionId);
  const setView = useAppStore((state) => state.setView);
  const loadHistory = useAppStore((state) => state.loadHistory);
  const openDecision = useAppStore((state) => state.openDecision);
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
      <section className="panel session-coach" aria-labelledby="session-coach-title">
        <header className="coach-heading">
          <div>
            <p className="eyebrow">Nouveau · Coach de session</p>
            <h2 id="session-coach-title">Un plan concret pour la prochaine table</h2>
            <p>{report.coach.summary}</p>
          </div>
          <div className="coach-score" aria-label={`Score de décision ${report.coach.session_score} sur 100`}>
            <strong>{report.coach.session_score}</strong>
            <span>/100</span>
          </div>
        </header>
        <div className="coach-metrics" aria-label="Mesures du coach">
          <article>
            <span>Écart d’EV cumulé</span>
            <strong>{report.coach.total_ev_loss_bb.toFixed(2)} BB</strong>
          </article>
          <article>
            <span>Confiance moyenne</span>
            <strong>{Math.round(report.coach.average_confidence * 100)} %</strong>
          </article>
          <article>
            <span>Décisions analysées</span>
            <strong>{report.coach.decisions_reviewed}</strong>
          </article>
        </div>
        <div className="coach-layout">
          <section className="coach-priorities" aria-labelledby="coach-priorities-title">
            <h3 id="coach-priorities-title">Décisions prioritaires</h3>
            {report.coach.top_decisions.length ? (
              <ol>
                {report.coach.top_decisions.map((decision) => (
                  <li key={decision.id}>
                    <button
                      type="button"
                      onClick={() => {
                        setView('historique');
                        void openDecision(decision.id);
                      }}
                    >
                      <span>
                        Main #{decision.hand_number} · {STREET_LABELS[decision.street]}
                      </span>
                      <strong>{decision.ev_loss_bb.toFixed(2)} BB</strong>
                      <small>
                        {decision.chosen_action} → {decision.recommended_action} · confiance{' '}
                        {Math.round(decision.confidence * 100)} %
                      </small>
                    </button>
                  </li>
                ))}
              </ol>
            ) : (
              <p className="coach-empty">Aucune décision fortement coûteuse détectée.</p>
            )}
          </section>
          <section className="coach-plan" aria-labelledby="coach-plan-title">
            <h3 id="coach-plan-title">Plan d’entraînement</h3>
            <ol>
              {report.coach.learning_plan.map((item, index) => (
                <li key={item.title}>
                  <span>{index + 1}</span>
                  <div>
                    <strong>{item.title}</strong>
                    <p>{item.reason}</p>
                    <small>{item.drill}</small>
                  </div>
                </li>
              ))}
            </ol>
          </section>
        </div>
        <div className="coach-strengths" aria-label="Points forts">
          {report.coach.strengths.map((strength) => (
            <span key={strength}>✓ {strength}</span>
          ))}
        </div>
        <footer className="coach-footer">
          <p>
            {report.coach.methodology} Poker IA reste un outil local d’entraînement : aucune estimation ne
            garantit un résultat futur.
          </p>
          <button type="button" className="ghost" onClick={() => downloadCoachReport(report)}>
            Exporter le bilan du coach
          </button>
        </footer>
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
              <span>{STREET_LABELS[street as Street] ?? street}</span>
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
