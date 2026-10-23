"""Turn FastF1 session-load failures into a message a person can act on."""
from __future__ import annotations

NOT_PUBLISHED = ('FastF1 could not load this session. It may not have run yet, '
                 'or its timing data is not published. Pick a completed session or try again later.')
RATE_LIMITED = ('FastF1 hit its download rate limit. Wait up to an hour and run again; '
                'sessions already downloaded stay cached.')
OFFLINE = ('FastF1 could not reach the F1 timing servers. Check your internet connection and run again.')
SIGN_IN = 'FastF1 could not sign in to your F1 account. Reconnect it in Settings and run again.'
UNKNOWN_EVENT = 'FastF1 does not recognise that event or session. Check the season, race and session names.'

NOT_PUBLISHED_TYPES = {'SessionNotAvailableError', 'DataNotLoadedError', 'NoLapDataError'}
NOT_PUBLISHED_TEXT = ('No laps found for', 'Failed to load any schedule data', 'API did not provide any usable data')


def _chain(exc):
    seen = set()
    while exc is not None and id(exc) not in seen:
        seen.add(id(exc))
        yield exc
        exc = exc.__cause__ or exc.__context__


def session_load_message(exc: BaseException) -> str | None:
    """Return a plain-language message for a FastF1 load failure, else None."""
    for error in _chain(exc):
        name, module, text = type(error).__name__, type(error).__module__, str(error)
        if name == 'RateLimitExceededError':
            return RATE_LIMITED
        if name == 'F1AuthError':
            return SIGN_IN
        if name in NOT_PUBLISHED_TYPES or any(part in text for part in NOT_PUBLISHED_TEXT):
            return NOT_PUBLISHED
        if name == 'FuzzyMatchError' or (module.startswith('fastf1') and isinstance(error, KeyError)):
            return UNKNOWN_EVENT
        if module.startswith(('requests', 'urllib3')) or isinstance(error, (ConnectionError, TimeoutError)):
            return OFFLINE
        if module.startswith('fastf1'):
            return f'FastF1 could not load the session data: {text}'
    return None
