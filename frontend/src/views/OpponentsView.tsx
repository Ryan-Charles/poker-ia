import { useMemo, useRef, useState } from 'react';
import { CardView } from '../components/CardView';
import { api } from '../api';
import { useAppStore } from '../store';
import { PROFILE_LABELS, type OpponentProfile } from '../types';
import { downloadBlob, safeJsonParse } from '../utils';

function EvolutionChart({ profile }: { profile: OpponentProfile }) {
  const points = profile.evolution;
  if (points.length < 2)
    return (
      <p className="insufficient-data">Au moins deux périodes sont nécessaires pour tracer l’évolution.</p>
    );
  const path = (key: 'vpip' | 'pfr' | 'aggression') =>
    points
      .map(
        (point, index) =>
          `${(index / Math.max(1, points.length - 1)) * 100},${100 - Math.min(100, Math.max(0, point[key] * (key === 'aggression' ? 20 : 100)))}`,
      )
      .join(' ');
  return (
    <div className="evolution-chart">
      <svg
        viewBox="0 0 100 100"
        preserveAspectRatio="none"
        role="img"
        aria-label="Évolution du VPIP, PFR et de l’agressivité"
      >
        <g className="chart-grid">
          <line x1="0" y1="25" x2="100" y2="25" />
          <line x1="0" y1="50" x2="100" y2="50" />
          <line x1="0" y1="75" x2="100" y2="75" />
        </g>
        <polyline className="vpip" points={path('vpip')} />
        <polyline className="pfr" points={path('pfr')} />
        <polyline className="aggression" points={path('aggression')} />
      </svg>
      <div className="chart-legend">
        <span className="vpip">VPIP</span>
        <span className="pfr">PFR</span>
        <span className="aggression">Agressivité</span>
      </div>
    </div>
  );
}

