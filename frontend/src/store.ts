import { create } from 'zustand';
import { api, ApiError } from './api';
import {
  MAIN_CARD_SLOTS,
  type Advice,
  type Card,
  type CardSlot,
  type DecisionDetail,
  type ExitReport,
  type HistoryDecision,
  type LegalAction,
  type MainCardSlot,
  type OpponentProfile,
  type SessionConfig,
  type TableState,
  type ViewName,
} from './types';
import {
  assertValidConfiguration,
  configurationForApi,
  derivePositionsFromBigBlind,
  nextEmptySlot,
} from './utils';

const DEFAULT_PLAYERS = [
  { id: 'hero', name: 'Ryanchl', seat: 1, stack: 10_000, initial_profile: 'unknown' as const },
  { id: 'player-2', name: 'Camille', seat: 2, stack: 10_000, initial_profile: 'unknown' as const },
  { id: 'player-3', name: 'Alex', seat: 3, stack: 10_000, initial_profile: 'unknown' as const },
  { id: 'player-4', name: 'Sacha', seat: 4, stack: 10_000, initial_profile: 'unknown' as const },
  { id: 'player-5', name: 'Morgan', seat: 5, stack: 10_000, initial_profile: 'unknown' as const },
  { id: 'player-6', name: 'Charlie', seat: 6, stack: 10_000, initial_profile: 'unknown' as const },
  { id: 'player-7', name: 'Dominique', seat: 7, stack: 10_000, initial_profile: 'unknown' as const },
  { id: 'player-8', name: 'Noa', seat: 8, stack: 10_000, initial_profile: 'unknown' as const },
];

export const DEFAULT_CONFIG: SessionConfig = {
  player_count: 6,
  players: DEFAULT_PLAYERS.slice(0, 6),
  unit: 'chips',
  small_blind: 50,
  big_blind: 100,
  ante: 0,
  ante_type: 'classic',
  game_mode: 'cash',
  dealer_id: 'player-4',
  small_blind_id: 'player-5',
  big_blind_id: 'player-6',
  blind_levels: [],
  advice_mode: 'immediate',
};

type ShowdownCards = Record<string, [Card | undefined, Card | undefined] | null>;

interface Notification {
  kind: 'error' | 'success' | 'info';
  message: string;
}

export interface QuizResult {
  handId: string;
  handNumber: number;
  recommendedAction: LegalAction['action'];
  recommendedAmount: number | undefined;
  chosenAction: LegalAction['action'];
  chosenAmount: number | undefined;
  evDifference: number;
  quality: 'excellent' | 'acceptable' | 'questionable' | 'mistake';
  explanation: string;
  confidence: number;
}

