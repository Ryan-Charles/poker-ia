import type {
  Advice,
  DecisionDetail,
  ExitReport,
  HistoryDecision,
  OpponentProfile,
  SessionConfig,
  TableState,
} from './types';

const API_ROOT = '/api';

export class ApiError extends Error {
  readonly status: number;

  constructor(message: string, status: number) {
    super(message);
    this.name = 'ApiError';
    this.status = status;
  }
}

async function parseError(response: Response): Promise<string> {
  try {
    const payload = (await response.json()) as { detail?: unknown; message?: unknown };
    if (typeof payload.message === 'string') return payload.message;
    if (typeof payload.detail === 'string') return payload.detail;
    if (Array.isArray(payload.detail)) {
      return payload.detail
        .map((entry) =>
          typeof entry === 'object' && entry && 'msg' in entry ? String(entry.msg) : String(entry),
        )
        .join(' · ');
    }
  } catch {
    // Une réponse non JSON est traduite ci-dessous sans exposer de trace technique.
  }
  if (response.status === 404) return 'Cette fonction n’est pas disponible dans le moteur local lancé.';
  if (response.status === 409) return 'Cette action n’est plus légale dans l’état actuel de la main.';
  if (response.status === 422) return 'Les informations saisies sont incomplètes ou incompatibles.';
  return 'Le moteur local n’a pas pu traiter la demande.';
}

async function request<T>(path: string, init: RequestInit = {}): Promise<T> {
  let response: Response;
  try {
    response = await fetch(`${API_ROOT}${path}`, {
      ...init,
      headers: { Accept: 'application/json', 'Content-Type': 'application/json', ...init.headers },
    });
  } catch {
    throw new ApiError('Le moteur local est injoignable. Vérifiez qu’il est bien démarré.', 0);
  }
  if (!response.ok) throw new ApiError(await parseError(response), response.status);
  if (response.status === 204) return undefined as T;
  return (await response.json()) as T;
}

async function requestBlob(path: string): Promise<Blob> {
  const response = await fetch(`${API_ROOT}${path}`, { headers: { Accept: 'application/json,text/csv' } });
  if (!response.ok) throw new ApiError(await parseError(response), response.status);
  return response.blob();
}

function payload<T>(data: T): string {
  return JSON.stringify(data);
}

