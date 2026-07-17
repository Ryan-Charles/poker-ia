export const RANKS = ['A', 'K', 'Q', 'J', 'T', '9', '8', '7', '6', '5', '4', '3', '2'] as const;
export const SUITS = ['s', 'h', 'd', 'c'] as const;
export type Rank = (typeof RANKS)[number];
export type Suit = (typeof SUITS)[number];
export type Card = `${Rank}${Suit}`;

export const MAIN_CARD_SLOTS = ['hero_1', 'hero_2', 'flop_1', 'flop_2', 'flop_3', 'turn', 'river'] as const;
export type MainCardSlot = (typeof MAIN_CARD_SLOTS)[number];
export type CardSlot = MainCardSlot | `showdown:${string}:1` | `showdown:${string}:2`;

export type Street = 'preflop' | 'flop' | 'turn' | 'river' | 'showdown' | 'terminee';
export type Phase = 'playing' | 'awaiting_cards' | 'showdown' | 'summary' | 'ended';
export type ViewName = 'configuration' | 'table' | 'historique' | 'adversaires' | 'bilan' | 'parametres';
export type PlayerStatus = 'active' | 'folded' | 'all_in' | 'away' | 'eliminated';
export type Unit = 'chips' | 'fictional_euros' | 'big_blinds';
export type GameMode = 'cash' | 'tournament';
export type AnteType = 'classic' | 'big_blind_ante';
export type AdviceMode = 'immediate' | 'quiz';
export type OpponentArchetype =
  | 'unknown'
  | 'very_tight'
  | 'tag'
  | 'lag'
  | 'loose_passive'
  | 'calling_station'
  | 'very_aggressive'
  | 'unpredictable'
  | 'custom';

export interface PlayerConfig {
  id: string;
  name: string;
  seat: number;
  stack: number;
  initial_profile: OpponentArchetype;
  custom_profile?: string;
}

export interface BlindLevel {
  after_hands: number;
  small_blind: number;
  big_blind: number;
  ante: number;
}

export interface SessionConfig {
  player_count: number;
  players: PlayerConfig[];
  unit: Unit;
  small_blind: number;
  big_blind: number;
  ante: number;
  ante_type: AnteType;
  game_mode: GameMode;
  dealer_id: string;
  small_blind_id: string;
  big_blind_id: string;
  blind_levels: BlindLevel[];
  advice_mode: AdviceMode;
}

export interface EstimatedProfile {
  initial: OpponentArchetype;
  estimated: string;
  confidence: number;
  hands_observed: number;
  adaptation_enabled: boolean;
}

export interface PlayerState {
  id: string;
  name: string;
  seat: number;
  position: string;
  stack: number;
  stack_bb: number;
  street_bet: number;
  total_contribution: number;
  last_action: string | null;
  status: PlayerStatus;
  pending_join?: boolean;
  is_dealer: boolean;
  is_small_blind: boolean;
  is_big_blind: boolean;
  profile: EstimatedProfile;
}

export interface SidePot {
  index: number;
  amount: number;
  eligible_player_ids: string[];
  winner_ids?: string[];
  shares?: Record<string, number>;
}

export interface ActionLogEntry {
  id: string;
  sequence: number;
  player_id: string;
  player_name: string;
  street: Street;
  action: string;
  amount: number;
  pot_after: number;
  created_at?: string;
}

export interface HandSummaryPlayer {
  player_id: string;
  name: string;
  revealed_cards?: Card[];
  best_five?: Card[];
  hand_name?: string;
  received: number;
  net: number;
}

export interface HandSummary {
  status: 'won' | 'lost' | 'split' | 'incomplete' | 'won_without_showdown';
  winners: string[];
  total_pot: number;
  hero_contribution: number;
  hero_received: number;
  hero_net: number;
  hero_net_bb: number;
  hero_new_stack: number;
  session_net: number;
  players: HandSummaryPlayer[];
  pots: SidePot[];
  principal_advice?: string;
  hero_action?: string;
  advice_difference?: string;
}

export interface HandState {
  id: string;
  number: number;
  street: Street;
  phase: Phase;
  unit: Unit;
  small_blind: number;
  big_blind: number;
  ante: number;
  pot: number;
  side_pots: SidePot[];
  to_call: number;
  current_bet: number;
  last_full_raise: number;
  active_player_id: string | null;
  players_remaining: number;
  board: Card[];
  hero_cards: Card[];
  action_log: ActionLogEntry[];
  showdown_player_ids?: string[];
  summary?: HandSummary;
}

export type LegalActionName = 'fold' | 'check' | 'call' | 'bet' | 'raise' | 'all_in';
export interface LegalAction {
  action: LegalActionName;
  enabled: boolean;
  reason?: string;
  min_amount?: number;
  max_amount?: number;
  call_amount?: number;
  all_in_call?: boolean;
}

export interface AdviceOption {
  action: LegalActionName;
  label: string;
  amount?: number;
  frequency?: number;
  ev?: number;
}

export interface AdviceSection {
  headline: string;
  action: LegalActionName;
  amount?: number;
  confidence: number;
  source: 'precomputed' | 'simulation' | 'solver' | 'model';
  is_exact: boolean;
  explanation?: string;
  options: AdviceOption[];
}

