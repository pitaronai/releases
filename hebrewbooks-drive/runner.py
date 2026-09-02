import os,re,io,json,time,gzip,sqlite3,hashlib,unicodedata,threading,urllib.request
from pathlib import Path
from collections import defaultdict,Counter
from concurrent.futures import ThreadPoolExecutor,as_completed
import boto3
from botocore.config import Config
from boto3.s3.transfer import TransferConfig
from kaggle_secrets import UserSecretsClient
from google.oauth2.service_account import Credentials
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload,MediaIoBaseUpload

ROOT='0ALbapXxUo3IoUk9PVA'; WORKERS=4; BATCH=8; HOURS=11.25
SMOKE=int(os.environ.get('HB_SMOKE_LIMIT','3'))
TMP=Path('/kaggle/temp/hb2drive'); TMP.mkdir(parents=True,exist_ok=True)
PUB='https://raw.githubusercontent.com/yossi-computers/HebrewBooks-2026/main/src/HebrewBooks.Services/HebrewBooks.Services.Downloader/R2MirrorClient.cs'
def log(*x): print(time.strftime('%H:%M:%S'),*x,flush=True)
def clean(x,n=160):
    x=unicodedata.normalize('NFC',str(x or '')); x=re.sub(r'[\\/:*?"<>|\x00-\x1f]',' ',x); return ' '.join(x.split()).strip(' .')[:n].rstrip(' .')
def qesc(x): return str(x).replace('\\','\\\\').replace("'","\\'")
def sortfid(x):
    f=x['fid'] if isinstance(x,dict) else str(x); return (0,int(f)) if f.isdigit() else (1,f)

def public_cfg():
    req=urllib.request.Request(PUB,headers={'User-Agent':'HB-Kaggle/1'}); src=urllib.request.urlopen(req,timeout=60).read().decode()
    d=dict(re.findall(r'(?:private|public)\s+const\s+string\s+(\w+)\s*=\s*"([^"]+)"',src))
    need=['Endpoint','Bucket','AccessKey','SecretKey','AppPrefix','BooksPrefix']
    if any(not d.get(k) for k in need): raise RuntimeError('official R2 config parse failed')
    return d
R=public_cfg(); log('R2 config:',R['Bucket'],R['BooksPrefix'])
BC=Config(signature_version='s3v4',retries={'max_attempts':10,'mode':'adaptive'},max_pool_connections=64,s3={'addressing_style':'path'})
TC=TransferConfig(multipart_threshold=32<<20,multipart_chunksize=16<<20,max_concurrency=4,use_threads=True)
def s3new(): return boto3.client('s3',endpoint_url=R['Endpoint'],aws_access_key_id=R['AccessKey'],aws_secret_access_key=R['SecretKey'],region_name='auto',config=BC)

ci=json.loads(UserSecretsClient().get_secret('GDRIVE_CREDENTIALS'))
def dnew(): return build('drive','v3',credentials=Credentials.from_service_account_info(ci,scopes=['https://www.googleapis.com/auth/drive']),cache_discovery=False)
D=dnew(); root=D.files().get(fileId=ROOT,supportsAllDrives=True,fields='id,name,driveId').execute(); DID=root.get('driveId') or ROOT; log('Drive:',root.get('name'),DID)
def dl(q,drive=None):
    drive=drive or D; out=[]; tok=None
    while True:
        r=drive.files().list(q=q,spaces='drive',corpora='drive',driveId=DID,includeItemsFromAllDrives=True,supportsAllDrives=True,pageSize=1000,pageToken=tok,fields='nextPageToken,files(id,name,size,parents,appProperties)').execute(); out+=r.get('files',[]); tok=r.get('nextPageToken')
        if not tok:return out
def folder(name,parent):
    name=clean(name,100) or 'ללא שם'; q=f"name='{qesc(name)}' and mimeType='application/vnd.google-apps.folder' and '{parent}' in parents and trashed=false"; f=dl(q)
    return f[0]['id'] if f else D.files().create(body={'name':name,'mimeType':'application/vnd.google-apps.folder','parents':[parent]},supportsAllDrives=True,fields='id').execute()['id']
def named(parent,name):
    f=dl(f"name='{qesc(name)}' and '{parent}' in parents and trashed=false"); return f[0] if f else None
def putbytes(parent,name,data):
    f=named(parent,name); m=MediaIoBaseUpload(io.BytesIO(data),mimetype='application/json',resumable=False)
    if f:return D.files().update(fileId=f['id'],media_body=m,supportsAllDrives=True,fields='id').execute()['id']
    return D.files().create(body={'name':name,'parents':[parent]},media_body=m,supportsAllDrives=True,fields='id').execute()['id']
