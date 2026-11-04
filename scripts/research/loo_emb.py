import json,numpy as np
from sklearn.feature_extraction.text import TfidfVectorizer
D='/tmp/claude-0/-home-user-financial-dashboard1/45600be0-a6c4-5ca9-a40b-02001a7bd8bf/scratchpad/emb/'
rows=json.load(open(D+'dataset.json')); E=np.load(D+'emb.npy')
ok=lambda r:r['sourced'] and r['gm'] is not None and len(r['text'])>10
ai=[i for i,r in enumerate(rows) if r['region']=='asia' and ok(r) and r['group']]
oi=[i for i,r in enumerate(rows) if r['region']!='asia' and ok(r)]
y=np.array([rows[i]['gm'] for i in ai]); grp=np.array([rows[i]['group'] for i in ai]); n=len(ai)
print('Asia test companies',n,'| extra US/Europe neighbours',len(oi))
ar=np.arange(n)
glob=np.array([np.median(np.delete(y,i)) for i in range(n)])
def gmed(i):
    m=(grp==grp[i])&(ar!=i); return np.median(y[m]) if m.sum()>=10 else glob[i]
grpm=np.array([gmed(i) for i in range(n)])
def rep(name,p,base=None):
    e=np.abs(p-y); s='%-46s MAE %.4f  median %.4f  within10pts %.1f%%'%(name,e.mean(),np.median(e),100*(e<=.10).mean())
    if base is not None:
        rng=np.random.default_rng(0); d=np.abs(base-y)-e; bs=[d[rng.integers(0,n,n)].mean() for _ in range(2000)]
        s+='  gain vs group %+.4f [95%% CI %+.4f,%+.4f]'%(d.mean(),*np.percentile(bs,[2.5,97.5]))
    print(s)
rep('global median',glob); rep('industry-group median (current)',grpm)
EA=E[ai]; S=EA@EA.T; np.fill_diagonal(S,-9)
vec=TfidfVectorizer(ngram_range=(1,2),sublinear_tf=True,stop_words='english').fit([rows[i]['text'] for i in ai+oi])
X=vec.transform([rows[i]['text'] for i in ai]); St=(X@X.T).toarray(); np.fill_diagonal(St,-9)
def knn(S,k,ex=None,ey=None,Sx=None):
    out=[]
    for i in range(n):
        s=S[i]; vals=y; idx=np.argsort(-s)[:k]; v=list(y[idx]); sc=list(s[idx])
        if Sx is not None:
            j=np.argsort(-Sx[i])[:k]; v+=list(ey[j]); sc+=list(Sx[i][j])
            o=np.argsort(-np.array(sc))[:k]; v=[v[t] for t in o]
        out.append(np.median(v))
    return np.array(out)
res={}
for k in (5,10,20,30):
    res[('emb',k)]=p=knn(S,k); rep('EmbeddingGemma 2 kNN k=%d'%k,p,grpm)
for k in (10,20):
    rep('TF-IDF kNN k=%d (stand-in)'%k,knn(St,k),grpm)
for k in (10,20):
    rep('EmbGemma blend w/ group median k=%d'%k,(res[('emb',k)]+grpm)/2,grpm)
# within-group
for k in (5,10):
    p=[]
    for i in range(n):
        s=S[i].copy(); s[grp!=grp[i]]=-9; idx=[j for j in np.argsort(-s)[:k] if s[j]>-9]
        p.append(np.median(y[idx]) if len(idx)>=3 else grpm[i])
    rep('EmbGemma kNN within same group k=%d'%k,np.array(p),grpm)
# cross-region neighbours added
ey=np.array([rows[i]['gm'] for i in oi]); EO=E[oi]; Sx=EA@EO.T
for k in (10,20):
    rep('EmbGemma kNN + US/EU neighbours k=%d'%k,knn(S,k,ey=ey,Sx=Sx),grpm)
# similarity-gated: use kNN only when mean top-10 similarity high
p=res[('emb',10)]; ms=np.sort(S,axis=1)[:,-10:].mean(1)
for q in (25,50):
    t=np.percentile(ms,q); hi=ms>=t
    e1=np.abs(p-y); e0=np.abs(grpm-y)
    print('top-%d%% most similar peers: kNN MAE %.4f vs group %.4f (n=%d)'%(100-q,e1[hi].mean(),e0[hi].mean(),hi.sum()))
# by group
print('\nby group (k=10): n, group MAE, EmbGemma MAE')
e1=np.abs(res[('emb',10)]-y); e0=np.abs(grpm-y)
for g in sorted(set(grp),key=lambda g:-(grp==g).sum()):
    m=grp==g
    if m.sum()>=15: print('  %-38s %3d  %.3f  %.3f'%(g,m.sum(),e0[m].mean(),e1[m].mean()))
