import {
  MAIN_CARD_SLOTS,
  type ActionLogEntry,
  type Card,
  type MainCardSlot,
  type PlayerConfig,
  type PlayerState,
  type SessionConfig,
  type Street,
  type TableState,
  type Unit,
} from './types';

export const ALL_CARDS: Card[] = ['s', 'h', 'd', 'c'].flatMap((suit) =>
  ['A', 'K', 'Q', 'J', 'T', '9', '8', '7', '6', '5', '4', '3', '2'].map((rank) => `${rank}${suit}` as Card),
);

export const SUIT_SYMBOL: Record<string, string> = { s: '♠', h: '♥', d: '♦', c: '♣' };
export const SUIT_LABEL: Record<string, string> = { s: 'Pique', h: 'Cœur', d: 'Carreau', c: 'Trèfle' };
export const RANK_LABEL: Record<string, string> = { A: 'A', K: 'K', Q: 'Q', J: 'J', T: '10' };

export function cardLabel(card: string): string {
  return `${RANK_LABEL[card[0] ?? ''] ?? card[0] ?? ''}${SUIT_SYMBOL[card[1] ?? ''] ?? ''}`;
}

const ACTION_VERBS: Record<string, string> = {
  fold: 'Fold',
  check: 'Check',
  call: 'Call',
  all_in_call: 'Call (tapis)',
  bet: 'Raise',
  raise: 'Raise',
  all_in: 'All-in',
};

/**
 * Traduit une chaîne brute d'action du moteur (ex. 'call', 'raise') en
 * vocabulaire poker anglais affiché à l'écran. Les chaînes inconnues sont
 * retournées telles quelles plutôt que vidées, pour ne jamais masquer une
 * information imprévue venant du backend.
 */
export function actionVerb(raw: string | null): string {
  if (raw === null) return '';
  return ACTION_VERBS[raw] ?? raw;
}

export function formatCardList(cards: readonly Card[]): string {
  return cards.map((card) => cardLabel(card)).join(' ');
}

export function playerName(table: TableState, playerId: string): string {
  if (playerId === 'hero') return 'Ryanchl';
  return table.players.find((player) => player.id === playerId)?.name ?? playerId;
}

export function amountScale(unit: Unit, bigBlind = 100): number {
  if (unit === 'fictional_euros') return 100;
  if (unit === 'big_blinds') return Math.max(1, bigBlind);
  return 1;
}

export function fromEngineAmount(value: number, unit: Unit, bigBlind = 100): number {
  return value / amountScale(unit, bigBlind);
}

export function toEngineAmount(value: number, unit: Unit, bigBlind = 100): number {
  return Math.round(value * amountScale(unit, bigBlind));
}

export function formatAmount(value: number, unit: Unit = 'chips', bigBlind = 100): string {
  const displayValue = fromEngineAmount(value, unit, bigBlind);
  const formatted = new Intl.NumberFormat('fr-FR', { maximumFractionDigits: 2 }).format(displayValue);
  if (unit === 'fictional_euros') return `${formatted} € fictifs`;
  if (unit === 'big_blinds') return `${formatted} BB`;
  return `${formatted} jetons`;
}

/* Montant court pour les boutons d'action : le nombre seul (suffixe bref hors
   jetons), afin de garder « Call 100 » compact comme demandé par Ryan. */
export function shortAmount(value: number, unit: Unit = 'chips', bigBlind = 100): string {
  const formatted = new Intl.NumberFormat('fr-FR', { maximumFractionDigits: 2 }).format(
    fromEngineAmount(value, unit, bigBlind),
  );
  if (unit === 'fictional_euros') return `${formatted} €`;
  if (unit === 'big_blinds') return `${formatted} BB`;
  return formatted;
}

export function formatConfiguredAmount(value: number, unit: Unit): string {
  const formatted = new Intl.NumberFormat('fr-FR', { maximumFractionDigits: 2 }).format(value);
  if (unit === 'fictional_euros') return `${formatted} € fictifs`;
  if (unit === 'big_blinds') return `${formatted} BB`;
  return `${formatted} jetons`;
}

export function convertConfigurationUnit(config: SessionConfig, unit: Unit): SessionConfig {
  if (config.unit === unit) return config;
  const previousScale = amountScale(config.unit);
  const nextScale = amountScale(unit);
  const convert = (value: number) => (value * previousScale) / nextScale;
  return {
    ...config,
    unit,
    players: config.players.map((player) => ({ ...player, stack: convert(player.stack) })),
    small_blind: convert(config.small_blind),
    big_blind: convert(config.big_blind),
    ante: convert(config.ante),
    blind_levels: config.blind_levels.map((level) => ({
      ...level,
      small_blind: convert(level.small_blind),
      big_blind: convert(level.big_blind),
      ante: convert(level.ante),
    })),
  };
}

