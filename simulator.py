"""Deterministic, discrete-minute model; hypothetical input, not a calibrated twin."""
import random, math
ZONES = [('I','Inferior',20),('P','Principal',30),('S','Superior',40)]
def layout():
    return [{'id':f'{p}-{i:02d}','zone':z,'seats':(2,4,4,6,4)[(i-1)%5]} for p,z,n in ZONES for i in range(1,n+1)]
def simulate(cfg):
    def integer(name, default, lo, hi):
        val=cfg.get(name,default)
        if isinstance(val,bool) or not isinstance(val,(int,float)) or not math.isfinite(val) or int(val)!=val or not lo<=val<=hi: raise ValueError(f'{name}: use um inteiro entre {lo} e {hi}')
        return int(val)
    staff=integer('staff',4,1,20); arrivals=integer('arrivals',22,1,60); duration=integer('duration',35,10,90); clean=integer('clean',4,1,15); seed=integer('seed',42,0,999999); patience=integer('patience',12,1,60); horizon=180
    rng=random.Random(seed); groups=[]
    for t in range(horizon):
        factor=1.35 if 45<=t<105 else .825
        rate=arrivals/10*factor; n=int(rate)+(rng.random()<rate%1)
        for _ in range(n): groups.append((t,rng.choices([1,2,3,4,5,6],[20,35,15,20,5,5])[0],max(5,duration+rng.randint(-8,8)),max(1,clean+rng.choice([-1,0,0,0,1]))))
    def run(smart):
        tables=[dict(m,state='free',until=0,dirty=0,clean=clean) for m in layout()]; workers=[0]*staff; queue=[]; ptr=0; seated=people=lost=lost_people=0; waits=[]; releases=[]; dirty_minutes=0; peak=0; samples=[]
        for t in range(horizon):
            for m in tables:
                if m['state']=='occupied' and m['until']<=t: m.update(state='dirty',dirty=t)
                elif m['state']=='cleaning' and m['until']<=t: m['state']='free'; releases.append(t-m['dirty'])
            while ptr<len(groups) and groups[ptr][0]==t: queue.append(groups[ptr]); ptr+=1
            pending=[]
            for g in queue:
                if t-g[0]>=patience: lost+=1; lost_people+=g[1]; continue
                candidates=[m for m in tables if m['state']=='free' and m['seats']>=g[1]]
                if not candidates: pending.append(g); continue
                m=min(candidates,key=lambda m:(m['seats'],m['id'])); m.update(state='occupied',until=t+g[2],clean=g[3]); seated+=1; people+=g[1]; waits.append(t-g[0])
            queue=pending
            dirty=[m for m in tables if m['state']=='dirty']
            free=[x for x in tables if x['state']=='free']; largest=max((x['seats'] for x in free),default=0); compatible={n:sum(largest<g[1]<=n for g in queue) for n in (2,4,6)}; vacancies={z:sum(x['zone']==z for x in free) for _,z,_ in ZONES}
            def priority(m):
                age=t-m['dirty']; fits=compatible[m['seats']]; scarcity=vacancies[m['zone']]
                return (age>=15, age if age>=15 else age+min(fits,8)*2+(2 if scarcity==0 else 0),age)
            dirty.sort(key=priority,reverse=True) if smart else dirty.sort(key=lambda m:(m['dirty'],m['id']))
            for k in range(staff):
                if workers[k]<=t and dirty:
                    m=dirty.pop(0); m.update(state='cleaning',until=t+m['clean']); workers[k]=m['until']
            count=sum(m['state'] in ('dirty','cleaning') for m in tables); dirty_minutes+=count; peak=max(peak,count)
            if t%10==0 or t==horizon-1: samples.append({'minute':t,'unavailable':count,'queue':len(queue)})
        return dict(seated=seated,people=people,lost=lost,lost_people=lost_people,queue=len(queue),queue_people=sum(g[1] for g in queue),mean_wait=round(sum(waits)/len(waits),2) if waits else None,mean_release=round(sum(releases)/len(releases),2) if releases else None,completed=len(releases),unfinished=sum(m['state'] in ('dirty','cleaning') for m in tables),dirty_minutes=dirty_minutes,peak=peak,samples=samples)
    return {'parameters':dict(staff=staff,arrivals=arrivals,duration=duration,clean=clean,seed=seed,patience=patience),'groups':len(groups),'people':sum(g[1] for g in groups),'horizon':horizon,'fifo':run(False),'smart':run(True)}


def benchmark(cfg):
    """Paired scenarios; same generated arrivals for both strategies per seed."""
    raw=cfg.get('runs',12)
    if type(raw) is not int or not 3<=raw<=20: raise ValueError('Escolha entre 3 e 20 repetições')
    first=simulate(cfg); seeds=[(first['parameters']['seed']+i)%1000000 for i in range(raw)]
    results=[first]+[simulate(dict(cfg,seed=seed)) for seed in seeds[1:]]
    ds=[r['smart']['people']-r['fifo']['people'] for r in results]
    dm=[r['fifo']['dirty_minutes']-r['smart']['dirty_minutes'] for r in results]
    return {'runs':raw,'seeds':seeds,'people':{'mean':round(sum(ds)/raw,2),'min':min(ds),'max':max(ds),'better':sum(x>0 for x in ds),'equal':sum(x==0 for x in ds),'worse':sum(x<0 for x in ds)},'minutes':{'mean':round(sum(dm)/raw,2),'min':min(dm),'max':max(dm)},'rows':[{'seed':seed,'people_delta':d,'minutes_delta':m} for seed,d,m in zip(seeds,ds,dm)]}
