from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import pandas as pd
import requests


OPENF1_BASE_URL = "https://api.openf1.org/v1"


@dataclass(frozen=True)
class OpenF1Endpoint:
    name: str
    path: str
    purpose: str


OPENF1_ENDPOINTS = {
    "sessions": OpenF1Endpoint(
        name="sessions",
        path="/sessions",
        purpose="Find session keys for race weekends.",
    ),
    "drivers": OpenF1Endpoint(
        name="drivers",
        path="/drivers",
        purpose="Map driver numbers to names, abbreviations, teams and colours.",
    ),
    "position": OpenF1Endpoint(
        name="position",
        path="/position",
        purpose="Live or historical track/race position updates.",
    ),
    "intervals": OpenF1Endpoint(
        name="intervals",
        path="/intervals",
        purpose="Live gaps to leader and intervals between cars.",
    ),
    "pit": OpenF1Endpoint(
        name="pit",
        path="/pit",
        purpose="Pit stop timing and pit lane events.",
    ),
    "stints": OpenF1Endpoint(
        name="stints",
        path="/stints",
        purpose="Tyre stint information.",
    ),
    "race_control": OpenF1Endpoint(
        name="race_control",
        path="/race_control",
        purpose="Race control messages, flags, safety cars, red flags and incidents.",
    ),
    "weather": OpenF1Endpoint(
        name="weather",
        path="/weather",
        purpose="Actual weather observations for a session.",
    ),
}