interface AppStore {
  view: ViewName;
  config: SessionConfig;
  validationErrors: string[];
  sessionId: string | null;
  table: TableState | null;
  mainCards: Partial<Record<MainCardSlot, Card>>;
  focusedSlot: CardSlot | null;
  showdownCards: ShowdownCards | undefined;
  showdownPlayerId: string | null;
  manualWinners: Record<number, string[]>;
  advice: Advice | null;
  adviceTab: 'balanced' | 'exploitative' | 'final';
  quizRevealed: boolean;
  lastQuizResult: QuizResult | null;
  adviceHistoryOpen: boolean;
  busy: boolean;
  analysisBusy: boolean;
  saveStatus: 'saved' | 'saving' | 'error';
  notification: Notification | null;
  history: HistoryDecision[];
  selectedDecision: DecisionDetail | null;
  opponents: OpponentProfile[];
  selectedOpponentId: string | null;
  exitReport: ExitReport | null;
  expertController: AbortController | null;
  setView: (view: ViewName) => void;
  setConfig: (config: SessionConfig) => void;
  setPlayerCount: (count: number) => void;
  setNotification: (notification: Notification | null) => void;
  setFocusedSlot: (slot: CardSlot | null) => void;
  setAdviceTab: (tab: 'balanced' | 'exploitative' | 'final') => void;
  setAdviceHistoryOpen: (open: boolean) => void;
  dismissQuizResult: () => void;
  createSession: () => Promise<void>;
  resumeSession: (sessionId?: string) => Promise<void>;
  refreshState: () => Promise<void>;
  performAction: (action: string, amount?: number) => Promise<void>;
  selectCard: (card: Card) => Promise<void>;
  clearCard: (slot: CardSlot) => Promise<void>;
  clearStreet: (street: 'hero' | 'flop' | 'turn' | 'river' | 'all') => Promise<void>;
  undo: () => Promise<void>;
  redo: () => Promise<void>;
  restartHand: () => Promise<void>;
  fetchAdvice: (force?: boolean) => Promise<void>;
  setShowdownMucked: (playerId: string, mucked: boolean) => void;
  setShowdownPlayer: (playerId: string) => void;
  setManualWinner: (potIndex: number, playerId: string) => void;
  submitShowdown: () => Promise<void>;
  nextHand: () => Promise<void>;
  updatePlayer: (
    playerId: string,
    changes: { name?: string; stack?: number; status?: string },
  ) => Promise<boolean>;
  replacePlayer: (
    playerId: string,
    changes: { name: string; stack?: number; initial_profile?: string },
  ) => Promise<boolean>;
  removePlayer: (playerId: string) => Promise<boolean>;
  seatPlayer: (
    playerId: string,
    changes: { name: string; stack: number; initial_profile?: string; custom_profile?: string },
  ) => Promise<boolean>;
  saveSession: () => Promise<void>;
  exitSession: () => Promise<void>;
  loadHistory: (query?: string) => Promise<void>;
  openDecision: (id: string) => Promise<void>;
  closeDecision: () => void;
  runExpertAnalysis: (id: string) => Promise<void>;
  cancelExpertAnalysis: () => void;
  loadOpponents: () => Promise<void>;
  selectOpponent: (id: string | null) => void;
  updateOpponent: (id: string, changes: { notes?: string; adaptation_enabled?: boolean }) => Promise<void>;
  resetOpponent: (id: string) => Promise<void>;
  mergeOpponents: (sourceId: string, targetId: string) => Promise<void>;
  importData: (data: unknown) => Promise<void>;
  deleteAllData: () => Promise<void>;
}

function errorMessage(error: unknown): string {
  if (error instanceof ApiError || error instanceof Error) return error.message;
  return 'Une erreur inattendue est survenue.';
}

function normalizeLegalActions(value: unknown): LegalAction[] {
  if (Array.isArray(value)) return value as LegalAction[];
  if (!value || typeof value !== 'object') return [];
  return Object.entries(value).map(([action, details]) => {
    if (typeof details === 'boolean') return { action: action as LegalAction['action'], enabled: details };
    return { action: action as LegalAction['action'], ...(details as Omit<LegalAction, 'action'>) };
  });
}

// Copie explicite: toute propriété de cartes privées injectée sur un adversaire par une API
// défectueuse est éliminée avant d'entrer dans le store ou le DOM.
export function sanitizeTableState(raw: TableState): TableState {
  const phase = raw.hand.phase;
  return {
    session_id: raw.session_id,
    ...(raw.config ? { config: raw.config } : {}),
    hand: {
      id: raw.hand.id,
      number: raw.hand.number,
      street: raw.hand.street,
      phase,
      unit: raw.hand.unit,
      small_blind: raw.hand.small_blind,
      big_blind: raw.hand.big_blind,
      ante: raw.hand.ante,
      pot: raw.hand.pot,
      side_pots: raw.hand.side_pots ?? [],
      to_call: raw.hand.to_call,
      current_bet: raw.hand.current_bet,
      last_full_raise: raw.hand.last_full_raise,
      active_player_id: raw.hand.active_player_id,
      players_remaining: raw.hand.players_remaining,
      board: raw.hand.board ?? [],
      hero_cards: raw.hand.hero_cards ?? [],
      action_log: raw.hand.action_log ?? [],
      ...(phase === 'showdown' && raw.hand.showdown_player_ids
        ? { showdown_player_ids: raw.hand.showdown_player_ids }
        : {}),
      ...(phase === 'summary' || phase === 'ended'
        ? raw.hand.summary
          ? { summary: raw.hand.summary }
          : {}
        : {}),
    },
    players: (raw.players ?? []).map((player) => ({
      id: player.id,
      name: player.id === 'hero' ? 'Ryanchl' : player.name,
      seat: player.seat,
      position: player.position,
      stack: player.stack,
      stack_bb: player.stack_bb,
      street_bet: player.street_bet,
      total_contribution: player.total_contribution,
      last_action: player.last_action,
      status: player.status,
      pending_join: player.pending_join ?? false,
      is_dealer: player.is_dealer,
      is_small_blind: player.is_small_blind,
      is_big_blind: player.is_big_blind,
      profile: player.profile,
    })),
    legal_actions: normalizeLegalActions(raw.legal_actions),
    selector: raw.selector ?? { next_slot: null, required_slots: [] },
    ...(raw.advice ? { advice: raw.advice } : {}),
    persistence_status: raw.persistence_status ?? 'saved',
  };
}

