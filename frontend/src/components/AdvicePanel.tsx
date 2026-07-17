import { useEffect } from 'react';
import { useAppStore } from '../store';
import {
  ACTION_LABELS,
  STREET_LABELS,
  type AdviceOption,
  type AdviceSection,
  type LegalActionName,
  type Unit,
} from '../types';
import { formatAmount } from '../utils';
import { CardView } from './CardView';

const TAB_LABELS = {
  balanced: 'Équilibré',
  exploitative: 'Exploitant',
  final: 'Conseil final',
} as const;

const TAB_HINTS = {
  balanced: 'Théorie pure : la stratégie équilibrée de référence, sans s’adapter aux adversaires.',
  exploitative: 'Ajusté : exploite les habitudes observées chez vos adversaires à cette table.',
  final: 'Le verdict : synthèse des deux, c’est le conseil à suivre.',
} as const;

function optionLabel(option: AdviceOption, unit: Unit, bigBlind: number): string {
  return option.amount !== undefined
    ? `${option.label} à ${formatAmount(option.amount, unit, bigBlind)}`
    : option.label;
}

/**
 * Classe de couleur reprenant exactement la palette des boutons du dock
 * d'actions : fold en rouge, check/call en bleu, bet/raise/all_in en vert.
 * Le conseil affiche ainsi visuellement quelle famille de bouton suivre.
 */
function actionColorClass(action: LegalActionName): string {
  if (action === 'fold') return 'advice-color-fold';
  if (action === 'check' || action === 'call') return 'advice-color-call';
  return 'advice-color-raise';
}

function AdviceContent({ section, sameAdvice }: { section: AdviceSection; sameAdvice: boolean }) {
  const table = useAppStore((state) => state.table);
  const unit = table?.hand.unit ?? 'chips';
  const bigBlind = table?.hand.big_blind ?? 100;
  const visibleOptions = section.options.filter((option) => Math.round((option.frequency ?? 0) * 100) > 0);
  const certainty = section.is_exact
    ? 'Table précalculée exacte pour cette abstraction'
    : 'Estimation approchée';
  return (
    <div className="advice-content">
      <div className={`advice-headline ${actionColorClass(section.action)}`}>
        <span className="recommended-icon" aria-hidden="true">
          ◎
        </span>
        <div>
          <small>Action à meilleure EV estimée</small>
          <h3>
            {ACTION_LABELS[section.action]}
            {section.amount !== undefined ? ` à ${formatAmount(section.amount, unit, bigBlind)}` : ''}
          </h3>
          <p>{section.headline}</p>
        </div>
        <div className="confidence-score">
          <strong>{Math.round(section.confidence * 100)} %</strong>
          <span>confiance</span>
        </div>
      </div>
      {sameAdvice ? (
        <p className="advice-agreement-note">
          Les trois stratégies tombent d’accord ici : même action recommandée.
        </p>
      ) : null}
      <div
        className="source-badge"
        title="Une simulation ou abstraction n’est jamais présentée comme une certitude mathématique."
      >
        <span className={section.is_exact ? 'exact' : 'approximate'}>
          {section.is_exact ? 'Exact dans le tableau' : 'Approximatif'}
        </span>
        {certainty} · source{' '}
        {section.source === 'precomputed'
          ? 'table préflop'
          : section.source === 'simulation'
            ? 'Monte-Carlo'
            : section.source === 'solver'
              ? 'solveur local'
              : 'modèle adverse'}
      </div>
      {visibleOptions.length ? (
        <div className="mixed-strategy">
          <span>Mix recommandé</span>
          <div className="mix-bar">
            {visibleOptions.map((option, index) => (
              <i
                key={`${option.action}-${index}`}
                className={`mix-${option.action}`}
                style={{ width: `${Math.max(2, (option.frequency ?? 0) * 100)}%` }}
                title={`${optionLabel(option, unit, bigBlind)} : ${Math.round((option.frequency ?? 0) * 100)} %${option.ev === undefined ? '' : ` · EV ${option.ev.toFixed(2)}`}`}
              />
            ))}
          </div>
          <div className="mix-legend">
            {visibleOptions.map((option, index) => (
              <span key={`${option.action}-${index}`}>
                <i className={`mix-${option.action}`} /> {optionLabel(option, unit, bigBlind)} ·{' '}
                {Math.round((option.frequency ?? 0) * 100)} %
              </span>
            ))}
          </div>
        </div>
      ) : null}
      {section.explanation ? <p className="advice-explanation">{section.explanation}</p> : null}
    </div>
  );
}

