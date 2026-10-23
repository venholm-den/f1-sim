"""Publication-aware FIA context; never combine grid revisions or infer sanctions."""
from __future__ import annotations

import pandas as pd

from src.data_sources.fia_extraction import published_utc


def context_asof(index, year, event, cutoff):
    empty = {name:pd.DataFrame() for name in ('official_grid','penalties','summons','classification')}
    if cutoff is None:
        return empty
    stamp = pd.Timestamp(cutoff)
    if stamp.tzinfo is None:
        raise ValueError('FIA cutoff must be timezone aware.')
    frame = index[index.year.eq(year) & index.event.str.casefold().eq(str(event).casefold())].copy()
    if frame.empty:
        return empty
    frame['_published'] = pd.to_datetime(frame.published_at.map(published_utc),utc=True,errors='coerce')
    frame['_seen'] = pd.to_datetime(frame.first_seen_at_utc,utc=True,errors='coerce',format='mixed')
    # Unobserved or undated extraction cannot qualify for a frozen forecast.
    frame = frame[frame._published.le(stamp) & frame._seen.le(stamp)]
    recalled = set(frame.loc[frame.status.eq('recalled'),'doc_number'].dropna())
    frame = frame[~frame.doc_number.isin(recalled)]
    grids = frame[frame.status.eq('verified_grid') & frame.session.eq('R') &
                  ~frame.document_title.str.contains('sprint',case=False,na=False)].copy()
    if not grids.empty:
        latest_listing = frame[frame.session.eq('R') & frame.document_title.str.contains(
            'starting grid',case=False,na=False) & ~frame.document_title.str.contains('sprint',case=False,na=False)]
        if not latest_listing.empty and latest_listing._published.max() > grids._published.max():
            grids = grids.iloc[:0]
        unparsed = latest_listing[latest_listing.status.eq('review_required')]
        if (not grids.empty and not unparsed.empty
                and unparsed._published.max() >= grids._published.max()
                and unparsed._seen.max() >= grids._seen.max()):
            grids = grids.iloc[:0]
    if not grids.empty:
        # A publication/PDF version is indivisible. Identical publication times
        # with different PDFs are ambiguous, not arbitrarily tie-broken.
        grids = grids[grids._published.eq(grids._published.max())]
        versions = grids[['document_url','pdf_sha256']].drop_duplicates()
        valid = (len(versions)==1 and grids.roster_size.notna().all()
                 and grids.roster_size.astype(float).eq(len(grids)).all()
                 and grids.driver.ne('').all() and not grids.driver.duplicated().any())
        positions = pd.to_numeric(grids.grid_position,errors='coerce')
        positive = positions[positions.gt(0)]
        pit = grids.pit_lane_start.astype(str).str.lower().eq('true')
        withdrawn = grids.withdrawn.astype(str).str.lower().eq('true')
        valid = (valid and not positive.duplicated().any() and positive.between(1,len(grids)).all()
                 and positions.notna().all() and positions.eq(positions.round()).all()
                 and (positions.gt(0) | (positions.eq(0)&pit) | (positions.eq(-1)&withdrawn)).all())
        if valid:
            grids['Driver'] = grids.driver
            grids['fia_grid_position'] = positions
            grids['fia_grid_source'] = grids.document_title
            grids['fia_pit_lane_start'] = pit
            grids['fia_withdrawn'] = withdrawn
            empty['official_grid'] = grids.drop(columns=['_published','_seen'])
    penalties = frame[frame.status.eq('verified_decision') & frame.penalty_type.isin(
        ['grid_drop','pit_lane','back_of_grid']) & frame.target_session.eq('R')].copy()
    if not penalties.empty:
        # Grid footnotes repeat a stewards decision. One decision per driver;
        # prefer the original decision text over a later grid summary.
        penalties['_footnote'] = penalties.document_type.eq('grid_penalty')
        penalties = penalties.sort_values(['_footnote','_published'],ascending=[True,False])
        penalties = penalties.drop_duplicates(['driver','decision_reference','penalty_type'])
        empty['penalties'] = penalties.drop(columns=['_published','_seen','_footnote'])
    return empty


def feature_cutoff(session, metadata, requested=None, *, now=None):
    """Live forecasts use collection time; historical replay uses session end."""
    current = pd.Timestamp(now or pd.Timestamp.now(tz='UTC'))
    if requested:
        stamp = pd.Timestamp(requested)
        if stamp.tzinfo is None or stamp > current:
            raise ValueError('Feature cutoff must be timezone aware and cannot be in the future.')
        return stamp.isoformat()
    if metadata.get('feature_cutoff_utc'):
        return feature_cutoff(session,{},metadata['feature_cutoff_utc'],now=current)
    event = getattr(session,'event',{})
    race_dates = [pd.to_datetime(event.get(f'Session{i}DateUtc'),utc=True,errors='coerce')
                  for i in range(1,6) if event.get(f'Session{i}') == 'Race']
    if any(pd.notna(date) and date>current for date in race_dates):
        return current.isoformat()
    try:
        status = session.session_status
        t0 = pd.to_datetime(session.t0_date,utc=True)
        times = pd.to_timedelta(status.Time,errors='coerce')
        if times.notna().any() and pd.notna(t0):
            return min(current,t0+times.max()).isoformat()
    except (AttributeError,KeyError,ValueError,TypeError):
        pass
    date = pd.to_datetime(getattr(session,'date',None),utc=True,errors='coerce')
    return min(current,date).isoformat() if pd.notna(date) else None
