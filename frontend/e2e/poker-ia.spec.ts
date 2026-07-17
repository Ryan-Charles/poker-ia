import { expect, test, type APIRequestContext, type Page } from '@playwright/test';

interface ApiLegalAction {
  action: string;
  enabled: boolean;
  min_amount?: number;
  max_amount?: number;
}

interface ApiPot {
  index: number;
  amount: number;
  eligible_player_ids: string[];
  winner_ids?: string[];
  shares?: Record<string, number>;
}

interface ApiSummary {
  status: string;
  winners: string[];
  total_pot: number;
  hero_contribution: number;
  hero_received: number;
  hero_net: number;
  hero_new_stack: number;
  session_net: number;
  pots: ApiPot[];
}

interface ApiState {
  session_id: string;
  hand: {
    id: string;
    number: number;
    phase: 'playing' | 'awaiting_cards' | 'showdown' | 'summary' | 'ended';
    street: string;
    pot: number;
    side_pots: ApiPot[];
    active_player_id: string | null;
    board: string[];
    hero_cards: string[];
    action_log: Array<{ player_id: string; street: string; action: string; amount: number }>;
    summary?: ApiSummary;
  };
  players: Array<{ id: string; name: string; stack: number; status?: string; pending_join?: boolean }>;
  legal_actions: ApiLegalAction[];
  selector: { required_slots: string[] };
}

interface AdviceResponse {
  id: string;
  balanced: { action: string; confidence: number; explanation: string };
  exploitative: { action: string; confidence: number; explanation: string };
  final: { action: string; confidence: number; explanation: string };
  explanation_pending: boolean;
}

interface HistoryItem {
  id: string;
  hand_number: number;
  quality: 'excellent' | 'acceptable' | 'questionable' | 'mistake';
  short_explanation: string;
}

interface DecisionDetail extends HistoryItem {
  detailed_explanation: string;
}

interface OpponentResponse {
  id: string;
  estimated_profile: string;
  confidence: number;
  hands_observed: number;
  stats: { vpip: number; pfr: number; aggression_factor: number };
  revealed_showdowns: Array<{ cards: string[]; bluff_observed: boolean }>;
  recommended_adaptations: string[];
}

const runoutCards: Record<string, string> = {
  flop_1: '2c',
  flop_2: '3d',
  flop_3: '7h',
  turn: '8c',
  river: '9d',
};

const bluffRunoutCards: Record<string, string> = {
  flop_1: '2s',
  flop_2: '3h',
  flop_3: '4d',
  turn: '9c',
  river: 'Jc',
};

const browserErrors = new WeakMap<Page, string[]>();

function configuration(playerCount: number, stacks?: number[]) {
  const players = Array.from({ length: playerCount }, (_, index) => ({
    id: index === 0 ? 'hero' : `player-${index + 1}`,
    name: index === 0 ? 'Ryanchl' : `Joueur ${index + 1}`,
    seat: index + 1,
    stack: stacks?.[index] ?? 10_000,
    initial_profile: index === 1 ? 'very_aggressive' : 'unknown',
  }));
  return {
    player_count: playerCount,
    players,
    unit: 'chips',
    small_blind: 50,
    big_blind: 100,
    ante: 0,
    ante_type: 'classic',
    game_mode: 'cash',
    dealer_id: 'hero',
    small_blind_id: playerCount === 2 ? 'hero' : 'player-2',
    big_blind_id: playerCount === 2 ? 'player-2' : 'player-3',
    blind_levels: [],
    advice_mode: 'immediate',
  };
}

async function createSession(
  request: APIRequestContext,
  count: number,
  stacks?: number[],
): Promise<ApiState> {
  const response = await request.post('/api/sessions', { data: configuration(count, stacks) });
  expect(response.status()).toBe(201);
  return (await response.json()) as ApiState;
}

async function getState(request: APIRequestContext, sessionId: string): Promise<ApiState> {
  const response = await request.get(`/api/sessions/${sessionId}/state`);
  expect(response.ok()).toBeTruthy();
  return (await response.json()) as ApiState;
}

