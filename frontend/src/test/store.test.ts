import { describe, expect, it, vi } from 'vitest';
import { DEFAULT_CONFIG, loadPersistedConfig, sanitizeTableState, useAppStore } from '../store';
import { assertValidConfiguration } from '../utils';
import { tableState } from './fixtures';

describe('store Poker IA', () => {
  it('supprime toute propriété de cartes privées adverse avant le store', () => {
    const raw = tableState() as any;
    raw.players[1].private_cards = ['7h', '7d'];
    raw.players[1].hole_cards = ['7h', '7d'];
    raw.hand.revealed_hands = { 'player-2': ['7h', '7d'] };
    const clean = sanitizeTableState(raw);
    const serialized = JSON.stringify(clean);
    expect(serialized).not.toContain('private_cards');
    expect(serialized).not.toContain('hole_cards');
    expect(serialized).not.toContain('7h');
    expect(serialized).not.toContain('revealed_hands');
  });

  it('ne crée l’état de saisie adverse qu’au showdown', () => {
    useAppStore.setState({ table: tableState(), mainCards: {}, showdownCards: undefined });
    expect(useAppStore.getState().showdownCards).toBeUndefined();
    expect(JSON.stringify(useAppStore.getState().table)).not.toContain('revealed_hands');
  });

  it('refuse immédiatement une carte en double sans requête API', async () => {
    const fetchSpy = vi.spyOn(globalThis, 'fetch');
    useAppStore.setState({
      sessionId: 'session-1',
      table: tableState(),
      mainCards: { hero_1: 'As' },
      focusedSlot: 'hero_2',
      showdownCards: undefined,
      busy: false,
      notification: null,
    });
    await useAppStore.getState().selectCard('As');
    expect(fetchSpy).not.toHaveBeenCalled();
    expect(useAppStore.getState().notification?.message).toMatch(/déjà utilisée/i);
  });

  it('valide de 2 à 8 joueurs et les rôles du heads-up', () => {
    const headsUp = {
      ...DEFAULT_CONFIG,
      player_count: 2,
      players: DEFAULT_CONFIG.players.slice(0, 2),
      dealer_id: 'hero',
      small_blind_id: 'hero',
      big_blind_id: 'player-2',
    };
    expect(assertValidConfiguration(headsUp)).toEqual([]);
    expect(assertValidConfiguration({ ...headsUp, player_count: 9 })).toContain(
      'La table doit réunir de 2 à 8 joueurs.',
    );
  });

  it('restaure l’unité et le mode quiz persistés avec la session', async () => {
    const persistedConfig = {
      ...DEFAULT_CONFIG,
      unit: 'big_blinds' as const,
      small_blind: 0.5,
      big_blind: 1,
      advice_mode: 'quiz' as const,
      players: DEFAULT_CONFIG.players.map((player) => ({ ...player, stack: 100 })),
    };
    const restored = tableState();
    restored.config = persistedConfig;
    restored.hand.unit = 'big_blinds';
    restored.hand.small_blind = 50;
    restored.hand.big_blind = 100;
    const fetchSpy = vi.spyOn(globalThis, 'fetch').mockResolvedValue(
      new Response(JSON.stringify(restored), {
        status: 200,
        headers: { 'Content-Type': 'application/json' },
      }),
    );
    const loadHistory = vi.fn().mockResolvedValue(undefined);
    useAppStore.setState({ config: DEFAULT_CONFIG, loadHistory, table: null, sessionId: null });

    await useAppStore.getState().resumeSession('session-1');

    expect(fetchSpy).toHaveBeenCalledWith(
      '/api/sessions/session-1/state',
      expect.objectContaining({ headers: expect.objectContaining({ Accept: 'application/json' }) }),
    );
    expect(useAppStore.getState().config.unit).toBe('big_blinds');
    expect(useAppStore.getState().config.big_blind).toBe(1);
    expect(useAppStore.getState().config.advice_mode).toBe('quiz');
    expect(loadHistory).toHaveBeenCalledWith('session_id=session-1');
  });
});

describe('configuration de départ mémorisée', () => {
  it('retombe sur la configuration par défaut si aucune valeur n’est stockée', () => {
    localStorage.removeItem('poker-ia-config');
    expect(loadPersistedConfig()).toEqual(DEFAULT_CONFIG);
  });

  it('retombe sur la configuration par défaut si le JSON stocké est corrompu', () => {
    localStorage.setItem('poker-ia-config', '{ceci n’est pas du JSON');
    expect(loadPersistedConfig()).toEqual(DEFAULT_CONFIG);
  });

  it('restitue une configuration valide précédemment sauvegardée', () => {
    const saved = {
      ...DEFAULT_CONFIG,
      unit: 'big_blinds' as const,
      small_blind: 0.5,
      big_blind: 1,
    };
    localStorage.setItem('poker-ia-config', JSON.stringify(saved));
    expect(loadPersistedConfig()).toEqual(saved);
  });

  it('enregistre chaque changement immédiatement, sans attendre le lancement d’une session', () => {
    localStorage.removeItem('poker-ia-config');
    const changed = { ...DEFAULT_CONFIG, small_blind: 25, big_blind: 50 };

    useAppStore.getState().setConfig(changed);

    expect(JSON.parse(localStorage.getItem('poker-ia-config') ?? '{}')).toEqual(changed);
    expect(loadPersistedConfig()).toEqual(changed);
  });

  it('retombe sur la configuration par défaut si la configuration stockée est invalide', () => {
    const invalid = {
      ...DEFAULT_CONFIG,
      player_count: 1,
      players: DEFAULT_CONFIG.players.slice(0, 1),
    };
    localStorage.setItem('poker-ia-config', JSON.stringify(invalid));
    expect(loadPersistedConfig()).toEqual(DEFAULT_CONFIG);
  });
});
