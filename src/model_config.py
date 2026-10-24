from __future__ import annotations


MODEL_VERSION = "phase_1_performance_profile"


# Session influence controls how much current weekend data affects the model.
SESSION_WEIGHTS = {
    "PRE": {
        "quali": 0.00,
        "race": 0.00,
        "strategy": 0.00,
    },
    "FP1": {
        "quali": 0.10,
        "race": 0.12,
        "strategy": 0.10,
    },
    "FP2": {
        "quali": 0.16,
        "race": 0.24,
        "strategy": 0.18,
    },
    "FP3": {
        "quali": 0.24,
        "race": 0.20,
        "strategy": 0.16,
    },
    "Q": {
        "quali": 0.80,
        "race": 0.20,
        "strategy": 0.10,
    },
    "SQ": {
        "quali": 0.70,
        "race": 0.20,
        "strategy": 0.12,
    },
    "S": {
        "quali": 0.30,
        "race": 0.45,
        "strategy": 0.22,
    },
    "R": {
        "quali": 0.20,
        "race": 0.70,
        "strategy": 0.35,
    },
}


RACE_LAPS_BY_EVENT_KEYWORD = {
    "bahrain": 57,
    "saudi": 50,
    "australian": 58,
    "japanese": 53,
    "chinese": 56,
    "miami": 57,
    "emilia": 63,
    "monaco": 78,
    "spanish": 66,
    "barcelona": 66,
    "canadian": 70,
    "austrian": 71,
    "british": 52,
    "hungarian": 70,
    "belgian": 44,
    "dutch": 72,
    "italian": 53,
    "azerbaijan": 51,
    "singapore": 62,
    "united states": 56,
    "mexico": 71,
    "brazil": 71,
    "las vegas": 50,
    "qatar": 57,
    "abu dhabi": 58,
}


DEFAULT_RACE_LAPS = 57
DEFAULT_BASE_LAP_TIME = 90.0
DEFAULT_PIT_AND_RACE_ALLOWANCE = 28.0


# Backtest target weights.
BACKTEST_METRIC_WEIGHTS = {
    "finish_mae": 1.00,
    "top10_brier": 1.00,
    "podium_brier": 0.50,
    "win_brier": 0.30,
    "fantasy_mae": 1.25,
}


# These are the race-engine knobs we tune after backtesting.
SIMULATION_PARAMETERS = {
    "race_pace_seconds_multiplier": 0.20,
    "long_run_penalty_multiplier": 0.25,
    "tyre_deg_multiplier": 7.00,
    "grid_loss_multiplier": 1.65,
    "strategy_loss_multiplier": 2.50,
    "race_noise_multiplier": 3.80,
    "start_noise_seconds": 1.15,
    "strategy_noise_seconds": 1.50,
    "chaos_noise_seconds": 1.25,
    "red_flag_field_compression": 0.72,
    "red_flag_noise_seconds": 2.00,
}


# Official F1 Fantasy scoring, current season. Every value below was checked
# against archived component points (scripts/verify_fantasy_scoring.py); the
# overtake estimate is the only fitted part, because the simulator does not
# count passes. Earlier seasons differ only where FANTASY_SEASON_OVERRIDES says.
FANTASY_SCORING = {
    "season": 2026,
    "finish_points": {
        1: 25,
        2: 18,
        3: 15,
        4: 12,
        5: 10,
        6: 8,
        7: 6,
        8: 4,
        9: 2,
        10: 1,
    },
    "quali_points": {
        1: 10,
        2: 9,
        3: 8,
        4: 7,
        5: 6,
        6: 5,
        7: 4,
        8: 3,
        9: 2,
        10: 1,
    },
    "sprint_finish_points": {1: 8, 2: 7, 3: 6, 4: 5, 5: 4, 6: 3, 7: 2, 8: 1},
    # Grid to finish, one point per place either way and no cap. A driver who
    # is not classified scores no position change.
    "position_gain_points_per_place": 1.0,
    "position_loss_points_per_place": -1.0,
    "position_change_min": None,
    "position_change_max": None,
    "overtake_points": 1.0,
    "fastest_lap_bonus": 10.0,
    "sprint_fastest_lap_bonus": 5.0,
    "dotd_bonus": 10.0,
    "dnf_penalty": -20.0,
    "sprint_dnf_penalty": -10.0,
    "quali_not_classified_penalty": -5.0,
    "quali_disqualified_penalty": -5.0,
    "race_disqualified_penalty": -20.0,
    "sprint_disqualified_penalty": -10.0,
    # Fitted to 2025-2026 archived overtakes (727 race, 243 sprint finishes):
    # base + per place gained/lost. Used only when a run has no pass count.
    "estimated_overtakes": {
        "race": {"base": 3.44, "per_place_gained": 0.36, "per_place_lost": 0.08,
                 "not_classified": 1.5},
        "sprint": {"base": 1.45, "per_place_gained": 0.36, "per_place_lost": 0.07,
                   "not_classified": 0.5},
    },
    "constructor": {
        # A constructor scores both drivers' points except Driver of the Day.
        "q2_cutoff": 16,
        "q3_cutoff": 10,
        "qualifying_teamwork": {"neither_q2": -1.0, "one_q2": 1.0, "both_q2": 3.0,
                                "one_q3": 5.0, "both_q3": 10.0},
        # Fastest stop of the race, inclusive upper bound in seconds.
        "pit_stop_bands": [[1.99, 20.0], [2.19, 10.0], [2.49, 5.0], [3.0, 2.0]],
        "fastest_pit_stop_bonus": 5.0,
        "world_record_pit_stop_bonus": 15.0,
    },
    # Team rules from the game's rulebook; the archive holds no team data, so
    # these are not archive-checked like the scoring above.
    "team": {"drivers": 5, "constructors": 2, "budget": 100.0, "boost_multiplier": 2.0,
             "free_transfers": 2, "transfer_penalty": -10.0},
}

# Rules that changed between seasons, as found in the archive.
FANTASY_SEASON_OVERRIDES = {
    2025: {"sprint_dnf_penalty": -20.0, "sprint_disqualified_penalty": -20.0,
           "constructor": {"q2_cutoff": 15}},
    2024: {"sprint_dnf_penalty": -20.0, "sprint_disqualified_penalty": -20.0,
           "quali_disqualified_penalty": -15.0, "race_disqualified_penalty": -25.0,
           "constructor": {"q2_cutoff": 15}},
    2023: {"sprint_dnf_penalty": -20.0, "sprint_disqualified_penalty": -20.0,
           "quali_disqualified_penalty": -15.0, "race_disqualified_penalty": -25.0,
           "constructor": {"q2_cutoff": 15}},
}


def fantasy_scoring_for_season(season: int | None = None) -> dict:
    """The scoring table for one season; the current table when unknown."""
    override = FANTASY_SEASON_OVERRIDES.get(int(season)) if season is not None else None
    if not override:
        return FANTASY_SCORING
    table = {**FANTASY_SCORING, **{k: v for k, v in override.items() if k != "constructor"}}
    table["season"] = int(season)
    table["constructor"] = {**FANTASY_SCORING["constructor"], **override.get("constructor", {})}
    return table
