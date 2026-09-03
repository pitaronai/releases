import re,io,json,time,csv,sqlite3,unicodedata,urllib.request
from pathlib import Path
from collections import defaultdict
import boto3
from botocore.config import Config
from boto3.s3.transfer import TransferConfig
from kaggle_secrets import UserSecretsClient
from google.oauth2.service_account import Credentials
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload,MediaIoBaseUpload

ROOT='0ALbapXxUo3IoUk9PVA'; TEST='_HB_SMOKE_V27'; TMP=Path('/kaggle/temp/hb_smoke_v27');TMP.mkdir(parents=True,exist_ok=True)
PUB='https://raw.githubusercontent.com/yossi-computers/HebrewBooks-2026/main/src/HebrewBooks.Services/HebrewBooks.Services.Downloader/R2MirrorClient.cs'
CLASSIFIER='https://raw.githubusercontent.com/pitaronai/releases/main/hebrewbooks-drive/integrated_final_simulation.py'
def log(*x):print(time.strftime('%H:%M:%S'),*x,flush=True)
def clean(x,n=160):
 x=unicodedata.normalize('NFC',str(x or ''));x=re.sub(r'[\\/:*?"<>|\x00-\x1f]',' ',x);return ' '.join(x.split()).strip(' .')[:n].rstrip(' .')
def qesc(x):return str(x).replace('\\','\\\\').replace("'","\\'")
ci=json.loads(UserSecretsClient().get_secret('GDRIVE_CREDENTIALS'));cr=Credentials.from_service_account_info(ci,scopes=['https://www.googleapis.com/auth/drive']);D=build('drive','v3',credentials=cr,cache_discovery=False)
root=D.files().get(fileId=ROOT,supportsAllDrives=True,fields='id,name,driveId').execute();DID=root.get('driveId') or ROOT;log('DRIVE',root['name'],DID)
def dl(q):
 out=[];tok=None
 while True:
  z=D.files().list(q=q,spaces='drive',corpora='drive',driveId=DID,includeItemsFromAllDrives=True,supportsAllDrives=True,pageSize=1000,pageToken=tok,fields='nextPageToken,files(id,name,mimeType,size,parents,appProperties)').execute();out+=z.get('files',[]);tok=z.get('nextPageToken')
  if not tok:return out
def ensure_folder(parent,name):
 z=dl(f"name='{qesc(name)}' and mimeType='application/vnd.google-apps.folder' and '{parent}' in parents and trashed=false")
 return z[0] if z else D.files().create(body={'name':name,'mimeType':'application/vnd.google-apps.folder','parents':[parent]},supportsAllDrives=True,fields='id,name,mimeType').execute()
before=dl(f"'{ROOT}' in parents and trashed=false");print('ROOT_BEFORE',json.dumps([{'id':x['id'],'name':x['name'],'mimeType':x['mimeType']} for x in before],ensure_ascii=False))
existing=[x for x in before if x['name']==TEST]
if existing:raise RuntimeError('stale smoke folder exists; refusing to overwrite: '+existing[0]['id'])
log('RUN CLASSIFIER')
code=urllib.request.urlopen(CLASSIFIER,timeout=60).read().decode();exec(compile(code,CLASSIFIER,'exec'),globals(),globals())
A={}
with open('/kaggle/working/integrated_final_assignments.csv',encoding='utf-8-sig') as f:
 for r in csv.DictReader(f):A[str(r['FileID'])]=r
src=urllib.request.urlopen(urllib.request.Request(PUB,headers={'User-Agent':'HB-V27/1'}),timeout=60).read().decode();R=dict(re.findall(r'(?:private|public)\s+const\s+string\s+(\w+)\s*=\s*"([^"]+)"',src))
S=boto3.client('s3',endpoint_url=R['Endpoint'],aws_access_key_id=R['AccessKey'],aws_secret_access_key=R['SecretKey'],region_name='auto',config=Config(signature_version='s3v4',retries={'max_attempts':8,'mode':'adaptive'},s3={'addressing_style':'path'}));TC=TransferConfig(multipart_threshold=32<<20,multipart_chunksize=16<<20,max_concurrency=3,use_threads=True)
manifest={};pref=R['BooksPrefix'].rstrip('/')+'/'
for pg in S.get_paginator('list_objects_v2').paginate(Bucket=R['Bucket'],Prefix=pref):
 for o in pg.get('Contents',[]):
  if not o['Key'].lower().endswith('.pdf'):continue
  fid=Path(o['Key']).stem
  if fid in A:
   e={'fid':fid,'key':o['Key'],'size':int(o.get('Size') or 0),'etag':str(o.get('ETag') or '').strip('"')};old=manifest.get(fid)
   if old is None or len(e['key'])<len(old['key']):manifest[fid]=e
want=['שו"ת','הלכה','תלמוד וש"ס','תורה ומפרשים','חסידות','מועדים','משנה','קבלה','כתבי עת וירחונים','לא מסווג'];chosen=[]
for t in want:
 c=[e for fid,e in manifest.items() if A[fid]['Top']==t and 0<e['size']<8*1024*1024]
 if c:chosen.append(min(c,key=lambda e:e['size']))
