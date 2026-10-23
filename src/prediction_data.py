"""Auditable offline inputs. Target-race outcomes are never predictor features."""
from __future__ import annotations

import numpy as np
import pandas as pd

from src.long_run_pace import estimate_long_run_pace
from src.result_status import classify_result_status, mechanical_label, retirement_label

KEYS = ['Year', 'Round', 'Event']
PRACTICE_FEATURES = [f'{s.lower()}_{v}' for s in ('FP1', 'FP2', 'FP3')
                     for v in ('long_run_relative_pace', 'long_run_laps', 'long_run_confidence',
                               'observed_stint_trend', 'track_temp_avg')]
RELIABILITY_FEATURES = ['prior_driver_starts', 'prior_driver_dnf_rate',
                        'prior_team_starts', 'prior_team_dnf_rate', 'prior_team_mechanical_rate']


def truth(values):
    return values.astype(str).str.lower().isin(['true', '1', '1.0'])


def practice_features(laps, messages=None, weather=None):
    """Require UTC message evidence that practice preceded qualifying.

    FastF1 race-control Time is UTC even in older archives lacking an offset.
    No timestamp evidence means no feature; this also excludes post-Q sprint FP2.
    """
    required = set(KEYS + ['Session', 'Driver', 'LapTimeSeconds', 'TrackStatus'])
    if laps.empty or not required.issubset(laps) or messages is None or messages.empty:
        return pd.DataFrame(columns=KEYS + ['DriverCode'] + PRACTICE_FEATURES)
    if not set(KEYS + ['Session', 'Time']).issubset(messages):
        return pd.DataFrame(columns=KEYS + ['DriverCode'] + PRACTICE_FEATURES)
    times = messages.copy()
    times['_utc'] = pd.to_datetime(times.Time, utc=True, errors='coerce')
    bounds = times.groupby(KEYS + ['Session'])._utc.agg(['min', 'max'])
    rows = []
    for key, event in laps.groupby(KEYS, dropna=False):
        qkey = (*key, 'Q')
        if qkey not in bounds.index or pd.isna(bounds.loc[qkey, 'min']):
            continue
        cutoff = bounds.loc[qkey, 'min']
        for session in ('FP1', 'FP2', 'FP3'):
            skey = (*key, session)
            if skey not in bounds.index or pd.isna(bounds.loc[skey, 'max']) or bounds.loc[skey, 'max'] >= cutoff:
                continue
            clean = event[event.Session.eq(session)].copy()
            clean = clean[clean.TrackStatus.astype(str).isin(['1', '1.0'])]
            for col in ('CleanPushLap', 'IsAccurate'):
                if col not in clean:
                    clean = clean.iloc[:0]
                    break
                clean = clean[truth(clean[col])]
            for col in ('Deleted', 'PitIn', 'PitOut'):
                if col in clean:
                    clean = clean[~truth(clean[col])]
            # Dry tyre selection is also enforced inside the matched-stint estimator.
            pace = estimate_long_run_pace(clean)
            for row in pace.to_dict('records'):
                driver = row.pop('Driver')
                driver_laps = clean[clean.Driver.eq(driver)]
                trends = []
                if {'Stint', 'TyreLife', 'Compound'}.issubset(driver_laps):
                    for _, stint in driver_laps.groupby(['Stint', 'Compound']):
                        stint = stint[stint.Compound.isin(['SOFT', 'MEDIUM', 'HARD'])].dropna(subset=['TyreLife', 'LapTimeSeconds'])
                        # Keep only continuous sustained runs. This trend also includes fuel burn.
                        for _, run in stint.sort_values('LapNumber').groupby(stint.sort_values('LapNumber').LapNumber.diff().gt(1).cumsum()):
                            if len(run) >= 5 and run.TyreLife.nunique() >= 3:
                                trends.append(float(np.polyfit(run.TyreLife, run.LapTimeSeconds, 1)[0]))
                row['observed_stint_trend'] = float(np.median(trends)) if trends else np.nan
                row['track_temp_avg'] = np.nan
                if weather is not None and not weather.empty and set(KEYS + ['Session', 'track_temp_avg']).issubset(weather):
                    w = weather
                    mask = w.Session.eq(session)
                    for col, value in zip(KEYS, key):
                        mask &= w[col].eq(value)
                    values = pd.to_numeric(w.loc[mask, 'track_temp_avg'], errors='coerce')
                    row['track_temp_avg'] = values.mean()
                rows.append({**dict(zip(KEYS, key)), 'DriverCode': driver,
                             **{f'{session.lower()}_{name}': value for name, value in row.items()}})
    if not rows:
        return pd.DataFrame(columns=KEYS + ['DriverCode'] + PRACTICE_FEATURES)
    return pd.DataFrame(rows).groupby(KEYS + ['DriverCode'], as_index=False).first()


