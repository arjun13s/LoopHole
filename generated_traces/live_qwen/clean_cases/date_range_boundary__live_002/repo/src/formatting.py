from datetime import date


def display_range(start: date, end: date) -> str:
    return f"{start.isoformat()}..{end.isoformat()}"
