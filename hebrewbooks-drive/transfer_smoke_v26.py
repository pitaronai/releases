import os,re,io,json,time,csv,sqlite3,hashlib,unicodedata,urllib.request
from pathlib import Path
from collections import defaultdict
import boto3
from botocore.config import Config
from boto3.s3.transfer import TransferConfig
from kaggle_secrets import UserSecretsClient
from google.oauth2.service_account import Credentials
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload,MediaIoBaseUpload
from googleapiclient.errors import HttpError

ROOT='0ALbapXxUo3IoUk9PVA'
SMOKE_NAME='_HB_SMOKE_V26'
TMP=Path('/kaggle/temp/hb_smoke_v26');TMP.mkdir(parents=True,exist_ok=True)
PUB='https://raw.githubusercontent.com/yossi-computers/HebrewBooks-2026/main/src/HebrewBooks.Services/HebrewBooks.Services.Downloader/R2MirrorClient.cs'
CLASSIFIER='https://raw.githubusercontent.com/pitaronai/releases/main/hebrewbooks-drive/integrated_final_simulation.py'

def log(*x):print(time.strftime('%H:%M:%S'),*x,flush=True)
def clean(x,n=160):
    x=unicodedata.normalize('NFC',str(x or ''));x=re.sub(r'[\\/:*?"<>|\x00-\x1f]',' ',x);return ' '.join(x.split()).strip(' .')[:n].rstrip(' .')
def qesc(x):return str(x).replace('\\','\\\\').replace("'","\\'")

def public_cfg():
    src=urllib.request.urlopen(urllib.request.Request(PUB,headers={'User-Agent':'HB-SmokeV26/1'}),timeout=60).read().decode()
    d=dict(re.findall(r'(?:private|public)\s+const\s+string\s+(\w+)\s*=\s*"([^"]+)"',src))
    for k in ['Endpoint','Bucket','AccessKey','SecretKey','AppPrefix','BooksPrefix']:
        if not d.get(k):raise RuntimeError('R2 public config missing '+k)
    return d

def drive_client():
    ci=json.loads(UserSecretsClient().get_secret('GDRIVE_CREDENTIALS'))
    cr=Credentials.from_service_account_info(ci,scopes=['https://www.googleapis.com/auth/drive'])
    return build('drive','v3',credentials=cr,cache_discovery=False)

D=drive_client();root=D.files().get(fileId=ROOT,supportsAllDrives=True,fields='id,name,driveId').execute();DID=root.get('driveId') or ROOT
log('DRIVE',root.get('name'),DID)

def dl(q):
    out=[];tok=None
    while True:
        r=D.files().list(q=q,spaces='drive',corpora='drive',driveId=DID,includeItemsFromAllDrives=True,supportsAllDrives=True,pageSize=1000,pageToken=tok,fields='nextPageToken,files(id,name,mimeType,size,parents,appProperties,createdTime,modifiedTime)').execute()
        out+=r.get('files',[]);tok=r.get('nextPageToken')
        if not tok:return out

def child(parent,name,mime='application/vnd.google-apps.folder'):
    z=dl(f"name='{qesc(name)}' and '{parent}' in parents and trashed=false")
    if z:return z[0]
    body={'name':name,'parents':[parent]}
    if mime:body['mimeType']=mime
    return D.files().create(body=body,supportsAllDrives=True,fields='id,name,mimeType').execute()

def delete_id(fid):
    D.files().delete(fileId=fid,supportsAllDrives=True).execute()

def root_snapshot(label):
    arr=dl(f"'{ROOT}' in parents and trashed=false")
    out=[{'id':x['id'],'name':x.get('name'),'mimeType':x.get('mimeType'),'size':x.get('size'),'appProperties':x.get('appProperties',{})} for x in arr]
    log(label,'ROOT_CHILDREN',len(out),json.dumps(out,ensure_ascii=False))
    return out

before=root_snapshot('BEFORE')
# Remove stale smoke folder from a previous interrupted smoke only.
for x in before:
    if x['name']==SMOKE_NAME:
        log('REMOVE_STALE_SMOKE',x['id']);delete_id(x['id'])

# Run the exact integrated classifier used in v25. It downloads Katalog.db and writes integrated_final_assignments.csv.
log('RUN_CLASSIFIER')
code=urllib.request.urlopen(CLASSIFIER,timeout=60).read().decode('utf-8')
exec(compile(code,CLASSIFIER,'exec'),globals(),globals())
assign_path=Path('/kaggle/working/integrated_final_assignments.csv')
cat_path=Path('/kaggle/working/Katalog.db')
if not assign_path.exists() or not cat_path.exists():raise RuntimeError('classifier outputs missing')
assign={}
with assign_path.open(encoding='utf-8-sig') as f:
    for r in csv.DictReader(f):assign[str(r['FileID'])]=r
log('ASSIGNMENTS',len(assign))