def outcome_records(results, confirmed_causes=None):
    if results.empty:
        return pd.DataFrame(columns=list(dict.fromkeys([*results.columns, *KEYS, 'DriverCode', 'Team',
                            'outcome_class', 'retired', 'mechanical', 'cause_evidence', 'independently_verified_cause'])))
    out = results[results.Session.eq('R')].copy()
    out['DriverCode'] = out.Abbreviation
    out['Team'] = out.TeamName
    out['outcome_class'] = out.Status.map(classify_result_status)
    out['retired'] = out.Status.map(retirement_label)
    out['mechanical'] = out.Status.map(mechanical_label)
    out['cause_evidence'] = np.where(out.outcome_class.eq('unspecified_dnf'), 'unknown', 'provider_status')
    out['independently_verified_cause'] = False
    if confirmed_causes is not None and not confirmed_causes.empty:
        required = set(KEYS + ['DriverCode', 'OutcomeClass', 'SourceURL', 'PublishedAtUtc', 'Verified'])
        if not required.issubset(confirmed_causes) or confirmed_causes.duplicated(KEYS + ['DriverCode']).any():
            raise ValueError('Confirmed retirement causes need unique event/driver identities and sourced publication times.')
        for cause in confirmed_causes.to_dict('records'):
            if not truth(pd.Series([cause['Verified']])).iloc[0] or not str(cause['SourceURL']).startswith('https://'):
                raise ValueError('Retirement cause must be verified with a source URL.')
            stamp = pd.Timestamp(cause['PublishedAtUtc'])
            if stamp.tzinfo is None:
                raise ValueError('Retirement cause publication must be timezone-aware.')
            if cause['OutcomeClass'] not in {'mechanical_dnf', 'non_mechanical_dnf', 'unspecified_dnf'}:
                raise ValueError('Unsupported confirmed retirement cause.')
            mask = out.DriverCode.eq(cause['DriverCode'])
            for key in KEYS:
                mask &= out[key].eq(cause[key])
            if mask.sum() != 1 or not out.loc[mask, 'retired'].eq(1).all():
                raise ValueError('Confirmed cause must identify one known retirement, not a finisher/DNS/DSQ.')
            out.loc[mask, 'outcome_class'] = cause['OutcomeClass']
            out.loc[mask, 'mechanical'] = 1.0 if cause['OutcomeClass'] == 'mechanical_dnf' else 0.0 if cause['OutcomeClass'] == 'non_mechanical_dnf' else np.nan
            out.loc[mask, 'cause_evidence'] = cause['SourceURL']
            out.loc[mask, 'cause_published_at_utc'] = stamp.isoformat()
            out.loc[mask, 'independently_verified_cause'] = True
    return out


def prior_reliability(features, results, confirmed_causes=None, cutoffs=None):
    """Expanding prior-round histories, reset each season; no target outcome use."""
    records = outcome_records(results)
    output = features.copy()
    for column in RELIABILITY_FEATURES:
        output[column] = np.nan
    if records.empty:
        return output
    for (year, number), part in output.groupby(['Year', 'Round']):
        prior = records[records.Year.eq(year) & records.Round.lt(number)]
        if confirmed_causes is not None and not confirmed_causes.empty and cutoffs is not None:
            cutoff = cutoffs.get((year, number))
            if cutoff is not None and pd.notna(cutoff):
                causes = confirmed_causes.copy()
                available = pd.to_datetime(causes.PublishedAtUtc, utc=True, errors='coerce').le(cutoff)
                causes = causes[available & causes.Year.eq(year) & causes.Round.lt(number)]
                # Use the original result schema to validate and apply causes.
                prior = outcome_records(results[results.Year.eq(year) & results.Round.lt(number)], causes)
        for index, row in part.iterrows():
            for kind, field, identity in [('driver', 'DriverCode', row.DriverCode), ('team', 'Team', row.Team)]:
                history = prior[prior[field].eq(identity)]
                known = history.retired.dropna()
                output.loc[index, f'prior_{kind}_starts'] = len(known)
                # Beta(1,9) is an explicit regularisation assumption, not a fitted prior.
                output.loc[index, f'prior_{kind}_dnf_rate'] = (known.sum() + 1) / (len(known) + 10)
                if kind == 'team':
                    mechanical = history.mechanical.dropna()
                    output.loc[index, 'prior_team_mechanical_rate'] = (mechanical.sum() + 1) / (len(mechanical) + 10)
    return output