def putfile(parent,name,path,mime):
    f=named(parent,name); m=MediaFileUpload(str(path),mimetype=mime,resumable=True,chunksize=32<<20)
    req=D.files().update(fileId=f['id'],media_body=m,supportsAllDrives=True,fields='id') if f else D.files().create(body={'name':name,'parents':[parent]},media_body=m,supportsAllDrives=True,fields='id')
    r=None
    while r is None: _,r=req.next_chunk(num_retries=5)
    return r
BOOKS=folder('ספרים',ROOT); STATE=folder('_HB_STATE',ROOT); META=folder('_HB_METADATA',ROOT)
p=D.files().create(body={'name':'probe.tmp','parents':[STATE]},media_body=MediaIoBaseUpload(b'ok'),supportsAllDrives=True,fields='id').execute(); D.files().delete(fileId=p['id'],supportsAllDrives=True).execute(); log('Drive write probe OK')

S=s3new(); pref=R['BooksPrefix'].rstrip('/')+'/'; mf={}; n=0
for pg in S.get_paginator('list_objects_v2').paginate(Bucket=R['Bucket'],Prefix=pref,PaginationConfig={'PageSize':1000}):
    for o in pg.get('Contents',[]):
        if not o['Key'].lower().endswith('.pdf'):continue
        fid=Path(o['Key']).stem; e={'fid':fid,'key':o['Key'],'size':int(o.get('Size') or 0),'etag':str(o.get('ETag') or '').strip('"')}; old=mf.get(fid)
        if old is None or len(e['key'])<len(old['key']):mf[fid]=e
        n+=1
    if n and n%10000<1000: log('listed',n)
M=sorted(mf.values(),key=sortfid); totalb=sum(x['size'] for x in M); mh=hashlib.sha256(''.join(f"{x['key']}\t{x['size']}\t{x['etag']}\n" for x in M).encode()).hexdigest(); log('Manifest',len(M),f'{totalb/2**30:.2f} GiB')
ck=R['AppPrefix'].rstrip('/')+'/Katalog.db'; CAT=TMP/'Katalog.db'
try:S.head_object(Bucket=R['Bucket'],Key=ck)
except Exception:
    ck=next(o['Key'] for pg in S.get_paginator('list_objects_v2').paginate(Bucket=R['Bucket'],Prefix=R['AppPrefix'].rstrip('/')+'/') for o in pg.get('Contents',[]) if o['Key'].lower().endswith('/katalog.db'))
S.download_file(R['Bucket'],ck,str(CAT),Config=TC); cmd5=hashlib.md5(CAT.read_bytes()).hexdigest(); log('Catalog',ck,CAT.stat().st_size)
C=sqlite3.connect(f'file:{CAT}?mode=ro',uri=True); C.row_factory=sqlite3.Row; tabs={x[0] for x in C.execute("select name from sqlite_master where type='table'")}; cols=[x[1] for x in C.execute('pragma table_info(Katalog)')]
by=defaultdict(list)
for x in C.execute('select * from Katalog'):
    r=dict(x); fid=str(r.get('FileID') or '').strip(); typ=str(r.get('SourceType') or 'PDF').lower()
    if fid and typ=='pdf':by[fid].append(r)
sh=defaultdict(list); madaf=[]
if {'Madaf','BookMadaf'}<=tabs:
    madaf=[dict(x) for x in C.execute('select MadafID,MadafName,IsVisible from Madaf order by MadafID')]
    for x in C.execute('select bm.BookID,m.MadafID,m.MadafName,m.IsVisible from BookMadaf bm join Madaf m on m.MadafID=bm.MadafID'):
        sh[int(x['BookID'])].append({'id':int(x['MadafID']),'name':str(x['MadafName'] or '').strip(),'vis':bool(x['IsVisible'])})
C.close()
def shelves(fid):
    z={}
    for r in by.get(fid,[]):
        try: bid=int(r.get('ID'))
        except:continue
        for s in sh.get(bid,[]):
            if s['name']:z[s['id']]=s
    return list(z.values())
sc=Counter()
for fid in mf:
    for s in {x['name'] for x in shelves(fid) if x['vis']}:sc[s]+=1
def best(fid):
    rr=by.get(fid,[])
    if not rr:return {}
    return max(rr,key=lambda r:(sum(r.get(k) not in (None,'') for k in ['BookName','AuthorName','PrintPlace','PrintYear','CountPage','Description','Categories','TocJson']),len(str(r.get('Description') or ''))))
