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


# Fantasy scoring knobs.
FANTASY_SCORING = {
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
    "position_gain_points_per_place": 1.0,
    "position_loss_points_per_place": -0.5,
    "position_change_min": -5.0,
    "position_change_max": 10.0,
    "fastest_lap_bonus": 5.0,
    "dotd_bonus": 10.0,
    "dnf_penalty": -10.0,
}
