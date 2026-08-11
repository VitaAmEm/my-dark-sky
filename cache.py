"""
cache.py

Two jobs, both backed by the same SQLite database via SQLAlchemy:

1. CacheEntry: a short-lived cache (5 minutes) so repeated requests for the
   same location don't burn through the OpenWeatherMap quota. This is the
   "cache system" required by the spec.

2. HistorySnapshot: an append-only log of every *meaningfully new* lookup
   we make (see get_latest_snapshot / the dedup check in app.py).
   OpenWeatherMap's free tier doesn't include real historical data, so
   instead of faking it, we record what we actually observed each time
   conditions genuinely change. Over time this becomes a genuine (if
   incomplete) "time machine" for locations you've looked up before -
   an honest substitute rather than a fabricated one, and it reads like
   a log of real weather changes rather than a log of API calls.
"""

import json
import os
from datetime import datetime, timedelta, timezone

from sqlalchemy import DateTime, Float, Integer, String, Text, create_engine
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, sessionmaker

CACHE_TTL = timedelta(minutes=5)

DB_PATH = os.environ.get("DATABASE_PATH", os.path.join(os.path.dirname(os.path.abspath(__file__)), "weather.db"))
engine = create_engine(f"sqlite:///{DB_PATH}", connect_args={"check_same_thread": False})
Session = sessionmaker(bind=engine)


class Base(DeclarativeBase):
    pass


def _location_key(lat, lon, units):
    """Round coordinates so nearby requests for 'the same place' share a cache row."""
    return f"{round(float(lat), 3)}:{round(float(lon), 3)}:{units}"


class CacheEntry(Base):
    __tablename__ = "cache_entries"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    location_key: Mapped[str] = mapped_column(String, unique=True, index=True, nullable=False)
    payload_json: Mapped[str] = mapped_column(Text, nullable=False)
    fetched_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)


class HistorySnapshot(Base):
    __tablename__ = "history_snapshots"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    location_key: Mapped[str] = mapped_column(String, index=True, nullable=False)
    place_name: Mapped[str] = mapped_column(String, nullable=False)
    units: Mapped[str] = mapped_column(String, nullable=False)
    temperature: Mapped[float] = mapped_column(Float, nullable=False)
    feels_like: Mapped[float] = mapped_column(Float, nullable=False)
    condition: Mapped[str] = mapped_column(String, nullable=False)
    icon: Mapped[str] = mapped_column(String, nullable=False)
    recorded_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, index=True)


Base.metadata.create_all(engine)


def get_cached_weather(lat, lon, units):
    """Return a cached payload (dict) if we have one younger than CACHE_TTL, else None."""
    key = _location_key(lat, lon, units)
    session = Session()
    try:
        entry = session.query(CacheEntry).filter_by(location_key=key).first()
        if entry is None:
            return None
        age = datetime.now(timezone.utc) - entry.fetched_at.replace(tzinfo=timezone.utc)
        if age > CACHE_TTL:
            return None
        return json.loads(entry.payload_json)
    finally:
        session.close()


def store_weather_in_cache(lat, lon, units, payload):
    """Upsert the cache row for this location."""
    key = _location_key(lat, lon, units)
    session = Session()
    try:
        entry = session.query(CacheEntry).filter_by(location_key=key).first()
        now = datetime.now(timezone.utc)
        if entry is None:
            entry = CacheEntry(location_key=key, payload_json=json.dumps(payload), fetched_at=now)
            session.add(entry)
        else:
            entry.payload_json = json.dumps(payload)
            entry.fetched_at = now
        session.commit()
    finally:
        session.close()


def get_latest_snapshot(lat, lon, units):
    """
    Return the most recently recorded history snapshot for this location,
    as a dict, or None if we've never recorded one. Used to decide whether
    a fresh fetch is worth logging as a new history entry.
    """
    key = _location_key(lat, lon, units)
    session = Session()
    try:
        row = (
            session.query(HistorySnapshot)
            .filter_by(location_key=key)
            .order_by(HistorySnapshot.recorded_at.desc())
            .first()
        )
        if row is None:
            return None
        return {
            "temperature": row.temperature,
            "condition": row.condition,
        }
    finally:
        session.close()


def record_history_snapshot(lat, lon, units, place_name, temperature, feels_like, condition, icon):
    """Append one row to the permanent history log (used by the Time Machine view)."""
    key = _location_key(lat, lon, units)
    session = Session()
    try:
        snapshot = HistorySnapshot(
            location_key=key,
            place_name=place_name,
            units=units,
            temperature=temperature,
            feels_like=feels_like,
            condition=condition,
            icon=icon,
            recorded_at=datetime.now(timezone.utc),
        )
        session.add(snapshot)
        session.commit()
    finally:
        session.close()


def get_history(lat, lon, units, limit=50):
    """Return past recorded snapshots for this location, most recent first."""
    key = _location_key(lat, lon, units)
    session = Session()
    try:
        rows = (
            session.query(HistorySnapshot)
            .filter_by(location_key=key)
            .order_by(HistorySnapshot.recorded_at.desc())
            .limit(limit)
            .all()
        )
        return [
            {
                "place_name": row.place_name,
                "temperature": row.temperature,
                "feels_like": row.feels_like,
                "condition": row.condition,
                "icon": row.icon,
                "recorded_at": row.recorded_at.replace(tzinfo=timezone.utc).isoformat(),
            }
            for row in rows
        ]
    finally:
        session.close()