export function configurationForApi(config: SessionConfig): SessionConfig {
  const scale = amountScale(config.unit);
  const convert = (value: number) => Math.round(value * scale);
  return {
    ...config,
    players: config.players.map((player) => ({ ...player, stack: convert(player.stack) })),
    small_blind: convert(config.small_blind),
    big_blind: convert(config.big_blind),
    ante: convert(config.ante),
    blind_levels: config.blind_levels.map((level) => ({
      ...level,
      small_blind: convert(level.small_blind),
      big_blind: convert(level.big_blind),
      ante: convert(level.ante),
    })),
  };
}

export function clamp(value: number, min: number, max: number): number {
  return Math.min(Math.max(value, min), max);
}

export function nextEmptySlot(
  cards: Partial<Record<MainCardSlot, Card>>,
  required: readonly MainCardSlot[] = MAIN_CARD_SLOTS,
): MainCardSlot | null {
  return required.find((slot) => cards[slot] === undefined) ?? null;
}

/**
 * Dérive le bouton et la petite blinde à partir des sièges et de la grosse blinde choisie.
 * Ordre circulaire croissant des sièges : la petite blinde est le joueur qui précède
 * immédiatement la grosse blinde, le bouton précède la petite blinde. En heads-up
 * (2 joueurs), le bouton EST la petite blinde.
 */
export function derivePositionsFromBigBlind(
  players: PlayerConfig[],
  bigBlindId: string,
): { dealer_id: string; small_blind_id: string; big_blind_id: string } {
  const sorted = [...players].sort((a, b) => a.seat - b.seat);
  const count = sorted.length;
  const bbIndex = sorted.findIndex((player) => player.id === bigBlindId);
  if (count === 0 || bbIndex === -1) {
    const fallback = sorted[0]?.id ?? bigBlindId;
    return { dealer_id: fallback, small_blind_id: fallback, big_blind_id: bigBlindId };
  }
  if (count === 1) return { dealer_id: bigBlindId, small_blind_id: bigBlindId, big_blind_id: bigBlindId };
  const sbIndex = (bbIndex - 1 + count) % count;
  const smallBlindId = sorted[sbIndex]!.id;
  if (count === 2) return { dealer_id: smallBlindId, small_blind_id: smallBlindId, big_blind_id: bigBlindId };
  const dealerIndex = (sbIndex - 1 + count) % count;
  const dealerId = sorted[dealerIndex]!.id;
  return { dealer_id: dealerId, small_blind_id: smallBlindId, big_blind_id: bigBlindId };
}

export function assertValidConfiguration(config: SessionConfig): string[] {
  const errors: string[] = [];
  if (config.player_count < 2 || config.player_count > 8)
    errors.push('La table doit réunir de 2 à 8 joueurs.');
  if (config.players.length !== config.player_count)
    errors.push('Le nombre de sièges ne correspond pas au nombre de joueurs.');
  if (config.players.some((player) => !player.name.trim()))
    errors.push('Chaque adversaire doit avoir un nom.');
  if (
    new Set(config.players.map((player) => player.name.trim().toLocaleLowerCase('fr'))).size !==
    config.players.length
  )
    errors.push('Les noms des joueurs doivent être uniques.');
  if (config.players.some((player) => !Number.isFinite(player.stack) || player.stack <= 0))
    errors.push('Chaque tapis doit être strictement positif.');
  if (!(config.small_blind > 0) || !(config.big_blind > config.small_blind))
    errors.push('La grosse blinde doit être supérieure à une petite blinde positive.');
  if (config.ante < 0) errors.push('L’ante ne peut pas être négative.');
  const playerIds = new Set(config.players.map((player) => player.id));
  if (![config.dealer_id, config.small_blind_id, config.big_blind_id].every((id) => playerIds.has(id)))
    errors.push('Le bouton et les blindes doivent être attribués à des joueurs présents.');
  if (
    config.player_count > 2 &&
    new Set([config.dealer_id, config.small_blind_id, config.big_blind_id]).size !== 3
  )
    errors.push('À plus de deux joueurs, bouton, petite blinde et grosse blinde doivent être distincts.');
  if (config.player_count === 2 && config.dealer_id !== config.small_blind_id)
    errors.push('En heads-up, le bouton doit être en petite blinde.');
  if (config.game_mode === 'tournament') {
    if (
      config.blind_levels.some(
        (level) =>
          !Number.isInteger(level.after_hands) ||
          level.after_hands < 1 ||
          !(level.small_blind > 0) ||
          !(level.big_blind > level.small_blind) ||
          level.ante < 0,
      )
    )
      errors.push(
        'Chaque niveau doit avoir un nombre de mains positif, des blindes valides et un ante positif ou nul.',
      );
    if (
      config.blind_levels.some(
        (level, index) => index > 0 && level.after_hands <= config.blind_levels[index - 1]!.after_hands,
      )
    )
      errors.push(
        'Les niveaux de tournoi doivent être ordonnés par un nombre de mains strictement croissant.',
      );
  }
  return errors;
}

