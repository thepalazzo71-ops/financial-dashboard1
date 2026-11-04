import json,sys
S='/tmp/claude-0/-home-user-financial-dashboard1/45600be0-a6c4-5ca9-a40b-02001a7bd8bf/scratchpad/asia/'; D='/home/user/financial-dashboard1/data-asia/'
F=("business_description","competitive_position","main_shareholders","red_flags","website","insider_ownership")
res={}
for f in sys.argv[1:]: res.update(json.load(open(S+f)))
ok={t:v['thesis'] for t,v in res.items() if v.get('thesis') and all(k in v['thesis'] for k in F) and v['thesis']['business_description']}
for p in ('companies_pool_all.json','companies_pool_nonfinancial.json'):
    pool=json.load(open(D+p)); n=0
    for c in pool:
        if c['ticker'] in ok: c['thesis']={k:ok[c['ticker']][k] for k in F}; c['hasThesis']=True; n+=1
    json.dump(pool,open(D+p,'w')); print(p,n)
print('merged',len(ok),'of',len(res))
for t,v in res.items():
    n=(v.get('notes') or '')
    if any(w in n.lower() for w in ('delist','taken private','suspend','tender offer','take-private')) and 'no takeover' not in n.lower()[:40]: print('CHECK',t,n[:200])
