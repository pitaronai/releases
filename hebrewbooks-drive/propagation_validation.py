import re, json, sqlite3, urllib.request
from pathlib import Path
from collections import Counter, defaultdict
import boto3
from botocore.config import Config

PUB='https://raw.githubusercontent.com/yossi-computers/HebrewBooks-2026/main/src/HebrewBooks.Services/HebrewBooks.Services.Downloader/R2MirrorClient.cs'
src=urllib.request.urlopen(urllib.request.Request(PUB,headers={'User-Agent':'HB-PropValidation/1'}),timeout=60).read().decode()
cfg=dict(re.findall(r'(?:private|public)\s+const\s+string\s+(\w+)\s*=\s*"([^"]+)"',src))
s3=boto3.client('s3',endpoint_url=cfg['Endpoint'],aws_access_key_id=cfg['AccessKey'],aws_secret_access_key=cfg['SecretKey'],region_name='auto',config=Config(signature_version='s3v4',s3={'addressing_style':'path'}))
pref=cfg['AppPrefix'].rstrip('/')+'/'
keys=[]
for pg in s3.get_paginator('list_objects_v2').paginate(Bucket=cfg['Bucket'],Prefix=pref): keys += [o['Key'] for o in pg.get('Contents',[])]
ck=next((k for k in keys if k.lower().endswith('/katalog.db')),None) or next(k for k in keys if k.lower().endswith('katalog.db'))
db=Path('/kaggle/working/Katalog.db'); s3.download_file(cfg['Bucket'],ck,str(db))
C=sqlite3.connect(f'file:{db}?mode=ro',uri=True); C.row_factory=sqlite3.Row; C.create_collation('HEB',lambda a,b:(str(a)>str(b))-(str(a)<str(b)))

def parse(v):
    v=str(v or '').strip()
    if not v:return []
    try:
        j=json.loads(v);out=[]
        def w(x):
            if isinstance(x,dict):
                for y in x.values():w(y)
            elif isinstance(x,list):
                for y in x:w(y)
            elif x is not None and str(x).strip():out.append(str(x).strip())
        w(j);return out
    except Exception:
        return [x.strip() for x in re.split(r'\s*[|;>]\s*',v) if x.strip()]

def n(x):
    x=str(x or '').replace('״','"').replace('“','"').replace('”','"').replace('׳',"'").lower()
    x=re.sub(r'[^0-9a-zא-ת\s"\']+',' ',x)
    return ' '.join(x.split())

def series(x):
    x=n(x)
    pats=[
      r'\s*[-–—]?\s*(חלק|כרך|קונטרס|מחברת)\s+[א-ת0-9]{1,4}\s*$',
      r'\s*[-–—]?\s*ח["״]?([אבגדהוזחטיכלמנסעפצקרשת])\s*$',
      r'\s*[-–—]?\s*(חלקים|כרכים)\s+[א-ת0-9\s\-]+$',
      r'\s*[-–—]?\s*(מהדורה|הוצאה)\s+[^-–—]{1,40}$'
    ]
    old=None
    while old!=x:
        old=x
        for p in pats:x=re.sub(p,'',x).strip()
    return x

