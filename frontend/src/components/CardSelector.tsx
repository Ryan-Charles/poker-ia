import { useEffect, useMemo, useRef, useState } from 'react';
import { CardView } from './CardView';
import { useAppStore } from '../store';
import { MAIN_CARD_SLOTS, SLOT_LABELS, type Card, type CardSlot, type MainCardSlot } from '../types';
import { ALL_CARDS, RANK_LABEL, SUIT_LABEL, SUIT_SYMBOL, cardLabel } from '../utils';

const RANK_KEYS: Record<string, string> = {
  A: 'A',
  K: 'K',
  Q: 'Q',
  J: 'J',
  T: 'T',
  '1': 'T',
  '9': '9',
  '8': '8',
  '7': '7',
  '6': '6',
  '5': '5',
  '4': '4',
  '3': '3',
  '2': '2',
};
const SUIT_KEYS: Record<string, string> = { S: 's', H: 'h', D: 'd', C: 'c' };

export function CardSelector({ centered = false }: { centered?: boolean }) {
  const table = useAppStore((state) => state.table);
  const mainCards = useAppStore((state) => state.mainCards);
  const focusedSlot = useAppStore((state) => state.focusedSlot);
  const showdownCards = useAppStore((state) => state.showdownCards);
  const setFocusedSlot = useAppStore((state) => state.setFocusedSlot);
  const selectCard = useAppStore((state) => state.selectCard);
  const clearCard = useAppStore((state) => state.clearCard);
  const clearStreet = useAppStore((state) => state.clearStreet);
  const undo = useAppStore((state) => state.undo);
  const redo = useAppStore((state) => state.redo);
  const [pendingRank, setPendingRank] = useState<string | null>(null);
  const [gridIndex, setGridIndex] = useState(0);
  const gridRef = useRef<HTMLDivElement>(null);

  const usedCards = useMemo(() => {
    const used = new Set<Card>(Object.values(mainCards).filter((card): card is Card => card !== undefined));
    if (showdownCards) {
      Object.values(showdownCards).forEach((cards) => cards?.forEach((card) => card && used.add(card)));
    }
    return used;
  }, [mainCards, showdownCards]);

  const currentCard = useMemo(() => {
    if (!focusedSlot) return undefined;
    if (!focusedSlot.startsWith('showdown:')) return mainCards[focusedSlot as MainCardSlot];
    const [, playerId, indexText] = focusedSlot.split(':');
    return showdownCards?.[playerId ?? '']?.[Number(indexText) - 1];
  }, [focusedSlot, mainCards, showdownCards]);

  useEffect(() => {
    const onKeyDown = (event: KeyboardEvent) => {
      const target = event.target;
      if (target instanceof Element && target.matches('input, textarea, select, [contenteditable="true"]'))
        return;
      const key = event.key.toUpperCase();
      if (event.key.startsWith('Arrow')) {
        event.preventDefault();
        setGridIndex((current) => {
          if (event.key === 'ArrowRight') return (current + 1) % 52;
          if (event.key === 'ArrowLeft') return (current + 51) % 52;
          if (event.key === 'ArrowDown') return (current + 13) % 52;
          return (current + 39) % 52;
        });
        gridRef.current?.focus();
        return;
      }
      if (event.key === 'Enter' && document.activeElement === gridRef.current) {
        event.preventDefault();
        const card = ALL_CARDS[gridIndex];
        if (card && (!usedCards.has(card) || card === currentCard)) void selectCard(card);
        return;
      }
      if (key === 'ESCAPE') {
        setPendingRank(null);
        delete document.body.dataset.cardSequence;
        return;
      }
      if (pendingRank) {
        const suit = SUIT_KEYS[key];
        if (suit) {
          event.preventDefault();
          Object.defineProperty(event, '__pokerCardHandled', { value: true, configurable: true });
          const card = `${pendingRank}${suit}` as Card;
          if (!usedCards.has(card) || card === currentCard) void selectCard(card);
          setPendingRank(null);
          queueMicrotask(() => delete document.body.dataset.cardSequence);
          return;
        }
        setPendingRank(null);
        delete document.body.dataset.cardSequence;
      }
      const rank = RANK_KEYS[key];
      if (rank) {
        event.preventDefault();
        setPendingRank(rank);
        document.body.dataset.cardSequence = 'true';
      }
    };
    window.addEventListener('keydown', onKeyDown);
    return () => window.removeEventListener('keydown', onKeyDown);
  }, [currentCard, gridIndex, pendingRank, selectCard, usedCards]);

  useEffect(
    () => () => {
      delete document.body.dataset.cardSequence;
    },
    [],
  );

  if (!table) return null;
  const showdown = table.hand.phase === 'showdown' && showdownCards !== undefined;
  const showdownPlayers = showdown
    ? table.players.filter(
        (player) => table.hand.showdown_player_ids?.includes(player.id) && player.id !== 'hero',
      )
    : [];

  return (
    <aside className={`card-selector panel${centered ? ' centered' : ''}`} aria-label="Sélecteur de cartes">
      <header className="panel-heading">
        <div>
          <p className="eyebrow">Saisie rapide</p>
          <h2>Sélecteur de cartes</h2>
        </div>
        <span className="deck-counter">{52 - usedCards.size} disponibles</span>
      </header>

      <div className="card-slots main-card-slots" aria-label="Cartes de Ryanchl et cartes communes">
        {MAIN_CARD_SLOTS.map((slot) => {
          const hiddenByProgress =
            table.selector.required_slots.length > 0 &&
            !table.selector.required_slots.includes(slot) &&
            !mainCards[slot];
          return (
            <div
              className={`slot-wrap ${focusedSlot === slot ? 'next' : ''} ${hiddenByProgress ? 'future' : ''}`}
              key={slot}
            >
              <span>{SLOT_LABELS[slot]}</span>
              <div className="slot-card">
                <CardView
                  card={mainCards[slot]}
                  compact
                  active={focusedSlot === slot}
                  label={SLOT_LABELS[slot]}
                  onClick={() => setFocusedSlot(slot)}
                />
                {mainCards[slot] ? (
                  <button
                    type="button"
                    className="slot-clear"
                    onClick={() => void clearCard(slot)}
                    aria-label={`Effacer ${SLOT_LABELS[slot]}`}
                  >
                    ×
                  </button>
                ) : null}
              </div>
            </div>
          );
        })}
      </div>

      {showdown ? (
        <section className="showdown-card-slots" aria-label="Cartes révélées au showdown">
          <h3>Cartes réellement révélées</h3>
          {showdownPlayers.map((player) => {
            const cards = showdownCards[player.id];
            const mucked = cards === null;
            return (
              <div className={`showdown-slot-row ${mucked ? 'mucked' : ''}`} key={player.id}>
                <div>
                  <strong>{player.name}</strong>
                  <small>{mucked ? 'Ne montre pas' : 'Showdown'}</small>
                </div>
                {!mucked ? (
                  <>
                    {([0, 1] as const).map((index) => {
                      const slot = `showdown:${player.id}:${index + 1}` as CardSlot;
                      return (
                        <CardView
                          key={slot}
                          card={cards?.[index]}
                          compact
                          active={focusedSlot === slot}
                          label={`Carte ${index + 1} de ${player.name}`}
                          onClick={() => setFocusedSlot(slot)}
                        />
                      );
                    })}
                  </>
                ) : (
                  <span className="muck-label">Cartes inconnues</span>
                )}
              </div>
            );
          })}
        </section>
      ) : null}

      <div className="keyboard-status" aria-live="polite">
        {pendingRank ? (
          <>
            Rang <kbd>{RANK_LABEL[pendingRank] ?? pendingRank}</kbd> choisi — tapez <kbd>S</kbd>, <kbd>H</kbd>
            , <kbd>D</kbd> ou <kbd>C</kbd>.
          </>
        ) : focusedSlot ? (
          <>
            Prochain emplacement :{' '}
            <strong>
              {focusedSlot.startsWith('showdown:')
                ? 'carte révélée'
                : SLOT_LABELS[focusedSlot as MainCardSlot]}
            </strong>
          </>
        ) : (
          'Toutes les cartes attendues sont renseignées.'
        )}
      </div>

      <div className="card-grid-header" aria-hidden="true">
        {['A', 'K', 'Q', 'J', '10', '9', '8', '7', '6', '5', '4', '3', '2'].map((rank) => (
          <span key={rank}>{rank}</span>
        ))}
      </div>
      <div
        className="card-grid"
        ref={gridRef}
        tabIndex={0}
        role="grid"
        aria-label="Paquet de 52 cartes. Utilisez les flèches puis Entrée."
        aria-activedescendant={`deck-card-${gridIndex}`}
      >
        {(['s', 'h', 'd', 'c'] as const).map((suit, suitIndex) => (
          <div className={`suit-row suit-${suit}`} role="row" aria-label={SUIT_LABEL[suit]} key={suit}>
            <span className="suit-name" aria-hidden="true">
              {SUIT_SYMBOL[suit]}
            </span>
            {ALL_CARDS.slice(suitIndex * 13, suitIndex * 13 + 13).map((card, rankIndex) => {
              const index = suitIndex * 13 + rankIndex;
              const disabled = usedCards.has(card) && currentCard !== card;
              const heroOwned = table.hand.hero_cards.includes(card);
              return (
                <button
                  type="button"
                  id={`deck-card-${index}`}
                  role="gridcell"
                  tabIndex={-1}
                  key={card}
                  className={`${index === gridIndex ? 'keyboard-active' : ''} ${currentCard === card ? 'current' : ''} ${heroOwned ? 'hero-owned' : ''}`}
                  disabled={disabled}
                  onMouseEnter={() => setGridIndex(index)}
                  onClick={() => void selectCard(card)}
                  aria-label={`${cardLabel(card)}${disabled ? ', déjà utilisée' : ''}${heroOwned ? ', carte de Ryanchl' : ''}`}
                >
                  <span>{RANK_LABEL[card[0] ?? ''] ?? card[0]}</span>
                  <small>{SUIT_SYMBOL[suit]}</small>
                </button>
              );
            })}
          </div>
        ))}
      </div>

      <div className="selector-actions">
        <button type="button" className="ghost" onClick={() => void undo()} title="Raccourci Z">
          ↶ Annuler
        </button>
        <button type="button" className="ghost" onClick={() => void redo()} title="Raccourci Y">
          ↷ Rétablir
        </button>
        {!centered ? (
          <details>
            <summary>Effacer…</summary>
            <div className="clear-menu">
              <button type="button" onClick={() => void clearStreet('hero')}>
                Cartes de Ryanchl
              </button>
              <button type="button" onClick={() => void clearStreet('flop')}>
                Flop
              </button>
              <button type="button" onClick={() => void clearStreet('turn')}>
                Turn
              </button>
              <button type="button" onClick={() => void clearStreet('river')}>
                River
              </button>
              <button type="button" className="danger" onClick={() => void clearStreet('all')}>
                Toute la sélection
              </button>
            </div>
          </details>
        ) : null}
      </div>
      {!centered ? (
        <details className="keyboard-help">
          <summary>Aide clavier</summary>
          <p>
            Rang puis couleur : <kbd>A</kbd> + <kbd>S</kbd> = A♠, <kbd>K</kbd> + <kbd>H</kbd> = K♥. Couleurs :
            S pique, H cœur, D carreau, C trèfle. Flèches + Entrée dans la grille.
          </p>
        </details>
      ) : null}
    </aside>
  );
}