export function AdvicePanel() {
  const table = useAppStore((state) => state.table);
  const advice = useAppStore((state) => state.advice);
  const tab = useAppStore((state) => state.adviceTab);
  const setTab = useAppStore((state) => state.setAdviceTab);
  const config = useAppStore((state) => state.config);
  const quizRevealed = useAppStore((state) => state.quizRevealed);
  const fetchAdvice = useAppStore((state) => state.fetchAdvice);
  if (!table || table.hand.active_player_id !== 'hero') return null;
  const hiddenForQuiz = config.advice_mode === 'quiz' && !quizRevealed;
  // Les trois onglets fonctionnent déjà, mais recommandent souvent la même
  // action : sans cette détection, l'utilisateur croit que le clic ne fait
  // rien. On compare action ET montant (undefined === undefined pour les
  // actions sans montant, ex. fold/check).
  const sameAdvice = Boolean(
    advice &&
    advice.balanced.action === advice.exploitative.action &&
    advice.exploitative.action === advice.final.action &&
    advice.balanced.amount === advice.exploitative.amount &&
    advice.exploitative.amount === advice.final.amount,
  );
  return (
    <section className="advice-panel panel" aria-label="Conseil stratégique">
      <header className="panel-heading">
        <div>
          <p className="eyebrow">Assistant stratégique</p>
          <h2>{hiddenForQuiz ? 'À vous de décider' : 'Conseil pour Ryanchl'}</h2>
        </div>
        {!hiddenForQuiz ? (
          <button type="button" className="ghost small" onClick={() => void fetchAdvice(true)}>
            Recalculer
          </button>
        ) : (
          <span className="quiz-badge">Mode quiz</span>
        )}
      </header>
      {hiddenForQuiz ? (
        <div className="quiz-cover">
          <span aria-hidden="true">?</span>
          <h3>Choisissez votre action avant de voir l’analyse.</h3>
          <p>
            La recommandation est déjà calculée, mais reste masquée. Après votre choix, l’écart d’EV et la
            note apparaîtront dans l’historique.
          </p>
        </div>
      ) : !advice ? (
        <div className="advice-loading" role="status">
          <span className="spinner" />
          <div>
            <strong>Calcul rapide en cours…</strong>
            <p>Les actions restent entièrement utilisables.</p>
          </div>
        </div>
      ) : (
        <>
          <div className="advice-tabs" role="tablist" aria-label="Type de stratégie">
            {(Object.keys(TAB_LABELS) as Array<keyof typeof TAB_LABELS>).map((name) => (
              <button
                type="button"
                role="tab"
                aria-selected={tab === name}
                className={tab === name ? 'active' : ''}
                key={name}
                title={TAB_HINTS[name]}
                onClick={() => setTab(name)}
              >
                {TAB_LABELS[name]}
              </button>
            ))}
          </div>
          <p className="advice-tab-hint">{TAB_HINTS[tab]}</p>
          <AdviceContent section={advice[tab]} sameAdvice={sameAdvice} />
          <div className="strategy-metrics">
            <span>
              <small>Pot odds</small>
              <strong>{(advice.pot_odds * 100).toFixed(1)} %</strong>
            </span>
            <span>
              <small>Équité min.</small>
              <strong>{(advice.minimum_equity * 100).toFixed(1)} %</strong>
            </span>
            <span>
              <small>Équité estimée</small>
              <strong>{(advice.estimated_equity * 100).toFixed(1)} %</strong>
            </span>
            <span>
              <small>SPR</small>
              <strong>{advice.spr.toFixed(2)}</strong>
            </span>
            <span>
              <small>Tapis effectif</small>
              <strong>{formatAmount(advice.effective_stack, table.hand.unit, table.hand.big_blind)}</strong>
            </span>
          </div>
          <p className="robust-advice">
            <strong>Action robuste :</strong> {advice.robust_action.label}. Elle limite le risque
            d’exploitation lorsque le modèle adverse est incertain.
          </p>
          {advice.explanation_pending ? (
            <p className="explanation-pending">
              <span className="spinner" /> L’explication détaillée arrive sans bloquer votre action.
            </p>
          ) : null}
          <details className="limitations">
            <summary>Limites du calcul</summary>
            <ul>
              {advice.limitations.map((limitation) => (
                <li key={limitation}>{limitation}</li>
              ))}
            </ul>
          </details>
        </>
      )}
    </section>
  );
}