def strategy_records(laps):
    """Descriptive labels only: tyre stints and measured pit-lane traversal.

    Pit-lane traversal includes stationary time; it is not total time lost versus
    a racing lap. Older archives missing crossing timestamps retain unknowns.
    """
    required = set(KEYS + ['Session', 'Driver', 'Stint', 'Compound', 'LapNumber', 'TyreLife'])
    if laps.empty or not required.issubset(laps):
        return pd.DataFrame(), pd.DataFrame()
    race = laps[laps.Session.eq('R')].copy()
    stints = race.groupby(KEYS + ['Driver', 'Stint', 'Compound'], as_index=False).agg(
        first_lap=('LapNumber', 'min'), last_lap=('LapNumber', 'max'),
        observed_laps=('LapNumber', 'size'), starting_tyre_age=('TyreLife', 'min'))
    pits = []
    if {'PitInTimeSeconds', 'PitOutTimeSeconds'}.issubset(race):
        for key, driver in race.groupby(KEYS + ['Driver']):
            driver = driver.sort_values('LapNumber')
            for _, entry in driver[driver.PitInTimeSeconds.notna()].iterrows():
                exits = driver[(driver.LapNumber >= entry.LapNumber) &
                               (driver.PitOutTimeSeconds > entry.PitInTimeSeconds)]
                if exits.empty:
                    continue
                exit_row = exits.iloc[0]
                elapsed = exit_row.PitOutTimeSeconds - entry.PitInTimeSeconds
                if not 0 < elapsed < 300 or exit_row.LapNumber > entry.LapNumber + 1:
                    continue
                status = str(entry.get('TrackStatus', '')) + str(exit_row.get('TrackStatus', ''))
                phase = 'red_flag' if '5' in status else 'safety_car' if '4' in status else 'vsc' if any(s in status for s in '67') else 'green' if status and set(status) <= set('1.0') else 'other_or_unknown'
                pits.append({**dict(zip(KEYS + ['Driver'], key)), 'lap': entry.LapNumber,
                             'pit_lane_seconds': float(elapsed), 'phase': phase})
    return stints, pd.DataFrame(pits, columns=KEYS + ['Driver', 'lap', 'pit_lane_seconds', 'phase'])


def delay_records(labels):
    """Only reviewed, sourced labels; missing entries never imply normal starts."""
    columns = KEYS + ['ScheduledStartUtc', 'ActualStartUtc', 'StartDefinition', 'Reason', 'SourceURL', 'Verified']
    if labels.empty:
        return pd.DataFrame(columns=columns + ['delay_minutes', 'delayed'])
    if not set(columns).issubset(labels):
        raise ValueError('Start-delay labels require event identity, UTC starts, reason, source and verification.')
    out = labels.copy()
    if not out.StartDefinition.isin(['formation_lap', 'lights_out', 'rolling_start']).all():
        raise ValueError('Start labels must use the same explicit start definition for scheduled and actual times.')
    if out.duplicated(KEYS).any():
        raise ValueError('Duplicate start-delay event labels.')
    for column in ['ScheduledStartUtc', 'ActualStartUtc']:
        # Refuse naive times rather than interpreting local times as UTC.
        if any(pd.isna(value) or pd.Timestamp(value).tzinfo is None for value in out[column]):
            raise ValueError('Start-delay timestamps must be timezone-aware.')
        out[column] = pd.to_datetime(out[column], utc=True)
    if not truth(out.Verified).all() or out.SourceURL.fillna('').str.strip().eq('').any() or out.Reason.fillna('').str.strip().eq('').any():
        raise ValueError('Start-delay labels need verified evidence and a cause, including normal starts.')
    out['delay_minutes'] = (out.ActualStartUtc - out.ScheduledStartUtc).dt.total_seconds() / 60
    if (out.delay_minutes < 0).any():
        raise ValueError('Actual start precedes scheduled start; review the label.')
    out['delayed'] = out.delay_minutes.gt(0)
    if (out.delayed & out.Reason.str.lower().eq('normal')).any() or (~out.delayed & ~out.Reason.str.lower().eq('normal')).any():
        raise ValueError('Normal controls and delayed-start causes disagree with their timestamps.')
    return out