function cardsFromTable(table: TableState): Partial<Record<MainCardSlot, Card>> {
  const cards: Partial<Record<MainCardSlot, Card>> = {};
  if (table.hand.hero_cards[0]) cards.hero_1 = table.hand.hero_cards[0];
  if (table.hand.hero_cards[1]) cards.hero_2 = table.hand.hero_cards[1];
  if (table.hand.board[0]) cards.flop_1 = table.hand.board[0];
  if (table.hand.board[1]) cards.flop_2 = table.hand.board[1];
  if (table.hand.board[2]) cards.flop_3 = table.hand.board[2];
  if (table.hand.board[3]) cards.turn = table.hand.board[3];
  if (table.hand.board[4]) cards.river = table.hand.board[4];
  return cards;
}

function shouldFetchAdvice(table: TableState | null | undefined): table is TableState {
  return table?.hand.active_player_id === 'hero' && table.hand.hero_cards.length === 2;
}

let adviceController: AbortController | null = null;

function cancelAdviceRequest(): void {
  adviceController?.abort();
  adviceController = null;
}

function nextShowdownPlayer(table: TableState, cards: ShowdownCards): string | null {
  return (
    table.hand.showdown_player_ids?.find((id) => id !== 'hero' && cards[id] === undefined) ??
    table.hand.showdown_player_ids?.find(
      (id) => id !== 'hero' && cards[id] !== null && cards[id]?.some((card) => !card),
    ) ??
    null
  );
}

function stateUpdateFromTable(raw: TableState): Partial<AppStore> {
  const table = sanitizeTableState(raw);
  if (table.config) persistConfig(table.config);
  const mainCards = cardsFromTable(table);
  const isShowdown = table.hand.phase === 'showdown';
  const showdownCards: ShowdownCards | undefined = isShowdown ? {} : undefined;
  const showdownPlayerId = isShowdown && showdownCards ? nextShowdownPlayer(table, showdownCards) : null;
  const focus = isShowdown
    ? showdownPlayerId
      ? (`showdown:${showdownPlayerId}:1` as CardSlot)
      : null
    : (table.selector.next_slot ?? nextEmptySlot(mainCards, table.selector.required_slots));
  return {
    table,
    ...(table.config ? { config: table.config } : {}),
    sessionId: table.session_id,
    mainCards,
    focusedSlot: focus,
    showdownCards,
    showdownPlayerId,
    advice: table.advice ?? null,
    saveStatus: table.persistence_status,
  };
}

function persistSessionId(sessionId: string | null): void {
  if (sessionId) localStorage.setItem('poker-ia-session', sessionId);
  else localStorage.removeItem('poker-ia-session');
}

const CONFIG_STORAGE_KEY = 'poker-ia-config';

function persistConfig(config: SessionConfig): void {
  try {
    localStorage.setItem(CONFIG_STORAGE_KEY, JSON.stringify(config));
  } catch {
    // Le stockage local indisponible ne doit jamais bloquer la table.
  }
}

function hasPlausibleConfigShape(value: unknown): value is SessionConfig {
  if (!value || typeof value !== 'object') return false;
  const candidate = value as Record<string, unknown>;
  return (
    Array.isArray(candidate.players) &&
    candidate.players.length > 0 &&
    typeof candidate.player_count === 'number'
  );
}

/**
 * Relit la configuration de départ mémorisée localement. Toute anomalie
 * (absence, JSON corrompu, forme inattendue ou configuration invalide au
 * sens métier) retombe silencieusement sur la configuration par défaut
 * plutôt que de bloquer le démarrage de l'application.
 */
export function loadPersistedConfig(): SessionConfig {
  try {
    const raw = localStorage.getItem(CONFIG_STORAGE_KEY);
    if (!raw) return DEFAULT_CONFIG;
    const parsed: unknown = JSON.parse(raw);
    if (!hasPlausibleConfigShape(parsed)) return DEFAULT_CONFIG;
    if (assertValidConfiguration(parsed).length > 0) return DEFAULT_CONFIG;
    return parsed;
  } catch {
    return DEFAULT_CONFIG;
  }
}

