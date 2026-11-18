"""Compact net-debt records for a dashboard payload (same shape as build_site.load_net_debt) from any folder's net_debt.json."""
import json
from pathlib import Path


def load(folder):
    path = Path(folder) / 'net_debt.json'
    if not path.exists():
        return {}
    out = {}
    for t, e in json.load(open(path)).get('entries', {}).items():
        if e.get('tier') == 'F':
            out[t] = {'tier': 'F'}
        elif e.get('netDebtUsd') is not None:
            out[t] = {'tier': e['tier'], 'cur': e['currency'], 'date': e.get('balanceSheetDate'), 'per': e.get('periodType'),
                      'gd': e.get('grossDebt'), 'cash': e.get('cash'), 'lease': e.get('leaseLiabilities'),
                      'rep': e.get('netDebtReported'), 'local': e.get('netDebt'), 'usd': e['netDebtUsd'], 'fx': e.get('fx'),
                      'src': e.get('sourceUrl'), 'srcType': e.get('sourceType'), 'note': e.get('notes'), 'flags': e.get('flags', [])}
    return out