/**
 * Angle (degrés, coordonnées écran y vers le bas) du siège d'un joueur.
 * Hero est fixe à 90° (bas centre). Les adversaires sont numérotés 1..M dans
 * l'ordre des sièges en partant de celui qui suit hero (liste triée par siège
 * puis pivotée pour que hero soit premier), et répartis sur l'arc de 250°
 * restant : le jeu tourne visuellement dans le sens horaire (hero → bas-gauche
 * → gauche → haut → droite → bas-droite → hero) et les 110° du bas
 * (35°-145°) restent réservés à hero seul.
 */
function seatAngleDegrees(player: PlayerState, players: PlayerState[]): number {
  if (player.id === 'hero') return 90;
  const sortedBySeat = [...players].sort((a, b) => a.seat - b.seat);
  const heroIndex = sortedBySeat.findIndex((candidate) => candidate.id === 'hero');
  const rotated =
    heroIndex === -1 ? sortedBySeat : [...sortedBySeat.slice(heroIndex), ...sortedBySeat.slice(0, heroIndex)];
  const opponents = rotated.filter((candidate) => candidate.id !== 'hero');
  const index = opponents.findIndex((candidate) => candidate.id === player.id);
  const M = opponents.length;
  if (index === -1 || M === 0) return 90;
  const i = index + 1;
  return 145 + (250 * (i - 0.5)) / M;
}

export function tablePosition(player: PlayerState, players: PlayerState[]): { left: string; top: string } {
  const radians = (seatAngleDegrees(player, players) * Math.PI) / 180;
  // Rayon vertical 48 (et non 46) : les paires diagonales voisines (θ≈170/220°)
  // se touchaient à 1-2 px près à 1600×900 avec les bulles complètes.
  return {
    left: `${50 + 48 * Math.cos(radians)}%`,
    top: `${50 + 48 * Math.sin(radians)}%`,
  };
}

/**
 * Position des jetons misés : même angle que le siège du joueur, mais ramenée
 * vers le centre du tapis (56 % du rayon des bulles) pour rester visuellement
 * entre le joueur et le pot.
 */
export function betMarkerPosition(
  player: PlayerState,
  players: PlayerState[],
): { left: string; top: string } {
  const radians = (seatAngleDegrees(player, players) * Math.PI) / 180;
  const factor = 0.56;
  return {
    left: `${50 + 48 * factor * Math.cos(radians)}%`,
    top: `${50 + 48 * factor * Math.sin(radians)}%`,
  };
}

/**
 * Nombre de jetons à empiler par joueur pour la rue en cours, calculé à
 * partir du journal d'actions (filtré sur la rue courante, trié par
 * séquence). Règle demandée : 1 jeton pour une mise ou un call ; chaque
 * relance qui dépasse la mise la plus haute déjà vue sur la rue affiche un
 * jeton de plus que cette mise précédente. Les blindes forcées n'apparaissent
 * pas dans le journal : un joueur avec une mise de rue mais aucune entrée
 * (typiquement SB/BB avant toute action) reçoit 1 jeton. L'affichage plafonne
 * ensuite ce nombre à 5 (le montant textuel, lui, reste exact).
 */
export function betChipCounts(
  actionLog: ActionLogEntry[],
  street: Street,
  bigBlind: number,
  players: PlayerState[],
): Record<string, number> {
  const streetTotal: Record<string, number> = {};
  const chips: Record<string, number> = {};
  let maxTotal = street === 'preflop' ? bigBlind : 0;
  let level = street === 'preflop' ? 1 : 0;
  const entries = actionLog
    .filter((entry) => entry.street === street && entry.amount > 0)
    .sort((a, b) => a.sequence - b.sequence);
  for (const entry of entries) {
    const total = (streetTotal[entry.player_id] ?? 0) + entry.amount;
    streetTotal[entry.player_id] = total;
    if (total > maxTotal) {
      level = maxTotal > 0 ? level + 1 : 1;
      maxTotal = total;
      chips[entry.player_id] = level;
    } else {
      chips[entry.player_id] = 1;
    }
  }
  for (const player of players) {
    if (player.street_bet > 0 && chips[player.id] === undefined) chips[player.id] = 1;
  }
  return chips;
}

export function downloadBlob(contents: BlobPart, filename: string, type: string): void {
  const url = URL.createObjectURL(new Blob([contents], { type }));
  const anchor = document.createElement('a');
  anchor.href = url;
  anchor.download = filename;
  anchor.click();
  URL.revokeObjectURL(url);
}

export function safeJsonParse(value: string): unknown {
  try {
    return JSON.parse(value) as unknown;
  } catch {
    throw new Error('Le fichier choisi ne contient pas un JSON valide.');
  }
}
