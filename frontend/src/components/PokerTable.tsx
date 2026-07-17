import { useEffect, useRef, useState } from 'react';
import { CardView } from './CardView';
import { useAppStore } from '../store';
import {
  PROFILE_LABELS,
  STREET_LABELS,
  type Card,
  type CardSlot,
  type OpponentArchetype,
  type PlayerState,
  type Unit,
} from '../types';
import {
  actionVerb,
  betChipCounts,
  betMarkerPosition,
  formatAmount,
  fromEngineAmount,
  shortAmount,
  tablePosition,
  toEngineAmount,
} from '../utils';

const STATUS_LABELS: Record<PlayerState['status'], string> = {
  active: 'Actif',
  folded: 'Couché',
  all_in: 'À tapis',
  away: 'Absent',
  eliminated: 'Éliminé',
};

function SeatShowdownCards({ player }: { player: PlayerState }) {
  const table = useAppStore((state) => state.table);
  const showdownCards = useAppStore((state) => state.showdownCards);
  const focusedSlot = useAppStore((state) => state.focusedSlot);
  const setFocusedSlot = useAppStore((state) => state.setFocusedSlot);
  if (!table) return null;
  const isHero = player.id === 'hero';
  const mucked = !isHero && showdownCards?.[player.id] === null;
  if (mucked) return <span className="showdown-mucked-badge">Ne montre pas</span>;
  const cards: [Card | undefined, Card | undefined] = isHero
    ? [table.hand.hero_cards[0], table.hand.hero_cards[1]]
    : (showdownCards?.[player.id] ?? [undefined, undefined]);
  return (
    <div className="seat-showdown-cards" aria-label={`Cartes de showdown de ${player.name}`}>
      {([0, 1] as const).map((index) => {
        const slot = `showdown:${player.id}:${index + 1}` as CardSlot;
        return (
          <CardView
            key={slot}
            card={cards[index]}
            compact
            active={!isHero && focusedSlot === slot}
            label={`Carte ${index + 1} de ${player.name}`}
            onClick={isHero ? undefined : () => setFocusedSlot(slot)}
          />
        );
      })}
    </div>
  );
}

function BetMarker({
  player,
  allPlayers,
  chips,
  unit,
  bigBlind,
}: {
  player: PlayerState;
  allPlayers: PlayerState[];
  chips: number;
  unit: Unit;
  bigBlind: number;
}) {
  const position = betMarkerPosition(player, allPlayers);
  // Plafonne l'affichage à 5 jetons empilés ; le montant textuel reste exact.
  const stackCount = Math.min(Math.max(chips, 1), 5);
  return (
    <div
      className={`bet-marker${player.id === 'hero' ? ' is-hero' : ''}${player.status === 'folded' ? ' is-folded' : ''}`}
      style={position}
      aria-label={`Mise de ${player.id === 'hero' ? 'Ryanchl' : player.name} : ${shortAmount(player.street_bet, unit, bigBlind)}`}
    >
      <div className="chip-stack">
        {Array.from({ length: stackCount }, (_, index) => (
          <span key={index} className="chip" style={{ bottom: `${index * 3}px` }} />
        ))}
      </div>
      <span className="bet-marker-amount">{shortAmount(player.street_bet, unit, bigBlind)}</span>
    </div>
  );
}

