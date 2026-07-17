import { useMemo, useState } from 'react';
import { CardView } from '../components/CardView';
import { api } from '../api';
import { useAppStore } from '../store';
import { STREET_LABELS, type HistoryDecision, type Street } from '../types';
import { downloadBlob, formatAmount } from '../utils';

type QualityFilter = 'all' | HistoryDecision['quality'];
type ResultFilter = 'all' | 'won' | 'lost';
type SortKey = 'date' | 'ev' | 'result' | 'confidence' | 'importance';

const QUALITY_LABELS = {
  excellent: 'Excellente',
  acceptable: 'Acceptable',
  questionable: 'Discutable',
  mistake: 'Erreur',
} as const;

export function DecisionDrawer() {
  const detail = useAppStore((state) => state.selectedDecision);
  const close = useAppStore((state) => state.closeDecision);
  const runExpert = useAppStore((state) => state.runExpertAnalysis);
  const cancelExpert = useAppStore((state) => state.cancelExpertAnalysis);
  const analysisBusy = useAppStore((state) => state.analysisBusy);
  const [replaySelection, setReplaySelection] = useState({ decisionId: '', step: 0 });
  if (!detail) return null;
  const replaySteps = detail.replay_steps;
  const step =
    replaySelection.decisionId === detail.id ? replaySelection.step : Math.max(0, replaySteps.length - 1);
  const setStep = (nextStep: number) => setReplaySelection({ decisionId: detail.id, step: nextStep });
  const safeStep = Math.min(step, Math.max(0, replaySteps.length - 1));
  const currentReplay = replaySteps[safeStep];
  const replayTable = currentReplay?.table_state ?? detail.table_state;
  const nextActor = replayTable.players.find((player) => player.id === replayTable.hand.active_player_id);
  return (
    <div
      className="drawer-backdrop"
      role="presentation"
      onMouseDown={(event) => event.currentTarget === event.target && close()}
    >
      <aside className="analysis-drawer" role="dialog" aria-modal="true" aria-labelledby="decision-title">
        <header>
          <div>
            <p className="eyebrow">
              Main #{detail.hand_number} · {STREET_LABELS[detail.street]}
            </p>
            <h2 id="decision-title">Analyse de la décision</h2>
          </div>
          <button type="button" className="icon-button" onClick={close} aria-label="Fermer">
            ×
          </button>
        </header>
        <div className="decision-verdict">
          <span className={`quality ${detail.quality}`}>{QUALITY_LABELS[detail.quality]}</span>
          <div>
            <small>Action choisie</small>
            <strong>{detail.chosen_action}</strong>
          </div>
          <div>
            <small>Conseil final</small>
            <strong>{detail.final_advice}</strong>
          </div>
          <div>
            <small>Écart d’EV</small>
            <strong>{detail.ev_difference.toFixed(2)}</strong>
          </div>
          <div>
            <small>Résultat réel</small>
            <strong>
              {detail.real_result > 0 ? '+' : ''}
              {detail.real_result}
            </strong>
          </div>
        </div>
        <section className="known-information">
          <h3>Informations connues à cet instant</h3>
          <div className="known-card-row">
            {(currentReplay?.known_cards ?? detail.known_cards).map((card) => (
              <CardView key={card} card={card} compact />
            ))}
          </div>
          <p>Les cartes adverses révélées plus tard ne sont pas réinjectées dans cette vue de la décision.</p>
        </section>
        <section className="replay-section">
          <div className="subheading-row">
            <div>
              <h3>Relecture action par action</h3>
              <p>État reconstruit depuis le journal d’événements, sans information future.</p>
            </div>
            <output>
              {safeStep + 1} / {Math.max(1, replaySteps.length)}
            </output>
          </div>
          <input
            type="range"
            min="0"
            max={Math.max(0, replaySteps.length - 1)}
            value={safeStep}
            disabled={replaySteps.length < 2}
            onChange={(event) => setStep(Number(event.target.value))}
            aria-label="Étape de relecture"
          />
          {currentReplay ? (
            <div className="replay-current">
              <strong>{currentReplay.label}</strong>
              <span>{currentReplay.actor_name ?? 'État initial de la main'}</span>
              <small>
                Pot : {formatAmount(currentReplay.pot, detail.unit, detail.big_blind)} · Transition :{' '}
                {nextActor ? `tour de ${nextActor.name}` : replayTable.hand.phase}
              </small>
            </div>
          ) : (
            <p>Aucun état antérieur enregistré.</p>
          )}
          <div className="replay-table-state" aria-label="État de la table à cette étape">
            <div className="replay-board">
              <small>{STREET_LABELS[replayTable.hand.street]} · Board connu</small>
              <div className="known-card-row">
                {replayTable.hand.board.length ? (
                  replayTable.hand.board.map((card) => <CardView key={card} card={card} compact />)
                ) : (
                  <span>Aucune carte commune</span>
                )}
              </div>
              <strong>Pot {formatAmount(replayTable.hand.pot, detail.unit, detail.big_blind)}</strong>
            </div>
            <div className="replay-players">
              {replayTable.players.map((player) => (
                <article
                  key={player.id}
                  className={player.id === replayTable.hand.active_player_id ? 'active' : ''}
                >
                  <span>
                    <strong>{player.name}</strong>
                    <small>{player.position}</small>
                  </span>
                  {player.id === 'hero' ? (
                    <div className="mini-cards">
                      {replayTable.hand.hero_cards.map((card) => (
                        <CardView card={card} compact key={card} />
                      ))}
                    </div>
                  ) : null}
                  <span>
                    <small>Tapis</small>
                    <b>{formatAmount(player.stack, detail.unit, detail.big_blind)}</b>
                  </span>
                  <span>
                    <small>Engagé</small>
                    <b>{formatAmount(player.total_contribution, detail.unit, detail.big_blind)}</b>
                  </span>
                  <em>{player.status}</em>
                </article>
              ))}
            </div>
          </div>
          {currentReplay?.advice ? (
            <div className="replay-advice">
              <strong>Conseil disponible à cette étape</strong>
              <span>Équilibré : {currentReplay.advice.balanced}</span>
              <span>Exploitant : {currentReplay.advice.exploitative}</span>
              <span>
                Final : {currentReplay.advice.final}
                {currentReplay.advice.recommended_amount !== undefined
                  ? ` à ${formatAmount(currentReplay.advice.recommended_amount, detail.unit, detail.big_blind)}`
                  : ''}
              </span>
            </div>
          ) : (
            <p className="replay-no-advice">Aucun conseil Ryanchl n’était associé à cette étape.</p>
          )}
          <ol className="replay-log">
            {replaySteps.map((replay, index) => (
              <li key={replay.cursor} className={index === safeStep ? 'active' : ''}>
                <button type="button" onClick={() => setStep(index)}>
                  <span>{index + 1}</span>
                  <strong>{replay.label}</strong>
                  <small>{formatAmount(replay.pot, detail.unit, detail.big_blind)}</small>
                </button>
              </li>
            ))}
          </ol>
        </section>
        <section>
          <h3>Indicateurs utilisés</h3>
          <div className="strategy-metrics detail-metrics">
            <span>
              <small>Pot odds</small>
              <strong>{(detail.pot_odds * 100).toFixed(1)} %</strong>
            </span>
            <span>
              <small>Équité</small>
              <strong>{(detail.equity * 100).toFixed(1)} %</strong>
            </span>
            <span>
              <small>SPR</small>
              <strong>{detail.spr.toFixed(2)}</strong>
            </span>
            {Object.entries(detail.statistics_used).map(([label, value]) => (
              <span key={label}>
                <small>{label}</small>
                <strong>{value.toFixed(2)}</strong>
              </span>
            ))}
          </div>
        </section>
        <section className="ev-comparison">
          <h3>EV estimée des actions légales</h3>
          {detail.action_evs.map((action) => (
            <div key={`${action.action}-${action.amount ?? 0}`}>
              <strong>{action.label}</strong>
              <span>{action.amount ?? '—'}</span>
              <meter min={-10} max={10} value={action.ev ?? 0} />
              <b>{action.ev?.toFixed(2) ?? 'n.d.'}</b>
            </div>
          ))}
        </section>
        <section className="range-estimates">
          <h3>Ranges adverses estimées</h3>
          {Object.entries(detail.estimated_ranges).map(([player, ranges]) => (
            <div key={player}>
              <strong>{player}</strong>
              <p>{ranges.join(' · ')}</p>
            </div>
          ))}
        </section>
        <section className="detailed-explanation">
          <h3>Explication détaillée</h3>
          <p>{detail.detailed_explanation}</p>
          <h4>Limites</h4>
          <ul>
            {detail.limitations.map((limitation) => (
              <li key={limitation}>{limitation}</li>
            ))}
          </ul>
        </section>
        <footer>
          {analysisBusy ? (
            <button type="button" className="danger-ghost" onClick={cancelExpert}>
              Annuler l’analyse
            </button>
          ) : (
            <button type="button" className="primary" onClick={() => void runExpert(detail.id)}>
              Lancer une analyse experte
            </button>
          )}
          <span>
            {analysisBusy
              ? 'Calcul backend en cours ; les autres écrans restent utilisables.'
              : 'L’analyse approfondie est calculée après la main.'}
          </span>
        </footer>
      </aside>
    </div>
  );
}