if len(chosen)<8:raise RuntimeError('not enough small smoke candidates')
C=sqlite3.connect('file:/kaggle/working/Katalog.db?mode=ro',uri=True);C.row_factory=sqlite3.Row;by=defaultdict(list)
for r in C.execute("select * from Katalog where lower(SourceType)='pdf'"):
 d=dict(r);fid=str(d.get('FileID') or '').strip();by[fid].append(d)
def best(fid):
 rr=by.get(fid,[]);return max(rr,key=lambda r:(sum(r.get(k) not in (None,'') for k in ['BookName','AuthorName','PrintPlace','PrintYear','CountPage','Description','Categories']),len(str(r.get('Description') or '')))) if rr else {}
def fname(fid,r):
 t=clean(r.get('BookName'),125) or f'ספר {fid}';a=clean(r.get('AuthorName'),45);return clean(t+(f' — {a}' if a and a!=t else ''),175)+f' [{fid}].pdf'
sm=ensure_folder(ROOT,TEST);state=ensure_folder(sm['id'],'_HB_STATE');state_body={'schema':27,'cursor':0,'selected':[x['fid'] for x in chosen]};sf=D.files().create(body={'name':'state.json','parents':[state['id']],'appProperties':{'hb_smoke':'true'}},media_body=MediaIoBaseUpload(io.BytesIO(json.dumps(state_body,ensure_ascii=False).encode()),mimetype='application/json'),supportsAllDrives=True,fields='id').execute();rb=json.loads(D.files().get_media(fileId=sf['id']).execute().decode());assert rb['schema']==27
cache={};uploaded=[]
for pos,e in enumerate(chosen,1):
 fid=e['fid'];a=A[fid];r=best(fid);top=a['Top'];sub=a['Sub']
 if top not in cache:cache[top]=ensure_folder(sm['id'],top)['id']
 if (top,sub) not in cache:cache[(top,sub)]=ensure_folder(cache[top],sub)['id']
 p=TMP/f'{fid}.pdf';S.download_file(R['Bucket'],e['key'],str(p),Config=TC);assert p.stat().st_size==e['size']
 name=fname(fid,r);lines=[f"שם הספר: {r.get('BookName') or ''}",f"מחבר: {r.get('AuthorName') or ''}",f"FileID: {fid}",f"קטגוריה סופית: {top} / {sub}",f"מקור סיווג: {a['Source']}",f"Categories: {r.get('Categories') or ''}",f"Description: {r.get('Description') or ''}",f"R2: {e['key']}",f"ETag: {e['etag']}"];desc='\n'.join(lines)[:30000];idx=desc[:100000]
 media=MediaFileUpload(str(p),mimetype='application/pdf',resumable=True,chunksize=8<<20);req=D.files().create(body={'name':name,'parents':[cache[(top,sub)]],'description':desc,'appProperties':{'hb_file_id':fid,'hb_schema':'27','hb_smoke':'true','hb_class_source':a['Source']},'contentHints':{'indexableText':idx}},media_body=media,supportsAllDrives=True,fields='id,name,size,appProperties');resp=None
 while resp is None:_,resp=req.next_chunk(num_retries=5)
 got=D.files().get(fileId=resp['id'],supportsAllDrives=True,fields='id,name,size,appProperties').execute();assert got['name']==name and int(got['size'])==e['size'] and got['appProperties']['hb_file_id']==fid
 uploaded.append({'fid':fid,'id':got['id'],'name':name,'top':top,'sub':sub,'size':e['size']});state_body['cursor']=pos;state_body['last_fid']=fid;D.files().update(fileId=sf['id'],media_body=MediaIoBaseUpload(io.BytesIO(json.dumps(state_body,ensure_ascii=False).encode()),mimetype='application/json'),supportsAllDrives=True,fields='id').execute();p.unlink(missing_ok=True);log('UPLOADED',pos,fid,top,sub)
# verify query, update and restore first filename
for u in uploaded:
 z=dl(f"appProperties has {{ key='hb_file_id' and value='{qesc(u['fid'])}' }} and appProperties has {{ key='hb_smoke' and value='true' }} and trashed=false");assert z
u=uploaded[0];tmp=clean(u['name'][:-4]+' — בדיקת שינוי.pdf',190);D.files().update(fileId=u['id'],body={'name':tmp},supportsAllDrives=True,fields='id').execute();D.files().update(fileId=u['id'],body={'name':u['name']},supportsAllDrives=True,fields='id').execute();assert D.files().get(fileId=u['id'],supportsAllDrives=True,fields='name').execute()['name']==u['name']
report={'smoke_ok':True,'smoke_folder_id':sm['id'],'uploaded':uploaded,'state_ok':True,'rename_ok':True,'root_before':[{'id':x['id'],'name':x['name'],'mimeType':x['mimeType']} for x in before]};Path('/kaggle/working/transfer_smoke_v27.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
print('SMOKE_OK',json.dumps({'folder_id':sm['id'],'uploaded':len(uploaded),'state_ok':True,'rename_ok':True},ensure_ascii=False));print('UPLOADED',json.dumps(uploaded,ensure_ascii=False));print('DONE smoke v27; test folder intentionally left in place; old library untouched')
C.close()