export function AdviceHistoryPanel() {
  const table = useAppStore((state) => state.table);
  const open = useAppStore((state) => state.adviceHistoryOpen);
  const setOpen = useAppStore((state) => state.setAdviceHistoryOpen);
  const history = useAppStore((state) => state.history);
  const loadHistory = useAppStore((state) => state.loadHistory);
  const openDecision = useAppStore((state) => state.openDecision);
  useEffect(() => {
    if (table?.session_id) void loadHistory(`session_id=${encodeURIComponent(table.session_id)}`);
  }, [loadHistory, table?.session_id]);
  if (!table) return null;
  const allDecisions = [...history].sort((left, right) => +new Date(left.date) - +new Date(right.date));
  const decisions = allDecisions.slice(-100);
  return (
    <section className={`live-history panel ${open ? 'open' : ''}`}>
      <button
        type="button"
        className="live-history-toggle"
        onClick={() => setOpen(!open)}
        aria-expanded={open}
      >
        <span>
          <strong>Historique des conseils</strong>
          <small>
            {allDecisions.length} conseil{allDecisions.length > 1 ? 's' : ''} dans la session
          </small>
        </span>
        <kbd>H</kbd>
        <span aria-hidden="true">{open ? '⌄' : '⌃'}</span>
      </button>
      {open ? (
        <div className="live-history-content">
          {allDecisions.length > decisions.length ? (
            <p className="live-history-limit">
              Les 100 conseils les plus récents sont affichés ici ; l’historique complet reste disponible.
            </p>
          ) : null}
          {decisions.length ? (
            decisions.map((decision) => (
              <button
                type="button"
                className="live-history-item"
                key={decision.id}
                onClick={() => void openDecision(decision.id)}
                aria-label={`Ouvrir le détail du conseil de la main ${decision.hand_number}, ${STREET_LABELS[decision.street]}`}
              >
                <span className="timeline-dot" />
                <div className="live-history-item-heading">
                  <span>
                    <small>
                      Main #{decision.hand_number} · {STREET_LABELS[decision.street]} · {decision.position}
                    </small>
                    <strong>
                      {decision.final_advice}
                      {decision.recommended_amount !== undefined
                        ? ` · ${formatAmount(decision.recommended_amount, decision.unit, decision.big_blind)}`
                        : ''}
                    </strong>
                  </span>
                  <span className={`quality ${decision.quality}`}>
                    {Math.round(decision.confidence * 100)} %
                  </span>
                </div>
                <div className="mini-cards" aria-label="Cartes connues de Ryanchl">
                  {decision.hero_cards.map((card) => (
                    <CardView card={card} compact key={card} />
                  ))}
                  {decision.board.length ? <span>·</span> : null}
                  {decision.board.map((card) => (
                    <CardView card={card} compact key={card} />
                  ))}
                </div>
                <dl>
                  <div>
                    <dt>Choix</dt>
                    <dd>{decision.chosen_action}</dd>
                  </div>
                  <div>
                    <dt>Résultat</dt>
                    <dd>
                      {decision.chosen_action === 'Non renseignée'
                        ? 'En attente du choix'
                        : table.hand.id === decision.hand_id &&
                            !['summary', 'ended'].includes(table.hand.phase)
                          ? 'En attente de la fin'
                          : formatAmount(decision.hand_result, decision.unit, decision.big_blind)}
                    </dd>
                  </div>
                </dl>
                <p>{decision.short_explanation}</p>
                <small className="open-detail">Ouvrir le détail sans recalcul →</small>
              </button>
            ))
          ) : (
            <p className="empty-state">Le premier conseil sera conservé dès l’action de Ryanchl.</p>
          )}
        </div>
      ) : null}
    </section>
  );
}

const QUIZ_QUALITY_LABELS = {
  excellent: 'Excellente',
  acceptable: 'Acceptable',
  questionable: 'Discutable',
  mistake: 'Mauvaise',
} as const;

export function QuizResultPanel() {
  const table = useAppStore((state) => state.table);
  const result = useAppStore((state) => state.lastQuizResult);
  const dismiss = useAppStore((state) => state.dismissQuizResult);
  if (!table || !result || result.handId !== table.hand.id) return null;
  const finalResult = table.hand.summary?.hero_net;
  const sameAction = result.chosenAction === result.recommendedAction;
  return (
    <section className="quiz-result-panel panel" aria-labelledby="quiz-result-title">
      <header className="panel-heading">
        <div>
          <p className="eyebrow">Correction du mode quiz · Main #{result.handNumber}</p>
          <h2 id="quiz-result-title">Votre décision comparée au conseil</h2>
        </div>
        <button type="button" className="icon-button" onClick={dismiss} aria-label="Fermer la correction">
          ×
        </button>
      </header>
      <div className="quiz-result-grid">
        <span>
          <small>Action recommandée</small>
          <strong>
            {ACTION_LABELS[result.recommendedAction]}
            {result.recommendedAmount !== undefined
              ? ` · ${formatAmount(result.recommendedAmount, table.hand.unit, table.hand.big_blind)}`
              : ''}
          </strong>
        </span>
        <span>
          <small>Votre choix</small>
          <strong>
            {ACTION_LABELS[result.chosenAction]}
            {result.chosenAmount !== undefined
              ? ` · ${formatAmount(result.chosenAmount, table.hand.unit, table.hand.big_blind)}`
              : ''}
          </strong>
        </span>
        <span>
          <small>Comparaison</small>
          <strong>{sameAction ? 'Action identique' : 'Action différente'}</strong>
        </span>
        <span>
          <small>Différence d’EV estimée</small>
          <strong>{formatAmount(result.evDifference, table.hand.unit, table.hand.big_blind)}</strong>
        </span>
        <span>
          <small>Notation</small>
          <strong className={`quality ${result.quality}`}>{QUIZ_QUALITY_LABELS[result.quality]}</strong>
        </span>
        <span>
          <small>Confiance</small>
          <strong>{Math.round(result.confidence * 100)} %</strong>
        </span>
        <span>
          <small>Résultat final</small>
          <strong>
            {finalResult === undefined
              ? 'En attente de la fin de la main'
              : `${finalResult > 0 ? '+' : ''}${formatAmount(finalResult, table.hand.unit, table.hand.big_blind)}`}
          </strong>
        </span>
      </div>
      <p className="quiz-result-explanation">{result.explanation}</p>
    </section>
  );
}
