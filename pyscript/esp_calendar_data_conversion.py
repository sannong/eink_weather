from datetime import datetime, date
from typing import Tuple, Optional
import inspect

# -------------------------
# Configuration / Constants
# -------------------------
CALENDAR_NAMES = {"calendar.X": "X", "calendar.Y": "Y"}
DAY_NAMES = ["Mo", "Tu", "We", "Th", "Fr", "Sa", "Su"]
DAY_NAMES_EN = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
MONTHS_EN = ["January", "February", "March", "April", "May", "June", "July", "August", "September", "October", "November", "December"]

MAX_ENTRIES = 8

# Local timezone from system/container
LOCAL_TZ = datetime.now().astimezone().tzinfo


# -------------------------
# Helpers
# -------------------------
def _ensure_not_coroutine(x, where: str):
    if inspect.iscoroutine(x):
        raise TypeError(f"Coroutine in {where}: expected value, got coroutine.")
    return x

def _iso_parse(s: str) -> Optional[datetime]:
    """
    ISO parser:
    - Accepts 'Z' (converted to +00:00)
    - Accepts offsets (+HH:MM)
    - Naive values are interpreted as local time
    Returns: aware datetime in local TZ
    """
    if not s:
        return None
    _ensure_not_coroutine(s, "ISO-Input")
    try:
        st = s
        if st.endswith("Z"):
            st = st[:-1] + "+00:00"
        dt = datetime.fromisoformat(st)
    except Exception:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=LOCAL_TZ)
    return dt.astimezone(LOCAL_TZ)

def _to_local(dt: datetime) -> datetime:
    _ensure_not_coroutine(dt, "to_local Input")
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=LOCAL_TZ)
    return dt.astimezone(LOCAL_TZ)

def _parse_to_local(dt_str: str) -> Tuple[Optional[datetime], Optional[str]]:
    """
    Parse ISO datetime string to (local datetime, ISO string with offset).
    """
    if not dt_str or "T" not in dt_str:
        return None, None
    dt_local = _iso_parse(dt_str)
    if dt_local is None:
        return None, None
    return dt_local, dt_local.isoformat(timespec="seconds")

def _local_date_str(s: Optional[str]) -> str:
    """
    Parse string into local date (YYYY-MM-DD). If invalid, return today.
    """
    if s:
        try:
            st = s[:-1] + "+00:00" if s.endswith("Z") else s
            d = datetime.fromisoformat(st)
            return _to_local(d).date().isoformat()
        except Exception:
            pass
    return _to_local(datetime.now()).date().isoformat()

def _norm_event_shape(calendar_payload):
    """
    Accepts {"events":[...]} or direct list, returns list of events.
    """
    if isinstance(calendar_payload, dict) and "events" in calendar_payload:
        return calendar_payload.get("events") or []
    if isinstance(calendar_payload, list):
        return calendar_payload
    return []

def _norm_ts_field(v):
    """
    Accepts string or {dateTime|date}, returns a string.
    """
    if v is None:
        return None
    if isinstance(v, str):
        return v
    if isinstance(v, dict):
        return v.get("dateTime") or v.get("date")
    return None

def _dt_from_str_local(s: str) -> datetime:
    """
    Always returns aware local datetime from string, otherwise raises.
    """
    _ensure_not_coroutine(s, "dt_from_str_local Input")
    dt = _iso_parse(s)
    if dt is None:
        raise ValueError(f"Invalid datetime format: {s!r}")
    return _ensure_not_coroutine(dt, "dt_from_str_local Output")

def _epoch_from_dt_str(s: str, where: str) -> float:
    """
    Returns float timestamp from datetime string for safe sorting.
    """
    dt = _dt_from_str_local(s)
    _ensure_not_coroutine(dt, f"{where} Key-datetime")
    ts = dt.timestamp()
    _ensure_not_coroutine(ts, f"{where} Key-timestamp")
    return float(ts)


