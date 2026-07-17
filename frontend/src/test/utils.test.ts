import { describe, expect, it } from 'vitest';
import {
  actionVerb,
  betChipCounts,
  cardLabel,
  derivePositionsFromBigBlind,
  formatCardList,
  playerName,
  tablePosition,
} from '../utils';
import type { ActionLogEntry, PlayerConfig, PlayerState } from '../types';
import { tableState } from './fixtures';

function player(id: string, seat: number): PlayerConfig {
  return { id, name: id, seat, stack: 10_000, initial_profile: 'unknown' };
}

function playerState(id: string, seat: number, overrides: Partial<PlayerState> = {}): PlayerState {
  return {
    id,
    name: id,
    seat,
    position: 'BTN',
    stack: 10_000,
    stack_bb: 100,
    street_bet: 0,
    total_contribution: 0,
    last_action: null,
    status: 'active',
    is_dealer: false,
    is_small_blind: false,
    is_big_blind: false,
    profile: {
      initial: 'unknown',
      estimated: 'Inconnu',
      confidence: 0,
      hands_observed: 0,
      adaptation_enabled: false,
    },
    ...overrides,
  };
}

function actionEntry(
  overrides: Partial<ActionLogEntry> & Pick<ActionLogEntry, 'player_id' | 'sequence'>,
): ActionLogEntry {
  return {
    id: `entry-${overrides.sequence}`,
    street: 'flop',
    action: 'bet',
    amount: 0,
    pot_after: 0,
    player_name: overrides.player_id,
    ...overrides,
  };
}

function parsePercent(value: string): number {
  return Number(value.replace('%', ''));
}

describe('derivePositionsFromBigBlind', () => {
  it('en heads-up (2 joueurs), le bouton EST la petite blinde', () => {
    const players = [player('hero', 1), player('player-2', 2)];
    expect(derivePositionsFromBigBlind(players, 'player-2')).toEqual({
      dealer_id: 'hero',
      small_blind_id: 'hero',
      big_blind_id: 'player-2',
    });
    // BB inversée : l'autre joueur devient bouton/petite blinde.
    expect(derivePositionsFromBigBlind(players, 'hero')).toEqual({
      dealer_id: 'player-2',
      small_blind_id: 'player-2',
      big_blind_id: 'hero',
    });
  });

  it('à 3 joueurs, SB et bouton précèdent la BB en remontant les sièges', () => {
    const players = [player('hero', 1), player('player-2', 2), player('player-3', 3)];
    expect(derivePositionsFromBigBlind(players, 'player-3')).toEqual({
      dealer_id: 'hero',
      small_blind_id: 'player-2',
      big_blind_id: 'player-3',
    });
    // BB au siège 1 : on remonte circulairement (siège 3 = SB, siège 2 = bouton).
    expect(derivePositionsFromBigBlind(players, 'hero')).toEqual({
      dealer_id: 'player-2',
      small_blind_id: 'player-3',
      big_blind_id: 'hero',
    });
  });

  it('à 6 joueurs, retrouve l’ordre standard bouton/SB/BB consécutif', () => {
    const players = [1, 2, 3, 4, 5, 6].map((seat) => player(seat === 1 ? 'hero' : `player-${seat}`, seat));
    expect(derivePositionsFromBigBlind(players, 'player-6')).toEqual({
      dealer_id: 'player-4',
      small_blind_id: 'player-5',
      big_blind_id: 'player-6',
    });
    // BB déplacée au siège 3 : bouton siège 1 (hero), SB siège 2.
    expect(derivePositionsFromBigBlind(players, 'player-3')).toEqual({
      dealer_id: 'hero',
      small_blind_id: 'player-2',
      big_blind_id: 'player-3',
    });
  });
});

describe('playerName', () => {
  it('affiche toujours « Ryanchl » pour le joueur héros, quel que soit le nom stocké', () => {
    const table = tableState();
    expect(playerName(table, 'hero')).toBe('Ryanchl');
  });

  it('retrouve le nom réel d’un adversaire à partir de son id', () => {
    const table = tableState();
    expect(playerName(table, 'player-2')).toBe('Camille');
  });

  it('retombe sur l’id brut si le joueur est introuvable', () => {
    const table = tableState();
    expect(playerName(table, 'player-999')).toBe('player-999');
  });
});

describe('actionVerb', () => {
  it('traduit les actions brutes du moteur en vocabulaire poker anglais', () => {
    expect(actionVerb('fold')).toBe('Fold');
    expect(actionVerb('check')).toBe('Check');
    expect(actionVerb('call')).toBe('Call');
    expect(actionVerb('all_in_call')).toBe('Call (tapis)');
    expect(actionVerb('bet')).toBe('Raise');
    expect(actionVerb('raise')).toBe('Raise');
    expect(actionVerb('all_in')).toBe('All-in');
  });

  it('retombe sur la chaîne d’origine pour une action inconnue, et sur une chaîne vide pour null', () => {
    expect(actionVerb('grosse blinde')).toBe('grosse blinde');
    expect(actionVerb(null)).toBe('');
  });
});