function ProfileDetail({ profile }: { profile: OpponentProfile }) {
  const updateOpponent = useAppStore((state) => state.updateOpponent);
  const resetOpponent = useAppStore((state) => state.resetOpponent);
  const opponents = useAppStore((state) => state.opponents);
  const mergeOpponents = useAppStore((state) => state.mergeOpponents);
  const setNotification = useAppStore((state) => state.setNotification);
  const [notes, setNotes] = useState(profile.notes);
  const [mergeTarget, setMergeTarget] = useState('');
  return (
    <section className="opponent-detail panel">
      <header className="opponent-identity">
        <span className="opponent-avatar">{profile.name.slice(0, 2).toUpperCase()}</span>
        <div>
          <p className="eyebrow">Fiche adversaire</p>
          <h2>{profile.name}</h2>
          <p>
            {PROFILE_LABELS[profile.initial_profile]} au départ · {profile.hands_observed} mains observées
          </p>
        </div>
        <div className="profile-confidence">
          <strong>{Math.round(profile.confidence * 100)} %</strong>
          <span>confiance</span>
        </div>
      </header>
      <div className="estimated-profile">
        <span>Profil estimé</span>
        <strong>{profile.estimated_profile}</strong>
        <label className="switch">
          <input
            type="checkbox"
            checked={profile.adaptation_enabled}
            onChange={(event) =>
              void updateOpponent(profile.id, { adaptation_enabled: event.target.checked })
            }
          />
          <i />
          <span>Adaptation exploitante {profile.adaptation_enabled ? 'active' : 'désactivée'}</span>
        </label>
      </div>
      <section>
        <h3>Statistiques comportementales</h3>
        <div className="opponent-stats">
          <span>
            <small>VPIP</small>
            <strong>{(profile.stats.vpip * 100).toFixed(1)} %</strong>
          </span>
          <span>
            <small>PFR</small>
            <strong>{(profile.stats.pfr * 100).toFixed(1)} %</strong>
          </span>
          <span>
            <small>3-bet</small>
            <strong>{(profile.stats.three_bet * 100).toFixed(1)} %</strong>
          </span>
          <span>
            <small>Fold vs c-bet</small>
            <strong>{(profile.stats.fold_to_cbet * 100).toFixed(1)} %</strong>
          </span>
          <span>
            <small>Facteur d’agression</small>
            <strong>{profile.stats.aggression_factor.toFixed(2)}</strong>
          </span>
          <span>
            <small>Mise moyenne</small>
            <strong>{profile.stats.average_bet_percent.toFixed(0)} % pot</strong>
          </span>
        </div>
      </section>
      <section>
        <div className="subheading-row">
          <div>
            <h3>Évolution</h3>
            <p>Les observations récentes reçoivent plus de poids sans effacer l’échantillon antérieur.</p>
          </div>
        </div>
        <EvolutionChart profile={profile} />
      </section>
      <div className="profile-two-columns">
        <section>
          <h3>Tendances récentes</h3>
          <ul className="insight-list">
            {profile.recent_trends.map((trend) => (
              <li key={trend}>{trend}</li>
            ))}
          </ul>
        </section>
        <section>
          <h3>Hypothèses — pas des certitudes</h3>
          <ul className="insight-list hypotheses">
            {profile.hypotheses.map((item) => (
              <li key={item}>{item}</li>
            ))}
          </ul>
        </section>
      </div>
      <section>
        <h3>Ranges estimées par position</h3>
        <div className="ranges-grid">
          {Object.entries(profile.ranges_by_position).map(([position, range]) => (
            <article key={position}>
              <strong>{position}</strong>
              <p>{range}</p>
            </article>
          ))}
        </div>
      </section>
      <section>
        <h3>Tailles de mise fréquentes</h3>
        <div className="sizing-bubbles">
          {profile.frequent_sizings.map((size) => (
            <span key={size}>{size.toFixed(0)} %</span>
          ))}
        </div>
      </section>
      <section>
        <h3>Cartes réellement révélées aux showdowns</h3>
        {profile.revealed_showdowns.length ? (
          <div className="revealed-list">
            {profile.revealed_showdowns.map((showdown) => (
              <article key={showdown.hand_id}>
                <div>
                  {showdown.cards.map((card) => (
                    <CardView key={card} card={card} compact />
                  ))}
                </div>
                <strong>{showdown.classification}</strong>
                <small>{new Intl.DateTimeFormat('fr-FR').format(new Date(showdown.date))}</small>
                {showdown.bluff_observed ? <span className="bluff-badge">Bluff observé</span> : null}
              </article>
            ))}
          </div>
        ) : (
          <p className="empty-inline">
            Aucune carte révélée. Le modèle ne conclut rien sur les mains restées inconnues.
          </p>
        )}
      </section>
      <section>
        <h3>Adaptations recommandées</h3>
        <ul className="adaptation-list">
          {profile.recommended_adaptations.map((item) => (
            <li key={item}>
              <span>→</span>
              {item}
            </li>
          ))}
        </ul>
      </section>
      <section className="notes-section">
        <label className="field">
          <span>Notes manuelles</span>
          <textarea
            rows={5}
            value={notes}
            onChange={(event) => setNotes(event.target.value)}
            placeholder="Vos observations personnelles…"
          />
        </label>
        <button
          type="button"
          className="primary"
          disabled={notes === profile.notes}
          onClick={() => void updateOpponent(profile.id, { notes })}
        >
          Enregistrer les notes
        </button>
      </section>
      <footer className="profile-tools">
        <button
          type="button"
          className="ghost"
          onClick={() =>
            void api
              .exportOpponent(profile.id)
              .then((blob) => downloadBlob(blob, `profil-${profile.name}.json`, 'application/json'))
              .catch((error: Error) => setNotification({ kind: 'error', message: error.message }))
          }
        >
          Exporter ce profil
        </button>
        <div className="merge-control">
          <select
            value={mergeTarget}
            onChange={(event) => setMergeTarget(event.target.value)}
            aria-label="Profil cible de la fusion"
          >
            <option value="">Fusionner vers…</option>
            {opponents
              .filter((candidate) => candidate.id !== profile.id)
              .map((candidate) => (
                <option key={candidate.id} value={candidate.id}>
                  {candidate.name}
                </option>
              ))}
          </select>
          <button
            type="button"
            className="ghost"
            disabled={!mergeTarget}
            onClick={() => void mergeOpponents(profile.id, mergeTarget)}
          >
            Fusionner
          </button>
        </div>
        <button
          type="button"
          className="danger-ghost"
          onClick={() =>
            window.confirm(`Réinitialiser l’apprentissage de ${profile.name} ?`) &&
            void resetOpponent(profile.id)
          }
        >
          Réinitialiser l’apprentissage
        </button>
      </footer>
    </section>
  );
}

