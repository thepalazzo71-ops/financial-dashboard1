import json,sys
# usage: mk_nd.py <lo> <hi> <tag> -> Europe companies ranked lo+1..hi (by total, excl. delisted), skipping ones already in nd_done.json; 4 files nd<tag>_in_{a..d}.json
lo,hi,tag=int(sys.argv[1]),int(sys.argv[2]),sys.argv[3]
R='/home/user/financial-dashboard1/'; S='/tmp/claude-0/-home-user-financial-dashboard1/45600be0-a6c4-5ca9-a40b-02001a7bd8bf/scratchpad/nd/'
d=json.load(open(R+'data/companies_1000_scored.json')); dl={k for k in json.load(open(R+'data/delisted.json')) if not k.startswith('_')}
rows=sorted([c for c in d if c['ticker'] not in dl],key=lambda c:-c['total'])
L=[{'rank':i+1,'ticker':c['ticker'],'name':c['name'],'country':c['country'],'mc_usd_mm':c.get('mc0'),'equity_usd_mm':c.get('equity')} for i,c in enumerate(rows)][lo:hi]
n=len(L); k=(n+3)//4; print(n,'companies')
for j,nm in enumerate('abcd'):
    json.dump(L[j*k:(j+1)*k],open(f'{S}nd{tag}_in_{nm}.json','w'),ensure_ascii=False,indent=1); print(nm,len(L[j*k:(j+1)*k]))
