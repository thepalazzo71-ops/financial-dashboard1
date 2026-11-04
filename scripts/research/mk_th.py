import json,sys
# usage: mk_th.py <lo> <hi> <tag>   -> gaps at ranks lo+1..hi (union of both pools), split into 4 files th<tag>_in_{a..d}.json
lo,hi,tag=int(sys.argv[1]),int(sys.argv[2]),sys.argv[3]
R='/home/user/financial-dashboard1/'; SP='/tmp/claude-0/-home-user-financial-dashboard1/45600be0-a6c4-5ca9-a40b-02001a7bd8bf/scratchpad/asia/'
d=json.load(open(R+'docs/all-data.json')); h=d['headers']; bi=h.index('Business description'); nf=h.index('Non-financial pool')
pool={c['ticker']:c for c in json.load(open(R+'data-asia/companies_pool_all.json'))}
allr=[r for r in d['regions'][2]['rows'] if not r[5]]; nfr=[r for r in allr if r[nf]=='yes']
print('gaps within top',lo,':',len([r for rs in (allr,nfr) for r in rs[:lo] if not r[bi]]))
gap={}
for rows in (allr,nfr):
    for i,r in enumerate(rows[:hi]):
        if i>=lo and not r[bi] and r[2] not in gap: gap[r[2]]=(i+1,r)
L=[{'rank':v[0],'ticker':t,'name':v[1][3],'country':v[1][4],'incorporation':pool[t].get('incorporation')} for t,v in sorted(gap.items(),key=lambda x:x[1][0])]
n=len(L); k=(n+3)//4; print(n,'companies')
for j,nm in enumerate('abcd'):
    json.dump(L[j*k:(j+1)*k],open(f'{SP}th{tag}_in_{nm}.json','w'),ensure_ascii=False,indent=1); print(nm,len(L[j*k:(j+1)*k]))
