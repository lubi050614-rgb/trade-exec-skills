"""Explicit local futures fixtures; no guessed settlement or stock volume units."""
import copy
from execution_common.values import require, stamp


class MarketDataProvider:
    def bars(self,contract_id,frequency,visible_at): raise NotImplementedError


class FixtureMarketDataProvider(MarketDataProvider):
    def __init__(self,records): self.records=copy.deepcopy(records)
    def bars(self,contract_id,frequency,visible_at):
        return [copy.deepcopy(x) for x in self.records if x['contract_id']==contract_id and x['frequency']==frequency and stamp(x['end_at'])<=stamp(visible_at)]


def map_record(record):
    required={'contract_id','multiplier','volume_unit','trade_date','start_at','end_at','frequency','price_basis','open','high','low','close','volume'}
    require(required<=set(record),'MISSING_FUTURES_MARKET_FIELDS')
    require(record['volume_unit']=='lots' and record['price_basis']=='UNADJUSTED','MARKET_UNIT_OR_BASIS_MISMATCH')
    require(stamp(record['start_at'])<stamp(record['end_at']),'INVALID_BAR_TIME')
    # prev_close is retained if present, never mapped to prev_settlement_price.
    return copy.deepcopy(record)