def cats(v):
    v=str(v or '').strip()
    if not v:return []
    try:
        j=json.loads(v); a=[]
        def w(x):
            if isinstance(x,dict):[w(y) for y in x.values()]
            elif isinstance(x,list):[w(y) for y in x]
            elif x not in (None,''):a.append(clean(x,100))
        w(j); return [x for x in a if x]
    except:return [clean(x,100) for x in re.split(r'\s*[|;>]\s*',v) if clean(x,100)]
def primary(fid,r):
    v=sorted({x['name'] for x in shelves(fid) if x['vis']}); ng=[x for x in v if x not in {'כל הספרים','הכל','כללי','ספרים','ראשי'}]
    if v:return min(ng or v,key=lambda x:(sc.get(x,10**9),x))
    c=cats(r.get('Categories'))
    if c:return c[0]
    f=clean(r.get('Folder'),100)
    if f:return f
    a=sorted({x['name'] for x in shelves(fid)}); return a[0] if a else 'ללא נושא'
def fn(fid,r):
    t=clean(r.get('BookName'),125) or f'ספר {fid}'; a=clean(r.get('AuthorName'),45); return clean(t+(f' — {a}' if a and a!=t else ''),175)+f' [{fid}].pdf'
def metadata(src,r):
    fid=src['fid']; rr=by.get(fid,[]); ss=sorted({x['name'] for x in shelves(fid)}); ps=primary(fid,r)
    lines=[f"שם הספר: {r.get('BookName') or ''}",f"מחבר: {r.get('AuthorName') or ''}",f"מקום דפוס: {r.get('PrintPlace') or ''}",f"שנת דפוס: {r.get('PrintYear') or ''}",f"מספר עמודים: {r.get('CountPage') or ''}",f'FileID: {fid}',f'מדף ראשי: {ps}','מדפים רשמיים: '+'; '.join(ss),f"Categories: {r.get('Categories') or ''}",f"Folder: {r.get('Folder') or ''}",f"Description: {r.get('Description') or ''}",f"R2: {src['key']}",f"ETag: {src['etag']}",'Catalog IDs: '+','.join(str(x.get('ID')) for x in rr if x.get('ID') is not None)]
    desc='\n'.join(lines)[:30000]; idx='\n'.join(lines+[f'{k}: {v}' for x in rr for k,v in x.items() if v not in (None,'')]); b=idx.encode()[:120*1024]
    while True:
        try:idx=b.decode();break
        except UnicodeDecodeError:b=b[:-1]
    return ps,desc,idx,{'hb_file_id':fid[:120],'hb_schema':'7','hb_source_size':str(src['size']),'hb_source_etag':src['etag'][:120]}
summary={'schema':7,'source_pdf_count':len(M),'source_bytes':totalb,'source_gib':round(totalb/2**30,3),'catalog_fileids':len(by),'catalog_md5':cmd5,'manifest_sha256':mh,'catalog_columns':cols,'tables':sorted(tabs),'duplicate_fileids':sum(len(v)>1 for v in by.values()),'source_without_catalog':len(set(mf)-set(by)),'catalog_without_source':len(set(by)-set(mf)),'visible_shelves':sc.most_common(),'all_madaf':madaf}
sp=TMP/'metadata-summary.json';sp.write_text(json.dumps(summary,ensure_ascii=False,indent=2)); putfile(META,'Katalog.db',CAT,'application/x-sqlite3'); putfile(META,'metadata-summary.json',sp,'application/json'); log('metadata uploaded; shelves',len(sc)); [log('shelf',a,b) for a,b in sc.most_common(20)]

sf=named(STATE,'state.json'); old=None
if sf:
    try:old=json.loads(D.files().get_media(fileId=sf['id']).execute().decode())
    except:old=None
if not isinstance(old,dict) or int(old.get('schema',old.get('v',0)) or 0)!=7: st={'schema':7,'manifest_sha256':mh,'catalog_md5':cmd5,'cursor':0,'inflight':[],'failures':{},'uploaded_files':0,'uploaded_bytes':0,'existing':0}
else:
    st=old; st.setdefault('failures',{});st.setdefault('inflight',[]);st.setdefault('uploaded_files',0);st.setdefault('uploaded_bytes',0);st.setdefault('existing',0)
    if st.get('manifest_sha256')!=mh:
        lf=str(st.get('last_fid') or ''); le=st.get('last_etag'); ix=next((i for i,x in enumerate(M) if x['fid']==lf and (not le or x['etag']==le)),None); st['cursor']=ix+1 if ix is not None else 0; st['manifest_sha256']=mh
    st['catalog_md5']=cmd5
def sav():
    global sf
    st['updated_at']=time.time(); data=json.dumps(st,ensure_ascii=False,separators=(',',':')).encode(); m=MediaIoBaseUpload(io.BytesIO(data),mimetype='application/json')
    if sf:D.files().update(fileId=sf['id'],media_body=m,supportsAllDrives=True,fields='id').execute()
    else:sf=D.files().create(body={'name':'state.json','parents':[STATE]},media_body=m,supportsAllDrives=True,fields='id,name').execute()