R=public_cfg();S=boto3.client('s3',endpoint_url=R['Endpoint'],aws_access_key_id=R['AccessKey'],aws_secret_access_key=R['SecretKey'],region_name='auto',config=Config(signature_version='s3v4',retries={'max_attempts':8,'mode':'adaptive'},s3={'addressing_style':'path'}))
TC=TransferConfig(multipart_threshold=32<<20,multipart_chunksize=16<<20,max_concurrency=3,use_threads=True)
pref=R['BooksPrefix'].rstrip('/')+'/'
manifest={}
for pg in S.get_paginator('list_objects_v2').paginate(Bucket=R['Bucket'],Prefix=pref,PaginationConfig={'PageSize':1000}):
    for o in pg.get('Contents',[]):
        if not o['Key'].lower().endswith('.pdf'):continue
        fid=Path(o['Key']).stem
        if fid not in assign:continue
        e={'fid':fid,'key':o['Key'],'size':int(o.get('Size') or 0),'etag':str(o.get('ETag') or '').strip('"')}
        old=manifest.get(fid)
        if old is None or len(e['key'])<len(old['key']):manifest[fid]=e
log('MANIFEST_MATCH',len(manifest))

# Pick one small representative from the largest useful topics + one unclassified.
want=['שו"ת','הלכה','תלמוד וש"ס','תורה ומפרשים','חסידות','מועדים','משנה','קבלה','כתבי עת וירחונים','תפילה וסידורים','לא מסווג']
chosen=[]
for top in want:
    cand=[e for fid,e in manifest.items() if assign[fid]['Top']==top and e['size']>0]
    if cand:chosen.append(min(cand,key=lambda x:x['size']))
# de-dupe by FileID
seen=set();chosen=[x for x in chosen if not (x['fid'] in seen or seen.add(x['fid']))]
if len(chosen)<8:raise RuntimeError('not enough representative smoke files')
log('CHOSEN',json.dumps([{'fid':x['fid'],'size':x['size'],'top':assign[x['fid']]['Top'],'sub':assign[x['fid']]['Sub']} for x in chosen],ensure_ascii=False))

C=sqlite3.connect(f'file:{cat_path}?mode=ro',uri=True);C.row_factory=sqlite3.Row
by=defaultdict(list)
for r in C.execute("select * from Katalog where lower(SourceType)='pdf'"):
    d=dict(r);fid=str(d.get('FileID') or '').strip()
    if fid:by[fid].append(d)
def best(fid):
    rr=by.get(fid,[])
    if not rr:return {}
    return max(rr,key=lambda r:(sum(r.get(k) not in (None,'') for k in ['BookName','AuthorName','PrintPlace','PrintYear','CountPage','Description','Categories','TocJson']),len(str(r.get('Description') or ''))))
def fname(fid,r):
    t=clean(r.get('BookName'),125) or f'ספר {fid}';a=clean(r.get('AuthorName'),45)
    return clean(t+(f' — {a}' if a and a!=t else ''),175)+f' [{fid}].pdf'
def meta(fid,e,r,asgn):
    rr=by.get(fid,[])
    lines=[f"שם הספר: {r.get('BookName') or ''}",f"מחבר: {r.get('AuthorName') or ''}",f"מקום דפוס: {r.get('PrintPlace') or ''}",f"שנת דפוס: {r.get('PrintYear') or ''}",f"מספר עמודים: {r.get('CountPage') or ''}",f"FileID: {fid}",f"קטגוריה סופית: {asgn['Top']} / {asgn['Sub']}",f"מקור סיווג: {asgn['Source']}",f"Categories: {r.get('Categories') or ''}",f"Description: {r.get('Description') or ''}",f"R2: {e['key']}",f"ETag: {e['etag']}",'Catalog IDs: '+','.join(str(x.get('ID')) for x in rr if x.get('ID') is not None)]
    desc='\n'.join(lines)[:30000]
    idx='\n'.join(lines+[f'{k}: {v}' for x in rr for k,v in x.items() if v not in (None,'')])
    b=idx.encode('utf-8')[:120*1024]
    while True:
        try:idx=b.decode('utf-8');break
        except UnicodeDecodeError:b=b[:-1]
    props={'hb_file_id':fid[:120],'hb_schema':'26','hb_source_size':str(e['size']),'hb_source_etag':e['etag'][:120],'hb_class_source':asgn['Source'][:120],'hb_smoke':'true'}
    return desc,idx,props

smoke=child(ROOT,SMOKE_NAME);smoke_id=smoke['id'];log('SMOKE_FOLDER',smoke_id)
state=child(smoke_id,'_HB_STATE');state_id=state['id']
state_body={'schema':26,'phase':'smoke','created_at':time.time(),'selected_fids':[x['fid'] for x in chosen],'cursor':0}
sdata=json.dumps(state_body,ensure_ascii=False).encode()
sf=D.files().create(body={'name':'state.json','parents':[state_id],'appProperties':{'hb_smoke':'true'}},media_body=MediaIoBaseUpload(io.BytesIO(sdata),mimetype='application/json',resumable=False),supportsAllDrives=True,fields='id,name,size').execute()
readback=json.loads(D.files().get_media(fileId=sf['id']).execute().decode('utf-8'))
if readback.get('schema')!=26 or readback.get('selected_fids')!=state_body['selected_fids']:raise RuntimeError('state readback mismatch')
log('STATE_READBACK_OK',sf['id'])

