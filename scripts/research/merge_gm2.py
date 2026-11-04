import json, sys
sys.path.insert(0,'/home/user/financial-dashboard1/scripts')
import us_scoring as U
S='/tmp/claude-0/-home-user-financial-dashboard1/45600be0-a6c4-5ca9-a40b-02001a7bd8bf/scratchpad/asia/'
D='/home/user/financial-dashboard1/data-asia/'
OFFICIAL={'company_statement','annual_report','results_announcement','filing_data_page'}
ALLOWED={'software_it_services','internet_media_games','semiconductors_electronic_components','electronic_equipment_hardware','machinery_equipment','auto_parts_transport_equipment','chemicals_materials','metals_steel_mining','food_beverage_agri','consumer_goods_apparel','retail_stores','wholesale_trading_distribution','restaurants_leisure_hospitality','construction_engineering','real_estate_property_services','transport_logistics_shipping','healthcare_pharma_biotech','medical_devices_equipment','staffing_education_business_services','telecom_utilities_energy','packaging_paper_printing','building_materials','other'}
res={}
for f in sys.argv[1:]:
    try: res.update(json.load(open(S+f)))
    except Exception as e: print('could not read',f,e)
log=json.load(open(D+'gm_research_log.json')); ind=json.load(open(D+'gm_industry.json'))
done=set(json.load(open(S+'gm2_done.json')))
ok=0; cnt={}
applied={}
for t,v in res.items():
    gm=v.get('gm'); good=v.get('status')=='ok' and isinstance(gm,(int,float)) and -0.5<gm<1.0
    cnt['ok' if good else 'not_found']=cnt.get('ok' if good else 'not_found',0)+1
    g=v.get('industry_group')
    if g in ALLOWED: ind[t]={'industry_group':g,'confidence':'high' if v.get('business') and v.get('business')!='unidentified' else 'low','business':(v.get('business') or '')[:120]}
    e=log['results'].setdefault(t,{})
    e.update({'attempt2':{k:v.get(k) for k in ('status','gm','fiscal_year','basis','how','source_url','source_type','notes')}})
    if good:
        applied[t]=v; e.update({'status':'ok','gm':gm,'fiscal_year':v.get('fiscal_year'),'source_url':v.get('source_url'),'source_type':v.get('source_type'),'applied':True})
        ok+=1
    done.add(t)
for p in ['companies_pool_all.json','companies_pool_nonfinancial.json']:
    pool=json.load(open(D+p))
    for c in pool:
        v=applied.get(c['ticker'])
        if not v: continue
        c['gm']=round(float(v['gm']),4); c['gmFiscalYear']=v.get('fiscal_year'); c['gmSourceUrl']=v.get('source_url'); c['gmSourceType']=v.get('source_type')
        c['gmIsVerified']=v.get('source_type') in OFFICIAL
        for k in ('gmEstimated','gmEstGroup','gmEstPeers'): c.pop(k,None)
        c['fixedPts'],c['fixedSumNoGm']=U.compute_fixed_pts(c)
    json.dump(pool,open(D+p,'w'))
json.dump(log,open(D+'gm_research_log.json','w'),indent=1,ensure_ascii=False)
json.dump(ind,open(D+'gm_industry.json','w'),ensure_ascii=False)
json.dump(sorted(done),open(S+'gm2_done.json','w'))
print('gm2 round:',cnt,'applied',ok,'| industry map',len(ind))
