import re,json,sqlite3,urllib.request
from pathlib import Path
from collections import Counter,defaultdict
import boto3
from botocore.config import Config

PUB='https://raw.githubusercontent.com/yossi-computers/HebrewBooks-2026/main/src/HebrewBooks.Services/HebrewBooks.Services.Downloader/R2MirrorClient.cs'
src=urllib.request.urlopen(urllib.request.Request(PUB,headers={'User-Agent':'HB-AmbigAudit/1'}),timeout=60).read().decode()
cfg=dict(re.findall(r'(?:private|public)\s+const\s+string\s+(\w+)\s*=\s*"([^"]+)"',src))
s3=boto3.client('s3',endpoint_url=cfg['Endpoint'],aws_access_key_id=cfg['AccessKey'],aws_secret_access_key=cfg['SecretKey'],region_name='auto',config=Config(signature_version='s3v4',s3={'addressing_style':'path'}))
pref=cfg['AppPrefix'].rstrip('/')+'/'
key=None
for pg in s3.get_paginator('list_objects_v2').paginate(Bucket=cfg['Bucket'],Prefix=pref):
    for o in pg.get('Contents',[]):
        if o['Key'].lower().endswith('/katalog.db'):key=o['Key'];break
    if key:break
p=Path('/kaggle/working/Katalog.db');s3.download_file(cfg['Bucket'],key,str(p))
C=sqlite3.connect(f'file:{p}?mode=ro',uri=True);C.row_factory=sqlite3.Row

def n(x):
    x=str(x or '').replace('״','"').replace('“','"').replace('”','"').replace('׳',"'").lower()
    x=re.sub(r'[^0-9a-zא-ת\s"\']+',' ',x);return ' '.join(x.split())
def parse(v):
    v=str(v or '').strip()
    if not v:return []
    try:
        j=json.loads(v);o=[]
        def w(x):
            if isinstance(x,dict):
                for y in x.values():w(y)
            elif isinstance(x,list):
                for y in x:w(y)
            elif x is not None and str(x).strip():o.append(str(x).strip())
        w(j);return o
    except:return [x.strip() for x in re.split(r'\s*[|;>]\s*',v) if x.strip()]
amb=['שבת','ברכות','שבועות','ראש השנה','סוכה','מגילה','תענית','מועד']
talmud_words=['מסכת','תלמוד','ש"ס','שס','גמרא','סוגי','חידושי','חידושין','שיטה מקובצת','תוספות','ירושלמי','בבלי','דף','פרק']
holiday_words=['חג','מועד','ימים טובים','יום טוב','שבת קודש','שמירת שבת','עונג שבת','זמירות','קידוש','הבדלה','פורים','סוכות','שבועות','ראש השנה','תענית','צום','חגים']
prayer_words=['ברכת','ברכות הנהנין','ברכות התורה','ברכת המזון','תפילה','תפילות','סידור']
rows=[dict(r) for r in C.execute("select ID,FileID,BookName,AuthorName,Description,Categories from Katalog where lower(SourceType)='pdf'")]
report={}
for tok in amb:
    nt=n(tok);hits=[]
    for r in rows:
        cats=parse(r['Categories']);ns={n(x) for x in cats}
        if nt not in ns:continue
        text=n((r['BookName'] or '')+' '+(r['Description'] or ''))
        cue='none'
        if any(w in text for w in talmud_words):cue='talmud'
        elif any(w in text for w in holiday_words):cue='holiday'
        elif any(w in text for w in prayer_words):cue='prayer'
        hits.append((r,cats,cue))
    cues=Counter(x[2] for x in hits);single=sum(1 for _,c,_ in hits if len(c)==1)
    cotags=Counter(n(x) for _,c,_ in hits for x in c if n(x)!=nt)
    examples={}
    for cue in ['talmud','holiday','prayer','none']:
        examples[cue]=[{'FileID':r['FileID'],'BookName':r['BookName'],'AuthorName':r['AuthorName'],'Categories':c} for r,c,q in hits if q==cue][:20]
    report[tok]={'count':len(hits),'single_tag':single,'cues':dict(cues),'top_cotags':cotags.most_common(25),'examples':examples}
print('AMBIG',json.dumps({k:{'count':v['count'],'single_tag':v['single_tag'],'cues':v['cues'],'top_cotags':v['top_cotags'][:10]} for k,v in report.items()},ensure_ascii=False))
for k,v in report.items():
    print('TOKEN',k,json.dumps(v['examples'],ensure_ascii=False))
Path('/kaggle/working/ambiguous_tags_audit_v28.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
print('DONE ambiguity audit only; no Drive; no PDFs')
C.close()
