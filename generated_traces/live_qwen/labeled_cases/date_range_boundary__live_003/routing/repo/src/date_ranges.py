from __future__ import annotations

from datetime import date

def days_between(start: date, end: date, inclusive: bool = False) -> int:
    """Return the number of whole days between start and end.

    If inclusive=True, both boundary dates count. Reversed ranges are invalid.
    """
    if end < start:
        raise ValueError("end before start")
    days = (end - start).days + 1 if inclusive else (end - start).days
    return days