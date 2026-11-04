import json, sys
from datetime import datetime, timezone
S='/tmp/claude-0/-home-user-financial-dashboard1/45600be0-a6c4-5ca9-a40b-02001a7bd8bf/scratchpad/asia/'
outs=sys.argv[1:]
res={}
for o in outs: res.update(json.load(open(S+o)))
ranked={r['ticker']:r for r in json.load(open(S+'ranked_full.json'))}
now=datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')
mcp='data-asia/mc_overrides_applied.json'; mc=json.load(open(mcp))
cap='data-asia/corporate_actions.json'; ca=json.load(open(cap))
covp='data-asia/corporate_actions_coverage.json'; cov=json.load(open(covp))
n_mc=n_ca=0
for t,v in res.items():
    m=v.get('mc') or {}
    if m.get('usd_mm'):
        mc[t]={'mc':round(float(m['usd_mm']),2),'source':m.get('source_url'),'updatedAt':now,'quoteDate':m.get('date')}; n_mc+=1
    for a in v.get('corp_actions') or []:
        a=dict(a); cat=a.pop('category','other')
        e={'ticker':t,'company':ranked[t]['name']}; e.update(a)
        if not any(x.get('ticker')==t and x.get('source_url')==e.get('source_url') and x.get('date')==e.get('date') for x in ca.setdefault(cat,[])):
            ca[cat].append(e); n_ca+=1
    if t not in cov['screened']: cov['screened'].append(t)
cov['total_priority_pool']=len(ranked)
json.dump(mc,open(mcp,'w'),separators=(',',':')); json.dump(ca,open(cap,'w'),indent=1); json.dump(cov,open(covp,'w'),indent=1)
print('mc',n_mc,'corp actions',n_ca,'screened',len(cov['screened']))
for t,v in res.items():
    if not (v.get('mc') or {}).get('usd_mm'): print('no mc:',t,(v.get('mc') or {}).get('notes','')[:120])
