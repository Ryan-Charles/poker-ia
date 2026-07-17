import { useMemo } from 'react';
import { LoadingButton } from '../components/LoadingButton';
import { DEFAULT_CONFIG, useAppStore } from '../store';
import { PROFILE_LABELS, type OpponentArchetype, type PlayerConfig, type SessionConfig } from '../types';
import { convertConfigurationUnit, derivePositionsFromBigBlind, formatConfiguredAmount } from '../utils';

function NumberField({
  label,
  value,
  onChange,
  min = 0,
  step = 1,
  suffix,
}: {
  label: string;
  value: number;
  onChange: (value: number) => void;
  min?: number;
  step?: number;
  suffix?: string;
}) {
  return (
    <label className="field">
      <span>{label}</span>
      <span className="input-with-suffix">
        <input
          type="number"
          value={Number.isFinite(value) ? value : ''}
          min={min}
          step={step}
          onChange={(event) => onChange(event.target.valueAsNumber)}
        />
        {suffix ? <small>{suffix}</small> : null}
      </span>
    </label>
  );
}

export function ConfigurationView() {
  const config = useAppStore((state) => state.config);
  const setConfig = useAppStore((state) => state.setConfig);
  const setPlayerCount = useAppStore((state) => state.setPlayerCount);
  const createSession = useAppStore((state) => state.createSession);
  const resumeSession = useAppStore((state) => state.resumeSession);
  const errors = useAppStore((state) => state.validationErrors);
  const busy = useAppStore((state) => state.busy);
  const exitReport = useAppStore((state) => state.exitReport);
  const setView = useAppStore((state) => state.setView);
  const savedSession = localStorage.getItem('poker-ia-session');

  const update = <K extends keyof SessionConfig>(key: K, value: SessionConfig[K]) =>
    setConfig({ ...config, [key]: value });

  const updatePlayer = (index: number, changes: Partial<PlayerConfig>) => {
    const players = config.players.map((player, playerIndex) =>
      playerIndex === index ? { ...player, ...changes } : player,
    );
    update('players', players);
  };

  const roleOptions = useMemo(
    () =>
      config.players.map((player) => ({ value: player.id, label: `${player.name} · siège ${player.seat}` })),
    [config.players],
  );

  const updateBigBlind = (bigBlindId: string) => {
    const positions = derivePositionsFromBigBlind(config.players, bigBlindId);
    setConfig({ ...config, ...positions });
  };
  const displayPlayerName = (player: PlayerConfig | undefined) =>
    player ? (player.id === 'hero' ? 'Ryanchl' : player.name) : '—';
  const smallBlindPlayer = config.players.find((player) => player.id === config.small_blind_id);
  const dealerPlayer = config.players.find((player) => player.id === config.dealer_id);

  return (
    <main className="configuration-page">
      <section className="configuration-hero">
        <div>
          <p className="eyebrow">Simulateur No-Limit Texas Hold’em</p>
          <h1>Préparez une table d’entraînement réaliste.</h1>
          <p>
            Contrôlez tous les joueurs, saisissez les cartes connues et recevez des conseils expliqués sans
            argent réel, compte externe ni connexion à une plateforme de poker.
          </p>
          {exitReport ? (
            <button
              type="button"
              className="ghost small previous-report-button"
              onClick={() => setView('bilan')}
            >
              Voir le bilan de la table précédente
            </button>
          ) : null}
        </div>
        <div className="hero-mark" aria-hidden="true">
          <img src="/assets/poker-ia-logo.png" alt="" />
        </div>
      </section>

      {savedSession ? (
        <section className="resume-banner">
          <span aria-hidden="true">↻</span>
          <div>
            <strong>Une session locale est disponible</strong>
            <p>
              Retrouvez les tapis, la main en cours et l’historique exactement au dernier état sauvegardé.
            </p>
          </div>
          <LoadingButton loading={busy} type="button" onClick={() => void resumeSession(savedSession)}>
            Reprendre la session
          </LoadingButton>
        </section>
      ) : null}

      <form
        className="configuration-form"
        noValidate
        onSubmit={(event) => {
          event.preventDefault();
          void createSession();
        }}
      >
        <section className="config-card player-count-card">
          <div className="section-heading">
            <span className="step">01</span>
            <div>
              <h2>Composition de la table</h2>
              <p>
                Choisissez le nombre maximal de sièges. Pendant la partie, les boutons − et + permettent de
                libérer ou réoccuper chaque siège adverse.
              </p>
            </div>
          </div>
          <div className="range-field">
            <label htmlFor="player-count">Nombre maximal de sièges</label>
            <output htmlFor="player-count">{config.player_count}</output>
            <input
              id="player-count"
              type="range"
              min="2"
              max="8"
              value={config.player_count}
              onChange={(event) => setPlayerCount(Number(event.target.value))}
            />
            <div className="range-labels" aria-hidden="true">
              <span>Heads-up</span>
              <span>6-max</span>
              <span>8 joueurs</span>
            </div>
          </div>
          <div className="player-config-list">
            {config.players.map((player, index) => (
              <article className={`player-config-row ${player.id === 'hero' ? 'hero' : ''}`} key={player.id}>
                <span className="seat-number">{player.seat}</span>
                <label className="field grow">
                  <span>Nom</span>
                  <input
                    value={player.id === 'hero' ? 'Ryanchl' : player.name}
                    disabled={player.id === 'hero'}
                    maxLength={30}
                    onChange={(event) => updatePlayer(index, { name: event.target.value })}
                  />
                </label>
                <NumberField
                  label="Tapis initial"
                  value={player.stack}
                  min={config.big_blind}
                  onChange={(stack) => updatePlayer(index, { stack })}
                  suffix={
                    config.unit === 'big_blinds'
                      ? 'BB'
                      : config.unit === 'fictional_euros'
                        ? '€ fictifs'
                        : 'jetons'
                  }
                />
                {player.id !== 'hero' ? (
                  <label className="field profile-field">
                    <span>A priori facultatif</span>
                    <select
                      value={player.initial_profile}
                      onChange={(event) =>
                        updatePlayer(index, { initial_profile: event.target.value as OpponentArchetype })
                      }
                    >
                      {Object.entries(PROFILE_LABELS).map(([value, label]) => (
                        <option value={value} key={value}>
                          {label}
                        </option>
                      ))}
                    </select>
                  </label>
                ) : (
                  <span className="hero-lock">Joueur principal</span>
                )}
                {player.initial_profile === 'custom' && player.id !== 'hero' ? (
                  <label className="field custom-profile">
                    <span>Description du profil</span>
                    <input
                      value={player.custom_profile ?? ''}
                      onChange={(event) => updatePlayer(index, { custom_profile: event.target.value })}
                      placeholder="Ex. sur-relance beaucoup au bouton"
                    />
                  </label>
                ) : null}
              </article>
            ))}
          </div>
        </section>

        <section className="config-card">
          <div className="section-heading">
            <span className="step">02</span>
            <div>
              <h2>Structure et positions</h2>
              <p>Les contrôles empêchent de lancer une configuration impossible.</p>
            </div>
          </div>
          <div className="form-grid four">
            <label className="field">
              <span>Unité d’affichage</span>
              <select
                value={config.unit}
                onChange={(event) =>
                  setConfig(convertConfigurationUnit(config, event.target.value as SessionConfig['unit']))
                }
              >
                <option value="chips">Jetons</option>
                <option value="fictional_euros">Euros fictifs</option>
                <option value="big_blinds">Grosses blindes</option>
              </select>
            </label>
            <NumberField
              label="Petite blinde"
              value={config.small_blind}
              min={0.01}
              step={config.unit === 'fictional_euros' ? 0.01 : 1}
              onChange={(small_blind) => update('small_blind', small_blind)}
            />
            <NumberField
              label="Grosse blinde"
              value={config.big_blind}
              min={0.02}
              step={config.unit === 'fictional_euros' ? 0.01 : 1}
              onChange={(big_blind) => update('big_blind', big_blind)}
            />
            <NumberField label="Ante" value={config.ante} min={0} onChange={(ante) => update('ante', ante)} />
            <label className="field">
              <span>Type d’ante</span>
              <select
                value={config.ante_type}
                onChange={(event) => update('ante_type', event.target.value as SessionConfig['ante_type'])}
                disabled={config.ante === 0}
              >
                <option value="classic">Ante classique</option>
                <option value="big_blind_ante">Big blind ante</option>
              </select>
            </label>
            <label className="field">
              <span>Grosse blinde</span>
              <select value={config.big_blind_id} onChange={(event) => updateBigBlind(event.target.value)}>
                {roleOptions.map((option) => (
                  <option value={option.value} key={option.value}>
                    {option.label}
                  </option>
                ))}
              </select>
            </label>
            <div className="field derived-role-field">
              <span>Petite blinde (dérivée)</span>
              <output>
                {displayPlayerName(smallBlindPlayer)}
                {smallBlindPlayer ? ` · siège ${smallBlindPlayer.seat}` : ''}
              </output>
            </div>
            <div className="field derived-role-field">
              <span>Bouton (dérivé)</span>
              <output>
                {displayPlayerName(dealerPlayer)}
                {dealerPlayer ? ` · siège ${dealerPlayer.seat}` : ''}
              </output>
            </div>
          </div>
          <div className="blind-summary">
            <span>Structure</span>
            <strong>
              {formatConfiguredAmount(config.small_blind, config.unit)} /{' '}
              {formatConfiguredAmount(config.big_blind, config.unit)}
              {config.ante ? ` · ante ${formatConfiguredAmount(config.ante, config.unit)}` : ''}
            </strong>
          </div>
        </section>

        <section className="config-card">
          <div className="section-heading">
            <span className="step">03</span>
            <div>
              <h2>Mode d’entraînement</h2>
              <p>
                Le conseil reste probabiliste et distingue toujours référence équilibrée et adaptation
                exploitante.
              </p>
            </div>
          </div>
          <div className="choice-cards">
            <label className={config.game_mode === 'cash' ? 'selected' : ''}>
              <input
                type="radio"
                name="game-mode"
                checked={config.game_mode === 'cash'}
                onChange={() => update('game_mode', 'cash')}
              />
              <strong>Cash game fictif</strong>
              <span>Blindes stables et gestion libre des tapis.</span>
            </label>
            <label className={config.game_mode === 'tournament' ? 'selected' : ''}>
              <input
                type="radio"
                name="game-mode"
                checked={config.game_mode === 'tournament'}
                onChange={() => update('game_mode', 'tournament')}
              />
              <strong>Tournoi fictif</strong>
              <span>Éliminations et niveaux de blindes facultatifs.</span>
            </label>
            <label className={config.advice_mode === 'immediate' ? 'selected' : ''}>
              <input
                type="radio"
                name="advice-mode"
                checked={config.advice_mode === 'immediate'}
                onChange={() => update('advice_mode', 'immediate')}
              />
              <strong>Conseil immédiat</strong>
              <span>Voir l’analyse quand Ryanchl doit agir.</span>
            </label>
            <label className={config.advice_mode === 'quiz' ? 'selected' : ''}>
              <input
                type="radio"
                name="advice-mode"
                checked={config.advice_mode === 'quiz'}
                onChange={() => update('advice_mode', 'quiz')}
              />
              <strong>Mode quiz</strong>
              <span>Choisir d’abord, comparer ensuite l’EV.</span>
            </label>
          </div>
          {config.game_mode === 'tournament' ? (
            <div className="blind-levels">
              <div className="subheading-row">
                <div>
                  <h3>Augmentation facultative des blindes</h3>
                  <p>Laissez la liste vide pour conserver les blindes de départ.</p>
                </div>
                <button
                  type="button"
                  className="ghost"
                  onClick={() =>
                    update('blind_levels', [
                      ...config.blind_levels,
                      {
                        after_hands: (config.blind_levels.at(-1)?.after_hands ?? 0) + 10,
                        small_blind: (config.blind_levels.at(-1)?.small_blind ?? config.small_blind) * 2,
                        big_blind: (config.blind_levels.at(-1)?.big_blind ?? config.big_blind) * 2,
                        ante: config.blind_levels.at(-1)?.ante ?? config.ante,
                      },
                    ])
                  }
                >
                  Ajouter un niveau
                </button>
              </div>
              {config.blind_levels.map((level, index) => (
                <div className="level-row" key={`${level.after_hands}-${index}`}>
                  <NumberField
                    label="Après (mains)"
                    value={level.after_hands}
                    min={1}
                    onChange={(after_hands) =>
                      update(
                        'blind_levels',
                        config.blind_levels.map((item, itemIndex) =>
                          itemIndex === index ? { ...item, after_hands } : item,
                        ),
                      )
                    }
                  />
                  <NumberField
                    label="Petite blinde"
                    value={level.small_blind}
                    min={1}
                    onChange={(small_blind) =>
                      update(
                        'blind_levels',
                        config.blind_levels.map((item, itemIndex) =>
                          itemIndex === index ? { ...item, small_blind } : item,
                        ),
                      )
                    }
                  />
                  <NumberField
                    label="Grosse blinde"
                    value={level.big_blind}
                    min={2}
                    onChange={(big_blind) =>
                      update(
                        'blind_levels',
                        config.blind_levels.map((item, itemIndex) =>
                          itemIndex === index ? { ...item, big_blind } : item,
                        ),
                      )
                    }
                  />
                  <NumberField
                    label="Ante"
                    value={level.ante}
                    min={0}
                    onChange={(ante) =>
                      update(
                        'blind_levels',
                        config.blind_levels.map((item, itemIndex) =>
                          itemIndex === index ? { ...item, ante } : item,
                        ),
                      )
                    }
                  />
                  <button
                    type="button"
                    className="icon-button danger-ghost"
                    aria-label={`Supprimer le niveau ${index + 1}`}
                    onClick={() =>
                      update(
                        'blind_levels',
                        config.blind_levels.filter((_, itemIndex) => itemIndex !== index),
                      )
                    }
                  >
                    ×
                  </button>
                </div>
              ))}
            </div>
          ) : null}
        </section>

        {errors.length ? (
          <div className="form-errors" role="alert">
            <strong>Corrigez la configuration avant de commencer :</strong>
            <ul>
              {errors.map((error) => (
                <li key={error}>{error}</li>
              ))}
            </ul>
          </div>
        ) : null}

        <footer className="configuration-submit">
          <button type="button" className="ghost" onClick={() => setConfig(DEFAULT_CONFIG)}>
            Réinitialiser
          </button>
          <LoadingButton loading={busy} type="submit" className="primary large">
            Installer les joueurs et commencer
            <span aria-hidden="true">→</span>
          </LoadingButton>
        </footer>
      </form>
    </main>
  );
}