folder_cache={}
def path_folder(top,sub):
    if top not in folder_cache:folder_cache[top]=child(smoke_id,top)['id']
    k=(top,sub)
    if k not in folder_cache:folder_cache[k]=child(folder_cache[top],sub)['id']
    return folder_cache[k]

uploaded=[]
for pos,e in enumerate(chosen,1):
    fid=e['fid'];a=assign[fid];r=best(fid);top=a['Top'];sub=a['Sub'];par=path_folder(top,sub)
    p=TMP/f'{fid}.pdf';S.download_file(R['Bucket'],e['key'],str(p),Config=TC)
    if p.stat().st_size!=e['size']:raise RuntimeError(f'size mismatch {fid}')
    name=fname(fid,r);desc,idx,props=meta(fid,e,r,a)
    media=MediaFileUpload(str(p),mimetype='application/pdf',resumable=True,chunksize=8<<20)
    req=D.files().create(body={'name':name,'parents':[par],'description':desc,'appProperties':props,'contentHints':{'indexableText':idx}},media_body=media,supportsAllDrives=True,fields='id,name,size,description,appProperties,parents')
    resp=None
    while resp is None:_,resp=req.next_chunk(num_retries=5)
    got=D.files().get(fileId=resp['id'],supportsAllDrives=True,fields='id,name,size,description,appProperties,parents').execute()
    if got['name']!=name or int(got.get('size') or 0)!=e['size'] or got.get('appProperties',{}).get('hb_file_id')!=fid:raise RuntimeError(f'drive verify failed {fid}')
    uploaded.append({'fid':fid,'id':got['id'],'name':got['name'],'top':top,'sub':sub,'size':e['size']})
    state_body['cursor']=pos;state_body['last_fid']=fid
    D.files().update(fileId=sf['id'],media_body=MediaIoBaseUpload(io.BytesIO(json.dumps(state_body,ensure_ascii=False).encode()),mimetype='application/json',resumable=False),supportsAllDrives=True,fields='id').execute()
    p.unlink(missing_ok=True);log('UPLOADED',pos,len(chosen),fid,top,'/',sub,name)

# Verify all expected files are present under the smoke tree by their appProperty.
verified=[]
for u in uploaded:
    z=dl(f"appProperties has {{ key='hb_file_id' and value='{qesc(u['fid'])}' }} and appProperties has {{ key='hb_smoke' and value='true' }} and trashed=false")
    if not z:raise RuntimeError('lookup verify missing '+u['fid'])
    verified.append(u['fid'])
log('LOOKUP_VERIFY_OK',len(verified))

# Test rename/update on one file and restore it.
u=uploaded[0];orig=u['name'];tmpname=clean(orig[:-4]+' — בדיקת שינוי.pdf',190)
D.files().update(fileId=u['id'],body={'name':tmpname},supportsAllDrives=True,fields='id,name').execute()
D.files().update(fileId=u['id'],body={'name':orig},supportsAllDrives=True,fields='id,name').execute()
if D.files().get(fileId=u['id'],supportsAllDrives=True,fields='name').execute()['name']!=orig:raise RuntimeError('rename restore failed')
log('RENAME_UPDATE_OK',u['fid'])

# Deleting the non-empty smoke folder is the critical destructive-operation probe.
try:
    delete_id(smoke_id);log('DELETE_SMOKE_OK',smoke_id)
except HttpError as e:
    log('DELETE_SMOKE_FAILED',getattr(e,'status_code',None),str(e));raise
# Confirm it is gone.
try:
    D.files().get(fileId=smoke_id,supportsAllDrives=True,fields='id').execute()
    raise RuntimeError('smoke folder still exists after delete')
except HttpError as e:
    if getattr(e,'status_code',None) not in (404,410):raise
log('DELETE_VERIFY_OK')
after=root_snapshot('AFTER')
report={'smoke_ok':True,'delete_ok':True,'drive_name':root.get('name'),'root_before':before,'root_after':after,'uploaded':uploaded,'state_ok':True,'rename_ok':True,'assignment_count':len(assign)}
Path('/kaggle/working/transfer_smoke_v26.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
print('SMOKE_OK',json.dumps({'uploaded':len(uploaded),'delete_ok':True,'state_ok':True,'rename_ok':True},ensure_ascii=False))
print('ROOT_BEFORE',json.dumps(before,ensure_ascii=False))
print('ROOT_AFTER',json.dumps(after,ensure_ascii=False))
print('DONE smoke v26; test folder deleted; old library untouched')
C.close()
