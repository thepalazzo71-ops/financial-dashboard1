"""Resync data/companies_1000_scored.json's valPts/total/rankFull against
currently-applied overrides, without doing a full site rebuild.

scripts/build_site.py already does this automatically on every run (that's
the normal way this happens - see scoring.resync_pool_ranks for why it's
needed). Use this script directly only when you want the resync without
also regenerating docs/index.html.

Usage: python3 scripts/resync_ranks.py
"""
import json

from scoring import DATA, load_companies, load_overrides, resync_pool_ranks

POOL_PATH = DATA / "companies_1000_scored.json"


def main():
    companies = load_companies()
    mc_overrides, gm_overrides = load_overrides()
    resync_pool_ranks(companies, mc_overrides, gm_overrides)
    with open(POOL_PATH, 'w') as f:
        json.dump(companies, f)
    print(f'resynced {len(companies)} companies against '
          f'{len(mc_overrides)} mc overrides, {len(gm_overrides)} gm overrides')


if __name__ == '__main__':
    main()
