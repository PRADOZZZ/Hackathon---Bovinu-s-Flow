"""Optional experimental single-ROI person detector; never confirms departure/cleanliness."""
import argparse, json, os, time, urllib.request
class Presence:
    def __init__(self,absence=10,presence=2): self.absence=absence; self.presence=presence; self.last=None; self.since=None
    def update(self,detected,now):
        if detected!=self.last: self.last=detected; self.since=now
        return 'present' if detected and now-self.since>=self.presence else 'absent' if not detected and now-self.since>=self.absence else None

def main():
    p=argparse.ArgumentParser();p.add_argument('--source',default='0');p.add_argument('--table',default='P-01');p.add_argument('--roi',nargs=4,type=int,metavar=('X','Y','W','H'),required=True);p.add_argument('--url',default='http://127.0.0.1:8000');p.add_argument('--absence',type=float,default=10);p.add_argument('--preview',action='store_true');args=p.parse_args()
    import cv2
    x,y,w,h=args.roi
    if min(x,y)<0 or min(w,h)<=0 or args.absence<2: p.error('ROI inválida ou ausência inferior a 2 segundos')
    cap=cv2.VideoCapture(int(args.source) if args.source.isdecimal() else args.source)
    if not cap.isOpened(): raise SystemExit('Não foi possível abrir a fonte de vídeo.')
    hog=cv2.HOGDescriptor();hog.setSVMDetector(cv2.HOGDescriptor_getDefaultPeopleDetector());presence=Presence(args.absence)
    token=os.environ.get('BOVIFLOW_TOKEN'); headers={'Content-Type':'application/json'}
    if token: headers['Authorization']='Bearer '+token
    def req(path,body=None):
        r=urllib.request.Request(args.url.rstrip('/')+'/api/'+path,data=json.dumps(body).encode() if body is not None else None,headers=headers)
        with urllib.request.urlopen(r,timeout=3) as response:return json.load(response)
    last_check=0
    print('Vision Lab experimental. Ctrl+C para sair. Não grava imagens.')
    try:
        while True:
            ok,frame=cap.read()
            if not ok: print('Fonte encerrada ou indisponível; nenhum estado alterado.');break
            if y+h>frame.shape[0] or x+w>frame.shape[1]: raise SystemExit(f'ROI fora do quadro {frame.shape[1]}x{frame.shape[0]}')
            now=time.monotonic(); crop=frame[y:y+h,x:x+w]; boxes=[]
            if crop.shape[0]>=128 and crop.shape[1]>=64: boxes,_=hog.detectMultiScale(crop,winStride=(8,8),padding=(8,8),scale=1.08)
            status=presence.update(len(boxes)>0,now)
            if status and now-last_check>=2:
                last_check=now
                try:
                    m=next(t for t in req('state')['tables'] if t['id']==args.table)
                    act={('present','free'):'occupy',('present','possible'):'return',('absent','occupied'):'suspect'}.get((status,m['state']))
                    if act: req('action',dict(id=m['id'],action=act,version=m['version'],actor='sensor')); print(m['id'],act,flush=True)
                except Exception as e: print('Sem evento:',e,flush=True)
            if args.preview:
                cv2.rectangle(frame,(x,y),(x+w,y+h),(0,180,255),2)
                for a,b,c,d in boxes:cv2.rectangle(frame,(x+a,y+b),(x+a+c,y+b+d),(0,200,0),2)
                cv2.imshow('BoviVision - Q encerra',frame)
                if cv2.waitKey(1)&255==ord('q'):break
            time.sleep(.12)
    except KeyboardInterrupt: pass
    finally:
        cap.release()
        if args.preview: cv2.destroyAllWindows()
if __name__=='__main__':main()
