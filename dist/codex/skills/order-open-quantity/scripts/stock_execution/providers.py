"""Explicit local fixture ingestion; ClickHouse is a future adapter only."""
import copy
from .engine import require, stamp


class MarketDataProvider:
    def bars(self, instrument_id, frequency, visible_at):
        raise NotImplementedError


class FixtureMarketDataProvider(MarketDataProvider):
    def __init__(self, bars):
        self.records = copy.deepcopy(bars)

    def bars(self, instrument_id, frequency, visible_at):
        return [copy.deepcopy(b) for b in self.records if b['instrument_id']==instrument_id
                and b['frequency']==frequency and stamp(b['end_at'])<=stamp(visible_at)]


def map_daily_record(record, *, price_basis, source, start_at, end_at, volume_unit):
    require(record['market'] in ('SSE','SZSE','BSE'), 'UNKNOWN_EXCHANGE')
    require(isinstance(record['security_code'],str), 'INVALID_SECURITY_CODE')
    require(price_basis=='UNADJUSTED', 'UNKNOWN_PRICE_BASIS')
    require(volume_unit=='shares', 'UNKNOWN_VOLUME_UNIT')
    require(start_at[:10]==record['trade_date']==end_at[:10], 'INVALID_BAR_TIME')
    return dict(instrument_id=record['market']+':'+record['security_code'], exchange=record['market'],
                security_code=record['security_code'], frequency='1d', trade_date=record['trade_date'],
                start_at=start_at,end_at=end_at, **{k:record[k] for k in ('open','high','low','close','volume','prev_close')},
                amount=record['total_turnover'], currency='CNY', source=source,price_basis=price_basis,volume_unit=volume_unit)