function PlayerSeat({
  player,
  allPlayers,
  unit,
  bigBlind,
  onEdit,
  onRemove,
}: {
  player: PlayerState;
  allPlayers: PlayerState[];
  unit: Unit;
  bigBlind: number;
  onEdit: () => void;
  onRemove: () => void;
}) {
  const table = useAppStore((state) => state.table);
  const showdownPlayerId = useAppStore((state) => state.showdownPlayerId);
  const active = table?.hand.active_player_id === player.id;
  const isShowdown = table?.hand.phase === 'showdown';
  const eligibleForShowdown = Boolean(isShowdown && table?.hand.showdown_player_ids?.includes(player.id));
  const isCurrentShowdownPlayer = eligibleForShowdown && showdownPlayerId === player.id;
  const position = tablePosition(player, allPlayers);
  // Halo argenté pour tout joueur encore en lice (actif ou à tapis) ; le tour
  // en cours (to-act) affiche un halo doré plus fort qui le remplace.
  const inHand = player.status === 'active' || player.status === 'all_in';
  const isHero = player.id === 'hero';
  const heroCards = isHero ? table?.hand.hero_cards : undefined;
  return (
    <article
      className={`player-seat ${isHero ? 'hero' : ''} ${player.pending_join ? 'pending-join' : ''} status-${player.status} ${inHand ? 'in-hand' : ''} ${active ? 'to-act' : ''} ${isCurrentShowdownPlayer ? 'showdown-active' : ''}`}
      style={position}
      aria-label={`${player.name}, ${player.position}, ${STATUS_LABELS[player.status]}${active ? ', doit agir' : ''}`}
    >
      {active ? <span className="turn-pulse">À VOUS</span> : null}
      <div className="seat-topline">
        <span className="seat-index">S{player.seat}</span>
        <div className="position-badges">
          {player.is_dealer ? <span className="dealer">D</span> : null}
          {player.is_small_blind ? <span>SB</span> : null}
          {player.is_big_blind ? <span>BB</span> : null}
        </div>
        <div className="seat-tools">
          {!isHero ? (
            <button
              type="button"
              className="seat-remove"
              onClick={onRemove}
              aria-label={`Retirer ${player.name} de la table`}
              title="Libérer ce siège"
            >
              −
            </button>
          ) : null}
          {!player.pending_join ? (
            <button
              type="button"
              className="seat-edit"
              onClick={onEdit}
              aria-label={`Modifier ${player.name}`}
            >
              ✎
            </button>
          ) : null}
        </div>
      </div>
      <strong className="player-name">{isHero ? 'Ryanchl' : player.name}</strong>
      <span className="player-position">{player.position}</span>
      {isHero ? (
        heroCards && heroCards.length > 0 ? (
          <div className="seat-hero-cards" aria-label="Cartes de Ryanchl">
            {([0, 1] as const).map((index) => (
              <CardView key={index} card={heroCards[index]} compact label={`Carte ${index + 1} de Ryanchl`} />
            ))}
          </div>
        ) : null
      ) : eligibleForShowdown ? (
        <SeatShowdownCards player={player} />
      ) : null}
      <div className="stack-line">
        <strong>{formatAmount(player.stack, unit, bigBlind)}</strong>
        {unit === 'big_blinds' ? null : <small>{player.stack_bb.toFixed(1)} BB</small>}
      </div>
      <dl className="seat-details">
        <div>
          <dt>Mise rue</dt>
          <dd>{shortAmount(player.street_bet, unit, bigBlind)}</dd>
        </div>
        <div>
          <dt>Engagé</dt>
          <dd>{shortAmount(player.total_contribution, unit, bigBlind)}</dd>
        </div>
      </dl>
      {player.pending_join ? (
        <span className="pending-join-badge">Arrive à la prochaine main</span>
      ) : player.last_action ? (
        <span className="last-action">{actionVerb(player.last_action)}</span>
      ) : (
        <span className="status-label">{STATUS_LABELS[player.status]}</span>
      )}
      {player.id !== 'hero' && !player.pending_join ? (
        <div className="profile-summary" title={`${player.profile.hands_observed} mains observées`}>
          <span>{player.profile.estimated || 'Profil en observation'}</span>
          <span className="confidence-bar">
            <i style={{ width: `${Math.round(player.profile.confidence * 100)}%` }} />
          </span>
          <small>
            {Math.round(player.profile.confidence * 100)} % · {player.profile.hands_observed} mains
          </small>
        </div>
      ) : null}
    </article>
  );
}

