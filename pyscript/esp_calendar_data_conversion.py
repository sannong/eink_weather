from homeassistant.util import dt as dt_util
from datetime import timezone, datetime

CALENDAR_NAMES = {"calendar.X": "X", "calendar.Y": "Y"}
DAY_NAMES = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
DAY_NAMES_DE = ["Monday","Tuesday","Wednesday","Thursday","Friday","Saturday","Sunday"]
MONTHS_DE = ["January","February","March","April","May","June","July","August","September","October","November","December"]

MAX_ENTRIES = 8

def _parse_to_local(dt_str: str):
    if not dt_str or "T" not in dt_str:
        return None, None
    dt = dt_util.parse_datetime(dt_str)
    if dt is None:
        try:
            dt = datetime.fromisoformat(dt_str)
        except Exception:
            return None, None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    dt_local = dt_util.as_local(dt)
    return dt_local, dt_local.strftime("%Y-%m-%dT%H:%M:%S")

def _local_date_str(s: str | None):
    if s:
        try:
            d = datetime.fromisoformat(s)
            if d.tzinfo:
                return dt_util.as_local(d).date().isoformat()
            return d.date().isoformat()
        except Exception:
            pass
    return dt_util.now().date().isoformat()

def _norm_event_shape(calendar_payload):
    """
    Takes either {"events":[...]} OR directly a list [...],
    and returns a list of events.
    """
    if isinstance(calendar_payload, dict) and "events" in calendar_payload:
        return calendar_payload.get("events") or []
    if isinstance(calendar_payload, list):
        return calendar_payload
    return []

def _norm_ts_field(v):
    """
    Takes either a string OR {dateTime|date} and returns a string.
    - dateTime -> unchanged
    - date -> YYYY-MM-DD
    """
    if v is None:
        return None
    if isinstance(v, str):
        return v
    if isinstance(v, dict):
        return v.get("dateTime") or v.get("date")
    return None

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
            end_raw = _norm_ts_field(event.get("end"))
            event["start"] = start_raw
            event["end"] = end_raw

            # Split location (optional)
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

            # ASCII-clean for summary
            if "summary" in event and isinstance(event["summary"], str):
                event["summary"] = event["summary"].encode("ascii", "ignore").decode("ascii")

            # Localize times
            start_dt_local, start_iso_local = _parse_to_local(start_raw) if start_raw else (None, None)
            end_dt_local, end_iso_local = _parse_to_local(end_raw) if end_raw else (None, None)

            # All-day: no "T" → keep only date; multi-day before today gets shifted to today
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
                    event["end"] = end_raw[:10]
                else:
                    if end_iso_local:
                        event["end"] = end_iso_local

            # Grouping key
            date_key = event["start"][:10] if event.get("start") else today_local
            events_by_date.setdefault(date_key, []).append(event)

    # Sorting, aggregation
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

        def _key_start(e):
            dt = dt_util.parse_datetime(e["start"]) or datetime.fromisoformat(e["start"])
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            return dt_util.as_local(dt)

        other_events.sort(key=_key_start)

        if other_events and date_key == today_local:
            now_local = dt_util.now()
            candidates = []
            for ev in other_events:
                e = ev.get("end")
                if not e or "T" not in e:
                    continue
                dt_end = dt_util.parse_datetime(e) or datetime.fromisoformat(e)
                if dt_end.tzinfo is None:
                    dt_end = dt_end.replace(tzinfo=timezone.utc)
                dt_end_local = dt_util.as_local(dt_end)
                if dt_end_local >= now_local:
                    candidates.append(dt_end_local)
            if candidates:
                candidates.sort()
                closest_end_time_local_iso = candidates[0].strftime("%Y-%m-%dT%H:%M:%S")

        # Day object
        d_local = datetime.fromisoformat(date_key + "T00:00:00")
        d_local = dt_util.as_local(d_local.replace(tzinfo=timezone.utc))
        day_item = {
            "date": date_key,
            "day": d_local.day,
            "is_today": int(date_key == today_local),
            "day_name": DAY_NAMES[d_local.weekday()],
            "all_day": all_day_events,
            "other": other_events,
        }
        result.append(day_item)

    return result, closest_end_time_local_iso

@service
def esp_calendar_convert(calendar: dict = None, now: str = "", entity_id: str = "sensor.esp_calendar_data"):
    """
    Service: pyscript.esp_calendar_convert
    Data:
        calendar: {...}   # output from calendar.get_events (response_variable)
        now: "YYYY-MM-DD" # optional, otherwise today local
        entity_id: sensor.esp_calendar_data  # target sensor
    """
    try:
        entries, closest_end = convert_calendar_format(calendar or {}, now or "")
        now_local = dt_util.now()
        # Write directly to the target sensor, incl. extra attributes
        state.set(
            entity_id,
            "ok",
            entries=entries,
            closest_end_time=closest_end,
            todays_day_name=DAY_NAMES_DE[now_local.weekday()],
            todays_date_month=MONTHS_DE[now_local.month - 1],
            friendly_name="ESP Calendar Data",
        )
        # Return value optional, in case you want to see it in the log
        return {"entries": entries, "closest_end_time": closest_end}
    except Exception as e:
        log.error(f"esp_calendar_convert error: {e}")
        state.set(entity_id, "error", error=str(e))
        return {"error": str(e)}