TRACT={'ברכות','שבת','עירובין','פסחים','יומא','סוכה','ביצה','ראש השנה','תענית','מגילה','מועד קטן','חגיגה','יבמות','כתובות','נדרים','נזיר','סוטה','גיטין','קידושין','בבא קמא','בבא מציעא','בבא בתרא','סנהדרין','מכות','שבועות','עבודה זרה','הוריות','זבחים','מנחות','חולין','בכורות','ערכין','תמורה','כריתות','מעילה','נדה'}
RULES=[
 ('כתבי עת וירחונים',{'ירחון','כתב עת','גליון','שבועון','רבעון'}),
 ('שו"ת',{'שו"ת'}),
 ('הלכה',{'הלכה','רמב"ם','כשרות','על השו"ע','בירורי הלכה','בירור הלכה','שחיטה','טריפות','ריבית','מקוואות','תערובות','מנהגים','נישואין','ברית מילה','חלה','תרי"ג מצוות','מצוות','פסקי הלכה','פסקי דינים','טור'}),
 ('תלמוד וש"ס',TRACT|{'מסכת','על הש"ס','סוגיות','תלמוד בבלי','ירושלמי','אגדות הש"ס','ביאור הגמ','כללי הש"ס','הדרנים','ברייתא'}),
 ('משנה',{'משניות','על המשניות','אבות','פרקי אבות','זרעים','מועד','נשים','נזיקין','קדשים','טהרות'}),
 ('תורה תנ"ך ומפרשים',{'עה"ת','על התורה','חומש','בראשית','שמות','ויקרא','במדבר','דברים','רש"י','אונקלוס','תרגום','מסורה','תנ"ך','על הנ"ך','הפטרות','נ"ך','חמש מגילות','תהלים','משלי','איוב','שיר השירים','קהלת','אסתר','איכה','רות','מגילת אסתר'}),
 ('חסידות',{'חסידות','ברסלב','חבד','אלכסנדר','מונקאטש','גור','ויזניץ','סאטמר','סאטמאר','צאנז','קרלין'}),
 ('קבלה',{'קבלה','זהר','רמח"ל','רשב"י','קמיעות','סגולות'}),
 ('מוסר מחשבה ואמונה',{'מוסר','אמונה','השקפה','חיזוק','פילוסופיה','הדרכה','מידות','מדות','לשון הרע','בין אדם לחברו'}),
 ('דרשות',{'דרשות','הספדים'}),
 ('תפילה וסידורים',{'סידור','מחזור','תפילה','תפילות','פיוט','פיוטים','זמירות'}),
 ('מועדים',{'מועדים','הגדה של פסח','ימים נוראים','חנוכה','פורים','פסח','סוכות','יום כיפור','יום הכיפורים','שבועות','ל"ג בעומר'}),
 ('מדרש ואגדה',{'מדרש','אגדה','ספרא','תורת כהנים'}),
 ('תולדות וביוגרפיה',{'תולדות','ביוגרפיה','ארץ ישראל','יודאיקה','סיפורים','היסטוריה','שואה','מסעות','אישים','זכרונות','מצבות'}),
 ('גאונים וראשונים',{'גאונים','ראשונים'}),
 ('לשון ודקדוק',{'דקדוק','לשון הקודש','מילון','פירוש המילים','שרשים','קונקורדנציה','שמות נרדפים'}),
 ('לוחות זמנים ומדעים',{'לוח','זמנים','עיבור','תקופות','תכונה','חשבון','אסטרונומיה','קידוש החודש','ברכת החמה','קו התאריך','נץ נראה','שקיעה'}),
 ('פולמוסים',{'פולמוס','ריפורם','ציונות','שבתי צבי'}),
 ('חינוך ולימוד',{'חינוך','תלמוד תורה','לימוד התורה','דרך הלימוד'}),
 ('אגרות ומכתבים',{'אגרות','מכתבים','צוואה'}),
 ('קבצים ואוספים',{'קובץ','ספר זכרון','ספר היובל','מאמרים','ליקוט','ליקוטים'}),
 ('ספרנות ומקורות',{'כתב יד','כתבי יד','גנוזות','ביבליוגרפיה','מפתח','אנציקלופדיה'}),
 ('שפות אחרות',{'english','יידיש','español','français'})
]
RULES=[(lab,{n(x) for x in tags}) for lab,tags in RULES]

def topic_set(cats):
    S={n(x) for x in cats}
    return {lab for lab,tags in RULES if S & tags}

def primary(cats):
    T=topic_set(cats)
    for lab,_ in RULES:
        if lab in T:return lab
    return None

rows=[dict(r) for r in C.execute("select ID,FileID,BookName,AuthorName,Categories,SourceType from Katalog where lower(SourceType)='pdf'")]
donors=[]
ambiguous=0
for r in rows:
    cats=parse(r['Categories']); p=primary(cats)
    if p:
        ts=topic_set(cats)
        if len(ts)>1:ambiguous+=1
        donors.append((r,p,ts))