export const api = {
  health: () => request<{ status: string; version?: string }>('/health'),
  listSessions: () => request<Array<{ id: string; status: string; updated_at: string }>>('/sessions'),
  createSession: (config: SessionConfig) =>
    request<TableState | { session_id: string; state: TableState }>('/sessions', {
      method: 'POST',
      body: payload(config),
    }),
  getState: (sessionId: string) => request<TableState>(`/sessions/${sessionId}/state`),
  action: (sessionId: string, action: string, amount?: number) =>
    request<TableState>(`/sessions/${sessionId}/actions`, {
      method: 'POST',
      body: payload(amount === undefined ? { action } : { action, amount }),
    }),
  setCard: (sessionId: string, slot: string, card: string, playerId?: string) =>
    request<TableState>(`/sessions/${sessionId}/cards`, {
      method: 'POST',
      body: payload(playerId === undefined ? { slot, card } : { slot, card, player_id: playerId }),
    }),
  deleteCard: (sessionId: string, slot: string) =>
    request<TableState>(`/sessions/${sessionId}/cards/${encodeURIComponent(slot)}`, { method: 'DELETE' }),
  undo: (sessionId: string) => request<TableState>(`/sessions/${sessionId}/undo`, { method: 'POST' }),
  redo: (sessionId: string) => request<TableState>(`/sessions/${sessionId}/redo`, { method: 'POST' }),
  restartHand: (sessionId: string) =>
    request<TableState>(`/sessions/${sessionId}/restart-hand`, { method: 'POST' }),
  nextHand: (sessionId: string) =>
    request<TableState>(`/sessions/${sessionId}/next-hand`, { method: 'POST' }),
  getAdvice: (sessionId: string, signal?: AbortSignal) =>
    request<Advice>(`/sessions/${sessionId}/advice`, signal ? { signal } : {}),
  refreshAdvice: (sessionId: string, signal?: AbortSignal) =>
    request<Advice>(`/sessions/${sessionId}/advice`, {
      method: 'POST',
      body: '{}',
      ...(signal ? { signal } : {}),
    }),
  submitShowdown: (
    sessionId: string,
    revealedHands: Record<string, [string, string] | null>,
    manualWinners?: Record<number, string[]>,
  ) =>
    request<TableState>(`/sessions/${sessionId}/showdown`, {
      method: 'POST',
      body: payload(
        manualWinners === undefined
          ? { revealed_hands: revealedHands }
          : { revealed_hands: revealedHands, manual_winners: manualWinners },
      ),
    }),
  updatePlayer: (
    sessionId: string,
    playerId: string,
    changes: { name?: string; stack?: number; status?: string },
  ) =>
    request<TableState>(`/sessions/${sessionId}/players/${playerId}`, {
      method: 'PATCH',
      body: payload(changes),
    }),
  replacePlayer: (
    sessionId: string,
    playerId: string,
    changes: { name: string; stack?: number; initial_profile?: string; custom_profile?: string },
  ) =>
    request<TableState>(`/sessions/${sessionId}/players/${playerId}/replace`, {
      method: 'POST',
      body: payload(changes),
    }),
  removePlayer: (sessionId: string, playerId: string) =>
    request<TableState>(`/sessions/${sessionId}/players/${playerId}/seat`, {
      method: 'DELETE',
    }),
  seatPlayer: (
    sessionId: string,
    playerId: string,
    changes: { name: string; stack: number; initial_profile?: string; custom_profile?: string },
  ) =>
    request<TableState>(`/sessions/${sessionId}/players/${playerId}/seat`, {
      method: 'POST',
      body: payload(changes),
    }),
  saveSession: (sessionId: string) =>
    request<{ saved: boolean; saved_at: string }>(`/sessions/${sessionId}/save`, {
      method: 'POST',
      body: '{}',
    }),
  exitSession: (sessionId: string) =>
    request<ExitReport>(`/sessions/${sessionId}/exit`, { method: 'POST', body: '{}' }),
  history: (query = '') => request<HistoryDecision[]>(`/history${query ? `?${query}` : ''}`),
  historyDetail: (id: string) => request<DecisionDetail>(`/history/${id}`),
  expertAnalysis: (id: string, signal?: AbortSignal) =>
    request<DecisionDetail>(`/history/${id}/expert-analysis`, {
      method: 'POST',
      body: '{}',
      ...(signal ? { signal } : {}),
    }),
  opponents: () => request<OpponentProfile[]>('/opponents'),
  opponent: (id: string) => request<OpponentProfile>(`/opponents/${id}`),
  updateOpponent: (id: string, changes: Partial<Pick<OpponentProfile, 'notes' | 'adaptation_enabled'>>) =>
    request<OpponentProfile>(`/opponents/${id}`, { method: 'PATCH', body: payload(changes) }),
  resetOpponent: (id: string) =>
    request<OpponentProfile>(`/opponents/${id}/reset`, { method: 'POST', body: '{}' }),
  mergeOpponents: (sourceId: string, targetId: string) =>
    request<OpponentProfile>('/opponents/merge', {
      method: 'POST',
      body: payload({ source_id: sourceId, target_id: targetId }),
    }),
  exportOpponent: (id: string) => requestBlob(`/opponents/${id}/export`),
  importOpponent: (profile: unknown) =>
    request<OpponentProfile>('/opponents/import', { method: 'POST', body: payload(profile) }),
  exportSession: (sessionId: string) => requestBlob(`/sessions/${sessionId}/export`),
  exportHand: (sessionId: string, handId: string) =>
    requestBlob(`/sessions/${sessionId}/hands/${handId}/export`),
  exportHistoryCsv: () => requestBlob('/history/export?format=csv'),
  importData: (data: unknown) =>
    request<{ imported: boolean; session_id?: string }>('/import', { method: 'POST', body: payload(data) }),
  deleteAllData: () => request<void>('/data', { method: 'DELETE' }),
};
