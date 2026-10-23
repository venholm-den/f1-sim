# Physical circuit identity

Grand Prix names identify events, not necessarily circuits. New source runs resolve
the season and event against physical circuit identity, then check schedule location
and the timing feed's circuit hint. The commercial event name remains available for
timing-data retrieval, FIA documents and comparison keys.

The 2026 Bahrain Grand Prix resolves to **Sepang International Circuit, Malaysia**,
with coordinates 2.76083, 101.738 and 56 scheduled laps. The 2026 Spanish Grand Prix
resolves to **Madring, Madrid**, coordinates 40.46528, -3.61528 and 57 scheduled laps.
Barcelona remains a separate event and circuit. Earlier Bahrain and Spanish events
retain Sakhir and Barcelona identity respectively.

References checked on 5 October 2026:

- [Formula 1: Bahrain GP in Malaysia](https://www.formula1.com/en/latest/article/formula-1-gulf-air-bahrain-grand-prix-in-malaysia-2026.1IHoy7D2dfCIugb5mH78cE)
- [Formula 1 and FIA venue announcement](https://corp.formula1.com/formula-1-and-fia-confirm-that-malaysia-will-join-the-2026-calendar-as-host-venue-for-the-bahrain-grand-prix/)
- [Aston Martin: 2026 Spanish GP](https://www.astonmartinf1.com/en-GB/races/2026-spanish-gp/)
- [Jolpica circuit coordinates](https://api.jolpi.ca/ergast/f1/2026.json), read through FastF1's Ergast client.

## Inputs and provenance

`src/venues.py` owns circuit IDs, names, coordinates, known layout changes and
season overrides. Country labels alone do not establish the venue: the relocated
Bahrain feed still labels its event country Bahrain. Conventional lap assumptions
for other circuits remain labelled assumptions, rather than published race bulletins.
Reduced distances, delayed starts and other operational changes need separate
race-specific evidence; circuit resolution does not estimate their probabilities.

- Track parameters match physical circuit ID. Legacy CSV event rows are associated
  with their original circuit, so a Bahrain row never supplies Sakhir factors to Sepang.
  `CircuitId` can explicitly identify a new profile row. Sepang and Madrid currently
  use labelled **generic, uncalibrated factors**: overtaking 0.55, safety-car chance
  0.40 and red-flag base chance 0.035. These are existing fallback assumptions.
- Historical tyre strategy imports require matching **circuit and layout**, checked
  against the historical schedule and loaded session. Event renames can share history;
  relocated events cannot. The existing 2018 history floor excludes Sepang's older
  F1 races. Madrid has no qualifying prior-season history in the current window.
- Unknown or conflicting feed identity withholds geographic weather and circuit
  history. Neutral track factors and the existing generic 57-lap fallback remain
  explicit assumptions, with uncertainty displayed in the Discord report.
- PRE contexts retain calendar location. Loaded sessions additionally check circuit
  hints. Append-only weather updates compare archived venue identity before reusing
  a cached capture. Shadow weather experiments record the venue and resolver hashes.
- New pipeline outputs include `venue_context.json`. New frozen manifests hash that
  file and the resolver, track and strategy source. Automated contexts archive the
  actual pipeline identity and retain the initial calendar request separately.
- New Discord titles show event and physical circuit, with venue, distance and
  calibration limitations. Older snapshots keep their original archived context.

Recent baseline `singapore-20261005-v4-venues` has 16 completed 2026 races, 18,381
lap rows and 339 driver-race feature rows. All race tables now include source circuit
and layout identifiers. Recent form still spans different circuits; circuit-specific
strategy history is the component that requires matching layout. The live two-race
baseline window and experimental accuracy switches remain unchanged.

## Validation and limits

The local Bahrain qualifying replay at `outputs/venue_resolution/bahrain-corrected`
ran 1,000 simulations for 22 drivers using Sepang identity and 56 laps, skipped
Sakhir historical strategy, and preserved 28 frozen forecast and delivery files.
This is a retrospective correctness check, not a pre-race prediction or evidence
of improved accuracy. The original forecast remains available unchanged.

This mapping is maintained source data, not automatic detection of every future
calendar change. Unrecognised locations fail conservatively and need a reviewed
registry update. Layout tracking covers the named changes in this registry and is
not an exhaustive historical circuit-layout database. Source automation uses the
new code on its next run; existing packaged executables have not been rebuilt.
