import type { Card } from '../types';
import { cardLabel } from '../utils';

interface CardViewProps {
  card?: Card | undefined;
  compact?: boolean | undefined;
  label?: string | undefined;
  active?: boolean | undefined;
  onClick?: (() => void) | undefined;
}

export function CardView({ card, compact = false, label, active = false, onClick }: CardViewProps) {
  const suit = card?.[1];
  const className = `playing-card${compact ? ' compact' : ''}${active ? ' active' : ''}${suit ? ` suit-${suit}` : ' empty'}`;
  const contents = card ? cardLabel(card) : '＋';
  if (onClick) {
    return (
      <button
        type="button"
        className={className}
        onClick={onClick}
        aria-label={`${label ?? 'Carte'}${card ? ` : ${contents}` : ', vide'}`}
        title={label}
      >
        {contents}
      </button>
    );
  }
  return (
    <span className={className} aria-label={label ? `${label} : ${contents}` : contents}>
      {contents}
    </span>
  );
}
