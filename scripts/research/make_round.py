import json, sys
S='/tmp/claude-0/-home-user-financial-dashboard1/45600be0-a6c4-5ca9-a40b-02001a7bd8bf/scratchpad/asia/'
r=int(sys.argv[1]); per=int(sys.argv[2]) if len(sys.argv)>2 else 25; n=int(sys.argv[3]) if len(sys.argv)>3 else 4
q=json.load(open(S+'gm_queue.json'))
researched=set(json.load(open('/home/user/financial-dashboard1/data-asia/gm_research_log.json'))['results'])
q=[x for x in q if x['ticker'] not in researched]
start=0
for k in range(n):
    part=q[start+k*per:start+(k+1)*per]
    if part: json.dump(part,open(S+f'gm_r{r:02d}_{"abcd"[k]}.json','w'),ensure_ascii=False,indent=1)
    print(f'gm_r{r:02d}_{"abcd"[k]}', len(part))