class OpenF1Client:
    """
    Lightweight OpenF1 REST client.

    This module is intentionally separate from src.collect, which currently owns
    the FastF1 data flow. OpenF1 should feed live/near-live context into reports
    and strategy later without replacing the existing model pipeline.
    """

    def __init__(
        self,
        base_url: str = OPENF1_BASE_URL,
        timeout_seconds: int = 20,
        bearer_token: str | None = None,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.timeout_seconds = timeout_seconds
        self.bearer_token = bearer_token

    def _headers(self) -> dict[str, str]:
        headers = {
            "Accept": "application/json",
            "User-Agent": "f1-sim/0.1",
        }

        if self.bearer_token:
            headers["Authorization"] = f"Bearer {self.bearer_token}"

        return headers

    def get_json(
        self,
        endpoint: str,
        params: dict[str, Any] | None = None,
    ) -> list[dict[str, Any]]:
        if endpoint not in OPENF1_ENDPOINTS:
            valid = ", ".join(sorted(OPENF1_ENDPOINTS))
            raise ValueError(f"Unknown OpenF1 endpoint '{endpoint}'. Valid: {valid}")

        path = OPENF1_ENDPOINTS[endpoint].path
        url = f"{self.base_url}{path}"

        response = requests.get(
            url,
            params=params or {},
            headers=self._headers(),
            timeout=self.timeout_seconds,
        )
        response.raise_for_status()

        data = response.json()

        if isinstance(data, list):
            return data

        if isinstance(data, dict):
            return [data]

        return []

    def get_dataframe(
        self,
        endpoint: str,
        params: dict[str, Any] | None = None,
    ) -> pd.DataFrame:
        return pd.DataFrame(self.get_json(endpoint=endpoint, params=params))

    def sessions(
        self,
        year: int | None = None,
        country_name: str | None = None,
        session_name: str | None = None,
    ) -> pd.DataFrame:
        params: dict[str, Any] = {}

        if year is not None:
            params["year"] = year

        if country_name is not None:
            params["country_name"] = country_name

        if session_name is not None:
            params["session_name"] = session_name

        return self.get_dataframe("sessions", params=params)

    def latest_session_key(
        self,
        year: int | None = None,
        session_name: str | None = None,
    ) -> int | str:
        sessions = self.sessions(year=year, session_name=session_name)

        if sessions.empty or "session_key" not in sessions.columns:
            return "latest"

        if "date_start" in sessions.columns:
            sessions = sessions.sort_values("date_start")

        return int(sessions["session_key"].iloc[-1])

    def live_snapshot(
        self,
        session_key: int | str = "latest",
    ) -> dict[str, pd.DataFrame]:
        """
        Returns current/latest session context.

        For live usage, call this repeatedly and merge the latest row per driver.
        """

        params = {"session_key": session_key}

        return {
            "drivers": self.get_dataframe("drivers", params=params),
            "position": self.get_dataframe("position", params=params),
            "intervals": self.get_dataframe("intervals", params=params),
            "pit": self.get_dataframe("pit", params=params),
            "stints": self.get_dataframe("stints", params=params),
            "race_control": self.get_dataframe("race_control", params=params),
            "weather": self.get_dataframe("weather", params=params),
        }

    def session_snapshot(
        self,
        session_key: int | str,
        endpoints: list[str] | None = None,
    ) -> dict[str, pd.DataFrame]:
        params = {"session_key": session_key}
        selected = endpoints or ["weather", "stints", "race_control", "pit"]

        return {
            endpoint: self.get_dataframe(endpoint, params=params)
            for endpoint in selected
        }


def latest_by_driver(
    df: pd.DataFrame,
    driver_col: str = "driver_number",
    date_col: str = "date",
) -> pd.DataFrame:
    """
    Returns the latest OpenF1 row per driver.

    Useful for position, intervals and stints where the endpoint returns a stream
    of timestamped rows.
    """

    if df.empty or driver_col not in df.columns:
        return df.copy()

    output = df.copy()

    if date_col in output.columns:
        output = output.sort_values(date_col)

    return output.groupby(driver_col, as_index=False).tail(1).reset_index(drop=True)


def build_live_timing_table(snapshot: dict[str, pd.DataFrame]) -> pd.DataFrame:
    """
    Combines position, intervals and driver metadata into one live timing table.

    This is intended for future use in report_card.py/live dashboards.
    """

    drivers = snapshot.get("drivers", pd.DataFrame()).copy()
    position = latest_by_driver(snapshot.get("position", pd.DataFrame()).copy())
    intervals = latest_by_driver(snapshot.get("intervals", pd.DataFrame()).copy())
    stints = latest_by_driver(snapshot.get("stints", pd.DataFrame()).copy())

    if position.empty:
        return pd.DataFrame()

    table = position.copy()

    if not intervals.empty:
        merge_cols = [col for col in intervals.columns if col not in table.columns or col == "driver_number"]
        table = table.merge(
            intervals[merge_cols],
            on="driver_number",
            how="left",
            suffixes=("", "_interval"),
        )

    if not stints.empty:
        merge_cols = [col for col in stints.columns if col not in table.columns or col == "driver_number"]
        table = table.merge(
            stints[merge_cols],
            on="driver_number",
            how="left",
            suffixes=("", "_stint"),
        )

    if not drivers.empty and "driver_number" in drivers.columns:
        driver_cols = [
            col
            for col in [
                "driver_number",
                "broadcast_name",
                "full_name",
                "name_acronym",
                "team_name",
                "team_colour",
            ]
            if col in drivers.columns
        ]

        table = table.merge(
            drivers[driver_cols].drop_duplicates(subset=["driver_number"]),
            on="driver_number",
            how="left",
        )

    if "position" in table.columns:
        table = table.sort_values("position")

    return table.reset_index(drop=True)


def save_live_snapshot(
    snapshot: dict[str, pd.DataFrame],
    output_dir: str = "outputs/data_sources/openf1",
) -> dict[str, str]:
    from pathlib import Path

    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)

    saved: dict[str, str] = {}

    for name, df in snapshot.items():
        file_path = output_path / f"{name}.csv"
        df.to_csv(file_path, index=False)
        saved[name] = str(file_path)

    timing = build_live_timing_table(snapshot)

    if not timing.empty:
        file_path = output_path / "live_timing_table.csv"
        timing.to_csv(file_path, index=False)
        saved["live_timing_table"] = str(file_path)

    return saved
