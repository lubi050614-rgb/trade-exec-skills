import hashlib
import json
from datetime import datetime
from decimal import Decimal

D = Decimal


class ToolError(ValueError):
    def __init__(self, code, **details):
        super().__init__(code)
        self.code, self.details = code, details


def require(condition, code, **details):
    if not condition:
        raise ToolError(code, **details)


def dec(value):
    require(type(value) in (str, int), 'INVALID_DECIMAL')
    result=D(value)
    require(result.is_finite(), 'INVALID_DECIMAL')
    return result


def stamp(value):
    result=datetime.fromisoformat(value)
    require(result.tzinfo is not None and result.utcoffset().total_seconds()==28800, 'SHANGHAI_TIME_REQUIRED')
    return result


def digest(value):
    return hashlib.sha256(json.dumps(value,sort_keys=True,ensure_ascii=False).encode()).hexdigest()


def amount(value):
    # Preserve precision internally; no rounding down of margin or fee reserves.
    return format(value if isinstance(value,D) else dec(value),'f')
