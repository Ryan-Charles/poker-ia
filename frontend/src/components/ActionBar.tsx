import { useState } from 'react';
import { useAppStore } from '../store';
import { ACTION_LABELS, type LegalAction, type LegalActionName } from '../types';
import { clamp, formatAmount, fromEngineAmount, shortAmount, toEngineAmount } from '../utils';

const PRESETS = [25, 33, 50, 66, 75, 100, 125, 150, 200];

function actionOf(actions: LegalAction[], name: LegalActionName): LegalAction | undefined {
  return actions.find((candidate) => candidate.action === name);
}

export function ActionBar() {
  const table = useAppStore((state) => state.table);
  const busy = useAppStore((state) => state.busy);
  const performAction = useAppStore((state) => state.performAction);
  const [amountEntry, setAmountEntry] = useState({ context: '', value: 0 });

  const activePlayer = table?.players.find((player) => player.id === table.hand.active_player_id);
  const actions = table?.legal_actions ?? [];
  const bigBlind = table?.hand.big_blind ?? 100;
  const unit = table?.hand.unit ?? 'chips';
  const fold = actionOf(actions, 'fold');
  const check = actionOf(actions, 'check');
  const call = actionOf(actions, 'call');
  const bet = actionOf(actions, 'bet');
  const raise = actionOf(actions, 'raise');
  const wagerAction = bet?.enabled ? bet : raise;
  const wagerName: LegalActionName = bet?.enabled ? 'bet' : 'raise';
  const minAmount = wagerAction?.min_amount ?? 0;
  const maxAmount = wagerAction?.max_amount ?? activePlayer?.stack ?? 0;
  const amountContext = `${table?.hand.id ?? ''}:${table?.hand.street ?? ''}:${activePlayer?.id ?? ''}:${wagerName}`;
  const defaultAmount = clamp(minAmount || Math.max(1, table?.hand.pot ?? 0), minAmount, maxAmount);
  const amount = amountEntry.context === amountContext ? amountEntry.value : defaultAmount;
  const setAmount = (value: number) => setAmountEntry({ context: amountContext, value });
  const canSubmitWager = Boolean(
    wagerAction?.enabled && !busy && Number.isFinite(amount) && amount >= minAmount && amount <= maxAmount,
  );

  const metrics = (() => {
    if (!table || !activePlayer) return null;
    const pot = table.hand.pot;
    const callAmount = Math.max(0, table.hand.current_bet - activePlayer.street_bet);
    const isRaise = wagerName === 'raise';
    const added = isRaise ? Math.max(0, amount - activePlayer.street_bet) : amount;
    const potAfterCall = pot + callAmount;
    const raiseIncrement = Math.max(0, amount - table.hand.current_bet);
    const percent = isRaise
      ? potAfterCall > 0
        ? (raiseIncrement / potAfterCall) * 100
        : 0
      : pot > 0
        ? (amount / pot) * 100
        : 0;
    return {
      added,
      total: isRaise ? amount : activePlayer.street_bet + amount,
      percent,
      remaining: Math.max(0, activePlayer.stack - added),
      potAfter: pot + added,
      callAmount,
    };
  })();

  if (!table || table.hand.phase !== 'playing' || !activePlayer) return null;

  const choosePreset = (percent: number) => {
    const pot = table.hand.pot;
    const callAmount = Math.max(0, table.hand.current_bet - activePlayer.street_bet);
    const raw =
      wagerName === 'raise'
        ? table.hand.current_bet + (pot + callAmount) * (percent / 100)
        : pot * (percent / 100);
    setAmount(clamp(Math.round(raw), minAmount, maxAmount));
  };

  const actionDisabledReason = (action: LegalAction | undefined, fallback: string) =>
    action?.reason ?? fallback;

  return (
    <section className="action-dock" aria-label={`Actions de ${activePlayer.name}`}>
      <div className="actor-strip">
        <span className="actor-avatar">
          {activePlayer.id === 'hero' ? 'R' : activePlayer.name.slice(0, 1).toUpperCase()}
        </span>
        <div>
          <small>Au tour de</small>
          <strong>{activePlayer.id === 'hero' ? 'Ryanchl' : activePlayer.name}</strong>
        </div>
        <span className="actor-stack">
          {formatAmount(activePlayer.stack, unit, bigBlind)}
          {unit === 'big_blinds' ? '' : ` · ${activePlayer.stack_bb.toFixed(1)} BB`}
        </span>
      </div>
      <div className="primary-actions">
        <div className="action-buttons">
          <button
            type="button"
            className="action-fold"
            disabled={!fold?.enabled || busy}
            title={
              !fold?.enabled ? actionDisabledReason(fold, 'Fold n’est pas légal maintenant.') : 'Raccourci F'
            }
            onClick={() => void performAction('fold')}
          >
            <span aria-hidden="true">×</span>
            Fold
          </button>
          {check?.enabled ? (
            <button
              type="button"
              className="action-passive"
              disabled={busy}
              title="Raccourci C"
              onClick={() => void performAction('check')}
            >
              <span aria-hidden="true">✓</span>
              Check
            </button>
          ) : (
            <button
              type="button"
              className="action-passive"
              disabled={!call?.enabled || busy}
              title={!call?.enabled ? actionDisabledReason(call, 'Aucune mise à suivre.') : 'Raccourci C'}
              onClick={() => void performAction('call')}
            >
              <span aria-hidden="true">↳</span>
              {call?.all_in_call ? 'Call tapis' : 'Call'}{' '}
              {shortAmount(call?.call_amount ?? table.hand.to_call, unit, bigBlind)}
            </button>
          )}
          <button
            type="button"
            className="action-aggressive"
            disabled={!canSubmitWager}
            title={
              !wagerAction?.enabled
                ? actionDisabledReason(wagerAction, 'Miser ou relancer n’est pas légal maintenant.')
                : 'Raccourci R'
            }
            onClick={() => void performAction(wagerName, amount)}
          >
            <span aria-hidden="true">↗</span>
            {ACTION_LABELS[wagerName]}
          </button>
        </div>
        <div className="wager-control">
          <div className="wager-input-row">
            <label>
              <span>{wagerName === 'raise' ? 'Relance totale à' : 'Montant de la mise'}</span>
              <input
                type="number"
                min={fromEngineAmount(minAmount, unit, bigBlind)}
                max={fromEngineAmount(maxAmount, unit, bigBlind)}
                step={unit === 'chips' ? 1 : 0.01}
                value={Number.isFinite(amount) ? fromEngineAmount(amount, unit, bigBlind) : ''}
                disabled={!wagerAction?.enabled || busy}
                onChange={(event) => setAmount(toEngineAmount(event.target.valueAsNumber, unit, bigBlind))}
                onKeyDown={(event) => {
                  if (event.key !== 'Enter' || !canSubmitWager) return;
                  event.preventDefault();
                  void performAction(wagerName, amount);
                }}
                aria-describedby="sizing-calculation"
              />
            </label>
          </div>
          <div className="sizing-presets" aria-label="Tailles rapides en pourcentage du pot">
            {PRESETS.map((percent) => (
              <button
                type="button"
                key={percent}
                disabled={!wagerAction?.enabled || busy}
                onClick={() => choosePreset(percent)}
              >
                {percent} %
              </button>
            ))}
            <button
              type="button"
              disabled={!wagerAction?.enabled || busy}
              onClick={() => setAmount(maxAmount)}
            >
              Tapis
            </button>
          </div>
        </div>
      </div>
      {metrics ? (
        <div className="sizing-calculation" id="sizing-calculation" aria-live="polite">
          <span>
            <small>Ajouté</small>
            <strong>{formatAmount(metrics.added, unit, bigBlind)}</strong>
          </span>
          <span>
            <small>Total atteint</small>
            <strong>{formatAmount(metrics.total, unit, bigBlind)}</strong>
          </span>
          <span>
            <small>Taille</small>
            <strong>{metrics.percent.toFixed(0)} % du pot</strong>
          </span>
          <span>
            <small>{wagerName === 'raise' ? 'Relance min.' : 'Mise min.'}</small>
            <strong>{formatAmount(minAmount, unit, bigBlind)}</strong>
          </span>
          <span>
            <small>Tapis restant</small>
            <strong>{formatAmount(metrics.remaining, unit, bigBlind)}</strong>
          </span>
          <span>
            <small>Pot estimé</small>
            <strong>{formatAmount(metrics.potAfter, unit, bigBlind)}</strong>
          </span>
        </div>
      ) : null}
    </section>
  );
}
