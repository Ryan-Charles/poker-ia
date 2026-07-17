import { useEffect } from 'react';
import { CardView } from './CardView';
import { useAppStore } from '../store';
import { api } from '../api';
import { downloadBlob, formatAmount, formatCardList, playerName } from '../utils';

const AUTO_SUBMIT_DELAY_MS = 600;

export function ShowdownPanel() {
  const table = useAppStore((state) => state.table);
  const showdownCards = useAppStore((state) => state.showdownCards);
  const currentPlayerId = useAppStore((state) => state.showdownPlayerId);
  const setMucked = useAppStore((state) => state.setShowdownMucked);
  const setManualWinner = useAppStore((state) => state.setManualWinner);
  const manualWinners = useAppStore((state) => state.manualWinners);
  const submit = useAppStore((state) => state.submitShowdown);
  const busy = useAppStore((state) => state.busy);

  const isShowdown = Boolean(table && table.hand.phase === 'showdown' && showdownCards !== undefined);
  const eligible =
    isShowdown && table
      ? table.players.filter((player) => table.hand.showdown_player_ids?.includes(player.id))
      : [];
  const opponents = eligible.filter((player) => player.id !== 'hero');
  const completeOrMucked = opponents.every((player) => {
    const cards = showdownCards?.[player.id];
    return cards === null || Boolean(cards?.[0] && cards[1]);
  });
  const unknownPlayers = opponents.filter((player) => showdownCards?.[player.id] === null);
  const pots =
    isShowdown && table
      ? table.hand.side_pots.length
        ? table.hand.side_pots
        : [{ index: 0, amount: table.hand.pot, eligible_player_ids: eligible.map((player) => player.id) }]
      : [];
  const manualPots = pots.filter((pot) =>
    unknownPlayers.some((player) => pot.eligible_player_ids.includes(player.id)),
  );
  const manualAssignmentsComplete = manualPots.every((pot) => (manualWinners[pot.index]?.length ?? 0) > 0);
  const readyToAutoSubmit =
    isShowdown && completeOrMucked && (unknownPlayers.length === 0 || manualAssignmentsComplete);

  // Enchaînement automatique (lot 5) : dès que toutes les révélations et attributions
  // nécessaires sont complètes, on laisse un court instant pour voir la dernière carte
  // se poser puis on valide seul. Le minuteur est annulé si l'état change entre-temps.
  useEffect(() => {
    if (!readyToAutoSubmit || busy) return;
    const timer = window.setTimeout(() => {
      void submit();
    }, AUTO_SUBMIT_DELAY_MS);
    return () => window.clearTimeout(timer);
  }, [readyToAutoSubmit, busy, submit]);

  if (!table || table.hand.phase !== 'showdown' || showdownCards === undefined) return null;

  const currentPlayer = opponents.find((player) => player.id === currentPlayerId);

  return (
    <section className="showdown-panel panel compact" aria-labelledby="showdown-title">
      <header className="panel-heading">
        <div>
          <p className="eyebrow">Révélation volontaire uniquement</p>
          <h2 id="showdown-title">Showdown</h2>
          <p>
            Cliquez les emplacements de cartes à côté des noms sur la table. Poker IA n’invente jamais une
            main non révélée.
          </p>
        </div>
        <span className="phase-badge">{eligible.length} joueurs éligibles</span>
      </header>
      <div className="showdown-compact-bar">
        <p>
          {currentPlayer ? (
            <>
              Joueur à renseigner : <strong>{currentPlayer.name}</strong>
            </>
          ) : completeOrMucked ? (
            'Toutes les révélations sont renseignées.'
          ) : (
            'Renseignez ou marquez comme non montrées les mains restantes.'
          )}
        </p>
        {currentPlayer ? (
          <button
            type="button"
            className={showdownCards[currentPlayer.id] === null ? 'selected' : 'ghost'}
            onClick={() => setMucked(currentPlayer.id, showdownCards[currentPlayer.id] !== null)}
          >
            {showdownCards[currentPlayer.id] === null ? '✓ Cartes non montrées' : 'Le joueur ne montre pas'}
          </button>
        ) : null}
      </div>
      {unknownPlayers.length ? (
        <section className="manual-winners">
          <h3>Attribution manuelle nécessaire</h3>
          <p>
            Au moins une main indispensable est inconnue. Choisissez le gagnant uniquement pour les pots que
            le moteur ne peut pas départager.
          </p>
          {manualPots.map((pot) => (
            <fieldset className="manual-pot" key={pot.index}>
              <legend>
                Pot {pot.index === 0 ? 'principal' : `secondaire ${pot.index}`} ·{' '}
                {formatAmount(pot.amount, table.hand.unit, table.hand.big_blind)}
              </legend>
              <div className="manual-winner-options" role="group" aria-label={`Gagnants du pot ${pot.index}`}>
                {eligible
                  .filter((player) => pot.eligible_player_ids.includes(player.id))
                  .map((player) => (
                    <label key={player.id}>
                      <input
                        type="checkbox"
                        checked={manualWinners[pot.index]?.includes(player.id) ?? false}
                        onChange={() => setManualWinner(pot.index, player.id)}
                      />
                      {player.name}
                    </label>
                  ))}
              </div>
              <small>
                Cochez plusieurs joueurs seulement en cas d’égalité : le pot sera partagé entre eux.
              </small>
            </fieldset>
          ))}
        </section>
      ) : null}
      <footer className="showdown-footer">
        <p>
          {completeOrMucked
            ? 'Toutes les révélations sont renseignées.'
            : 'Renseignez ou marquez comme non montrées les mains restantes.'}
        </p>
        <button
          type="button"
          className="primary large"
          disabled={busy || !completeOrMucked || (unknownPlayers.length > 0 && !manualAssignmentsComplete)}
          onClick={() => void submit()}
        >
          {busy ? 'Évaluation…' : 'Valider le showdown'}
        </button>
      </footer>
    </section>
  );
}

