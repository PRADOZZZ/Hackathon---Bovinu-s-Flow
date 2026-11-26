import sqlite3, time, math, csv, io, secrets
from pathlib import Path
from contextlib import contextmanager
from simulator import layout
STATES={'free':'Disponível','occupied':'Ocupada','possible':'Possível saída','dirty':'Aguardando limpeza','cleaning':'Em limpeza','blocked':'Bloqueada'}
TRANSITIONS={'occupy':({'free'},'occupied'),'suspect':({'occupied'},'possible'),'return':({'possible'},'occupied'),'depart':({'occupied','possible'},'dirty'),'start':({'dirty'},'cleaning'),'finish':({'cleaning'},'free'),'block':({'free'},'blocked'),'unblock':({'blocked'},'free'),'cancel':({'cleaning'},'dirty')}
class Conflict(Exception): pass
class Store:
    def __init__(self,path, demo=True):
        self.path=str(path); self.demo=demo; Path(path).parent.mkdir(parents=True,exist_ok=True)
        with self.tx() as c:
            c.executescript('''CREATE TABLE IF NOT EXISTS tables(id TEXT PRIMARY KEY,zone TEXT NOT NULL,seats INTEGER NOT NULL,state TEXT NOT NULL,since REAL NOT NULL,dirty_since REAL,clean_since REAL,version INTEGER NOT NULL DEFAULT 0); CREATE TABLE IF NOT EXISTS events(id INTEGER PRIMARY KEY AUTOINCREMENT,table_id TEXT,zone TEXT,action TEXT,old_state TEXT,new_state TEXT,ts REAL,actor TEXT,wait_s REAL,clean_s REAL,total_s REAL); CREATE TABLE IF NOT EXISTS settings(key TEXT PRIMARY KEY,value TEXT NOT NULL);''')
            c.execute('INSERT OR IGNORE INTO settings VALUES (?,?)',('mode','demo' if demo else 'operacional'))
            if c.execute("SELECT value FROM settings WHERE key='mode'").fetchone()[0] != ('demo' if demo else 'operacional'): raise ValueError('Banco pertence a outro modo; use um arquivo separado.')
            c.execute('INSERT OR IGNORE INTO settings VALUES (?,?)',('goal','5'))
            c.execute('INSERT OR IGNORE INTO settings VALUES (?,?)',('demand','-1'))
            if not c.execute('SELECT 1 FROM tables LIMIT 1').fetchone(): self.seed(c,demo)
    @contextmanager
    def tx(self):
        c=sqlite3.connect(self.path,timeout=8,isolation_level=None); c.row_factory=sqlite3.Row
        try:
            c.execute('PRAGMA busy_timeout=8000'); c.execute('BEGIN IMMEDIATE'); yield c; c.commit()
        except: c.rollback(); raise
        finally: c.close()
    def seed(self,c,demo):
        now=time.time(); c.execute('DELETE FROM events'); c.execute('DELETE FROM tables'); c.execute("UPDATE settings SET value='5' WHERE key='goal'"); c.execute("UPDATE settings SET value=? WHERE key='demand'",('65' if demo else '-1',))
        for i,m in enumerate(layout()):
            s=('occupied','occupied','free','occupied','dirty','occupied','occupied','cleaning','free','occupied','possible','free')[i%12] if demo else 'free'; age=(i%9+1)*48 if demo else 0; since=now-age; dirty=since if s=='dirty' else since-100 if s=='cleaning' else None
            c.execute('INSERT INTO tables VALUES (?,?,?,?,?,?,?,?)',(m['id'],m['zone'],m['seats'],s,since,dirty,since if s=='cleaning' else None,secrets.randbits(50)))
            if demo:
                for j in range(2):
                    w=45+(i*13+j*47)%280; cl=85+(i*7+j*31)%115; stamp=now-((i*37+j*600)%4200+90)
                    c.execute('INSERT INTO events(table_id,zone,action,old_state,new_state,ts,actor,wait_s,clean_s,total_s) VALUES (?,?,?,?,?,?,?,?,?,?)',(m['id'],m['zone'],'finish','cleaning','free',stamp,'semente-demo',w,cl,w+cl))
    def reset(self):
        if not self.demo: raise ValueError('Reset permitido apenas em demonstração')
        with self.tx() as c: self.seed(c,True)
    def action(self,tid,action,version,actor='equipe'):
        if not isinstance(tid,str) or len(tid)>12: raise ValueError('Identificador de mesa inválido')
        if not isinstance(action,str) or action not in TRANSITIONS: raise ValueError('Ação inválida')
        if type(version) is not int: raise ValueError('Versão da mesa obrigatória')
        if actor not in ('gerencia','equipe','sensor','simulacao'): raise ValueError('Origem inválida')
        if actor=='simulacao' and not self.demo: raise ValueError('Eventos simulados só no modo demonstração')
        if actor in ('sensor','simulacao') and action not in ('occupy','suspect','return'): raise ValueError('Sensor não confirma limpeza ou saída')
        with self.tx() as c:
            self._transition(c,tid,action,version,actor)
        return self.snapshot()
    def _transition(self,c,tid,action,version,actor):
        row=c.execute('SELECT * FROM tables WHERE id=?',(tid,)).fetchone()
        if not row: raise KeyError('Mesa não encontrada')
        m=dict(row); allowed,new=TRANSITIONS[action]
        if version!=m['version']: raise Conflict('Mesa atualizada por outro dispositivo. Tente novamente.')
        if m['state'] not in allowed: raise Conflict('Transição não permitida para o estado atual.')
        now=time.time(); dirty=m['dirty_since']; cleaning=m['clean_since']; w=cl=total=None
        if action=='depart': dirty=now
        elif action=='start': cleaning=now
        elif action=='cancel': cleaning=None
        elif action=='finish':
            w=max(0,cleaning-dirty); cl=max(0,now-cleaning); total=w+cl; dirty=cleaning=None
        c.execute('UPDATE tables SET state=?,since=?,dirty_since=?,clean_since=?,version=version+1 WHERE id=?',(new,now,dirty,cleaning,tid))
        c.execute('INSERT INTO events(table_id,zone,action,old_state,new_state,ts,actor,wait_s,clean_s,total_s) VALUES (?,?,?,?,?,?,?,?,?,?)',(tid,m['zone'],action,m['state'],new,now,actor,w,cl,total))
    def claim_next(self,zone='Todos'):
        if zone not in ('Todos','Inferior','Principal','Superior'): raise ValueError('Salão inválido')
        with self.tx() as c:
            tables=[dict(r) for r in c.execute('SELECT * FROM tables ORDER BY id')]
            settings={r['key']:int(r['value']) for r in c.execute("SELECT * FROM settings WHERE key IN ('goal','demand')")}
            _,_,priority=self.rank(tables,settings,time.time())
            target=next((m for m in priority if zone=='Todos' or m['zone']==zone),None)
            if target is None: raise Conflict('Nenhuma limpeza pendente neste salão.')
            self._transition(c,target['id'],'start',target['version'],'equipe')
        return {'claimed':target['id'],'state':self.snapshot()}
    def demo_signal(self):
        if not self.demo: raise ValueError('Disponível apenas em demonstração')
        with self.tx() as c:
            target=c.execute("SELECT * FROM tables WHERE state='occupied' ORDER BY CASE WHEN id='I-01' THEN 0 ELSE 1 END,id LIMIT 1").fetchone()
            if target is None: raise Conflict('Nenhuma mesa ocupada; reinicie o cenário.')
            self._transition(c,target['id'],'suspect',target['version'],'simulacao')
        return {'table':target['id'],'state':self.snapshot()}
    def configure(self,goal,demand):
        if type(goal) is not int or not 1<=goal<=60 or type(demand) is not int or not -1<=demand<=100: raise ValueError('Meta: 1–60 minutos; demanda: -1 (desconhecida) ou 0–100')
        with self.tx() as c: c.executemany('UPDATE settings SET value=? WHERE key=?',[(str(goal),'goal'),(str(demand),'demand')])
    @staticmethod
    def rank(tables,settings,now):
        zones={z:{s:0 for s in STATES} for z in ('Inferior','Principal','Superior')}; counts={s:0 for s in STATES}
        for m in tables: zones[m['zone']][m['state']]+=1; counts[m['state']]+=1
        for m in tables:
            m['elapsed']=max(0,now-m['since']); m['dirty_elapsed']=max(0,now-m['dirty_since']) if m['dirty_since'] is not None else 0
            if m['state']=='dirty':
                z=zones[m['zone']]; occ=(z['occupied']+z['possible'])/sum(z.values()); age=m['dirty_elapsed']/60; goal=settings['goal']; factors=[(40,min(age/(goal*2),1)),(25,occ),(10,min(m['seats']/6,1)),(5,float(age>=goal))]; demand=settings['demand'];
                if demand>=0: factors.append((20,demand/100))
                m['score']=round(sum(w*v for w,v in factors)/sum(w for w,v in factors)*100); m['urgent']=age>=goal*2; m['reason']=f'{age:.1f} min de espera · {occ:.0%} ocupação do salão · {m["seats"]} lugares'+(' · limite máximo excedido' if m['urgent'] else '')
        priority=sorted((m for m in tables if m['state']=='dirty'),key=lambda m:(not m['urgent'],-m['dirty_elapsed'] if m['urgent'] else -m['score'],-m['dirty_elapsed'],m['id']))
        return zones,counts,priority
    def snapshot(self):
        now=time.time()
        with self.tx() as c:
            tables=[dict(r) for r in c.execute('SELECT * FROM tables ORDER BY id')]; settings={r['key']:int(r['value']) for r in c.execute("SELECT * FROM settings WHERE key IN ('goal','demand')")}; events=[dict(r) for r in c.execute('SELECT * FROM events ORDER BY ts DESC,id DESC LIMIT 30')]; history=[dict(r) for r in c.execute("SELECT * FROM events WHERE action='finish' AND ts>=? ORDER BY ts",(now-86400,))]
        zones,counts,priority=self.rank(tables,settings,now)
        active=[m for m in tables if m['state'] in ('dirty','cleaning')]
        overdue=[m for m in active if m['dirty_elapsed']>=settings['goal']*60]
        critical=[m for m in active if m['dirty_elapsed']>=settings['goal']*120]
        alerts={'overdue':len(overdue),'critical':len(critical),'oldest_s':max((m['dirty_elapsed'] for m in active),default=0),'possible':counts['possible'],'blocked':counts['blocked'],'zones_no_free':[z for z,c in zones.items() if c['free']==0]}
        def metrics(rows):
            n=len(rows); avg=lambda k:round(sum(r[k] for r in rows)/n,1) if n else None
            return {'n':n,'avg_wait':avg('wait_s'),'avg_clean':avg('clean_s'),'avg_total':avg('total_s'),'p90_total':round(sorted(r['total_s'] for r in rows)[math.ceil(.9*n)-1],1) if n else None,'within':round(sum(r['total_s']<=settings['goal']*60 for r in rows)/n*100) if n else None}
        return dict(mode='demo' if self.demo else 'operacional',now=now,tables=tables,counts=counts,zones=zones,settings=settings,alerts=alerts,priority=priority,events=events,metrics=metrics(history),by_zone={z:metrics([r for r in history if r['zone']==z]) for z in zones})
    def export(self):
        with self.tx() as c: rows=c.execute('SELECT * FROM events ORDER BY id').fetchall()
        out=io.StringIO(); writer=csv.writer(out,delimiter=';'); writer.writerow(['id','mesa','salao','acao','estado_anterior','estado_novo','timestamp_unix','origem','espera_s','limpeza_s','total_s']); writer.writerows([tuple(r) for r in rows]); return '\ufeff'+out.getvalue()