function ReplacePlayerSection({ player, onReplaced }: { player: PlayerState; onReplaced: () => void }) {
  const replacePlayer = useAppStore((state) => state.replacePlayer);
  const unit = useAppStore((state) => state.table?.hand.unit ?? 'chips');
  const bigBlind = useAppStore((state) => state.table?.hand.big_blind ?? 100);
  const [replaceName, setReplaceName] = useState('');
  const [replaceProfile, setReplaceProfile] = useState<OpponentArchetype>('unknown');
  const [replaceStack, setReplaceStack] = useState(player.stack);
  const [replacing, setReplacing] = useState(false);
  return (
    <section className="replace-player-section">
      <h3>Remplacer ce joueur</h3>
      <p className="info-callout">
        Le nouveau joueur prend ce siège avec un profil vierge. En cours de main, il hérite des mises déjà
        engagées.
      </p>
      <label className="field">
        <span>Nom du nouveau joueur</span>
        <input
          value={replaceName}
          maxLength={30}
          onChange={(event) => setReplaceName(event.target.value)}
          placeholder="Ex. Jordan"
        />
      </label>
      <label className="field">
        <span>Profil initial</span>
        <select
          value={replaceProfile}
          onChange={(event) => setReplaceProfile(event.target.value as OpponentArchetype)}
        >
          {Object.entries(PROFILE_LABELS).map(([value, label]) => (
            <option value={value} key={value}>
              {label}
            </option>
          ))}
        </select>
      </label>
      <label className="field">
        <span>Tapis (facultatif)</span>
        <input
          type="number"
          min="0"
          step={unit === 'chips' ? 1 : 0.01}
          value={fromEngineAmount(replaceStack, unit, bigBlind)}
          onChange={(event) => setReplaceStack(toEngineAmount(event.target.valueAsNumber, unit, bigBlind))}
        />
      </label>
      <button
        type="button"
        className="danger-ghost"
        disabled={replacing || !replaceName.trim()}
        onClick={() => {
          setReplacing(true);
          void replacePlayer(player.id, {
            name: replaceName.trim(),
            stack: replaceStack,
            initial_profile: replaceProfile,
          }).then((success) => {
            setReplacing(false);
            if (success) onReplaced();
          });
        }}
      >
        {replacing ? 'Remplacement…' : 'Remplacer'}
      </button>
    </section>
  );
}

function VacantSeat({
  player,
  allPlayers,
  onAdd,
}: {
  player: PlayerState;
  allPlayers: PlayerState[];
  onAdd: () => void;
}) {
  return (
    <article
      className="player-seat vacant-seat"
      style={tablePosition(player, allPlayers)}
      aria-label={`Siège ${player.seat} libre`}
    >
      <span className="seat-index">S{player.seat}</span>
      <button
        type="button"
        className="vacant-seat-add"
        onClick={onAdd}
        aria-label={`Ajouter un joueur au siège ${player.seat}`}
      >
        <span aria-hidden="true">+</span>
        <strong>Ajouter un joueur</strong>
      </button>
    </article>
  );
}

