import json, sys
sys.path.insert(0,'/home/user/financial-dashboard1/scripts')
import us_scoring as U
S='/tmp/claude-0/-home-user-financial-dashboard1/45600be0-a6c4-5ca9-a40b-02001a7bd8bf/scratchpad/asia/'
D='/home/user/financial-dashboard1/data-asia/'
OFFICIAL={'results_announcement','annual_report','filing_data_page'}
res={}
for f in sys.argv[1:]:
    try: res.update(json.load(open(S+f)))
    except Exception as e: print('could not read',f,e)
logp=D+'gm_research_log.json'; log=json.load(open(logp))
ok=0; cnt={}
for t,v in res.items():
    st=v.get('status'); gm=v.get('gm')
    good = st=='ok' and isinstance(gm,(int,float)) and -0.5<gm<1.0
    if st=='ok' and not good: st='rejected'
    rev,gp=v.get('revenue'),v.get('gross_profit')
    if good and rev and gp is not None and abs((gp/rev)-gm)>0.02: good=False; st='rejected'
    cnt[st]=cnt.get(st,0)+1
    e={k:v.get(k) for k in ('status','gm','fiscal_year','currency','revenue','gross_profit','source_url','source_type','notes')}
    e['applied']=good
    if st=='rejected': e['skipped_reason']='failed sanity check (gm out of range or revenue/gross profit mismatch)'
    log['results'][t]=e
    if good: ok+=1
for p in ['companies_pool_all.json','companies_pool_nonfinancial.json']:
    pool=json.load(open(D+p))
    for c in pool:
        e=log['results'].get(c['ticker'])
        if not e or not e.get('applied') or c['ticker'] not in res: continue
        v=res[c['ticker']]
        c['gm']=round(float(v['gm']),4); c['gmFiscalYear']=v.get('fiscal_year'); c['gmSourceUrl']=v.get('source_url'); c['gmSourceType']=v.get('source_type')
        c['gmIsVerified']=v.get('source_type') in OFFICIAL
        c['fixedPts'],c['fixedSumNoGm']=U.compute_fixed_pts(c)
    json.dump(pool,open(D+p,'w'))
json.dump(log,open(logp,'w'),indent=1,ensure_ascii=False)
allp=json.load(open(D+'companies_pool_nonfinancial.json'))
print('round:',cnt,'| applied',ok,'| non-financial pool with GM:',sum(1 for c in allp if c['gm'] is not None),'/',len(allp),'| researched total:',len(log['results']))
