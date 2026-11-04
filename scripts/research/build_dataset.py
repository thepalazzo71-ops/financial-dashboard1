import json
R='/home/user/financial-dashboard1/'
ind=json.load(open(R+'data-asia/gm_industry.json'))
rows=[]
def add(region,c,group=None,biz=''):
    th=c.get('thesis') or {}
    text=' '.join(x for x in (biz, th.get('business_description') or '') if x).strip()
    rows.append({'ticker':c['ticker'],'region':region,'country':c.get('country'),'group':group,'text':text,
                 'gm':c.get('gm'),'sourced':c.get('gm') is not None and not c.get('gmEstimated'),'financial':bool(c.get('isFinancial') or c.get('financial'))})
for c in json.load(open(R+'data-asia/companies_pool_nonfinancial.json')):
    i=ind.get(c['ticker'],{}); add('asia',c,i.get('industry_group'),i.get('business',''))
for c in json.load(open(R+'data-us/companies_pool_nonfinancial.json')): add('us',c)
for c in json.load(open(R+'data/companies_1000_scored.json')): add('europe',c)
json.dump(rows,open('/tmp/claude-0/-home-user-financial-dashboard1/45600be0-a6c4-5ca9-a40b-02001a7bd8bf/scratchpad/emb/dataset.json','w'),ensure_ascii=False)
import collections
for r in ('asia','us','europe'):
    s=[x for x in rows if x['region']==r]
    print(r,len(s),'sourced',sum(x['sourced'] for x in s),'sourced+text',sum(x['sourced'] and len(x['text'])>20 for x in s),'avg len',sum(len(x['text']) for x in s)//max(1,len(s)))