async function openSession(page: Page, sessionId: string): Promise<void> {
  await page.goto('/');
  await page.evaluate((id) => localStorage.setItem('poker-ia-session', id), sessionId);
  await page.reload();
  await page.getByRole('button', { name: 'Reprendre la session' }).click();
  await expect(page.locator('.poker-zone').getByText(/^Main #\d+$/)).toBeVisible();
}

async function setCard(
  request: APIRequestContext,
  sessionId: string,
  slot: string,
  card: string,
): Promise<ApiState> {
  const response = await request.post(`/api/sessions/${sessionId}/cards`, { data: { slot, card } });
  expect(response.ok()).toBeTruthy();
  return (await response.json()) as ApiState;
}

async function prepareHero(
  request: APIRequestContext,
  sessionId: string,
  first = 'As',
  second = 'Ah',
): Promise<void> {
  await setCard(request, sessionId, 'hero_1', first);
  await setCard(request, sessionId, 'hero_2', second);
}

function enabled(state: ApiState, action: string): ApiLegalAction | undefined {
  return state.legal_actions.find((candidate) => candidate.action === action && candidate.enabled);
}

async function act(
  request: APIRequestContext,
  sessionId: string,
  action: string,
  amount?: number,
): Promise<ApiState> {
  const response = await request.post(`/api/sessions/${sessionId}/actions`, {
    data: amount === undefined ? { action } : { action, amount },
  });
  expect(response.ok()).toBeTruthy();
  return (await response.json()) as ApiState;
}

async function fillAwaitingCards(
  request: APIRequestContext,
  sessionId: string,
  state: ApiState,
  cards: Record<string, string>,
): Promise<ApiState> {
  let current = state;
  while (current.hand.phase === 'awaiting_cards') {
    const slot = current.selector.required_slots[0];
    if (!slot || !cards[slot]) throw new Error(`Emplacement inattendu: ${slot ?? 'aucun'}`);
    current = await setCard(request, sessionId, slot, cards[slot]);
  }
  return current;
}

async function advanceToShowdown(
  request: APIRequestContext,
  sessionId: string,
  allIn = false,
): Promise<{ state: ApiState; actions: Array<{ street: string; actor: string; action: string }> }> {
  const actions: Array<{ street: string; actor: string; action: string }> = [];
  for (let iteration = 0; iteration < 100; iteration += 1) {
    let state = await getState(request, sessionId);
    state = await fillAwaitingCards(request, sessionId, state, runoutCards);
    if (state.hand.phase === 'showdown') return { state, actions };
    if (state.hand.phase !== 'playing' || !state.hand.active_player_id)
      throw new Error(`Phase inattendue avant showdown: ${state.hand.phase}`);
    const action =
      allIn && enabled(state, 'all_in')
        ? 'all_in'
        : enabled(state, 'check')
          ? 'check'
          : enabled(state, 'call')
            ? 'call'
            : null;
    if (!action) throw new Error('Aucune action passive ou à tapis ne permet de poursuivre la main.');
    actions.push({ street: state.hand.street, actor: state.hand.active_player_id, action });
    await act(request, sessionId, action);
  }
  throw new Error('La main n’a pas atteint le showdown dans la limite prévue.');
}

async function nextHand(request: APIRequestContext, sessionId: string): Promise<ApiState> {
  const response = await request.post(`/api/sessions/${sessionId}/next-hand`, { data: {} });
  expect(response.ok()).toBeTruthy();
  return (await response.json()) as ApiState;
}

async function advice(request: APIRequestContext, sessionId: string, seed = 9): Promise<AdviceResponse> {
  const response = await request.post(`/api/sessions/${sessionId}/advice`, {
    data: { trials: 100, seed },
  });
  expect(response.ok()).toBeTruthy();
  return (await response.json()) as AdviceResponse;
}

async function history(request: APIRequestContext, sessionId: string): Promise<HistoryItem[]> {
  const response = await request.get(`/api/history?session_id=${sessionId}`);
  expect(response.ok()).toBeTruthy();
  return (await response.json()) as HistoryItem[];
}

async function waitForDetailedExplanation(
  request: APIRequestContext,
  adviceId: string,
): Promise<DecisionDetail> {
  let detail: DecisionDetail | undefined;
  await expect
    .poll(
      async () => {
        const response = await request.get(`/api/history/${adviceId}`);
        if (!response.ok()) return '';
        detail = (await response.json()) as DecisionDetail;
        return detail.detailed_explanation;
      },
      { timeout: 8_000 },
    )
    .toContain('Aucun nouveau calcul');
  if (!detail) throw new Error('L’explication détaillée n’a pas été récupérée.');
  return detail;
}

async function settleShowdown(
  request: APIRequestContext,
  sessionId: string,
  revealedHands: Record<string, string[]>,
): Promise<ApiState> {
  const response = await request.post(`/api/sessions/${sessionId}/showdown`, {
    data: { revealed_hands: revealedHands, manual_winners: {} },
  });
  expect(response.ok()).toBeTruthy();
  return (await response.json()) as ApiState;
}

async function playHeroMistakeHand(
  request: APIRequestContext,
  sessionId: string,
  seed: number,
): Promise<AdviceResponse> {
  await prepareHero(request, sessionId);
  let state = await getState(request, sessionId);
  while (state.hand.active_player_id !== 'hero') {
    const passive = enabled(state, 'check') ? 'check' : enabled(state, 'call') ? 'call' : null;
    if (!passive) throw new Error('Ryanchl ne peut pas récupérer la parole dans cette main.');
    state = await act(request, sessionId, passive);
  }
  const currentAdvice = await advice(request, sessionId, seed);
  expect(enabled(state, 'fold')).toBeTruthy();
  const completed = await act(request, sessionId, 'fold');
  expect(completed.hand.phase).toBe('summary');
  return currentAdvice;
}

async function playAggressiveShowdown(request: APIRequestContext, sessionId: string): Promise<ApiState> {
  await prepareHero(request, sessionId);
  let villainRaised = false;
  let villainBetFlop = false;
  for (let iteration = 0; iteration < 80; iteration += 1) {
    let state = await getState(request, sessionId);
    state = await fillAwaitingCards(request, sessionId, state, bluffRunoutCards);
    if (state.hand.phase === 'showdown')
      return settleShowdown(request, sessionId, { 'player-2': ['7s', '6d'] });
    if (state.hand.phase !== 'playing' || !state.hand.active_player_id)
      throw new Error(`Phase inattendue dans la main agressive: ${state.hand.phase}`);
    if (
      state.hand.active_player_id === 'player-2' &&
      state.hand.street === 'preflop' &&
      !villainRaised &&
      enabled(state, 'raise')
    ) {
      const raise = enabled(state, 'raise')!;
      villainRaised = true;
      await act(request, sessionId, 'raise', raise.min_amount);
    } else if (
      state.hand.active_player_id === 'player-2' &&
      state.hand.street === 'flop' &&
      !villainBetFlop &&
      enabled(state, 'bet')
    ) {
      const bet = enabled(state, 'bet')!;
      villainBetFlop = true;
      await act(request, sessionId, 'bet', bet.min_amount);
    } else {
      const passive = enabled(state, 'check') ? 'check' : enabled(state, 'call') ? 'call' : null;
      if (!passive) throw new Error('Aucune réponse passive dans la main agressive.');
      await act(request, sessionId, passive);
    }
  }
  throw new Error('Le showdown agressif n’a pas été atteint.');
}

async function playAggressiveFoldHand(request: APIRequestContext, sessionId: string): Promise<ApiState> {
  await prepareHero(request, sessionId);
  let villainRaised = false;
  for (let iteration = 0; iteration < 12; iteration += 1) {
    const state = await getState(request, sessionId);
    if (state.hand.phase === 'summary') return state;
    if (state.hand.phase !== 'playing' || !state.hand.active_player_id)
      throw new Error(`Phase inattendue dans la main courte: ${state.hand.phase}`);
    if (state.hand.active_player_id === 'player-2' && enabled(state, 'raise')) {
      const raise = enabled(state, 'raise')!;
      villainRaised = true;
      await act(request, sessionId, 'raise', raise.min_amount);
    } else if (state.hand.active_player_id === 'hero' && villainRaised && enabled(state, 'fold')) {
      await act(request, sessionId, 'fold');
    } else {
      const passive = enabled(state, 'call') ? 'call' : enabled(state, 'check') ? 'check' : null;
      if (!passive) throw new Error('Aucune action pour déclencher la relance adverse.');
      await act(request, sessionId, passive);
    }
  }
  throw new Error('La main agressive courte n’est pas terminée.');
}

test.beforeEach(async ({ page, request }) => {
  const errors: string[] = [];
  browserErrors.set(page, errors);
  page.on('console', (message) => {
    if (message.type() === 'error') errors.push(message.text());
  });
  page.on('pageerror', (error) => errors.push(error.message));
  const response = await request.delete('/api/data');
  expect(response.status()).toBe(204);
});

test.afterEach(({ page }) => {
  expect(browserErrors.get(page) ?? [], 'aucune erreur console ou page').toEqual([]);
});

test('Scénario A — relance, victoire préflop, résultat net exact et main suivante', async ({
  page,
  request,
}) => {
  await page.goto('/');
  await page.getByRole('button', { name: /Installer les joueurs et commencer/ }).click();
  await expect(page.getByText('Main #1', { exact: true })).toBeVisible();
  const sessionId = await page.evaluate(() => localStorage.getItem('poker-ia-session'));
  expect(sessionId).toBeTruthy();
  await page.getByRole('gridcell', { name: 'A♠' }).click();
  await page.getByRole('gridcell', { name: 'A♥' }).click();
  await expect(page.getByText('Action à meilleure EV estimée')).toBeVisible({ timeout: 20_000 });
  await page.getByRole('button', { name: 'Raise', exact: true }).click();
  for (let fold = 0; fold < 5; fold += 1) {
    const button = page.getByRole('button', { name: 'Fold', exact: true });
    await expect(button).toBeEnabled();
    await button.click();
  }
  await expect(page.getByRole('heading', { name: 'Gagnée sans showdown' })).toBeVisible();
  // Plus d'enchaînement automatique en fin de main : le bilan reste affiché
  // jusqu'au clic sur « Main suivante → » (comportement couvert par un test dédié).
  const completed = await getState(request, sessionId!);
  expect(completed.hand.summary).toMatchObject({
    status: 'won_without_showdown',
    winners: ['hero'],
    total_pot: 250,
    hero_contribution: 100,
    hero_received: 250,
    hero_net: 150,
  });
  expect(completed.hand.action_log).toContainEqual(
    expect.objectContaining({ player_id: 'hero', action: 'raise', amount: 200 }),
  );
  await expect(page.locator('.net-result strong')).toHaveText('+150 jetons');
  // Ryanchl a saisi ses propres cartes pour le conseil : elles apparaissent
  // légitimement dans le récapitulatif, mais plus aucun placeholder "Cartes
  // non montrées" ne doit polluer une main gagnée sans showdown (bug corrigé :
  // la section ne liste plus que les mains réellement connues).
  await expect(page.locator('.showdown-results article')).toHaveCount(1);
  await expect(page.locator('.showdown-results')).not.toContainText('Cartes non montrées');
  await page.getByRole('button', { name: /Main suivante/ }).click();
  await expect(page.getByText('Main #2', { exact: true })).toBeVisible();
  const next = await getState(request, sessionId!);
  expect(next.hand.number).toBe(2);
  expect(next.hand.hero_cards).toEqual([]);
});

test('Scénario B — check jusqu’à la river, saisie adverse et gagnant automatique', async ({
  page,
  request,
}) => {
  const created = await createSession(request, 3);
  await prepareHero(request, created.session_id);
  const showdown = await advanceToShowdown(request, created.session_id);
  expect(showdown.state.hand.phase).toBe('showdown');
  expect(showdown.state.hand.board).toEqual(['2c', '3d', '7h', '8c', '9d']);
  for (const street of ['flop', 'turn', 'river']) {
    const streetActions = showdown.actions.filter((item) => item.street === street);
    expect(streetActions).toHaveLength(3);
    expect(streetActions.every((item) => item.action === 'check')).toBe(true);
  }
  await openSession(page, created.session_id);
  await expect(page.getByRole('heading', { name: 'Showdown', level: 2 })).toBeVisible();
  // Notation anglaise des rangs dans la grille (K/Q/J, pas R/D/V).
  for (const card of ['K♠', 'K♥', 'Q♠', 'Q♥']) await page.getByRole('gridcell', { name: card }).click();
  // Le showdown se valide seul 600 ms après la dernière carte saisie (lot 5) :
  // pas de clic sur "Valider le showdown", on attend directement le bilan, qui
  // reste ensuite affiché sans enchaînement automatique.
  await expect(page.getByRole('heading', { name: 'Main gagnée' })).toBeVisible({ timeout: 10_000 });
  const completed = await getState(request, created.session_id);
  expect(completed.hand.summary).toMatchObject({
    status: 'won',
    winners: ['hero'],
    total_pot: 300,
    hero_contribution: 100,
    hero_received: 300,
    hero_net: 200,
  });
  await expect(page.locator('.net-result strong')).toHaveText('+200 jetons');
});

test('Scénario C — pot principal, deux pots secondaires, gagnants distincts et net exact', async ({
  page,
  request,
}) => {
  const created = await createSession(request, 4, [500, 1_000, 2_000, 3_000]);
  await prepareHero(request, created.session_id);
  const showdown = await advanceToShowdown(request, created.session_id, true);
  expect(showdown.state.hand.side_pots.map((pot) => pot.amount)).toEqual([2_000, 1_500, 2_000]);
  await openSession(page, created.session_id);
  // Notation anglaise des rangs dans la grille (K/Q/J, pas R/D/V).
  for (const card of ['K♠', 'K♥', 'Q♠', 'Q♥', 'J♠', 'J♥'])
    await page.getByRole('gridcell', { name: card }).click();
  // Idem : auto-validation 600 ms après la dernière carte, aucun clic requis.
  // Le bilan reste ensuite affiché sans enchaînement automatique.
  await expect(page.getByRole('heading', { name: 'Main gagnée' })).toBeVisible({ timeout: 10_000 });
  const completed = await getState(request, created.session_id);
  expect(completed.hand.summary?.pots.map((pot) => pot.winner_ids)).toEqual([
    ['hero'],
    ['player-2'],
    ['player-3'],
  ]);
  expect(completed.hand.summary).toMatchObject({
    hero_contribution: 500,
    hero_received: 2_000,
    hero_net: 1_500,
  });
  // Le tableau affiche les noms visibles ("Ryanchl", "Joueur N"), pas les
  // identifiants internes ("hero", "player-2") : la table utilise les mêmes
  // noms que ceux configurés par createSession() pour les joueurs 2 à 4.
  const rows = page.locator('.pot-table-wrap tbody tr');
  await expect(rows).toHaveCount(3);
  await expect(rows.nth(0)).toContainText('Ryanchl');
  await expect(rows.nth(1)).toContainText('Joueur 2');
  await expect(rows.nth(2)).toContainText('Joueur 3');
  await expect(page.locator('.net-result strong')).toHaveText(/\+1\s?500 jetons/);
});

test('Scénario D — conseil immédiat, explication, historique repliable et poursuite', async ({
  page,
  request,
}) => {
  const created = await createSession(request, 2);
  await prepareHero(request, created.session_id);
  await openSession(page, created.session_id);
  await expect(page.getByText('Action à meilleure EV estimée')).toBeVisible({ timeout: 20_000 });
  let unexpectedAdviceRequests = 0;
  page.on('request', (requestEvent) => {
    if (requestEvent.url().includes(`/api/sessions/${created.session_id}/advice`))
      unexpectedAdviceRequests += 1;
  });
  const passive = page.locator('.action-passive:not(:disabled)');
  await passive.click();
  const historyToggle = page.getByRole('button', { name: /Historique des conseils/ });
  await expect(historyToggle).toContainText('1 conseil');
  await historyToggle.click();
  const liveItem = page.locator('.live-history-item');
  await expect(liveItem).toHaveCount(1);
  await expect(liveItem).toContainText('Main #1');
  await expect(liveItem).toContainText('Choix');
  await expect(liveItem).toContainText('%');
  await expect(page.locator('.poker-zone')).toBeVisible();
  const items = await history(request, created.session_id);
  expect(items).toHaveLength(1);
  await waitForDetailedExplanation(request, items[0].id);
  const detailResponse = page.waitForResponse((response) =>
    response.url().endsWith(`/api/history/${items[0].id}`),
  );
  await liveItem.click();
  await detailResponse;
  await expect(page.getByRole('heading', { name: 'Analyse de la décision' })).toBeVisible();
  expect(unexpectedAdviceRequests).toBe(0);
  await page.getByRole('button', { name: 'Fermer' }).click();
  const nextPassive = page.locator('.action-passive:not(:disabled)');
  await expect(nextPassive).toBeEnabled();
  await nextPassive.click();
  await expect(page.locator('.compact-log')).toContainText('Joueur 2');
});

test('Scénario E — explication réellement différée sans bloquer action ni joueur suivant', async ({
  page,
  request,
}) => {
  const created = await createSession(request, 3);
  await prepareHero(request, created.session_id);
  await page.goto('/');
  await page.evaluate((id) => localStorage.setItem('poker-ia-session', id), created.session_id);
  await page.reload();
  const adviceResponse = page.waitForResponse(
    (response) =>
      response.url().endsWith(`/api/sessions/${created.session_id}/advice`) &&
      response.request().method() === 'GET',
  );
  await page.getByRole('button', { name: 'Reprendre la session' }).click();
  const pendingAdvice = (await (await adviceResponse).json()) as AdviceResponse;
  expect(pendingAdvice.explanation_pending).toBe(true);
  await expect(page.getByText(/explication détaillée arrive sans bloquer/i)).toBeVisible();
  const actionResponse = page.waitForResponse(
    (response) =>
      response.url().endsWith(`/api/sessions/${created.session_id}/actions`) &&
      response.request().method() === 'POST',
  );
  const actionStarted = Date.now();
  await page
    .locator('.action-passive:not(:disabled)')
    .evaluate((button: HTMLButtonElement) => button.click());
  const completedAction = await actionResponse;
  expect(completedAction.ok()).toBe(true);
  expect(Date.now() - actionStarted).toBeLessThan(800);
  const transitioned = await getState(request, created.session_id);
  expect(transitioned.hand.active_player_id).toBe('player-2');
  await expect(page.locator('.actor-strip')).toContainText('Joueur 2');
  const detail = await waitForDetailedExplanation(request, pendingAdvice.id);
  expect(detail.id).toBe(pendingAdvice.id);
  await page.getByRole('button', { name: 'Historique', exact: true }).click();
  await expect(page.locator('.history-list tbody tr')).toHaveCount(1);
  const detailResponse = page.waitForResponse((response) =>
    response.url().endsWith(`/api/history/${pendingAdvice.id}`),
  );
  await page.locator('.history-list tbody tr').click();
  expect((await detailResponse).ok()).toBe(true);
  await expect(page.getByRole('heading', { name: 'Analyse de la décision' })).toBeVisible();
  await expect(page.getByText(/Aucun nouveau calcul du solveur/i)).toBeVisible();
});

test('Scénario F — plusieurs mains, choix de sortie, bilan, erreurs et réouverture', async ({
  page,
  request,
}) => {
  const created = await createSession(request, 2);
  const adviceIds: string[] = [];
  for (let hand = 0; hand < 3; hand += 1) {
    const handAdvice = await playHeroMistakeHand(request, created.session_id, 100 + hand);
    adviceIds.push(handAdvice.id);
    await nextHand(request, created.session_id);
  }
  for (const id of adviceIds) await waitForDetailedExplanation(request, id);
  await openSession(page, created.session_id);
  let exitRequests = 0;
  page.on('request', (requestEvent) => {
    if (requestEvent.url().endsWith(`/api/sessions/${created.session_id}/exit`)) exitRequests += 1;
  });
  await page.getByRole('button', { name: 'Sortir de la table' }).click();
  const dialog = page.getByRole('dialog', { name: 'Que souhaitez-vous faire ?' });
  await expect(dialog).toBeVisible();
  await dialog.getByRole('button', { name: 'Annuler', exact: true }).click();
  await expect(dialog).toHaveCount(0);
  expect(exitRequests).toBe(0);
  await page.getByRole('button', { name: 'Sortir de la table' }).click();
  await page.getByRole('dialog').getByRole('button', { name: 'Terminer la main' }).click();
  await expect(page.locator('.poker-zone')).toBeVisible();
  expect(exitRequests).toBe(0);
  await page.getByRole('button', { name: 'Sortir de la table' }).click();
  const exitResponse = page.waitForResponse(
    (response) =>
      response.url().endsWith(`/api/sessions/${created.session_id}/exit`) &&
      response.request().method() === 'POST',
  );
  await page.getByRole('dialog').getByRole('button', { name: 'Sauvegarder et sortir' }).click();
  const report = await (await exitResponse).json();
  expect(report.hands_played).toBe(3);
  // Nouveau comportement : la sortie ramène à l'écran de configuration (session
  // locale effacée) ; le bilan reste accessible via un bouton dédié.
  await expect(page.getByRole('button', { name: /Installer les joueurs et commencer/ })).toBeVisible();
  expect(await page.evaluate(() => localStorage.getItem('poker-ia-session'))).toBeFalsy();
  await page.getByRole('button', { name: 'Voir le bilan de la table précédente' }).click();
  await expect(page.getByRole('heading', { name: 'Bilan de Ryanchl' })).toBeVisible();
  await expect(page.getByText('3 mains en', { exact: false })).toBeVisible();
  expect((await getState(request, created.session_id)).hand.number).toBe(4);
  await page.getByRole('button', { name: 'Tous les conseils et explications' }).click();
  await expect(page.locator('.history-list-heading strong')).toHaveText('3 décisions');
  const items = await history(request, created.session_id);
  expect(items).toHaveLength(3);
  expect(items.every((item) => item.short_explanation.length > 30)).toBe(true);
  const mistakes = items.filter((item) => item.quality === 'mistake');
  expect(mistakes.length).toBeGreaterThan(0);
  await page.getByLabel('Qualité').selectOption('mistake');
  await expect(page.locator('.history-list tbody tr')).toHaveCount(mistakes.length);
  await page.locator('.history-list tbody tr').first().click();
  await expect(page.getByRole('heading', { name: 'Analyse de la décision' })).toBeVisible();
  await expect(page.getByRole('heading', { name: 'Relecture action par action' })).toBeVisible();
  await expect(page.getByText(/Aucun nouveau calcul du solveur/i)).toBeVisible();
});

test('Scénario G — apprentissage agressif, bluffs révélés, garde-fou puis adaptation', async ({
  page,
  request,
}) => {
  test.setTimeout(90_000);
  const created = await createSession(request, 2, [100_000, 100_000]);
  await prepareHero(request, created.session_id);
  const lowSampleAdvice = await advice(request, created.session_id, 41);
  expect(lowSampleAdvice.final.explanation).toContain('échantillon adverse est encore faible');
  expect(lowSampleAdvice.final.explanation).toContain('adaptation reste minime');
  let state = await getState(request, created.session_id);
  while (state.hand.phase !== 'summary') {
    if (state.hand.phase === 'awaiting_cards') {
      state = await fillAwaitingCards(request, created.session_id, state, bluffRunoutCards);
    } else if (state.hand.phase === 'showdown') {
      state = await settleShowdown(request, created.session_id, { 'player-2': ['7s', '6d'] });
    } else if (state.hand.active_player_id === 'player-2' && enabled(state, 'raise')) {
      const raise = enabled(state, 'raise')!;
      state = await act(request, created.session_id, 'raise', raise.min_amount);
    } else if (
      state.hand.active_player_id === 'player-2' &&
      state.hand.street === 'flop' &&
      enabled(state, 'bet')
    ) {
      const bet = enabled(state, 'bet')!;
      state = await act(request, created.session_id, 'bet', bet.min_amount);
    } else {
      const passive = enabled(state, 'check') ? 'check' : enabled(state, 'call') ? 'call' : null;
      if (!passive) throw new Error('La première main agressive ne peut pas avancer.');
      state = await act(request, created.session_id, passive);
    }
  }
  for (let hand = 1; hand < 3; hand += 1) {
    await nextHand(request, created.session_id);
    const completed = await playAggressiveShowdown(request, created.session_id);
    expect(completed.hand.summary?.status).toBe('won');
  }
  for (let hand = 3; hand < 30; hand += 1) {
    await nextHand(request, created.session_id);
    const completed = await playAggressiveFoldHand(request, created.session_id);
    expect(completed.hand.summary?.status).toBe('lost');
  }
  const profileResponse = await request.get(`/api/opponents/player-2?session_id=${created.session_id}`);
  expect(profileResponse.ok()).toBeTruthy();
  const profile = (await profileResponse.json()) as OpponentResponse;
  expect(profile.hands_observed).toBe(30);
  expect(profile.confidence).toBeGreaterThanOrEqual(0.25);
  expect(profile.estimated_profile).toBe('large_agressif');
  expect(profile.stats.pfr).toBeGreaterThan(0.6);
  expect(profile.revealed_showdowns).toHaveLength(3);
  expect(profile.revealed_showdowns.every((showdown) => showdown.bluff_observed)).toBe(true);
  await nextHand(request, created.session_id);
  await prepareHero(request, created.session_id);
  const adaptedAdvice = await advice(request, created.session_id, 42);
  expect(adaptedAdvice.final.confidence).toBeGreaterThan(lowSampleAdvice.final.confidence);
  expect(adaptedAdvice.final.explanation).toMatch(/assez d[’']observations/);
  expect(adaptedAdvice.final.explanation).toContain('adaptation modérée');
  await openSession(page, created.session_id);
  await page.getByRole('button', { name: 'Adversaires' }).click();
  const profilePanel = page.locator('.opponent-detail');
  await expect(profilePanel).toContainText('30 mains observées');
  await expect(profilePanel).toContainText('large_agressif');
  await expect(profilePanel.getByText('Bluff observé')).toHaveCount(3);
  await expect(profilePanel).toContainText(/Protéger la range de check/i);
});

test('Scénario H — aucune carte adverse dans API, état visible ou DOM avant showdown', async ({
  page,
  request,
}) => {
  const created = await createSession(request, 6);
  const raw = await request.get(`/api/sessions/${created.session_id}/state`);
  const serialized = await raw.text();
  expect(serialized).not.toContain('revealed_hands');
  expect(serialized).not.toContain('private_cards');
  expect(serialized).not.toContain('hole_cards');
  await openSession(page, created.session_id);
  await expect(page.getByText('Cartes réellement révélées')).toHaveCount(0);
  await expect(page.locator('[aria-label^="Carte 1 de "]')).toHaveCount(0);
  await expect(page.getByRole('gridcell')).toHaveCount(52);
  await expect(page.locator('.card-selector')).toBeVisible();
  await expect(page.locator('.poker-zone')).toBeVisible();
  await expect(page.locator('.action-dock')).toBeVisible();
});

test('Adaptation tablette — table, sélecteur et actions sans chevauchement horizontal', async ({ page }) => {
  await page.setViewportSize({ width: 820, height: 1180 });
  await page.goto('/');
  await page.getByRole('button', { name: /Installer les joueurs et commencer/ }).click();
  await expect(page.getByText('Main #1', { exact: true })).toBeVisible();
  await expect(page.getByRole('region', { name: 'Table de poker' })).toBeVisible();
  await expect(page.getByRole('complementary', { name: 'Sélecteur de cartes' })).toBeVisible();
  await expect(page.getByRole('region', { name: 'Actions de Ryanchl' })).toBeVisible();

  const layout = await page.evaluate(() => {
    const pageElement = document.querySelector<HTMLElement>('.table-page');
    const selector = document.querySelector<HTMLElement>('.card-selector');
    const grid = document.querySelector<HTMLElement>('.card-grid');
    const actionDock = document.querySelector<HTMLElement>('.action-dock');
    const essential = [pageElement, selector, grid, actionDock];
    const rects = essential.map((element) => element?.getBoundingClientRect());
    return {
      viewportWidth: window.innerWidth,
      documentScrollWidth: document.documentElement.scrollWidth,
      display: pageElement ? getComputedStyle(pageElement).display : '',
      flexDirection: pageElement ? getComputedStyle(pageElement).flexDirection : '',
      gridFits: grid ? grid.scrollWidth <= grid.clientWidth + 1 : false,
      essentialsInsideViewport: rects.every(
        (rect) => rect && rect.left >= -1 && rect.right <= window.innerWidth + 1,
      ),
    };
  });
  expect(layout.documentScrollWidth).toBeLessThanOrEqual(layout.viewportWidth + 1);
  expect(layout.display).toBe('flex');
  expect(layout.flexDirection).toBe('column');
  expect(layout.gridFits).toBe(true);
  expect(layout.essentialsInsideViewport).toBe(true);
});

test('Bilan de main — aucune section de mains révélées si personne n’a montré ses cartes', async ({
  page,
  request,
}) => {
  const created = await createSession(request, 3);
  // Ryanchl ne saisit jamais ses cartes ici : la main se termine sans
  // showdown et sans qu'aucune main ne soit réellement connue.
  let state = await getState(request, created.session_id);
  expect(state.hand.active_player_id).toBe('hero');
  const raise = enabled(state, 'raise')!;
  state = await act(request, created.session_id, 'raise', raise.min_amount);
  while (state.hand.phase === 'playing') {
    state = await act(request, created.session_id, 'fold');
  }
  expect(state.hand.summary?.status).toBe('won_without_showdown');
  await openSession(page, created.session_id);
  await expect(page.getByRole('heading', { name: 'Gagnée sans showdown' })).toBeVisible();
  await expect(page.locator('.showdown-results')).toHaveCount(0);
});

async function reloadSession(page: Page): Promise<void> {
  await page.reload();
  await page.getByRole('button', { name: 'Reprendre la session' }).click();
}

async function assertNoPageScroll(page: Page, viewport: { width: number; height: number }): Promise<void> {
  const dimensions = await page.evaluate(() => ({
    scrollWidth: document.documentElement.scrollWidth,
    scrollHeight: document.documentElement.scrollHeight,
  }));
  expect(dimensions.scrollWidth, `largeur ${viewport.width}x${viewport.height}`).toBeLessThanOrEqual(
    viewport.width,
  );
  expect(dimensions.scrollHeight, `hauteur ${viewport.width}x${viewport.height}`).toBeLessThanOrEqual(
    viewport.height,
  );
}

test('Mise en page — aucun défilement à 1600x900 et 1366x768 dans toutes les phases', async ({
  page,
  request,
}) => {
  test.setTimeout(60_000);
  for (const viewport of [
    { width: 1600, height: 900 },
    { width: 1366, height: 768 },
  ]) {
    await page.setViewportSize(viewport);
    const created = await createSession(request, 3);
    const sessionId = created.session_id;

    // Phase "jeu" (préflop, avant toute saisie de carte).
    await openSession(page, sessionId);
    await expect(page.locator('.poker-zone')).toBeVisible();
    await expect(page.locator('.card-selector')).toBeVisible();
    await expect(page.locator('.action-dock')).toBeVisible();
    await assertNoPageScroll(page, viewport);

    // Phase "saisie des cartes" : on avance jusqu'à ce que le moteur réclame
    // les cartes du flop (tout le monde suit/parole au préflop).
    await prepareHero(request, sessionId);
    let state = await getState(request, sessionId);
    while (state.hand.phase === 'playing') {
      const passive = enabled(state, 'check') ? 'check' : enabled(state, 'call') ? 'call' : null;
      if (!passive) throw new Error('Aucune action passive pour atteindre la saisie de cartes.');
      state = await act(request, sessionId, passive);
    }
    expect(state.hand.phase).toBe('awaiting_cards');
    await reloadSession(page);
    await expect(page.locator('.card-selector')).toBeVisible();
    await assertNoPageScroll(page, viewport);

    // Phase "showdown".
    for (let iteration = 0; iteration < 60 && state.hand.phase !== 'showdown'; iteration += 1) {
      state = await fillAwaitingCards(request, sessionId, state, runoutCards);
      if (state.hand.phase === 'showdown') break;
      const passive = enabled(state, 'check') ? 'check' : enabled(state, 'call') ? 'call' : null;
      if (!passive) throw new Error('Aucune action passive pour atteindre le showdown.');
      state = await act(request, sessionId, passive);
    }
    expect(state.hand.phase).toBe('showdown');
    await reloadSession(page);
    await expect(page.getByRole('heading', { name: 'Showdown', level: 2 })).toBeVisible();
    await assertNoPageScroll(page, viewport);

    // Phase "bilan" (overlay ouvert) : reste affiché sans enchaînement automatique.
    await settleShowdown(request, sessionId, { 'player-2': ['2h', '3h'], 'player-3': ['4h', '5h'] });
    await reloadSession(page);
    await expect(page.locator('.hand-summary')).toBeVisible();
    await assertNoPageScroll(page, viewport);
  }
});

test('Recommencer la main — confirmation en deux temps et remise à zéro', async ({ page, request }) => {
  const created = await createSession(request, 3);
  await prepareHero(request, created.session_id);
  await openSession(page, created.session_id);
  const initialPot = (await getState(request, created.session_id)).hand.pot;

  // Deux actions jouées via l'interface pour faire grossir le pot et le journal.
  await page.locator('.action-passive:not(:disabled)').click();
  await expect(page.locator('.compact-log')).not.toContainText('En attente de la première action.');
  await page.locator('.action-passive:not(:disabled)').click();
  const midHandState = await getState(request, created.session_id);
  expect(midHandState.hand.pot).toBeGreaterThan(initialPot);
  expect(midHandState.hand.action_log.length).toBeGreaterThan(0);

  const restartButton = page.getByRole('button', { name: '↺ Recommencer la main' });
  await restartButton.click();
  await expect(page.getByText('Confirmer ?')).toBeVisible();
  await page.getByRole('button', { name: 'Oui, tout remettre à zéro' }).click();

  await expect(page.locator('.compact-log')).toContainText('En attente de la première action.');
  const restarted = await getState(request, created.session_id);
  expect(restarted.hand.pot).toBe(initialPot);
  expect(restarted.hand.action_log).toEqual([]);
  expect(restarted.hand.number).toBe(midHandState.hand.number);
});

test('Recommencer la main — Annuler referme la confirmation sans rien changer', async ({ page, request }) => {
  const created = await createSession(request, 3);
  await prepareHero(request, created.session_id);
  await openSession(page, created.session_id);
  await page.locator('.action-passive:not(:disabled)').click();
  const midHandState = await getState(request, created.session_id);

  await page.getByRole('button', { name: '↺ Recommencer la main' }).click();
  await expect(page.getByText('Confirmer ?')).toBeVisible();
  // "Annuler" seul est ambigu avec le "↶ Annuler" du sélecteur de cartes :
  // on cible celui de la confirmation de recommencement, sous forme exacte.
  await page.locator('.restart-hand-confirm').getByRole('button', { name: 'Annuler', exact: true }).click();
  await expect(page.getByText('Confirmer ?')).toHaveCount(0);

  const unchanged = await getState(request, created.session_id);
  expect(unchanged.hand.pot).toBe(midHandState.hand.pot);
  expect(unchanged.hand.action_log.length).toBe(midHandState.hand.action_log.length);
});

test('Remplacement de joueur en cours de main — nouveau nom et profil vierge', async ({ page, request }) => {
  const created = await createSession(request, 2);
  await prepareHero(request, created.session_id);
  await openSession(page, created.session_id);
  // Une action pour être bien "en cours de main" avant le remplacement.
  await page.locator('.action-passive:not(:disabled)').click();

  await page.getByRole('button', { name: 'Modifier Joueur 2' }).click();
  await expect(page.getByRole('heading', { name: 'Modifier Joueur 2' })).toBeVisible();
  await page.getByRole('heading', { name: 'Remplacer ce joueur' }).scrollIntoViewIfNeeded();
  await page.getByLabel('Nom du nouveau joueur').fill('Jordan');
  await page.getByRole('button', { name: 'Remplacer', exact: true }).click();

  // Le tiroir se referme automatiquement une fois le remplacement effectué.
  await expect(page.getByRole('heading', { name: 'Modifier Joueur 2' })).toHaveCount(0);
  const seat = page.locator('.player-seat', { hasText: 'Jordan' });
  await expect(seat).toBeVisible();
  await expect(seat).toContainText('inconnu');
  await expect(seat).toContainText('0 % · 0 mains');
  await expect(page.locator('.player-seat', { hasText: 'Joueur 2' })).toHaveCount(0);

  const state = await getState(request, created.session_id);
  expect(state.players.find((player) => player.id === 'player-2')?.name).toBe('Jordan');
});

test('Configuration — la grosse blinde pilotée dérive petite blinde et bouton', async ({ page }) => {
  await page.goto('/');
  await expect(page.locator('.derived-role-field', { hasText: 'Petite blinde (dérivée)' })).toContainText(
    'Morgan · siège 5',
  );
  await expect(page.locator('.derived-role-field', { hasText: 'Bouton (dérivé)' })).toContainText(
    'Sacha · siège 4',
  );

  await page.getByRole('combobox', { name: 'Grosse blinde' }).selectOption({ label: 'Alex · siège 3' });

  await expect(page.locator('.derived-role-field', { hasText: 'Petite blinde (dérivée)' })).toContainText(
    'Camille · siège 2',
  );
  await expect(page.locator('.derived-role-field', { hasText: 'Bouton (dérivé)' })).toContainText(
    'Ryanchl · siège 1',
  );
});

test('Bilan de main — reste affiché sans enchaînement automatique jusqu’au clic sur Main suivante', async ({
  page,
  request,
}) => {
  test.setTimeout(20_000);
  await page.goto('/');
  await page.getByRole('button', { name: /Installer les joueurs et commencer/ }).click();
  await expect(page.getByText('Main #1', { exact: true })).toBeVisible();
  const sessionId = await page.evaluate(() => localStorage.getItem('poker-ia-session'));
  await page.getByRole('gridcell', { name: 'A♠' }).click();
  await page.getByRole('gridcell', { name: 'A♥' }).click();
  await expect(page.getByText('Action à meilleure EV estimée')).toBeVisible({ timeout: 20_000 });
  await page.getByRole('button', { name: 'Raise', exact: true }).click();
  for (let fold = 0; fold < 5; fold += 1) {
    const button = page.getByRole('button', { name: 'Fold', exact: true });
    await expect(button).toBeEnabled();
    await button.click();
  }
  const summaryHeading = page.getByRole('heading', { name: 'Gagnée sans showdown' });
  await expect(summaryHeading).toBeVisible();
  // Aucun compte à rebours n'a été supprimé sans conséquence : le bilan reste
  // affiché tel quel plusieurs secondes plus tard, sans bannière ni bascule
  // automatique vers la main suivante.
  await page.waitForTimeout(7_000);
  await expect(summaryHeading).toBeVisible();
  await expect(page.getByText(/Main suivante dans/)).toHaveCount(0);
  expect((await getState(request, sessionId!)).hand.number).toBe(1);
  await page.getByRole('button', { name: /Main suivante/ }).click();
  await expect(page.getByText('Main #2', { exact: true })).toBeVisible();
  expect((await getState(request, sessionId!)).hand.number).toBe(2);
});

test('Disposition des sièges — 8 joueurs sans chevauchement à 1600x900 et 1366x768', async ({
  page,
  request,
}) => {
  test.setTimeout(60_000);
  for (const viewport of [
    { width: 1600, height: 900 },
    { width: 1366, height: 768 },
  ]) {
    await page.setViewportSize(viewport);
    const created = await createSession(request, 8);
    await openSession(page, created.session_id);
    await expect(page.locator('.table-canvas.crowded')).toBeVisible();
    const layout = await page.evaluate(() => {
      const canvas = document.querySelector<HTMLElement>('.table-canvas');
      const seats = Array.from(document.querySelectorAll<HTMLElement>('.player-seat')).map((seat) => ({
        name: seat.querySelector<HTMLElement>('.player-name')?.textContent ?? 'Siège inconnu',
        rect: seat.getBoundingClientRect(),
      }));
      if (!canvas) return { seatCount: seats.length, insideCanvas: false, overlaps: ['table absente'] };
      const canvasRect = canvas.getBoundingClientRect();
      const insideCanvas = seats.every(
        ({ rect }) =>
          rect.left >= canvasRect.left - 1 &&
          rect.top >= canvasRect.top - 1 &&
          rect.right <= canvasRect.right + 1 &&
          rect.bottom <= canvasRect.bottom + 1,
      );
      const overlaps: string[] = [];
      for (let i = 0; i < seats.length; i += 1) {
        for (let j = i + 1; j < seats.length; j += 1) {
          const a = seats[i].rect;
          const b = seats[j].rect;
          if (a.left < b.right && a.right > b.left && a.top < b.bottom && a.bottom > b.top) {
            const overlapWidth = Math.min(a.right, b.right) - Math.max(a.left, b.left);
            const overlapHeight = Math.min(a.bottom, b.bottom) - Math.max(a.top, b.top);
            overlaps.push(
              `${seats[i].name}/${seats[j].name} (${overlapWidth.toFixed(1)} × ${overlapHeight.toFixed(1)} px)`,
            );
          }
        }
      }
      return { seatCount: seats.length, insideCanvas, overlaps };
    });
    expect(layout.seatCount, `${viewport.width}x${viewport.height}`).toBe(8);
    expect(layout.insideCanvas, `${viewport.width}x${viewport.height}`).toBe(true);
    expect(layout.overlaps, `${viewport.width}x${viewport.height}`).toEqual([]);
  }
});

test('Assistant stratégique — changer d’onglet met à jour l’indice affiché', async ({ page, request }) => {
  const created = await createSession(request, 2);
  await prepareHero(request, created.session_id);
  await openSession(page, created.session_id);
  await expect(page.getByText('Action à meilleure EV estimée')).toBeVisible({ timeout: 20_000 });

  const finalTab = page.getByRole('tab', { name: 'Conseil final' });
  const balancedTab = page.getByRole('tab', { name: 'Équilibré' });
  await expect(finalTab).toHaveClass(/active/);
  await expect(balancedTab).not.toHaveClass(/active/);
  const hint = page.locator('.advice-tab-hint');
  const initialHint = await hint.textContent();

  await balancedTab.click();
  await expect(balancedTab).toHaveClass(/active/);
  await expect(finalTab).not.toHaveClass(/active/);
  await expect(hint).not.toHaveText(initialHint ?? '');
  await expect(hint).toContainText('Théorie pure');
});

test('Sortie de table — retour à la configuration, session effacée, configuration conservée', async ({
  page,
}) => {
  await page.goto('/');
  await page.getByRole('button', { name: /Installer les joueurs et commencer/ }).click();
  await expect(page.getByText('Main #1', { exact: true })).toBeVisible();

  await page.getByRole('button', { name: 'Sortir de la table' }).click();
  const dialog = page.getByRole('dialog', { name: 'Que souhaitez-vous faire ?' });
  const dialogAppeared = await dialog
    .waitFor({ state: 'visible', timeout: 2_000 })
    .then(() => true)
    .catch(() => false);
  if (dialogAppeared) {
    await dialog.getByRole('button', { name: 'Sauvegarder et sortir' }).click();
  }

  await expect(page.getByRole('button', { name: /Installer les joueurs et commencer/ })).toBeVisible();
  const sessionValue = await page.evaluate(() => localStorage.getItem('poker-ia-session'));
  expect(sessionValue).toBeFalsy();
  const configValue = await page.evaluate(() => localStorage.getItem('poker-ia-config'));
  expect(configValue).toBeTruthy();
  expect((JSON.parse(configValue ?? '{}') as { player_count?: number }).player_count).toBeGreaterThan(0);
});

test('Sélecteur flottant — centré en début de main puis docké après les cartes de Ryanchl', async ({
  page,
  request,
}) => {
  const created = await createSession(request, 3);
  await openSession(page, created.session_id);

  await expect(page.locator('.card-selector-float .card-selector')).toBeVisible();
  await expect(page.locator('.table-right-column .card-selector')).toHaveCount(0);

  await page.getByRole('gridcell', { name: 'K♠' }).click();
  await page.getByRole('gridcell', { name: 'K♥' }).click();

  await expect(page.locator('.table-right-column .card-selector')).toBeVisible({ timeout: 10_000 });
  await expect(page.locator('.card-selector-float')).toHaveCount(0);
});

test('Bureau compact — toutes les cartes restent accessibles et le dock s’arrête à la table', async ({
  page,
  request,
}) => {
  await page.setViewportSize({ width: 1518, height: 710 });
  const created = await createSession(request, 6);
  await openSession(page, created.session_id);
  await expect(page.locator('.card-selector-float .card-selector')).toBeVisible();

  const geometry = await page.evaluate(() => {
    const left = document.querySelector<HTMLElement>('.table-left-column')?.getBoundingClientRect();
    const selector = document
      .querySelector<HTMLElement>('.card-selector-float .card-selector')
      ?.getBoundingClientRect();
    const lastCard = document
      .querySelector<HTMLElement>('.card-selector-float .suit-c button:last-of-type')
      ?.getBoundingClientRect();
    const dock = document.querySelector<HTMLElement>('.action-dock')?.getBoundingClientRect();
    if (!left || !selector || !lastCard || !dock) return null;
    return {
      selectorInsideTable: selector.top >= left.top - 1 && selector.bottom <= left.bottom + 1,
      lastCardInsideTable: lastCard.top >= left.top - 1 && lastCard.bottom <= left.bottom + 1,
      dockAlignedToTable: Math.abs(dock.left - left.left) <= 1 && Math.abs(dock.right - left.right) <= 1,
    };
  });

  expect(geometry).not.toBeNull();
  expect(geometry?.selectorInsideTable).toBe(true);
  expect(geometry?.lastCardInsideTable).toBe(true);
  expect(geometry?.dockAlignedToTable).toBe(true);
});

test('Montants fictifs — le tapis ressort et la mise de Ryanchl affiche exactement 0,05 €', async ({
  page,
  request,
}) => {
  const response = await request.post('/api/sessions', {
    data: {
      player_count: 2,
      players: [
        { id: 'hero', name: 'Ryanchl', seat: 1, stack: 400, initial_profile: 'unknown' },
        { id: 'player-2', name: 'Joueur 2', seat: 2, stack: 400, initial_profile: 'unknown' },
      ],
      unit: 'fictional_euros',
      small_blind: 2,
      big_blind: 5,
      ante: 0,
      ante_type: 'classic',
      game_mode: 'cash',
      dealer_id: 'hero',
      small_blind_id: 'hero',
      big_blind_id: 'player-2',
      blind_levels: [],
      advice_mode: 'immediate',
    },
  });
  expect(response.status()).toBe(201);
  const created = (await response.json()) as ApiState;

  await prepareHero(request, created.session_id);
  const afterCall = await act(request, created.session_id, 'call');
  expect(afterCall.hand.active_player_id).toBe('player-2');
  await openSession(page, created.session_id);

  const heroSeat = page.locator('.player-seat.hero');
  const heroStack = heroSeat.locator('.stack-line strong');
  const heroBet = page.locator('.bet-marker.is-hero');

  await expect(heroStack).toHaveText(/3,95\s*€ fictifs/);
  await expect(heroBet).toBeVisible();
  await expect(heroBet).toHaveText(/^0,05\s*€$/);
  await expect(heroBet).toHaveAttribute('aria-label', /Mise de Ryanchl\s*:\s*0,05\s*€/);
  await expect(heroSeat.locator('.seat-details')).toContainText(/Mise rue\s*0,05\s*€/);

  const prominence = await heroStack.evaluate((element) => {
    const style = getComputedStyle(element);
    return {
      fontSize: Number.parseFloat(style.fontSize),
      color: style.color,
      weight: Number.parseInt(style.fontWeight, 10),
    };
  });
  expect(prominence.fontSize).toBeGreaterThanOrEqual(17);
  expect(prominence.weight).toBeGreaterThanOrEqual(700);
  expect(prominence.color).not.toBe('rgb(255, 255, 255)');
});

test('Gestion des sièges — retirer avec − puis ajouter avec + pour la main suivante', async ({
  page,
  request,
}) => {
  const created = await createSession(request, 3);
  await openSession(page, created.session_id);

  await page.getByRole('button', { name: 'Retirer Joueur 2 de la table' }).click();
  const addButton = page.getByRole('button', { name: 'Ajouter un joueur au siège 2' });
  await expect(addButton).toBeVisible();
  await addButton.click();

  const dialog = page.getByRole('dialog', { name: 'Ajouter un joueur' });
  await dialog.getByLabel('Nom du joueur').fill('Jordan');
  await dialog.getByLabel('Tapis réellement possédé').fill('8000');
  await dialog.getByRole('button', { name: 'Ajouter à ce siège' }).click();

  const pendingSeat = page.locator('.player-seat.pending-join', { hasText: 'Jordan' });
  await expect(pendingSeat).toBeVisible();
  await expect(pendingSeat).toContainText('Arrive à la prochaine main');
  let state = await getState(request, created.session_id);
  const pending = state.players.find((player) => player.id === 'player-2');
  expect(pending?.status).toBe('away');
  expect(pending?.pending_join).toBe(true);

  state = await act(request, created.session_id, 'fold');
  expect(state.hand.phase).toBe('summary');
  await nextHand(request, created.session_id);
  await openSession(page, created.session_id);

  const joinedSeat = page.locator('.player-seat', { hasText: 'Jordan' });
  await expect(joinedSeat).toBeVisible();
  await expect(joinedSeat).not.toHaveClass(/pending-join/);
  await expect(page.getByRole('button', { name: 'Ajouter un joueur au siège 2' })).toHaveCount(0);
});

test('Tapis en pleine main — la somme réellement possédée est modifiée immédiatement', async ({
  page,
  request,
}) => {
  const created = await createSession(request, 3);
  await prepareHero(request, created.session_id);
  await act(request, created.session_id, 'call');
  await openSession(page, created.session_id);

  await page.getByRole('button', { name: 'Modifier Joueur 2' }).click();
  const dialog = page.getByRole('dialog', { name: 'Modifier Joueur 2' });
  await dialog.getByLabel('Tapis réellement possédé maintenant').fill('777');
  await dialog.getByRole('button', { name: 'Appliquer' }).click();

  await expect(dialog).toHaveCount(0);
  await expect(
    page.locator('.player-seat', { hasText: 'Joueur 2' }).locator('.stack-line strong'),
  ).toHaveText(/777 jetons/);
  const state = await getState(request, created.session_id);
  expect(state.players.find((player) => player.id === 'player-2')?.stack).toBe(777);
});

test('Raise au clavier — Entrée dans le champ valide directement la relance', async ({ page, request }) => {
  const created = await createSession(request, 2);
  await prepareHero(request, created.session_id);
  await openSession(page, created.session_id);

  const input = page.getByLabel('Relance totale à');
  await input.fill('300');
  await input.press('Enter');

  await expect
    .poll(async () => {
      const state = await getState(request, created.session_id);
      const last = state.hand.action_log.at(-1);
      return `${last?.player_id ?? ''}:${last?.action ?? ''}`;
    })
    .toBe('hero:raise');
});

test('Paramètres par défaut — les derniers choix restent après réouverture', async ({ page }) => {
  await page.goto('/');
  await page.getByLabel('Nombre maximal de sièges').fill('5');
  await page.getByRole('combobox', { name: 'Unité d’affichage' }).selectOption('fictional_euros');
  const secondPlayer = page.locator('.player-config-row').nth(1);
  await secondPlayer.getByLabel('Nom').fill('Dernier nom');

  const stored = await page.evaluate(() => JSON.parse(localStorage.getItem('poker-ia-config') ?? '{}'));
  expect(stored.player_count).toBe(5);
  expect(stored.unit).toBe('fictional_euros');
  expect(stored.players[1].name).toBe('Dernier nom');

  await page.reload();
  await expect(page.getByLabel('Nombre maximal de sièges')).toHaveValue('5');
  await expect(page.getByRole('combobox', { name: 'Unité d’affichage' })).toHaveValue('fictional_euros');
  await expect(page.locator('.player-config-row').nth(1).getByLabel('Nom')).toHaveValue('Dernier nom');
});