function SeatPlayerDrawer({ player, onClose }: { player: PlayerState; onClose: () => void }) {
  const seatPlayer = useAppStore((state) => state.seatPlayer);
  const unit = useAppStore((state) => state.table?.hand.unit ?? 'chips');
  const bigBlind = useAppStore((state) => state.table?.hand.big_blind ?? 100);
  const [name, setName] = useState('');
  const [profile, setProfile] = useState<OpponentArchetype>('unknown');
  const [customProfile, setCustomProfile] = useState('');
  const [stack, setStack] = useState(Math.max(player.stack, bigBlind * 20));
  const [saving, setSaving] = useState(false);

  return (
    <div
      className="drawer-backdrop"
      role="presentation"
      onMouseDown={(event) => event.currentTarget === event.target && onClose()}
    >
      <aside className="edit-drawer" role="dialog" aria-modal="true" aria-labelledby="seat-player-title">
        <header>
          <div>
            <p className="eyebrow">Siège {player.seat}</p>
            <h2 id="seat-player-title">Ajouter un joueur</h2>
          </div>
          <button type="button" className="icon-button" onClick={onClose} aria-label="Fermer">
            ×
          </button>
        </header>
        <p className="info-callout">
          Le joueur est enregistré immédiatement et participera à partir de la prochaine main.
        </p>
        <label className="field">
          <span>Nom du joueur</span>
          <input value={name} maxLength={30} onChange={(event) => setName(event.target.value)} autoFocus />
        </label>
        <label className="field">
          <span>Tapis réellement possédé</span>
          <input
            type="number"
            min={unit === 'chips' ? 1 : 0.01}
            step={unit === 'chips' ? 1 : 0.01}
            value={fromEngineAmount(stack, unit, bigBlind)}
            onChange={(event) => setStack(toEngineAmount(event.target.valueAsNumber, unit, bigBlind))}
          />
        </label>
        <label className="field">
          <span>Profil initial</span>
          <select value={profile} onChange={(event) => setProfile(event.target.value as OpponentArchetype)}>
            {Object.entries(PROFILE_LABELS).map(([value, label]) => (
              <option value={value} key={value}>
                {label}
              </option>
            ))}
          </select>
        </label>
        {profile === 'custom' ? (
          <label className="field">
            <span>Description du profil</span>
            <textarea
              value={customProfile}
              onChange={(event) => setCustomProfile(event.target.value)}
              rows={3}
            />
          </label>
        ) : null}
        <footer>
          <button type="button" className="ghost" onClick={onClose}>
            Annuler
          </button>
          <button
            type="button"
            className="primary"
            disabled={
              saving ||
              !name.trim() ||
              !Number.isFinite(stack) ||
              stack <= 0 ||
              (profile === 'custom' && !customProfile.trim())
            }
            onClick={() => {
              setSaving(true);
              void seatPlayer(player.id, {
                name: name.trim(),
                stack,
                initial_profile: profile,
                ...(profile === 'custom' ? { custom_profile: customProfile.trim() } : {}),
              }).then((success) => {
                setSaving(false);
                if (success) onClose();
              });
            }}
          >
            {saving ? 'Ajout…' : 'Ajouter à ce siège'}
          </button>
        </footer>
      </aside>
    </div>
  );
}

function PlayerEditor({ player, onClose }: { player: PlayerState; onClose: () => void }) {
  const updatePlayer = useAppStore((state) => state.updatePlayer);
  const unit = useAppStore((state) => state.table?.hand.unit ?? 'chips');
  const bigBlind = useAppStore((state) => state.table?.hand.big_blind ?? 100);
  const [name, setName] = useState(player.name);
  const [stack, setStack] = useState(player.stack);
  const [status, setStatus] = useState(player.status);
  const [saving, setSaving] = useState(false);
  return (
    <div
      className="drawer-backdrop"
      role="presentation"
      onMouseDown={(event) => event.currentTarget === event.target && onClose()}
    >
      <aside className="edit-drawer" role="dialog" aria-modal="true" aria-labelledby="edit-player-title">
        <header>
          <div>
            <p className="eyebrow">Mode édition</p>
            <h2 id="edit-player-title">Modifier {player.name}</h2>
          </div>
          <button type="button" className="icon-button" onClick={onClose} aria-label="Fermer">
            ×
          </button>
        </header>
        <p className="info-callout">
          Le tapis saisi devient immédiatement le montant réellement disponible, même si la main a déjà
          commencé.
        </p>
        <label className="field">
          <span>Nom affiché</span>
          <input
            value={player.id === 'hero' ? 'Ryanchl' : name}
            disabled={player.id === 'hero'}
            onChange={(event) => setName(event.target.value)}
          />
        </label>
        <label className="field">
          <span>Tapis réellement possédé maintenant</span>
          <input
            type="number"
            min="0"
            step={unit === 'chips' ? 1 : 0.01}
            value={fromEngineAmount(stack, unit, bigBlind)}
            onChange={(event) => setStack(toEngineAmount(event.target.valueAsNumber, unit, bigBlind))}
          />
        </label>
        <label className="field">
          <span>Statut</span>
          <select value={status} onChange={(event) => setStatus(event.target.value as PlayerState['status'])}>
            <option value="active">Actif</option>
            <option value="away">Absent</option>
            <option value="eliminated">Éliminé</option>
            {player.status === 'folded' ? <option value="folded">Couché dans la main</option> : null}
            {player.status === 'all_in' ? <option value="all_in">À tapis dans la main</option> : null}
          </select>
        </label>
        <footer>
          <button type="button" className="ghost" onClick={onClose}>
            Annuler
          </button>
          <button
            type="button"
            className="primary"
            disabled={saving || !name.trim() || !Number.isFinite(stack) || stack < 0}
            onClick={() => {
              setSaving(true);
              const changes: { name?: string; stack?: number; status?: string } = {};
              const nextName = player.id === 'hero' ? 'Ryanchl' : name.trim();
              if (nextName !== player.name) changes.name = nextName;
              if (stack !== player.stack) changes.stack = stack;
              if (
                status !== player.status &&
                (status === 'active' || status === 'away' || status === 'eliminated')
              )
                changes.status = status;
              void updatePlayer(player.id, changes).then((success) => {
                setSaving(false);
                if (success) onClose();
              });
            }}
          >
            {saving ? 'Enregistrement…' : 'Appliquer'}
          </button>
        </footer>
        {player.id !== 'hero' ? <ReplacePlayerSection player={player} onReplaced={onClose} /> : null}
      </aside>
    </div>
  );
}

