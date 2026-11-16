from datetime import date, datetime, time
from decimal import Decimal
from uuid import UUID

def json_value(value):
    if isinstance(value, (datetime, date, time)):
        return value.isoformat()
    if isinstance(value, Decimal):
        return float(value)
    if isinstance(value, UUID):
        return str(value)
    if isinstance(value, bytes):
        return value.decode("utf-8", errors="replace")
    return value

def row_dict(row):
    return {k: json_value(v) for k, v in dict(row).items()}