export function HistoryView() {
  const history = useAppStore((state) => state.history);
  const opponents = useAppStore((state) => state.opponents);
  const openDecision = useAppStore((state) => state.openDecision);
  const analysisBusy = useAppStore((state) => state.analysisBusy);
  const setNotification = useAppStore((state) => state.setNotification);
  const loadOpponents = useAppStore((state) => state.loadOpponents);
  const [street, setStreet] = useState<'all' | Street>('all');
  const [quality, setQuality] = useState<QualityFilter>('all');
  const [result, setResult] = useState<ResultFilter>('all');
  const [position, setPosition] = useState('all');
  const [opponent, setOpponent] = useState('all');
  const [depth, setDepth] = useState('all');
  const [sort, setSort] = useState<SortKey>('date');
  const [visibleCount, setVisibleCount] = useState(200);

  useMemo(() => {
    if (!opponents.length) void loadOpponents();
  }, [loadOpponents, opponents.length]);

  const positions = [...new Set(history.map((item) => item.position))];
  const filtered = useMemo(() => {
    const resultItems = history.filter((item) => {
      if (street !== 'all' && item.street !== street) return false;
      if (quality !== 'all' && item.quality !== quality) return false;
      if (result === 'won' && item.hand_result <= 0) return false;
      if (result === 'lost' && item.hand_result >= 0) return false;
      if (position !== 'all' && item.position !== position) return false;
      if (opponent !== 'all' && !item.opponent_ids.includes(opponent)) return false;
      if (depth === 'short' && item.effective_stack_bb >= 40) return false;
      if (depth === 'medium' && (item.effective_stack_bb < 40 || item.effective_stack_bb > 100)) return false;
      if (depth === 'deep' && item.effective_stack_bb <= 100) return false;
      return true;
    });
    return resultItems.sort((a, b) => {
      if (sort === 'date') return new Date(b.date).getTime() - new Date(a.date).getTime();
      if (sort === 'ev') return b.ev_difference - a.ev_difference;
      if (sort === 'result') return Math.abs(b.hand_result) - Math.abs(a.hand_result);
      if (sort === 'confidence') return b.confidence - a.confidence;
      return Math.abs(b.ev_difference) - Math.abs(a.ev_difference);
    });
  }, [depth, history, opponent, position, quality, result, sort, street]);

  const summary = useMemo(() => {
    const resultByHand = new Map<string, number>();
    history.forEach((item) => resultByHand.set(item.hand_id, item.hand_result));
    return {
      total: history.length,
      aligned: history.filter((item) => item.quality === 'excellent').length,
      acceptable: history.filter((item) => item.quality === 'acceptable').length,
      mistakes: history.filter((item) => ['questionable', 'mistake'].includes(item.quality)).length,
      net: [...resultByHand.values()].reduce((sum, resultValue) => sum + resultValue, 0),
      unit: history[0]?.unit ?? 'chips',
      bigBlind: history[0]?.big_blind ?? 100,
    };
  }, [history]);
  const visibleDecisions = filtered.slice(0, visibleCount);

  return (
    <main className="history-page content-page">
      <header className="page-heading">
        <div>
          <p className="eyebrow">Apprentissage de Ryanchl</p>
          <h1>Historique des décisions</h1>
          <p>La qualité stratégique reste séparée du résultat fictif de la main.</p>
        </div>
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
          Exporter en CSV
        </button>
      </header>
      <section className="history-kpis">
        <span>
          <small>Décisions</small>
          <strong>{summary.total}</strong>
        </span>
        <span>
          <small>Identiques au conseil</small>
          <strong>{summary.aligned}</strong>
        </span>
        <span>
          <small>Acceptables</small>
          <strong>{summary.acceptable}</strong>
        </span>
        <span>
          <small>Erreurs</small>
          <strong>{summary.mistakes}</strong>
        </span>
        <span>
          <small>Résultat fictif</small>
          <strong className={summary.net >= 0 ? 'positive-text' : 'negative-text'}>
            {summary.net > 0 ? '+' : ''}
            {formatAmount(summary.net, summary.unit, summary.bigBlind)}
          </strong>
        </span>
      </section>
      <section className="history-filters panel" aria-label="Filtres de l’historique">
        <label>
          <span>Rue</span>
          <select value={street} onChange={(event) => setStreet(event.target.value as 'all' | Street)}>
            <option value="all">Toutes</option>
            <option value="preflop">Préflop</option>
            <option value="flop">Flop</option>
            <option value="turn">Turn</option>
            <option value="river">River</option>
          </select>
        </label>
        <label>
          <span>Qualité</span>
          <select value={quality} onChange={(event) => setQuality(event.target.value as QualityFilter)}>
            <option value="all">Toutes</option>
            <option value="excellent">Bonne décision</option>
            <option value="acceptable">Acceptable</option>
            <option value="questionable">Discutable</option>
            <option value="mistake">Erreur</option>
          </select>
        </label>
        <label>
          <span>Résultat</span>
          <select value={result} onChange={(event) => setResult(event.target.value as ResultFilter)}>
            <option value="all">Tous</option>
            <option value="won">Main gagnée</option>
            <option value="lost">Main perdue</option>
          </select>
        </label>
        <label>
          <span>Position</span>
          <select value={position} onChange={(event) => setPosition(event.target.value)}>
            <option value="all">Toutes</option>
            {positions.map((item) => (
              <option value={item} key={item}>
                {item}
              </option>
            ))}
          </select>
        </label>
        <label>
          <span>Adversaire</span>
          <select value={opponent} onChange={(event) => setOpponent(event.target.value)}>
            <option value="all">Tous</option>
            {opponents.map((item) => (
              <option value={item.id} key={item.id}>
                {item.name}
              </option>
            ))}
          </select>
        </label>
        <label>
          <span>Profondeur</span>
          <select value={depth} onChange={(event) => setDepth(event.target.value)}>
            <option value="all">Toutes</option>
            <option value="short">Moins de 40 BB</option>
            <option value="medium">40 à 100 BB</option>
            <option value="deep">Plus de 100 BB</option>
          </select>
        </label>
        <label>
          <span>Trier par</span>
          <select value={sort} onChange={(event) => setSort(event.target.value as SortKey)}>
            <option value="date">Date</option>
            <option value="ev">Différence d’EV</option>
            <option value="result">Gain ou perte</option>
            <option value="confidence">Confiance</option>
            <option value="importance">Importance de l’erreur</option>
          </select>
        </label>
      </section>
      <section className="history-list panel">
        <div className="history-list-heading">
          <strong>
            {filtered.length} décision{filtered.length > 1 ? 's' : ''}
          </strong>
          <span>Cliquez une ligne pour l’analyse complète</span>
        </div>
        {filtered.length ? (
          <div className="history-table-wrap">
            <table>
              <thead>
                <tr>
                  <th>Main / date</th>
                  <th>Situation</th>
                  <th>Cartes connues</th>
                  <th>Conseil final</th>
                  <th>Choix</th>
                  <th>Qualité / EV</th>
                  <th>Résultat</th>
                </tr>
              </thead>
              <tbody>
                {visibleDecisions.map((decision) => (
                  <tr
                    key={decision.id}
                    tabIndex={0}
                    onClick={() => void openDecision(decision.id)}
                    onKeyDown={(event) => event.key === 'Enter' && void openDecision(decision.id)}
                  >
                    <td>
                      <strong>#{decision.hand_number}</strong>
                      <small>
                        {new Intl.DateTimeFormat('fr-FR', { dateStyle: 'short', timeStyle: 'short' }).format(
                          new Date(decision.date),
                        )}
                      </small>
                    </td>
                    <td>
                      <strong>
                        {STREET_LABELS[decision.street]} · {decision.position}
                      </strong>
                      <small>
                        {decision.effective_stack_bb.toFixed(0)} BB · {decision.preceding_action}
                      </small>
                    </td>
                    <td>
                      <div className="mini-cards">
                        {decision.hero_cards.map((card) => (
                          <CardView card={card} compact key={card} />
                        ))}
                        <span>·</span>
                        {decision.board.map((card) => (
                          <CardView card={card} compact key={card} />
                        ))}
                      </div>
                    </td>
                    <td>
                      <strong>{decision.final_advice}</strong>
                      <small>{decision.short_explanation}</small>
                    </td>
                    <td>{decision.chosen_action}</td>
                    <td>
                      <span className={`quality ${decision.quality}`}>
                        {QUALITY_LABELS[decision.quality]}
                      </span>
                      <small>EV {decision.ev_difference.toFixed(2)}</small>
                    </td>
                    <td>
                      <strong className={decision.hand_result >= 0 ? 'positive-text' : 'negative-text'}>
                        {decision.hand_result > 0 ? '+' : ''}
                        {formatAmount(decision.hand_result, decision.unit, decision.big_blind)}
                      </strong>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
            {visibleDecisions.length < filtered.length ? (
              <button
                type="button"
                className="ghost history-load-more"
                onClick={() => setVisibleCount((count) => count + 200)}
              >
                Afficher 200 décisions supplémentaires ({filtered.length - visibleDecisions.length} restantes)
              </button>
            ) : null}
          </div>
        ) : (
          <div className="empty-state">
            <span aria-hidden="true">↺</span>
            <h2>Aucune décision pour ces filtres</h2>
            <p>Modifiez les filtres ou jouez une main pour enrichir l’historique.</p>
          </div>
        )}
      </section>
      {analysisBusy && !useAppStore.getState().selectedDecision ? (
        <div className="full-loading">
          <span className="spinner" /> Chargement de l’analyse…
        </div>
      ) : null}
      <DecisionDrawer />
    </main>
  );
}