function RestartHandButton() {
  const restartHand = useAppStore((state) => state.restartHand);
  const busy = useAppStore((state) => state.busy);
  const [confirming, setConfirming] = useState(false);
  const resetTimer = useRef<number | null>(null);

  useEffect(
    () => () => {
      if (resetTimer.current !== null) window.clearTimeout(resetTimer.current);
    },
    [],
  );

  const cancelConfirm = () => {
    if (resetTimer.current !== null) window.clearTimeout(resetTimer.current);
    resetTimer.current = null;
    setConfirming(false);
  };

  if (confirming) {
    return (
      <div className="restart-hand-confirm">
        <span>Confirmer ?</span>
        <button
          type="button"
          className="danger"
          disabled={busy}
          onClick={() => {
            cancelConfirm();
            void restartHand();
          }}
        >
          Oui, tout remettre à zéro
        </button>
        <button type="button" className="ghost" onClick={cancelConfirm}>
          Annuler
        </button>
      </div>
    );
  }
  return (
    <button
      type="button"
      className="ghost small restart-hand-button"
      onClick={() => {
        setConfirming(true);
        if (resetTimer.current !== null) window.clearTimeout(resetTimer.current);
        resetTimer.current = window.setTimeout(() => setConfirming(false), 4000);
      }}
    >
      ↺ Recommencer la main
    </button>
  );
}