export function OpponentsView() {
  const opponents = useAppStore((state) => state.opponents);
  const selectedId = useAppStore((state) => state.selectedOpponentId);
  const selectOpponent = useAppStore((state) => state.selectOpponent);
  const loadOpponents = useAppStore((state) => state.loadOpponents);
  const setNotification = useAppStore((state) => state.setNotification);
  const importRef = useRef<HTMLInputElement>(null);
  const selected = useMemo(
    () => opponents.find((opponent) => opponent.id === selectedId) ?? opponents[0],
    [opponents, selectedId],
  );
  return (
    <main className="opponents-page content-page">
      <header className="page-heading">
        <div>
          <p className="eyebrow">Modèle comportemental local</p>
          <h1>Profils adverses</h1>
          <p>
            Les a priori évoluent avec les actions observées ; un faible échantillon limite automatiquement
            l’adaptation.
          </p>
        </div>
        <div className="page-actions">
          <input
            ref={importRef}
            type="file"
            accept="application/json,.json"
            hidden
            onChange={(event) => {
              const file = event.target.files?.[0];
              if (!file) return;
              void file
                .text()
                .then((text) => api.importOpponent(safeJsonParse(text)))
                .then(() => loadOpponents())
                .catch((error: Error) => setNotification({ kind: 'error', message: error.message }));
            }}
          />
          <button type="button" className="ghost" onClick={() => importRef.current?.click()}>
            Importer un profil
          </button>
        </div>
      </header>
      <div className="opponents-layout">
        <aside className="opponent-list panel">
          <header>
            <strong>
              {opponents.length} adversaire{opponents.length > 1 ? 's' : ''}
            </strong>
            <button
              type="button"
              className="icon-button"
              onClick={() => void loadOpponents()}
              aria-label="Actualiser"
            >
              ↻
            </button>
          </header>
          {opponents.length ? (
            opponents.map((opponent) => (
              <button
                type="button"
                key={opponent.id}
                className={selected?.id === opponent.id ? 'active' : ''}
                onClick={() => selectOpponent(opponent.id)}
              >
                <span className="opponent-avatar small">{opponent.name.slice(0, 2).toUpperCase()}</span>
                <div>
                  <strong>{opponent.name}</strong>
                  <small>{opponent.estimated_profile}</small>
                  <span className="confidence-bar">
                    <i style={{ width: `${opponent.confidence * 100}%` }} />
                  </span>
                </div>
                <b>{opponent.hands_observed}</b>
              </button>
            ))
          ) : (
            <div className="empty-state compact">
              <p>Les adversaires apparaîtront après la première session enregistrée.</p>
            </div>
          )}
        </aside>
        {selected ? (
          <ProfileDetail key={selected.id} profile={selected} />
        ) : (
          <section className="panel empty-state">
            <span>◎</span>
            <h2>Aucun profil sélectionné</h2>
            <p>Jouez une session ou importez une fiche adverse.</p>
          </section>
        )}
      </div>
    </main>
  );
}