export interface Advice {
  id: string;
  hand_id: string;
  street: Street;
  balanced: AdviceSection;
  exploitative: AdviceSection;
  final: AdviceSection;
  robust_action: AdviceOption;
  pot_odds: number;
  minimum_equity: number;
  estimated_equity: number;
  spr: number;
  effective_stack: number;
  limitations: string[];
  explanation_pending: boolean;
}

export interface SelectorState {
  next_slot: MainCardSlot | null;
  required_slots: MainCardSlot[];
}

export interface TableState {
  session_id: string;
  config?: SessionConfig;
  hand: HandState;
  players: PlayerState[];
  legal_actions: LegalAction[];
  selector: SelectorState;
  advice?: Advice;
  persistence_status: 'saved' | 'saving' | 'error';
}

export interface HistoryDecision {
  id: string;
  hand_id: string;
  hand_number: number;
  date: string;
  street: Street;
  position: string;
  hero_cards: Card[];
  board: Card[];
  preceding_action: string;
  balanced_advice: string;
  exploitative_advice: string;
  final_advice: string;
  recommended_amount?: number;
  chosen_action: string;
  ev_difference: number;
  hand_result: number;
  quality: 'excellent' | 'acceptable' | 'questionable' | 'mistake';
  confidence: number;
  opponent_ids: string[];
  effective_stack_bb: number;
  short_explanation: string;
  unit: Unit;
  big_blind: number;
}

export interface DecisionDetail extends HistoryDecision {
  table_state: Omit<TableState, 'advice'>;
  known_cards: Card[];
  prior_actions: ActionLogEntry[];
  replay_steps: DecisionReplayStep[];
  estimated_ranges: Record<string, string[]>;
  statistics_used: Record<string, number>;
  pot_odds: number;
  equity: number;
  spr: number;
  action_evs: AdviceOption[];
  real_result: number;
  detailed_explanation: string;
  limitations: string[];
}

export interface DecisionReplayStep {
  index: number;
  cursor: number;
  event_type: string;
  label: string;
  actor_id: string | null;
  actor_name: string | null;
  action: LegalActionName | null;
  amount: number | null;
  pot: number;
  street: Street;
  next_actor_id: string | null;
  known_cards: Card[];
  table_state: Omit<TableState, 'advice'>;
  estimated_ranges: Record<string, string[]>;
  opponent_profiles: Record<string, { estimated: string; confidence: number; hands_observed: number }>;
  advice: {
    balanced: string;
    exploitative: string;
    final: string;
    recommended_amount?: number;
    confidence: number;
  } | null;
}

export interface OpponentStats {
  vpip: number;
  pfr: number;
  three_bet: number;
  fold_to_cbet: number;
  aggression_factor: number;
  average_bet_percent: number;
}

export interface RevealedShowdown {
  hand_id: string;
  date: string;
  cards: Card[];
  classification: string;
  bluff_observed: boolean;
}

export interface OpponentProfile {
  id: string;
  name: string;
  initial_profile: OpponentArchetype;
  estimated_profile: string;
  confidence: number;
  hands_observed: number;
  stats: OpponentStats;
  recent_trends: string[];
  hypotheses: string[];
  ranges_by_position: Record<string, string>;
  frequent_sizings: number[];
  revealed_showdowns: RevealedShowdown[];
  notes: string;
  recommended_adaptations: string[];
  adaptation_enabled: boolean;
  evolution: Array<{ hand: number; vpip: number; pfr: number; aggression: number }>;
}

export interface ExitReport {
  session_id: string;
  started_at: string;
  ended_at: string;
  hands_played: number;
  initial_stack: number;
  final_stack: number;
  net_result: number;
  net_result_bb: number;
  unit: Unit;
  big_blind: number;
  hands_won: number;
  hands_lost: number;
  split_pots: number;
  wins_without_showdown: number;
  showdown_wins: number;
  biggest_pot_won: number;
  biggest_pot_lost: number;
  decisions: number;
  excellent: number;
  acceptable: number;
  mistakes: number;
  advice_follow_rate: number;
  street_mistakes: Record<string, number>;
  insights: string[];
}

export interface ApiErrorPayload {
  detail?: string | { msg?: string }[];
  message?: string;
}

export const PROFILE_LABELS: Record<OpponentArchetype, string> = {
  unknown: 'Inconnu',
  very_tight: 'Très serré',
  tag: 'Serré-agressif',
  lag: 'Large-agressif',
  loose_passive: 'Large-passif',
  calling_station: 'Calling station',
  very_aggressive: 'Très agressif',
  unpredictable: 'Imprévisible',
  custom: 'Personnalisé',
};

export const STREET_LABELS: Record<Street, string> = {
  preflop: 'Préflop',
  flop: 'Flop',
  turn: 'Turn',
  river: 'River',
  showdown: 'Showdown',
  terminee: 'Terminée',
};

export const ACTION_LABELS: Record<LegalActionName, string> = {
  fold: 'Fold',
  check: 'Check',
  call: 'Call',
  bet: 'Raise',
  raise: 'Raise',
  all_in: 'All-in',
};

export const SLOT_LABELS: Record<MainCardSlot, string> = {
  hero_1: 'Carte Ryanchl 1',
  hero_2: 'Carte Ryanchl 2',
  flop_1: 'Flop 1',
  flop_2: 'Flop 2',
  flop_3: 'Flop 3',
  turn: 'Turn',
  river: 'River',
};