describe('notation anglaise des cartes', () => {
  it('cardLabel conserve le rang anglais (K/Q/J/A) et ajoute le symbole de couleur', () => {
    expect(cardLabel('Kh')).toBe('K♥');
    expect(cardLabel('Qd')).toBe('Q♦');
    expect(cardLabel('Jc')).toBe('J♣');
    expect(cardLabel('As')).toBe('A♠');
    expect(cardLabel('Th')).toBe('10♥');
    expect(cardLabel('9c')).toBe('9♣');
  });

  it('formatCardList formate une liste de cartes séparées par des espaces', () => {
    expect(formatCardList(['Qh', 'Qd', 'Jc', '9c', '7d'])).toBe('Q♥ Q♦ J♣ 9♣ 7♦');
  });
});

describe('tablePosition', () => {
  it('place toujours hero au centre bas (left 50 %, top 96 % ou plus)', () => {
    const players = [playerState('hero', 1), playerState('player-2', 2), playerState('player-3', 3)];
    const position = tablePosition(players[0]!, players);
    expect(parsePercent(position.left)).toBeCloseTo(50, 5);
    expect(parsePercent(position.top)).toBeGreaterThanOrEqual(96);
  });

  it('garde toutes les coordonnées dans les bornes [0,100] de 2 à 8 joueurs', () => {
    for (let count = 2; count <= 8; count += 1) {
      const players = Array.from({ length: count }, (_, index) =>
        playerState(index === 0 ? 'hero' : `player-${index + 1}`, index + 1),
      );
      for (const candidate of players) {
        const position = tablePosition(candidate, players);
        const left = parsePercent(position.left);
        const top = parsePercent(position.top);
        expect(left).toBeGreaterThanOrEqual(0);
        expect(left).toBeLessThanOrEqual(100);
        expect(top).toBeGreaterThanOrEqual(0);
        expect(top).toBeLessThanOrEqual(100);
      }
    }
  });

  it('place les adversaires dans l’ordre des sièges après hero, en tournant si besoin', () => {
    // hero au siège 3 : l’ordre attendu part du siège 4 et boucle jusqu’au siège 2.
    const players = [
      playerState('player-1', 1),
      playerState('player-2', 2),
      playerState('hero', 3),
      playerState('player-4', 4),
      playerState('player-5', 5),
      playerState('player-6', 6),
    ];
    const expectedOrder = ['player-4', 'player-5', 'player-6', 'player-1', 'player-2'];
    const M = expectedOrder.length;
    expectedOrder.forEach((id, index) => {
      const theta = 145 + (250 * (index + 1 - 0.5)) / M;
      const radians = (theta * Math.PI) / 180;
      const expected = { left: 50 + 48 * Math.cos(radians), top: 50 + 48 * Math.sin(radians) };
      const candidate = players.find((entry) => entry.id === id)!;
      const position = tablePosition(candidate, players);
      expect(parsePercent(position.left)).toBeCloseTo(expected.left, 5);
      expect(parsePercent(position.top)).toBeCloseTo(expected.top, 5);
    });
  });
});

describe('betChipCounts', () => {
  it('blindes seules (aucune entrée de journal) : 1 jeton pour SB et BB', () => {
    const players = [
      playerState('sb', 1, { street_bet: 50, is_small_blind: true }),
      playerState('bb', 2, { street_bet: 100, is_big_blind: true }),
    ];
    expect(betChipCounts([], 'preflop', 100, players)).toEqual({ sb: 1, bb: 1 });
  });

  it('bet puis call : 1 jeton chacun', () => {
    const players = [playerState('a', 1, { street_bet: 100 }), playerState('b', 2, { street_bet: 100 })];
    const log: ActionLogEntry[] = [
      actionEntry({ player_id: 'a', sequence: 1, street: 'flop', action: 'bet', amount: 100 }),
      actionEntry({ player_id: 'b', sequence: 2, street: 'flop', action: 'call', amount: 100 }),
    ];
    expect(betChipCounts(log, 'flop', 100, players)).toEqual({ a: 1, b: 1 });
  });

  it('bet puis raise puis call : le relanceur affiche un jeton de plus que le miseur', () => {
    const players = [playerState('a', 1, { street_bet: 300 }), playerState('b', 2, { street_bet: 300 })];
    const log: ActionLogEntry[] = [
      actionEntry({ player_id: 'a', sequence: 1, street: 'flop', action: 'bet', amount: 100 }),
      actionEntry({ player_id: 'b', sequence: 2, street: 'flop', action: 'raise', amount: 300 }),
      actionEntry({ player_id: 'a', sequence: 3, street: 'flop', action: 'call', amount: 200 }),
    ];
    expect(betChipCounts(log, 'flop', 100, players)).toEqual({ a: 1, b: 2 });
  });

  it('bet puis raise puis re-raise : chaque relance ajoute un jeton', () => {
    const players = [playerState('a', 1, { street_bet: 700 }), playerState('b', 2, { street_bet: 300 })];
    const log: ActionLogEntry[] = [
      actionEntry({ player_id: 'a', sequence: 1, street: 'flop', action: 'bet', amount: 100 }),
      actionEntry({ player_id: 'b', sequence: 2, street: 'flop', action: 'raise', amount: 300 }),
      actionEntry({ player_id: 'a', sequence: 3, street: 'flop', action: 'raise', amount: 600 }),
    ];
    expect(betChipCounts(log, 'flop', 100, players)).toEqual({ a: 3, b: 2 });
  });
});
