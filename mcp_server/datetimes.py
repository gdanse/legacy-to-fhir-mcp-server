"""Parses the legacy date formats (Ticket 1's mangling) back into FHIR date strings.

Inverse of the transforms in legacy_data/mangle.py -- kept separate because
that module mangles synthetic data going in, this one translates real
legacy-shaped data going out.
"""
from datetime import datetime, timezone

_MONTHS = {m: i + 1 for i, m in enumerate(
    ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]
)}


def parse_mmddyyyy(s):
    """'10/30/1954' -> '1954-10-30'"""
    m, d, y = s.split("/")
    return f"{y}-{int(m):02d}-{int(d):02d}"


def parse_dd_mon_yyyy(s):
    """'23-Dec-1972' -> '1972-12-23'"""
    d, mon, y = s.split("-")
    return f"{y}-{_MONTHS[mon]:02d}-{int(d):02d}"


def parse_yyyymmdd(s):
    """'20080228' -> '2008-02-28'"""
    return f"{s[0:4]}-{s[4:6]}-{s[6:8]}"


def mmddyyyy_to_yyyymmdd(s):
    """'10/30/1954' -> '19541030', for comparing against dob_epoch."""
    m, d, y = s.split("/")
    return f"{y}{int(m):02d}{int(d):02d}"


def epoch_to_yyyymmdd(epoch):
    """Unix timestamp -> '19541030', for comparing against dob_mmddyyyy."""
    dt = datetime.fromtimestamp(int(epoch), tz=timezone.utc)
    return dt.strftime("%Y%m%d")