export const useAppStore = create<AppStore>((set, get) => ({
  view: 'configuration',
  config: loadPersistedConfig(),
  validationErrors: [],
  sessionId: null,
  table: null,
  mainCards: {},
  focusedSlot: 'hero_1',
  showdownCards: undefined,
  showdownPlayerId: null,
  manualWinners: {},
  advice: null,
  adviceTab: 'final',
  quizRevealed: false,
  lastQuizResult: null,
  adviceHistoryOpen: false,
  busy: false,
  analysisBusy: false,
  saveStatus: 'saved',
  notification: null,
  history: [],
  selectedDecision: null,
  opponents: [],
  selectedOpponentId: null,
  exitReport: null,
  expertController: null,

  setView: (view) => {
    set({ view });
    if (view === 'historique') void get().loadHistory();
    if (view === 'adversaires') void get().loadOpponents();
  },
  setConfig: (config) => {
    persistConfig(config);
    set({ config, validationErrors: [] });
  },
  setPlayerCount: (count) => {
    const playerCount = Math.min(8, Math.max(2, count));
    const current = get().config;
    const players = DEFAULT_PLAYERS.slice(0, playerCount).map(
      (fallback, index) => current.players[index] ?? fallback,
    );
    const bigBlindId = players[playerCount - 1]?.id ?? 'player-2';
    const positions = derivePositionsFromBigBlind(players, bigBlindId);
    const config = { ...current, player_count: playerCount, players, ...positions };
    persistConfig(config);
    set({
      config,
      validationErrors: [],
    });
  },
  setNotification: (notification) => set({ notification }),
  setFocusedSlot: (focusedSlot) => set({ focusedSlot }),
  setAdviceTab: (adviceTab) => set({ adviceTab }),
  setAdviceHistoryOpen: (adviceHistoryOpen) => set({ adviceHistoryOpen }),
  dismissQuizResult: () => set({ lastQuizResult: null }),

  createSession: async () => {
    const config = get().config;
    const validationErrors = assertValidConfiguration(config);
    if (validationErrors.length > 0) {
      set({ validationErrors });
      return;
    }
    set({ busy: true, notification: null });
    try {
      const response = await api.createSession(configurationForApi(config));
      const table = 'state' in response ? response.state : response;
      const nextState = stateUpdateFromTable(table);
      persistSessionId(table.session_id);
      persistConfig(config);
      set({
        ...nextState,
        view: 'table',
        busy: false,
        quizRevealed: false,
        lastQuizResult: null,
        history: [],
        selectedDecision: null,
        validationErrors: [],
      });
      if (shouldFetchAdvice(table)) void get().fetchAdvice();
    } catch (error) {
      set({ busy: false, notification: { kind: 'error', message: errorMessage(error) } });
    }
  },
  resumeSession: async (providedId) => {
    const sessionId = providedId ?? localStorage.getItem('poker-ia-session');
    if (!sessionId) return;
    set({ busy: true, notification: null });
    try {
      const table = await api.getState(sessionId);
      set({
        ...stateUpdateFromTable(table),
        view: 'table',
        busy: false,
        lastQuizResult: null,
        selectedDecision: null,
      });
      void get().loadHistory(`session_id=${encodeURIComponent(sessionId)}`);
      if (shouldFetchAdvice(table)) void get().fetchAdvice();
    } catch (error) {
      persistSessionId(null);
      set({ busy: false, notification: { kind: 'error', message: errorMessage(error) } });
    }
  },
  refreshState: async () => {
    const { sessionId } = get();
    if (!sessionId) return;
    try {
      const table = await api.getState(sessionId);
      set(stateUpdateFromTable(table));
    } catch (error) {
      set({ notification: { kind: 'error', message: errorMessage(error) } });
    }
  },
  performAction: async (action, amount) => {
    const { sessionId, busy, table, config } = get();
    if (!sessionId || busy) return;
    cancelAdviceRequest();
    const wasHero = table?.hand.active_player_id === 'hero';
    const adviceBeforeAction = wasHero ? get().advice : null;
    set({ busy: true, notification: null, saveStatus: 'saving' });
    try {
      const next = await api.action(sessionId, action, amount);
      const quizResult =
        wasHero && config.advice_mode === 'quiz' && adviceBeforeAction && table
          ? (() => {
              const matching = adviceBeforeAction.final.options
                .filter((option) => option.action === action)
                .sort(
                  (left, right) =>
                    Math.abs((left.amount ?? 0) - (amount ?? left.amount ?? 0)) -
                    Math.abs((right.amount ?? 0) - (amount ?? right.amount ?? 0)),
                )[0];
              const bestEv = Math.max(
                ...adviceBeforeAction.final.options.map((option) => option.ev ?? Number.NEGATIVE_INFINITY),
              );
              const evDifference =
                Number.isFinite(bestEv) && matching?.ev !== undefined ? Math.max(0, bestEv - matching.ev) : 0;
              const scale = table.hand.big_blind;
              const quality =
                evDifference <= 0.02 * scale
                  ? 'excellent'
                  : evDifference <= 0.1 * scale
                    ? 'acceptable'
                    : evDifference <= 0.3 * scale
                      ? 'questionable'
                      : 'mistake';
              return {
                handId: table.hand.id,
                handNumber: table.hand.number,
                recommendedAction: adviceBeforeAction.final.action,
                recommendedAmount: adviceBeforeAction.final.amount,
                chosenAction: action as LegalAction['action'],
                chosenAmount: amount,
                evDifference,
                quality,
                explanation: adviceBeforeAction.final.explanation ?? adviceBeforeAction.final.headline,
                confidence: adviceBeforeAction.final.confidence,
              } satisfies QuizResult;
            })()
          : null;
      set({
        ...stateUpdateFromTable(next),
        busy: false,
        quizRevealed: wasHero && config.advice_mode === 'quiz',
        ...(quizResult ? { lastQuizResult: quizResult } : {}),
      });
      if (wasHero) void get().loadHistory(`session_id=${encodeURIComponent(sessionId)}`);
      if (shouldFetchAdvice(next)) void get().fetchAdvice();
    } catch (error) {
      set({
        busy: false,
        saveStatus: 'error',
        notification: { kind: 'error', message: errorMessage(error) },
      });
    }
  },
  selectCard: async (card) => {
    const { sessionId, focusedSlot, mainCards, showdownCards, table, busy } = get();
    if (!sessionId || !focusedSlot || busy || !table) return;
    const used = new Set<Card>(
      Object.values(mainCards).filter((value): value is Card => value !== undefined),
    );
    if (showdownCards) {
      Object.values(showdownCards).forEach((cards) => cards?.forEach((value) => value && used.add(value)));
    }
    const current = focusedSlot.startsWith('showdown:')
      ? (() => {
          const [, playerId, index] = focusedSlot.split(':');
          return showdownCards?.[playerId ?? '']?.[Number(index) - 1];
        })()
      : mainCards[focusedSlot as MainCardSlot];
    if (used.has(card) && current !== card) {
      set({ notification: { kind: 'error', message: 'Cette carte est déjà utilisée dans cette main.' } });
      return;
    }
    if (focusedSlot.startsWith('showdown:')) {
      if (table.hand.phase !== 'showdown' || !showdownCards) return;
      const [, playerId, indexText] = focusedSlot.split(':');
      if (!playerId) return;
      const index = Number(indexText) - 1;
      const previous = showdownCards[playerId] ?? [undefined, undefined];
      const nextPair: [Card | undefined, Card | undefined] = [...previous];
      nextPair[index] = card;
      const nextCards = { ...showdownCards, [playerId]: nextPair };
      const nextFocus = !nextPair[1]
        ? (`showdown:${playerId}:2` as CardSlot)
        : (() => {
            const nextPlayer = nextShowdownPlayer(table, nextCards);
            return nextPlayer ? (`showdown:${nextPlayer}:1` as CardSlot) : null;
          })();
      set({
        showdownCards: nextCards,
        showdownPlayerId: nextShowdownPlayer(table, nextCards),
        focusedSlot: nextFocus,
        manualWinners: {},
      });
      return;
    }
    const slot = focusedSlot as MainCardSlot;
    const optimistic = { ...mainCards, [slot]: card };
    set({
      mainCards: optimistic,
      focusedSlot: nextEmptySlot(
        optimistic,
        table.selector.required_slots.length ? table.selector.required_slots : MAIN_CARD_SLOTS,
      ),
      saveStatus: 'saving',
      notification: null,
    });
    try {
      const next = await api.setCard(sessionId, slot, card);
      set(stateUpdateFromTable(next));
      if (shouldFetchAdvice(next)) void get().fetchAdvice();
    } catch (error) {
      set({ mainCards, saveStatus: 'error', notification: { kind: 'error', message: errorMessage(error) } });
    }
  },
  clearCard: async (slot) => {
    const { sessionId, mainCards, showdownCards, table } = get();
    if (!sessionId || !table) return;
    if (slot.startsWith('showdown:')) {
      if (table.hand.phase !== 'showdown' || !showdownCards) return;
      const [, playerId, indexText] = slot.split(':');
      if (!playerId) return;
      const pair = showdownCards[playerId] ?? [undefined, undefined];
      const nextPair: [Card | undefined, Card | undefined] = [...pair];
      nextPair[Number(indexText) - 1] = undefined;
      set({
        showdownCards: { ...showdownCards, [playerId]: nextPair },
        focusedSlot: slot,
        manualWinners: {},
      });
      return;
    }
    const previous = mainCards;
    const next = { ...mainCards };
    delete next[slot as MainCardSlot];
    set({ mainCards: next, focusedSlot: slot, saveStatus: 'saving' });
    try {
      set(stateUpdateFromTable(await api.deleteCard(sessionId, slot)));
    } catch (error) {
      set({
        mainCards: previous,
        saveStatus: 'error',
        notification: { kind: 'error', message: errorMessage(error) },
      });
    }
  },
  clearStreet: async (street) => {
    const slots: MainCardSlot[] =
      street === 'hero'
        ? ['hero_1', 'hero_2']
        : street === 'flop'
          ? ['flop_1', 'flop_2', 'flop_3']
          : street === 'turn'
            ? ['turn']
            : street === 'river'
              ? ['river']
              : [...MAIN_CARD_SLOTS];
    for (const slot of slots.filter((candidate) => get().mainCards[candidate] !== undefined))
      await get().clearCard(slot);
  },
  undo: async () => {
    const { sessionId, table } = get();
    if (!sessionId || !table) return;
    try {
      set(stateUpdateFromTable(await api.undo(sessionId)));
    } catch (error) {
      set({ notification: { kind: 'error', message: errorMessage(error) } });
    }
  },
  redo: async () => {
    const { sessionId, table } = get();
    if (!sessionId || !table) return;
    try {
      set(stateUpdateFromTable(await api.redo(sessionId)));
    } catch (error) {
      set({ notification: { kind: 'error', message: errorMessage(error) } });
    }
  },
  restartHand: async () => {
    const { sessionId, table } = get();
    if (!sessionId || !table) return;
    try {
      const next = await api.restartHand(sessionId);
      set({
        ...stateUpdateFromTable(next),
        showdownCards: undefined,
        showdownPlayerId: null,
        manualWinners: {},
        lastQuizResult: null,
        quizRevealed: false,
      });
    } catch (error) {
      set({ notification: { kind: 'error', message: errorMessage(error) } });
    }
  },
  fetchAdvice: async (force = false) => {
    const { sessionId, table } = get();
    if (!sessionId || !shouldFetchAdvice(table)) return;
    cancelAdviceRequest();
    const controller = new AbortController();
    adviceController = controller;
    try {
      const advice = force
        ? await api.refreshAdvice(sessionId, controller.signal)
        : await api.getAdvice(sessionId, controller.signal);
      if (controller.signal.aborted || get().sessionId !== sessionId || !shouldFetchAdvice(get().table))
        return;
      set({ advice });
      void get().loadHistory(`session_id=${encodeURIComponent(sessionId)}`);
      if (advice.explanation_pending) {
        window.setTimeout(() => {
          if (get().sessionId === sessionId && shouldFetchAdvice(get().table)) void get().fetchAdvice();
        }, 900);
      }
    } catch (error) {
      if (controller.signal.aborted) return;
      if (error instanceof ApiError && error.status === 409) return;
      set({ notification: { kind: 'error', message: errorMessage(error) } });
    } finally {
      if (adviceController === controller) adviceController = null;
    }
  },
  setShowdownMucked: (playerId, mucked) => {
    const showdownCards = get().showdownCards;
    if (!showdownCards) return;
    set({
      showdownCards: { ...showdownCards, [playerId]: mucked ? null : [undefined, undefined] },
      manualWinners: {},
    });
  },
  setShowdownPlayer: (playerId) =>
    set({ showdownPlayerId: playerId, focusedSlot: `showdown:${playerId}:1` as CardSlot }),
  setManualWinner: (potIndex, playerId) =>
    set((state) => {
      const current = state.manualWinners[potIndex] ?? [];
      const next = current.includes(playerId)
        ? current.filter((candidate) => candidate !== playerId)
        : [...current, playerId];
      const manualWinners = { ...state.manualWinners };
      if (next.length) manualWinners[potIndex] = next;
      else delete manualWinners[potIndex];
      return { manualWinners };
    }),
  submitShowdown: async () => {
    const { sessionId, showdownCards, manualWinners } = get();
    if (!sessionId || !showdownCards) return;
    const revealed: Record<string, [string, string] | null> = {};
    for (const [playerId, pair] of Object.entries(showdownCards)) {
      if (pair === null) revealed[playerId] = null;
      else if (pair[0] && pair[1]) revealed[playerId] = [pair[0], pair[1]];
    }
    set({ busy: true, notification: null });
    try {
      const next = await api.submitShowdown(
        sessionId,
        revealed,
        Object.keys(manualWinners).length ? manualWinners : undefined,
      );
      set({ ...stateUpdateFromTable(next), busy: false, showdownCards: undefined, showdownPlayerId: null });
    } catch (error) {
      set({ busy: false, notification: { kind: 'error', message: errorMessage(error) } });
    }
  },
  nextHand: async () => {
    const { sessionId } = get();
    if (!sessionId) return;
    set({ busy: true, notification: null });
    try {
      const next = await api.nextHand(sessionId);
      set({
        ...stateUpdateFromTable(next),
        busy: false,
        quizRevealed: false,
        lastQuizResult: null,
        manualWinners: {},
      });
      if (shouldFetchAdvice(next)) void get().fetchAdvice();
    } catch (error) {
      set({ busy: false, notification: { kind: 'error', message: errorMessage(error) } });
    }
  },
  updatePlayer: async (playerId, changes) => {
    const { sessionId } = get();
    if (!sessionId) return false;
    try {
      set(stateUpdateFromTable(await api.updatePlayer(sessionId, playerId, changes)));
      set({ notification: { kind: 'success', message: 'Joueur mis à jour.' } });
      return true;
    } catch (error) {
      set({ notification: { kind: 'error', message: errorMessage(error) } });
      return false;
    }
  },
  replacePlayer: async (playerId, changes) => {
    const { sessionId } = get();
    if (!sessionId) return false;
    try {
      set(stateUpdateFromTable(await api.replacePlayer(sessionId, playerId, changes)));
      set({ notification: { kind: 'success', message: 'Joueur remplacé.' } });
      return true;
    } catch (error) {
      set({ notification: { kind: 'error', message: errorMessage(error) } });
      return false;
    }
  },
  removePlayer: async (playerId) => {
    const { sessionId } = get();
    if (!sessionId) return false;
    try {
      set(stateUpdateFromTable(await api.removePlayer(sessionId, playerId)));
      set({ notification: { kind: 'success', message: 'Siège libéré.' } });
      return true;
    } catch (error) {
      set({ notification: { kind: 'error', message: errorMessage(error) } });
      return false;
    }
  },
  seatPlayer: async (playerId, changes) => {
    const { sessionId } = get();
    if (!sessionId) return false;
    try {
      set(stateUpdateFromTable(await api.seatPlayer(sessionId, playerId, changes)));
      set({
        notification: {
          kind: 'success',
          message: `${changes.name} prendra place à la prochaine main.`,
        },
      });
      return true;
    } catch (error) {
      set({ notification: { kind: 'error', message: errorMessage(error) } });
      return false;
    }
  },
  saveSession: async () => {
    const { sessionId } = get();
    if (!sessionId) return;
    set({ saveStatus: 'saving' });
    try {
      await api.saveSession(sessionId);
      set({
        saveStatus: 'saved',
        notification: { kind: 'success', message: 'Session sauvegardée localement.' },
      });
    } catch (error) {
      set({ saveStatus: 'error', notification: { kind: 'error', message: errorMessage(error) } });
    }
  },
  exitSession: async () => {
    const { sessionId } = get();
    if (!sessionId) return;
    set({ busy: true, notification: null });
    try {
      const exitReport = await api.exitSession(sessionId);
      persistSessionId(null);
      set({
        exitReport,
        sessionId: null,
        table: null,
        advice: null,
        mainCards: {},
        focusedSlot: 'hero_1',
        showdownCards: undefined,
        showdownPlayerId: null,
        manualWinners: {},
        history: [],
        selectedDecision: null,
        lastQuizResult: null,
        quizRevealed: false,
        adviceHistoryOpen: false,
        busy: false,
        view: 'configuration',
        notification: {
          kind: 'success',
          message: 'Table clôturée et sauvegardée. Configurez une nouvelle table.',
        },
      });
    } catch (error) {
      set({ busy: false, notification: { kind: 'error', message: errorMessage(error) } });
    }
  },
  loadHistory: async (query = '') => {
    try {
      set({ history: await api.history(query) });
    } catch (error) {
      set({ notification: { kind: 'error', message: errorMessage(error) } });
    }
  },
  openDecision: async (id) => {
    set({ analysisBusy: true });
    try {
      set({ selectedDecision: await api.historyDetail(id), analysisBusy: false });
    } catch (error) {
      set({ analysisBusy: false, notification: { kind: 'error', message: errorMessage(error) } });
    }
  },
  closeDecision: () => set({ selectedDecision: null }),
  runExpertAnalysis: async (id) => {
    const controller = new AbortController();
    set({ expertController: controller, analysisBusy: true });
    try {
      const selectedDecision = await api.expertAnalysis(id, controller.signal);
      set({ selectedDecision, analysisBusy: false, expertController: null });
    } catch (error) {
      if (!controller.signal.aborted)
        set({
          notification: { kind: 'error', message: errorMessage(error) },
          analysisBusy: false,
          expertController: null,
        });
    }
  },
  cancelExpertAnalysis: () => {
    get().expertController?.abort();
    set({
      expertController: null,
      analysisBusy: false,
      notification: { kind: 'info', message: 'Analyse experte annulée.' },
    });
  },
  loadOpponents: async () => {
    try {
      set({ opponents: await api.opponents() });
    } catch (error) {
      set({ notification: { kind: 'error', message: errorMessage(error) } });
    }
  },
  selectOpponent: (selectedOpponentId) => set({ selectedOpponentId }),
  updateOpponent: async (id, changes) => {
    try {
      const updated = await api.updateOpponent(id, changes);
      set((state) => ({
        opponents: state.opponents.map((opponent) => (opponent.id === id ? updated : opponent)),
        notification: { kind: 'success', message: 'Fiche adverse enregistrée.' },
      }));
    } catch (error) {
      set({ notification: { kind: 'error', message: errorMessage(error) } });
    }
  },
  resetOpponent: async (id) => {
    try {
      const updated = await api.resetOpponent(id);
      set((state) => ({
        opponents: state.opponents.map((opponent) => (opponent.id === id ? updated : opponent)),
        notification: { kind: 'success', message: 'Apprentissage de cet adversaire réinitialisé.' },
      }));
    } catch (error) {
      set({ notification: { kind: 'error', message: errorMessage(error) } });
    }
  },
  mergeOpponents: async (sourceId, targetId) => {
    try {
      await api.mergeOpponents(sourceId, targetId);
      await get().loadOpponents();
      set({ notification: { kind: 'success', message: 'Profils fusionnés.' } });
    } catch (error) {
      set({ notification: { kind: 'error', message: errorMessage(error) } });
    }
  },
  importData: async (data) => {
    try {
      const result = await api.importData(data);
      if (result.session_id) persistSessionId(result.session_id);
      set({ notification: { kind: 'success', message: 'Données importées et contrôlées.' } });
      if (result.session_id) await get().resumeSession(result.session_id);
    } catch (error) {
      set({ notification: { kind: 'error', message: errorMessage(error) } });
    }
  },
  deleteAllData: async () => {
    try {
      await api.deleteAllData();
      persistSessionId(null);
      set({
        sessionId: null,
        table: null,
        history: [],
        opponents: [],
        view: 'configuration',
        notification: { kind: 'success', message: 'Toutes les données locales ont été supprimées.' },
      });
    } catch (error) {
      set({ notification: { kind: 'error', message: errorMessage(error) } });
    }
  },
}));