# Global counts for leave-one-out prediction.
exact_ta=defaultdict(Counter); exact_t=defaultdict(Counter); series_a=defaultdict(Counter); series_only=defaultdict(Counter); author=defaultdict(Counter)
for r,p,ts in donors:
    t=n(r['BookName']); a=n(r['AuthorName']); s=series(r['BookName'])
    if t and a:exact_ta[(t,a)][p]+=1
    if t:exact_t[t][p]+=1
    if s and a:series_a[(s,a)][p]+=1
    if s:series_only[s][p]+=1
    if a:author[a][p]+=1

def minus(c,label):
    z=c.copy(); z[label]-=1
    if z[label]<=0:del z[label]
    return z

def unanimous(c,min_n=1):
    tot=sum(c.values())
    return next(iter(c)) if tot>=min_n and len(c)==1 else None

def author_pred(c,min_n=5,ratio=.9):
    tot=sum(c.values())
    if tot<min_n:return None
    b,k=c.most_common(1)[0]
    return b if k/tot>=ratio else None

methods=['exact_title_author','exact_title','series_title_author','series_title_consensus','author_90pct_5plus']
ind={m:Counter() for m in methods}; seq=Counter(); seq_by=defaultdict(Counter); errors=defaultdict(list)
for r,actual,actual_set in donors:
    t=n(r['BookName']);a=n(r['AuthorName']);s=series(r['BookName'])
    candidates={}
    if t and a:candidates['exact_title_author']=unanimous(minus(exact_ta[(t,a)],actual),1)
    if t:candidates['exact_title']=unanimous(minus(exact_t[t],actual),1)
    if s and a and s!=t:candidates['series_title_author']=unanimous(minus(series_a[(s,a)],actual),1)
    if s and s!=t:candidates['series_title_consensus']=unanimous(minus(series_only[s],actual),2)
    if a:candidates['author_90pct_5plus']=author_pred(minus(author[a],actual),5,.9)
    for m,pred in candidates.items():
        if pred:
            ind[m]['eligible']+=1
            if pred in actual_set:ind[m]['correct_anytopic']+=1
            if pred==actual:ind[m]['correct_primary']+=1
            if pred!=actual and len(errors[m])<30:errors[m].append({'FileID':r['FileID'],'BookName':r['BookName'],'AuthorName':r['AuthorName'],'actual':actual,'actual_topics':sorted(actual_set),'pred':pred})
    for m in methods:
        pred=candidates.get(m)
        if pred:
            seq['eligible']+=1;seq_by[m]['eligible']+=1
            if pred in actual_set:seq['correct_anytopic']+=1;seq_by[m]['correct_anytopic']+=1
            if pred==actual:seq['correct_primary']+=1;seq_by[m]['correct_primary']+=1
            if pred!=actual and len(errors['seq_'+m])<20:errors['seq_'+m].append({'FileID':r['FileID'],'BookName':r['BookName'],'AuthorName':r['AuthorName'],'actual':actual,'actual_topics':sorted(actual_set),'pred':pred})
            break

def pack(c):
    e=c['eligible']
    return {'eligible':e,'correct_primary':c['correct_primary'],'accuracy_primary_pct':round(c['correct_primary']*100/e,2) if e else None,'correct_anytopic':c['correct_anytopic'],'accuracy_anytopic_pct':round(c['correct_anytopic']*100/e,2) if e else None}
report={'pdf_rows':len(rows),'donor_rows':len(donors),'ambiguous_donor_rows':ambiguous,'individual':{m:pack(ind[m]) for m in methods},'sequential':pack(seq),'sequential_by_method':{m:pack(seq_by[m]) for m in methods},'errors':dict(errors)}
Path('/kaggle/working/propagation_validation.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
print('PDF',len(rows),'DONORS',len(donors),'AMBIGUOUS',ambiguous)
print('INDIVIDUAL',json.dumps(report['individual'],ensure_ascii=False))
print('SEQUENTIAL',json.dumps(report['sequential'],ensure_ascii=False))
print('SEQ_BY_METHOD',json.dumps(report['sequential_by_method'],ensure_ascii=False))
for m in methods: print('ERRORS',m,json.dumps(errors[m][:8],ensure_ascii=False))
print('DONE validation only; no Drive; no PDFs')
C.close()