export function PokerTable() {
  const table = useAppStore((state) => state.table);
  const removePlayer = useAppStore((state) => state.removePlayer);
  const [editedPlayer, setEditedPlayer] = useState<PlayerState | null>(null);
  const [vacantPlayer, setVacantPlayer] = useState<PlayerState | null>(null);
  if (!table) return null;
  const hand = table.hand;
  const anyAllIn = table.players.some((player) => player.status === 'all_in');
  const principalPot = hand.side_pots.find((pot) => pot.index === 0)?.amount ?? hand.pot;
  const secondaryPots = hand.side_pots.filter((pot) => pot.index > 0);
  const recentActions = hand.action_log.slice(-6).reverse();
  // Les jetons ne s'affichent que pendant les rues jouées, pas au récapitulatif.
  const showBetMarkers = hand.street !== 'showdown' && hand.street !== 'terminee';
  const chipCounts = betChipCounts(hand.action_log, hand.street, hand.big_blind, table.players);
  return (
    <section className="poker-zone panel" aria-label="Table de poker">
      <header className="table-toolbar">
        <div>
          <p className="eyebrow">Main #{hand.number}</p>
          <h1>{STREET_LABELS[hand.street]}</h1>
        </div>
        <div className="table-toolbar-right">
          <div className="table-metrics">
            <span>
              <small>Joueurs en lice</small>
              <strong>{hand.players_remaining}</strong>
            </span>
            <span>
              <small>Mise maximale</small>
              <strong>{formatAmount(hand.current_bet, hand.unit, hand.big_blind)}</strong>
            </span>
            <span>
              <small>Dernière relance complète</small>
              <strong>{formatAmount(hand.last_full_raise, hand.unit, hand.big_blind)}</strong>
            </span>
          </div>
          <RestartHandButton />
        </div>
      </header>
      {/* À 7-8 joueurs, les bulles latérales voisines sont presque alignées
          verticalement : le mode « crowded » réduit leur contenu pour garantir
          qu'aucune bulle ne chevauche jamais sa voisine. */}
      <div className={`table-canvas ${table.players.length >= 7 ? 'crowded' : ''}`}>
        <div className="felt" aria-hidden="true">
          <span className="felt-line" />
        </div>
        <div className="seat-layer">
          {showBetMarkers
            ? table.players
                .filter((player) => player.street_bet > 0)
                .map((player) => (
                  <BetMarker
                    key={player.id}
                    player={player}
                    allPlayers={table.players}
                    chips={chipCounts[player.id] ?? 1}
                    unit={hand.unit}
                    bigBlind={hand.big_blind}
                  />
                ))
            : null}
          {table.players.map((player) =>
            player.status === 'away' && !player.pending_join ? (
              <VacantSeat
                key={player.id}
                player={player}
                allPlayers={table.players}
                onAdd={() => setVacantPlayer(player)}
              />
            ) : (
              <PlayerSeat
                key={player.id}
                player={player}
                allPlayers={table.players}
                unit={hand.unit}
                bigBlind={hand.big_blind}
                onEdit={() => setEditedPlayer(player)}
                onRemove={() => void removePlayer(player.id)}
              />
            ),
          )}
        </div>
        <div className="table-center">
          <p className="street-chip">{STREET_LABELS[hand.street]}</p>
          <div className="board-cards" aria-label="Cartes communes">
            {[0, 1, 2, 3, 4].map((index) => (
              <CardView key={index} card={hand.board[index]} label={`Carte commune ${index + 1}`} />
            ))}
          </div>
          <div className="pot-display">
            {anyAllIn ? (
              <>
                <span>Pot principal</span>
                <strong>{formatAmount(principalPot, hand.unit, hand.big_blind)}</strong>
                {hand.side_pots.length ? (
                  <small>Pot total : {formatAmount(hand.pot, hand.unit, hand.big_blind)}</small>
                ) : null}
              </>
            ) : (
              <>
                <span>Pot</span>
                <strong>{formatAmount(hand.pot, hand.unit, hand.big_blind)}</strong>
              </>
            )}
          </div>
          {anyAllIn && secondaryPots.length ? (
            <div className="side-pots">
              {secondaryPots.map((pot) => (
                <span key={pot.index}>
                  Pot secondaire {pot.index} · {formatAmount(pot.amount, hand.unit, hand.big_blind)}
                </span>
              ))}
            </div>
          ) : null}
          {hand.to_call > 0 ? (
            <span className="to-call">
              À suivre : {formatAmount(hand.to_call, hand.unit, hand.big_blind)}
            </span>
          ) : null}
        </div>
        <aside className="compact-log" aria-label="Dernières actions">
          <strong>Actions</strong>
          {recentActions.length ? (
            <ol>
              {recentActions.map((entry) => (
                <li key={entry.id}>
                  <span>{entry.player_name}</span>
                  <strong>
                    {actionVerb(entry.action)}
                    {entry.amount ? ` ${shortAmount(entry.amount, hand.unit, hand.big_blind)}` : ''}
                  </strong>
                </li>
              ))}
            </ol>
          ) : (
            <p>En attente de la première action.</p>
          )}
        </aside>
      </div>
      {editedPlayer ? <PlayerEditor player={editedPlayer} onClose={() => setEditedPlayer(null)} /> : null}
      {vacantPlayer ? <SeatPlayerDrawer player={vacantPlayer} onClose={() => setVacantPlayer(null)} /> : null}
    </section>
  );
}