sav(); TLS=threading.local();fc={};lock=threading.Lock()
def clients():
    if not hasattr(TLS,'s'):TLS.s=s3new()
    if not hasattr(TLS,'d'):TLS.d=dnew()
    return TLS.s,TLS.d
def subfolder(x):
    x=clean(x,100) or 'ללא נושא'
    with lock:
        if x not in fc:fc[x]=folder(x,BOOKS)
        return fc[x]
def existing(fid,name,parent,d):
    z=dl(f"appProperties has {{ key='hb_file_id' and value='{qesc(fid)}' }} and trashed=false",d)
    if z:return z[0]
    z=dl(f"name='{qesc(name)}' and '{parent}' in parents and trashed=false",d);return z[0] if z else None
def one(src,r,recon=False):
    fid=src['fid']; ps,desc,idx,props=metadata(src,r); par=subfolder(ps); name=fn(fid,r); s,d=clients()
    if recon:
        e=existing(fid,name,par,d)
        if e:d.files().update(fileId=e['id'],body={'name':name,'description':desc,'contentHints':{'indexableText':idx},'appProperties':props},supportsAllDrives=True).execute();return ('existing',int(e.get('size') or src['size']),ps,name)
    p=TMP/f'{fid}-{threading.get_ident()}.pdf'
    try:
        for a in range(3):
            try:
                p.unlink(missing_ok=True);s.download_file(R['Bucket'],src['key'],str(p),Config=TC)
                if p.stat().st_size!=src['size']:raise IOError('size mismatch')
                break
            except:
                if a==2:raise
                time.sleep(2**(a+1))
        m=MediaFileUpload(str(p),mimetype='application/pdf',resumable=True,chunksize=32<<20);req=d.files().create(body={'name':name,'parents':[par],'description':desc,'contentHints':{'indexableText':idx},'appProperties':props},media_body=m,supportsAllDrives=True,fields='id,size');o=None
        while o is None:_,o=req.next_chunk(num_retries=6)
        if o.get('size') and int(o['size'])!=src['size']:raise IOError('Drive size mismatch')
        return ('uploaded',src['size'],ps,name)
    finally:p.unlink(missing_ok=True)

start=time.monotonic();deadline=start+HOURS*3600;cur=max(0,min(int(st.get('cursor',0)),len(M)));end=min(len(M),cur+SMOKE) if SMOKE else len(M);recon=set(map(str,st.get('inflight',[])));log('resume',cur,'/',len(M),'end',end if SMOKE else 'FULL')
while cur<end and time.monotonic()<deadline:
    be=min(end,cur+BATCH);batch=M[cur:be];st['inflight']=[x['fid'] for x in batch];sav();res={}
    with ThreadPoolExecutor(max_workers=min(WORKERS,len(batch))) as ex:
        fs={ex.submit(one,x,best(x['fid']),x['fid'] in recon):x['fid'] for x in batch}
        for f in as_completed(fs):
            fid=fs[f]
            try:r=f.result();res[fid]=r;log('OK',r[0],fid,'->',r[2],r[3])
            except Exception as e:res[fid]=('failed',0,'','');st['failures'].setdefault(fid,{'attempts':0});st['failures'][fid]['attempts']+=1;st['failures'][fid]['error']=repr(e)[-1500:];log('FAILED',fid,repr(e))
    for x in batch:
        fid=x['fid'];r=res[fid]
        if r[0]=='uploaded':st['uploaded_files']+=1;st['uploaded_bytes']+=r[1];st['failures'].pop(fid,None)
        elif r[0]=='existing':st['existing']+=1;st['failures'].pop(fid,None)
    cur=be;st['cursor']=cur;st['inflight']=[];st['last_fid']=batch[-1]['fid'];st['last_etag']=batch[-1]['etag'];sav();log('PROGRESS',cur,'/',len(M),f"{cur*100/len(M):.4f}%",'uploaded',st['uploaded_files'],f"{st['uploaded_bytes']/2**30:.3f}GiB",'failures',len(st['failures']))
st['cursor']=cur;st['inflight']=[];sav();putbytes(STATE,'last-run-report.json',json.dumps({'cursor':cur,'total':len(M),'uploaded_files':st['uploaded_files'],'uploaded_bytes':st['uploaded_bytes'],'existing':st['existing'],'failures':st['failures'],'smoke_limit':SMOKE},ensure_ascii=False,indent=2).encode());log('STOP CLEAN',cur,'/',len(M),'smoke',SMOKE)
