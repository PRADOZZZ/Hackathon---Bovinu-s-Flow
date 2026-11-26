#!/usr/bin/env python3
"""BoviFlow local prototype. No third-party packages required for core."""
import argparse, json, os, mimetypes, hmac
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse
from core import Store, Conflict
from simulator import simulate, benchmark
ROOT=Path(__file__).resolve().parent
class Server(ThreadingHTTPServer):
    daemon_threads=True
    def __init__(self,addr,store,token=None): self.store=store; self.token=token; super().__init__(addr,Handler)
class Handler(BaseHTTPRequestHandler):
    def send(self,status,data,ctype='application/json; charset=utf-8',headers=None):
        if not isinstance(data,bytes): data=json.dumps(data,ensure_ascii=False,allow_nan=False).encode() if ctype.startswith('application/json') else data.encode()
        self.send_response(status); self.send_header('Content-Type',ctype); self.send_header('Content-Length',str(len(data))); self.send_header('Cache-Control','no-store'); self.send_header('X-Content-Type-Options','nosniff'); self.send_header('Referrer-Policy','no-referrer'); self.send_header('Content-Security-Policy',"default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data:; connect-src 'self'; frame-ancestors 'none'")
        for k,v in (headers or {}).items(): self.send_header(k,v)
        self.end_headers(); self.wfile.write(data)
    def allowed(self):
        token=self.server.token
        if token and not hmac.compare_digest(self.headers.get('Authorization',''), 'Bearer '+token): self.send(401,{'error':'Código de acesso necessário.'}); return False
        return True
    def do_GET(self):
        p=urlparse(self.path).path
        try:
            if p.startswith('/api/'):
                if not self.allowed(): return
                if p=='/api/state': return self.send(200,self.server.store.snapshot())
                if p=='/api/export': return self.send(200,self.server.store.export(),'text/csv; charset=utf-8',{'Content-Disposition':'attachment; filename="boviflow-eventos.csv"'})
                return self.send(404,{'error':'Rota não encontrada'})
            files={'/':'index.html','/staff':'index.html','/static/app.js':'app.js','/static/style.css':'style.css','/static/plant.png':'plant.png','/static/logo.svg':'logo.svg'}
            if p not in files: return self.send(404,{'error':'Página não encontrada'})
            f=ROOT/'static'/files[p]; return self.send(200,f.read_bytes(),mimetypes.guess_type(str(f))[0] or 'application/octet-stream')
        except (BrokenPipeError,ConnectionResetError): pass
        except Exception as e: print('GET:',repr(e)); self.send(500,{'error':'Falha interna'})
    def do_POST(self):
        if not self.allowed(): return
        # Same-origin JSON only; no permissive CORS.
        if self.headers.get('Origin') and urlparse(self.headers['Origin']).netloc!=self.headers.get('Host'): return self.send(403,{'error':'Origem não permitida'})
        try:
            if self.headers.get_content_type()!='application/json': return self.send(415,{'error':'Envie JSON'})
            n=int(self.headers.get('Content-Length','0'))
            if not 0<n<=16384: return self.send(400,{'error':'Tamanho inválido'})
            b=json.loads(self.rfile.read(n)); p=urlparse(self.path).path; s=self.server.store
            if not isinstance(b,dict): raise ValueError('Objeto JSON obrigatório')
            if p=='/api/action': return self.send(200,s.action(b.get('id'),b.get('action'),b.get('version'),b.get('actor','equipe')))
            if p=='/api/claim': return self.send(200,s.claim_next(b.get('zone','Todos')))
            if p=='/api/demo-signal': return self.send(200,s.demo_signal())
            if p=='/api/benchmark': return self.send(200,benchmark(b))
            if p=='/api/simulate': return self.send(200,simulate(b))
            if p=='/api/settings': s.configure(b.get('goal'),b.get('demand')); return self.send(200,s.snapshot())
            if p=='/api/reset': s.reset(); return self.send(200,s.snapshot())
            return self.send(404,{'error':'Rota não encontrada'})
        except Conflict as e: self.send(409,{'error':str(e)})
        except KeyError as e: self.send(404,{'error':str(e)})
        except (ValueError,TypeError,OverflowError) as e: self.send(400,{'error':str(e)})
        except (BrokenPipeError,ConnectionResetError): pass
        except Exception as e: print('POST:',repr(e)); self.send(500,{'error':'Falha interna'})
def main():
    p=argparse.ArgumentParser(); p.add_argument('--host',default='127.0.0.1'); p.add_argument('--port',type=int,default=8000); p.add_argument('--operacional',action='store_true'); p.add_argument('--db'); args=p.parse_args(); token=os.environ.get('BOVIFLOW_TOKEN');
    if (args.operacional or args.host not in ('127.0.0.1','localhost','::1')) and not token: p.error('Defina BOVIFLOW_TOKEN para modo operacional ou acesso pela rede.')
    path=args.db or ROOT/'data'/('operacional.db' if args.operacional else 'demo.db'); server=Server((args.host,args.port),Store(path,not args.operacional),token); print(f'BoviFlow | http://localhost:{args.port} | {"OPERACIONAL" if args.operacional else "DEMONSTRAÇÃO"}',flush=True)
    try: server.serve_forever()
    except KeyboardInterrupt: pass
    finally: server.server_close()
if __name__=='__main__': main()