const RESULT_LABELS = {
  won: 'Main gagnée',
  lost: 'Main perdue',
  split: 'Pot partagé',
  incomplete: 'Résultat incomplet',
  won_without_showdown: 'Gagnée sans showdown',
} as const;

export function HandSummaryPanel() {
  const table = useAppStore((state) => state.table);
  const nextHand = useAppStore((state) => state.nextHand);
  const setView = useAppStore((state) => state.setView);
  const setNotification = useAppStore((state) => state.setNotification);
  const busy = useAppStore((state) => state.busy);
  const summary = table?.hand.summary;
  const isSummaryPhase = Boolean(table && summary && ['summary', 'ended'].includes(table.hand.phase));

  if (!table || !summary || !isSummaryPhase) return null;
  const heroResultClass = summary.hero_net > 0 ? 'positive' : summary.hero_net < 0 ? 'negative' : 'neutral';
  const revealedPlayers = summary.players.filter((player) => (player.revealed_cards?.length ?? 0) > 0);
  return (
    <div className="drawer-backdrop hand-summary-backdrop" role="presentation">
      <section className="hand-summary panel" aria-labelledby="summary-title">
        <header className={`summary-hero ${heroResultClass}`}>
          <span className="result-icon" aria-hidden="true">
            {summary.hero_net > 0 ? '↑' : summary.hero_net < 0 ? '↓' : '↔'}
          </span>
          <div>
            <p className="eyebrow">Main #{table.hand.number} terminée</p>
            <h2 id="summary-title">{RESULT_LABELS[summary.status]}</h2>
            <p>
              Gagnant{summary.winners.length > 1 ? 's' : ''} :{' '}
              {summary.winners.map((id) => playerName(table, id)).join(', ')}
            </p>
          </div>
          <div className="net-result">
            <small>Résultat net de Ryanchl</small>
            <strong>
              {summary.hero_net > 0 ? '+' : ''}
              {formatAmount(summary.hero_net, table.hand.unit, table.hand.big_blind)}
            </strong>
            <span>
              {summary.hero_net_bb > 0 ? '+' : ''}
              {summary.hero_net_bb.toFixed(2)} BB
            </span>
          </div>
        </header>
        <div className="summary-metrics">
          <span>
            <small>Pot total</small>
            <strong>{formatAmount(summary.total_pot, table.hand.unit, table.hand.big_blind)}</strong>
          </span>
          <span>
            <small>Ryanchl engagé</small>
            <strong>{formatAmount(summary.hero_contribution, table.hand.unit, table.hand.big_blind)}</strong>
          </span>
          <span>
            <small>Ryanchl reçu</small>
            <strong>{formatAmount(summary.hero_received, table.hand.unit, table.hand.big_blind)}</strong>
          </span>
          <span>
            <small>Nouveau tapis</small>
            <strong>{formatAmount(summary.hero_new_stack, table.hand.unit, table.hand.big_blind)}</strong>
          </span>
          <span>
            <small>Session cumulée</small>
            <strong className={summary.session_net >= 0 ? 'positive-text' : 'negative-text'}>
              {summary.session_net > 0 ? '+' : ''}
              {formatAmount(summary.session_net, table.hand.unit, table.hand.big_blind)}
            </strong>
          </span>
        </div>
        {revealedPlayers.length ? (
          <div className="showdown-results">
            <h3>Meilleures combinaisons révélées</h3>
            {revealedPlayers.map((player) => (
              <article key={player.player_id}>
                <strong>{player.name}</strong>
                <div className="revealed-cards">
                  {player.revealed_cards?.map((card) => <CardView key={card} card={card} compact />) ?? (
                    <span>Cartes non montrées</span>
                  )}
                </div>
                <div>
                  <span>{player.hand_name ?? 'Main non déterminable'}</span>
                  {player.best_five?.length ? <small>{formatCardList(player.best_five)}</small> : null}
                </div>
                <strong className={player.net >= 0 ? 'positive-text' : 'negative-text'}>
                  {player.net > 0 ? '+' : ''}
                  {formatAmount(player.net, table.hand.unit, table.hand.big_blind)}
                </strong>
              </article>
            ))}
          </div>
        ) : null}
        <div className="pot-table-wrap">
          <table>
            <caption>Répartition exacte des pots</caption>
            <thead>
              <tr>
                <th>Pot</th>
                <th>Montant</th>
                <th>Joueurs éligibles</th>
                <th>Gagnant(s)</th>
                <th>Parts reçues</th>
              </tr>
            </thead>
            <tbody>
              {summary.pots.map((pot) => (
                <tr key={pot.index}>
                  <td>{pot.index === 0 ? 'Principal' : `Secondaire ${pot.index}`}</td>
                  <td>{formatAmount(pot.amount, table.hand.unit, table.hand.big_blind)}</td>
                  <td>{pot.eligible_player_ids.map((id) => playerName(table, id)).join(', ')}</td>
                  <td>{pot.winner_ids?.map((id) => playerName(table, id)).join(', ') ?? 'Incomplet'}</td>
                  <td>
                    {pot.shares
                      ? Object.entries(pot.shares)
                          .map(
                            ([id, amount]) =>
                              `${playerName(table, id)} : ${formatAmount(amount, table.hand.unit, table.hand.big_blind)}`,
                          )
                          .join(' · ')
                      : '—'}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        <section className="decision-recap">
          <h3>Décision de Ryanchl</h3>
          <dl>
            <div>
              <dt>Conseil principal</dt>
              <dd>{summary.principal_advice ?? 'Aucun tour de Ryanchl dans cette main'}</dd>
            </div>
            <div>
              <dt>Action choisie</dt>
              <dd>{summary.hero_action ?? 'Aucune'}</dd>
            </div>
            <div>
              <dt>Comparaison</dt>
              <dd>{summary.advice_difference ?? 'Non applicable'}</dd>
            </div>
          </dl>
          <p>
            La qualité de la décision est évaluée selon son EV estimée, indépendamment du résultat de cette
            main.
          </p>
        </section>
        <footer>
          <button
            type="button"
            className="ghost"
            onClick={() => {
              void api
                .exportHand(table.session_id, table.hand.id)
                .then((blob) =>
                  downloadBlob(blob, `poker-ia-main-${table.hand.number}.json`, 'application/json'),
                )
                .catch((error: Error) => setNotification({ kind: 'error', message: error.message }));
            }}
          >
            Exporter cette main
          </button>
          <button type="button" className="ghost" onClick={() => setView('historique')}>
            Analyser les décisions
          </button>
          <button type="button" className="primary large" disabled={busy} onClick={() => void nextHand()}>
            {busy ? 'Préparation…' : 'Main suivante →'}
          </button>
        </footer>
      </section>
    </div>
  );
}