# -------------------------
# Core logic
# -------------------------
def convert_calendar_format(data: dict, today_str: str):
    events_by_date = {}
    entry_count = 0
    closest_end_time_local_iso = None

    today_local = _local_date_str(today_str)

    for calendar_key, payload in (data or {}).items():
        for ev in _norm_event_shape(payload):
            event = dict(ev)

            # Normalize start/end
            start_raw = _norm_ts_field(event.get("start"))
            end_raw   = _norm_ts_field(event.get("end"))
            event["start"] = start_raw
            event["end"]   = end_raw

            # Location -> first line only
            loc = event.get("location")
            if isinstance(loc, str) and loc.strip():
                lines = loc.split("\n")
                if len(lines) >= 1:
                    event["location_name"] = lines[0]
                event.pop("location", None)

            # Calendar name
            event["calendar_name"] = CALENDAR_NAMES.get(
                calendar_key,
                calendar_key.split(".")[1].capitalize() if "." in calendar_key else str(calendar_key),
            )

            # Localize times
            start_dt_local, start_iso_local = _parse_to_local(start_raw) if start_raw and "T" in start_raw else (None, None)
            end_dt_local,   end_iso_local   = _parse_to_local(end_raw)   if end_raw   and "T" in end_raw   else (None, None)

            # All-day / date-only handling
            if start_raw and "T" not in start_raw:
                start_date = start_raw[:10]
                if start_date and start_date < today_local:
                    event["start"] = today_local
                else:
                    event["start"] = start_date or today_local
            else:
                if start_iso_local:
                    event["start"] = start_iso_local

            if end_raw:
                if "T" not in end_raw:
                    event["end"] = end_raw[:10]  # all-day, exclusive
                else:
                    if end_iso_local:
                        event["end"] = end_iso_local

            # Group by start date
            date_key = (event.get("start") or today_local)[:10]
            events_by_date.setdefault(date_key, []).append(event)

    # Sort and aggregate
    sorted_dates = sorted(events_by_date.keys())
    result = []

    for date_key in sorted_dates:
        if entry_count >= MAX_ENTRIES:
            break

        all_day_events, other_events = [], []
        for ev in events_by_date[date_key]:
            if entry_count >= MAX_ENTRIES:
                break
            if "T" not in (ev.get("start") or ""):
                all_day_events.append(ev)
            else:
                other_events.append(ev)
            entry_count += 1

        # Safe sorting using (timestamp, event) tuples
        keyed = []
        for ev in other_events:
            try:
                ts = _epoch_from_dt_str(ev["start"], "other_events sort")
            except Exception as ex:
                log.error(f"Sort key error for event {ev.get('summary')!r}: {ex}")
                ts = float("inf")
            keyed.append((ts, ev))

        keyed.sort(key=lambda kv: kv[0])
        other_events = [ev for _, ev in keyed]

        # Closest end time today
        if other_events and date_key == today_local:
            now_local = _to_local(datetime.now())
            candidates_ts = []
            for ev in other_events:
                e_end = ev.get("end")
                if not e_end or "T" not in e_end:
                    continue
                try:
                    dt_end_local = _dt_from_str_local(e_end)
                    if dt_end_local >= now_local:
                        candidates_ts.append(dt_end_local.timestamp())
                except Exception as ex:
                    log.error(f"End parse error for event {ev.get('summary')!r}: {ex}")
            if candidates_ts:
                candidates_ts.sort()
                ts = candidates_ts[0]
                closest_end_time_local_iso = datetime.fromtimestamp(ts, tz=LOCAL_TZ).isoformat(timespec="seconds")

        # Daily object
        y, m, d = map(int, date_key.split("-"))
        d_local = datetime(y, m, d, 0, 0, 0, tzinfo=LOCAL_TZ)
        result.append({
            "date": date_key,
            "day": d,
            "is_today": int(date_key == today_local),
            "day_name": DAY_NAMES[d_local.weekday()],
            "all_day": all_day_events,
            "other": other_events,
        })

    return result, closest_end_time_local_iso


# -------------------------
# Service wrapper
# -------------------------
@service
def esp_calendar_convert(calendar: dict = None, now: str = "", entity_id: str = "sensor.esp_calendar_data"):
    try:
        res = convert_calendar_format(calendar or {}, now or "")

        if isinstance(res, tuple):
            entries, closest_end = res
        elif isinstance(res, dict):
            entries = res.get("entries", [])
            closest_end = res.get("closest_end_time")
        else:
            raise TypeError(f"convert_calendar_format returned {type(res).__name__}, expected tuple or dict")

        now_local = _to_local(datetime.now())

        state.set(
            entity_id,
            "ok",
            entries=entries,
            closest_end_time=closest_end,
            todays_day_name=DAY_NAMES_EN[now_local.weekday()],
            todays_date_month=MONTHS_EN[now_local.month - 1],
            friendly_name="ESP Calendar Data",
        )

        return {"entries": entries, "closest_end_time": closest_end}

    except Exception as e:
        log.error(f"esp_calendar_convert error: {e}")
        state.set(entity_id, "error", error=str(e))
        return {"error": str(e)}
