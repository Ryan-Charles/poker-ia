import { useEffect } from 'react';
import { ActionBar } from '../components/ActionBar';
import { AdviceHistoryPanel, AdvicePanel, QuizResultPanel } from '../components/AdvicePanel';
import { CardSelector } from '../components/CardSelector';
import { HandSummaryPanel, ShowdownPanel } from '../components/ShowdownPanel';
import { PokerTable } from '../components/PokerTable';
import { useAppStore } from '../store';
import { DecisionDrawer } from './HistoryView';

export function TableView() {
  const table = useAppStore((state) => state.table);
  const showdownCards = useAppStore((state) => state.showdownCards);
  const undo = useAppStore((state) => state.undo);
  const redo = useAppStore((state) => state.redo);
  const historyOpen = useAppStore((state) => state.adviceHistoryOpen);
  const setHistoryOpen = useAppStore((state) => state.setAdviceHistoryOpen);

  useEffect(() => {
    const shortcuts = (event: KeyboardEvent) => {
      const target = event.target;
      if (target instanceof Element && target.matches('input, textarea, select, [contenteditable="true"]'))
        return;
      if ((event as KeyboardEvent & { __pokerCardHandled?: boolean }).__pokerCardHandled) return;
      if (document.body.dataset.cardSequence === 'true') return;
      const key = event.key.toUpperCase();
      if (key === 'F') {
        const button = document.querySelector<HTMLButtonElement>('.action-fold:not(:disabled)');
        if (button) {
          event.preventDefault();
          button.click();
        }
      } else if (key === 'C') {
        const button = document.querySelector<HTMLButtonElement>('.action-passive:not(:disabled)');
        if (button) {
          event.preventDefault();
          button.click();
        }
      } else if (key === 'R') {
        const button = document.querySelector<HTMLButtonElement>('.action-aggressive:not(:disabled)');
        if (button) {
          event.preventDefault();
          button.click();
        }
      } else if (key === 'Z') {
        event.preventDefault();
        void undo();
      } else if (key === 'Y') {
        event.preventDefault();
        void redo();
      } else if (key === 'H') {
        event.preventDefault();
        setHistoryOpen(!historyOpen);
      }
    };
    window.addEventListener('keydown', shortcuts);
    return () => window.removeEventListener('keydown', shortcuts);
  }, [historyOpen, redo, setHistoryOpen, undo]);

  if (!table) {
    return (
      <main className="empty-page">
        <div className="spinner" />
        <h1>Chargement de la table…</h1>
      </main>
    );
  }
  const phase = table.hand.phase;
  const nextSlot = table.selector.next_slot;
  // Au showdown, le sélecteur doit revenir au centre tant qu'au moins un
  // adversaire éligible n'a ni révélé une paire complète ni été marqué
  // « ne montre pas » (même logique que completeOrMucked dans ShowdownPanel).
  const showdownIncomplete =
    phase === 'showdown' &&
    showdownCards !== undefined &&
    (table.hand.showdown_player_ids ?? []).some((playerId) => {
      if (playerId === 'hero') return false;
      const cards = showdownCards[playerId];
      return !(cards === null || Boolean(cards?.[0] && cards[1]));
    });
  const selectorCentered =
    (phase === 'awaiting_cards' && nextSlot !== null) ||
    (phase === 'playing' && nextSlot !== null && nextSlot.startsWith('hero')) ||
    showdownIncomplete;
  return (
    <main className={`table-page phase-${phase}`}>
      <div className="table-left-column">
        <PokerTable />
        {phase === 'showdown' ? <ShowdownPanel /> : null}
        {selectorCentered ? (
          <div className="card-selector-float">
            <CardSelector centered />
          </div>
        ) : null}
      </div>
      <div className="table-right-column">
        {!selectorCentered ? <CardSelector /> : null}
        <div className="advice-scroll-area">
          {phase === 'playing' || phase === 'awaiting_cards' ? <AdvicePanel /> : null}
          <QuizResultPanel />
          <AdviceHistoryPanel />
        </div>
      </div>
      <ActionBar />
      {phase === 'summary' || phase === 'ended' ? <HandSummaryPanel /> : null}
      <DecisionDrawer />
    </main>
  );
}
