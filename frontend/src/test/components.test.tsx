import { fireEvent, render, screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { CardSelector } from '../components/CardSelector';
import { AdviceHistoryPanel, AdvicePanel, QuizResultPanel } from '../components/AdvicePanel';
import { ActionBar } from '../components/ActionBar';
import { HandSummaryPanel, ShowdownPanel } from '../components/ShowdownPanel';
import { ConfigurationView } from '../views/ConfigurationView';
import { TableView } from '../views/TableView';
import { DEFAULT_CONFIG, useAppStore } from '../store';
import { advice, tableState } from './fixtures';

describe('interface de jeu', () => {
  beforeEach(() => {
    useAppStore.setState({
      view: 'table',
      config: DEFAULT_CONFIG,
      sessionId: 'session-1',
      table: tableState(),
      mainCards: {},
      focusedSlot: 'hero_1',
      showdownCards: undefined,
      showdownPlayerId: null,
      manualWinners: {},
      advice: null,
      adviceHistoryOpen: false,
      busy: false,
      notification: null,
    });
  });

  it('affiche en permanence les 52 cartes dans quatre lignes fixes', () => {
    render(<CardSelector />);
    const grid = screen.getByRole('grid', { name: /paquet de 52 cartes/i });
    expect(within(grid).getAllByRole('gridcell')).toHaveLength(52);
    expect(within(grid).getAllByRole('row')).toHaveLength(4);
    expect(screen.getAllByText('Carte Ryanchl 1')[0]).toBeVisible();
    expect(screen.getAllByText('River')[0]).toBeVisible();
  });

  it('n’affiche aucun emplacement adverse avant le showdown', () => {
    render(<TableView />);
    expect(screen.queryByText('Cartes réellement révélées')).not.toBeInTheDocument();
    expect(screen.queryByText(/Carte 1 de Camille/i)).not.toBeInTheDocument();
  });

  it('interprète A puis H comme As de cœur sans ouvrir l’historique', () => {
    const selectCard = vi.fn().mockResolvedValue(undefined);
    useAppStore.setState({ selectCard });
    render(<TableView />);
    fireEvent.keyDown(window, { key: 'a' });
    fireEvent.keyDown(window, { key: 'h' });
    expect(selectCard).toHaveBeenCalledWith('Ah');
    expect(useAppStore.getState().adviceHistoryOpen).toBe(false);
  });

  it('présente les sizings réels et calcule le preset 50 %', async () => {
    const user = userEvent.setup();
    useAppStore.setState({ table: tableState({ pot: 200 }) });
    render(<ActionBar />);
    await user.click(screen.getByRole('button', { name: '50 %' }));
    expect(screen.getByLabelText('Montant de la mise')).toHaveValue(100);
    expect(screen.getByText('50 % du pot')).toBeVisible();
  });

  it('valide le montant agressif avec Entrée depuis le champ de saisie', () => {
    const performAction = vi.fn().mockResolvedValue(undefined);
    useAppStore.setState({ table: tableState({ pot: 200 }), performAction });
    render(<ActionBar />);
    const input = screen.getByLabelText('Montant de la mise');

    fireEvent.change(input, { target: { value: '125' } });
    fireEvent.keyDown(input, { key: 'Enter' });

    expect(performAction).toHaveBeenCalledWith('bet', 125);
  });

  it('affiche immédiatement la comparaison complète après un choix en mode quiz', () => {
    useAppStore.setState({
      lastQuizResult: {
        handId: 'hand-1',
        handNumber: 1,
        recommendedAction: 'raise',
        recommendedAmount: 250,
        chosenAction: 'call',
        chosenAmount: 100,
        evDifference: 35,
        quality: 'acceptable',
        explanation: 'La relance conserve davantage de valeur estimée dans cette situation.',
        confidence: 0.72,
      },
    });
    render(<QuizResultPanel />);
    expect(screen.getByRole('heading', { name: /décision comparée/i })).toBeVisible();
    expect(screen.getByText('Raise · 250 jetons')).toBeVisible();
    expect(screen.getByText('Call · 100 jetons')).toBeVisible();
    expect(screen.getByText('35 jetons')).toBeVisible();
    expect(screen.getByText('Acceptable')).toBeVisible();
    expect(screen.getByText(/attente de la fin de la main/i)).toBeVisible();
  });

  it('présente les conseils figés de la session et ouvre leur détail sans recalcul', async () => {
    const user = userEvent.setup();
    const loadHistory = vi.fn().mockResolvedValue(undefined);
    const openDecision = vi.fn().mockResolvedValue(undefined);
    useAppStore.setState({
      loadHistory,
      openDecision,
      history: [
        {
          id: 'decision-1',
          hand_id: 'hand-1',
          hand_number: 1,
          date: '2026-07-16T00:00:00Z',
          street: 'preflop',
          position: 'BTN',
          hero_cards: ['As', 'Ah'],
          board: [],
          preceding_action: 'Raise',
          balanced_advice: 'Raise',
          exploitative_advice: 'Raise',
          final_advice: 'Raise',
          recommended_amount: 250,
          chosen_action: 'Call',
          ev_difference: 35,
          hand_result: 0,
          quality: 'acceptable',
          confidence: 0.72,
          opponent_ids: ['player-2'],
          effective_stack_bb: 99,
          short_explanation: 'La position et la profondeur favorisent la relance.',
          unit: 'chips',
          big_blind: 100,
        },
      ],
    });
    render(<AdviceHistoryPanel />);
    await user.click(screen.getByRole('button', { name: /Historique des conseils/ }));
    expect(screen.getByText(/Main #1 · Préflop · BTN/)).toBeVisible();
    expect(screen.getByText('Raise · 250 jetons')).toBeVisible();
    expect(screen.getByText('Call')).toBeVisible();
    expect(screen.getByText(/72 %/)).toBeVisible();
    await user.click(screen.getByRole('button', { name: /Ouvrir le détail du conseil/ }));
    expect(openDecision).toHaveBeenCalledWith('decision-1');
    expect(loadHistory).toHaveBeenCalledWith('session_id=session-1');
  });

  it('permet d’attribuer manuellement un pot à plusieurs gagnants à égalité', async () => {
    const user = userEvent.setup();
    useAppStore.setState({
      table: tableState({
        phase: 'showdown',
        street: 'showdown',
        active_player_id: null,
        hero_cards: ['As', 'Ah'],
        board: ['2c', '3d', '7h', '8c', '9d'],
        showdown_player_ids: ['hero', 'player-2'],
        side_pots: [{ index: 0, amount: 200, eligible_player_ids: ['hero', 'player-2'] }],
      }),
      showdownCards: { 'player-2': null },
      showdownPlayerId: 'player-2',
      manualWinners: {},
    });
    render(<ShowdownPanel />);
    await user.click(screen.getByRole('checkbox', { name: 'Ryanchl' }));
    await user.click(screen.getByRole('checkbox', { name: 'Camille' }));
    expect(useAppStore.getState().manualWinners[0]).toEqual(['hero', 'player-2']);
    expect(screen.getByRole('button', { name: 'Valider le showdown' })).toBeEnabled();
  });

  it('affiche les noms des joueurs (pas les ids) et masque du résumé les joueurs qui n’ont pas atteint le showdown', () => {
    useAppStore.setState({
      table: tableState({
        phase: 'summary',
        street: 'terminee',
        active_player_id: null,
        summary: {
          status: 'won',
          winners: ['player-2'],
          total_pot: 300,
          hero_contribution: 100,
          hero_received: 0,
          hero_net: -100,
          hero_net_bb: -1,
          hero_new_stack: 9800,
          session_net: -100,
          players: [
            {
              player_id: 'player-2',
              name: 'Camille',
              revealed_cards: ['Qh', 'Qd'],
              best_five: ['Qh', 'Qd', 'Jc', '9c', '7d'],
              hand_name: 'Paire de dames',
              received: 300,
              net: 200,
            },
            // Couché avant le showdown : absent de tout pot, doit être filtré du récapitulatif.
            { player_id: 'hero', name: 'Ryanchl', received: 0, net: -100 },
          ],
          pots: [
            {
              index: 0,
              amount: 300,
              eligible_player_ids: ['player-2'],
              winner_ids: ['player-2'],
              shares: { 'player-2': 300 },
            },
          ],
        },
      }),
    });
    render(<HandSummaryPanel />);
    expect(screen.getByText(/Gagnant : Camille/)).toBeVisible();
    expect(screen.queryByText('player-2')).not.toBeInTheDocument();
    // Notation anglaise des cartes (K/Q/J), pas la notation française brute ni les codes bruts.
    expect(screen.getByText('Q♥ Q♦ J♣ 9♣ 7♦')).toBeVisible();
    const results = screen.getByText('Meilleures combinaisons révélées').closest('div');
    expect(results ? within(results).queryByText('Ryanchl') : null).not.toBeInTheDocument();
  });
});

describe('conseil stratégique', () => {
  it('affiche le montant de chaque relance dans le mix et masque les entrées à 0 %', () => {
    useAppStore.setState({
      table: tableState({ active_player_id: 'hero' }),
      config: DEFAULT_CONFIG,
      quizRevealed: false,
      adviceTab: 'final',
      advice: {
        ...advice,
        final: {
          ...advice.final,
          options: [
            { action: 'raise', label: 'Raise', amount: 300, frequency: 0.26, ev: 2 },
            { action: 'raise', label: 'Raise', amount: 600, frequency: 0.08, ev: 1.5 },
            { action: 'call', label: 'Call', frequency: 0 },
          ],
        },
      },
    });
    render(<AdvicePanel />);
    expect(screen.getByText(/Raise à 300 jetons/)).toBeVisible();
    expect(screen.getByText(/Raise à 600 jetons/)).toBeVisible();
    expect(screen.queryByText(/^Call$/)).not.toBeInTheDocument();
  });
});

describe('configuration', () => {
  it('permet réellement de configurer une table de huit joueurs', () => {
    useAppStore.setState({
      view: 'configuration',
      config: DEFAULT_CONFIG,
      validationErrors: [],
      busy: false,
      sessionId: null,
    });
    render(<ConfigurationView />);
    fireEvent.change(screen.getByLabelText('Nombre maximal de sièges'), { target: { value: '8' } });
    expect(screen.getAllByText(/A priori facultatif/)).toHaveLength(7);
    expect(screen.getByDisplayValue('Ryanchl')).toBeDisabled();
  });
});
