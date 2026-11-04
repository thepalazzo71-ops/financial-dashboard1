import json, sys
S='/tmp/claude-0/-home-user-financial-dashboard1/45600be0-a6c4-5ca9-a40b-02001a7bd8bf/scratchpad/asia/'
r=int(sys.argv[1]); per=25; n=4
q=json.load(open(S+'gm2_queue.json'))
log=set(json.load(open(S+'gm2_done.json'))) if __import__('os').path.exists(S+'gm2_done.json') else set()
q=[x for x in q if x['ticker'] not in log]
for k in range(n):
    part=q[k*per:(k+1)*per]
    if part: json.dump(part,open(S+f'gm2_r{r:02d}_{"abcd"[k]}.json','w'),ensure_ascii=False,indent=1)
    print(f'gm2_r{r:02d}_{"abcd"[k]}',len(part))
print('left in queue',len(q))
