import re, json, sqlite3, urllib.request
from pathlib import Path
from collections import Counter, defaultdict
import boto3
from botocore.config import Config

PUB='https://raw.githubusercontent.com/yossi-computers/HebrewBooks-2026/main/src/HebrewBooks.Services/HebrewBooks.Services.Downloader/R2MirrorClient.cs'
src=urllib.request.urlopen(urllib.request.Request(PUB,headers={'User-Agent':'HB-ClassTune/1'}),timeout=60).read().decode()
cfg=dict(re.findall(r'(?:private|public)\s+const\s+string\s+(\w+)\s*=\s*"([^"]+)"',src))
s3=boto3.client('s3',endpoint_url=cfg['Endpoint'],aws_access_key_id=cfg['AccessKey'],aws_secret_access_key=cfg['SecretKey'],region_name='auto',config=Config(signature_version='s3v4',s3={'addressing_style':'path'}))
pref=cfg['AppPrefix'].rstrip('/')+'/'
keys=[]
for pg in s3.get_paginator('list_objects_v2').paginate(Bucket=cfg['Bucket'],Prefix=pref): keys += [o['Key'] for o in pg.get('Contents',[])]
ck=next((k for k in keys if k.lower().endswith('/katalog.db')),None) or next(k for k in keys if k.lower().endswith('katalog.db'))
db=Path('/kaggle/working/Katalog.db');s3.download_file(cfg['Bucket'],ck,str(db))
C=sqlite3.connect(f'file:{db}?mode=ro',uri=True);C.row_factory=sqlite3.Row;C.create_collation('HEB',lambda a,b:(str(a)>str(b))-(str(a)<str(b)))

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
    except Exception:return [x.strip() for x in re.split(r'\s*[|;>]\s*',v) if x.strip()]

def n(x):
    x=str(x or '').replace('״','"').replace('“','"').replace('”','"').replace('׳',"'").lower()
    x=re.sub(r'[^0-9a-zא-ת\s"\']+',' ',x)
    return ' '.join(x.split())

def series(x):
    x=n(x);old=None
    pats=[r'\s*[-–—]?\s*(חלק|כרך|קונטרס|מחברת)\s+[א-ת0-9]{1,4}\s*$',r'\s*[-–—]?\s*ח["״]?([אבגדהוזחטיכלמנסעפצקרשת])\s*$',r'\s*[-–—]?\s*(חלקים|כרכים)\s+[א-ת0-9\s\-]+$',r'\s*[-–—]?\s*(מהדורה|הוצאה)\s+[^-–—]{1,40}$']
    while old!=x:
        old=x
        for p in pats:x=re.sub(p,'',x).strip()
    return x

TRACT={'ברכות','שבת','עירובין','פסחים','יומא','סוכה','ביצה','ראש השנה','תענית','מגילה','מועד קטן','חגיגה','יבמות','כתובות','נדרים','נזיר','סוטה','גיטין','קידושין','בבא קמא','בבא מציעא','בבא בתרא','סנהדרין','מכות','שבועות','עבודה זרה','הוריות','זבחים','מנחות','חולין','בכורות','ערכין','תמורה','כריתות','מעילה','נדה'}
RULES=[
 ('כתבי עת וירחונים',{'ירחון','כתב עת','גליון','שבועון','רבעון'}),('שו"ת',{'שו"ת'}),('הלכה',{'הלכה','רמב"ם','כשרות','על השו"ע','בירורי הלכה','בירור הלכה','שחיטה','טריפות','ריבית','מקוואות','תערובות','מנהגים','נישואין','ברית מילה','חלה','תרי"ג מצוות','מצוות','פסקי הלכה','פסקי דינים','טור'}),('תלמוד וש"ס',TRACT|{'מסכת','על הש"ס','סוגיות','תלמוד בבלי','ירושלמי','אגדות הש"ס','ביאור הגמ','כללי הש"ס','הדרנים','ברייתא'}),('משנה',{'משניות','על המשניות','אבות','פרקי אבות','זרעים','מועד','נשים','נזיקין','קדשים','טהרות'}),('תורה תנ"ך ומפרשים',{'עה"ת','על התורה','חומש','בראשית','שמות','ויקרא','במדבר','דברים','רש"י','אונקלוס','תרגום','מסורה','תנ"ך','על הנ"ך','הפטרות','נ"ך','חמש מגילות','תהלים','משלי','איוב','שיר השירים','קהלת','אסתר','איכה','רות','מגילת אסתר'}),('חסידות',{'חסידות','ברסלב','חבד','אלכסנדר','מונקאטש','גור','ויזניץ','סאטמר','סאטמאר','צאנז','קרלין'}),('קבלה',{'קבלה','זהר','רמח"ל','רשב"י','קמיעות','סגולות'}),('מוסר מחשבה ואמונה',{'מוסר','אמונה','השקפה','חיזוק','פילוסופיה','הדרכה','מידות','מדות','לשון הרע','בין אדם לחברו'}),('דרשות',{'דרשות','הספדים'}),('תפילה וסידורים',{'סידור','מחזור','תפילה','תפילות','פיוט','פיוטים','זמירות'}),('מועדים',{'מועדים','הגדה של פסח','ימים נוראים','חנוכה','פורים','פסח','סוכות','יום כיפור','יום הכיפורים','שבועות','ל"ג בעומר'}),('מדרש ואגדה',{'מדרש','אגדה','ספרא','תורת כהנים'}),('תולדות וביוגרפיה',{'תולדות','ביוגרפיה','ארץ ישראל','יודאיקה','סיפורים','היסטוריה','שואה','מסעות','אישים','זכרונות','מצבות'}),('גאונים וראשונים',{'גאונים','ראשונים'}),('לשון ודקדוק',{'דקדוק','לשון הקודש','מילון','פירוש המילים','שרשים','קונקורדנציה','שמות נרדפים'}),('לוחות זמנים ומדעים',{'לוח','זמנים','עיבור','תקופות','תכונה','חשבון','אסטרונומיה','קידוש החודש','ברכת החמה','קו התאריך','נץ נראה','שקיעה'}),('פולמוסים',{'פולמוס','ריפורם','ציונות','שבתי צבי'}),('חינוך ולימוד',{'חינוך','תלמוד תורה','לימוד התורה','דרך הלימוד'}),('אגרות ומכתבים',{'אגרות','מכתבים','צוואה'}),('קבצים ואוספים',{'קובץ','ספר זכרון','ספר היובל','מאמרים','ליקוט','ליקוטים'}),('ספרנות ומקורות',{'כתב יד','כתבי יד','גנוזות','ביבליוגרפיה','מפתח','אנציקלופדיה'}),('שפות אחרות',{'english','יידיש','español','français'})]
RULES=[(lab,{n(x) for x in tags}) for lab,tags in RULES]
def topic_set(cats):
    S={n(x) for x in cats};return {lab for lab,tags in RULES if S&tags}
def primary(cats):
    T=topic_set(cats)
    for lab,_ in RULES:
        if lab in T:return lab
    return None

def title_pred(book,desc='',use_desc=False):
    t=' '+n(book)+' '
    if use_desc:t+=' '+n(desc)+' '
    # conservative title/description patterns only
    if ' שו"ת ' in t or ' שאלות ותשובות ' in t:return 'שו"ת'
    if any((' '+x+' ') in t for x in ['משניות','משנה ברורה']):return 'משנה' if 'משניות' in t else 'הלכה'
    for tr in sorted(TRACT,key=len,reverse=True):
        if (' '+n(tr)+' ') in t and any(w in t for w in [' מסכת ',' תלמוד ',' חידושי ',' שיטה ',' סוגיות ',' על ']):return 'תלמוד וש"ס'
    if any(x in t for x in [' תלמוד בבלי ',' תלמוד ירושלמי ',' על הש"ס ',' כללי הש"ס ']):return 'תלמוד וש"ס'
    if any(x in t for x in [' שלחן ערוך ',' שולחן ערוך ',' הלכות ',' פסקי הלכה ',' משנה ברורה ',' כף החיים ']):return 'הלכה'
    if any(x in t for x in [' חומש ',' על התורה ',' פירוש התורה ',' פרשת ']):return 'תורה תנ"ך ומפרשים'
    if any(x in t for x in [' סידור ',' מחזור ',' סדר תפילות ',' פיוטים ']):return 'תפילה וסידורים'
    if ' הגדה של פסח ' in t:return 'מועדים'
    if any(x in t for x in [' זוהר ',' קבלה ',' עץ חיים ',' שער הכוונות ']):return 'קבלה'
    if any(x in t for x in [' חסידות ',' ליקוטי מוהר"ן ',' לקוטי מוהר"ן ',' תניא ']):return 'חסידות'
    if any(x in t for x in [' מוסר ',' אמונה ובטחון ',' אמונה וביטחון ']):return 'מוסר מחשבה ואמונה'
    if any(x in t for x in [' מדרש ',' ילקוט שמעוני ']):return 'מדרש ואגדה'
    if any(x in t for x in [' ירחון ',' כתב עת ',' שבועון ',' רבעון ']):return 'כתבי עת וירחונים'
    if any(x in t for x in [' דקדוק ',' מילון ',' לשון הקודש ']):return 'לשון ודקדוק'
    if any(x in t for x in [' לוח ',' קידוש החודש ',' אסטרונומיה ',' חשבון תקופות ']):return 'לוחות זמנים ומדעים'
    return None

rows=[dict(r) for r in C.execute("select ID,FileID,BookName,AuthorName,Description,Categories from Katalog where lower(SourceType)='pdf'")]
donors=[];nocat=[]
for r in rows:
    p=primary(parse(r['Categories']))
    if p:donors.append((r,p,topic_set(parse(r['Categories']))))
    if not str(r['Categories'] or '').strip():nocat.append(r)

author=defaultdict(Counter);sa=defaultdict(Counter);eta=defaultdict(Counter)
for r,p,ts in donors:
    a=n(r['AuthorName']);s=series(r['BookName']);t=n(r['BookName'])
    if a:author[a][p]+=1
    if a and s:sa[(s,a)][p]+=1
    if a and t:eta[(t,a)][p]+=1

def minus(c,label):
    z=c.copy();z[label]-=1
    if z[label]<=0:del z[label]
    return z

def pred(c,min_n,ratio):
    tot=sum(c.values())
    if tot<min_n or not c:return None
    b,k=c.most_common(1)[0]
    return b if k/tot>=ratio else None

def score_map(kind,mins,ratios):
    out=[]
    mp={'author':author,'series_author':sa,'exact_title_author':eta}[kind]
    for mn in mins:
      for rr in ratios:
        e=cp=ca=0
        for r,actual,aset in donors:
            a=n(r['AuthorName']);s=series(r['BookName']);t=n(r['BookName'])
            key=a if kind=='author' else ((s,a) if kind=='series_author' else (t,a))
            if not key or (isinstance(key,tuple) and not all(key)):continue
            q=pred(minus(mp.get(key,Counter()),actual),mn,rr)
            if not q:continue
            e+=1;cp+=q==actual;ca+=q in aset
        # coverage on actual no-category PDFs, using full donor maps
        cov=0
        for r in nocat:
            a=n(r['AuthorName']);s=series(r['BookName']);t=n(r['BookName'])
            key=a if kind=='author' else ((s,a) if kind=='series_author' else (t,a))
            if key and (not isinstance(key,tuple) or all(key)) and pred(mp.get(key,Counter()),mn,rr):cov+=1
        out.append({'kind':kind,'min_n':mn,'ratio':rr,'eligible_validation':e,'accuracy_primary_pct':round(cp*100/e,2) if e else None,'accuracy_anytopic_pct':round(ca*100/e,2) if e else None,'coverage_no_categories':cov})
    return out
sweeps=[]
sweeps+=score_map('author',[3,5,8,10,15],[0.90,0.95,1.0])
sweeps+=score_map('series_author',[1,2,3,4],[0.9,0.95,1.0])
sweeps+=score_map('exact_title_author',[1,2,3],[0.9,0.95,1.0])
# title heuristic validation + no-category coverage
title_stats={}
for use_desc in [False,True]:
    e=cp=ca=0;by=defaultdict(Counter)
    for r,actual,aset in donors:
        q=title_pred(r['BookName'],r['Description'],use_desc)
        if not q:continue
        e+=1;cp+=q==actual;ca+=q in aset;by[q]['eligible']+=1;by[q]['correct']+=q in aset
    cov=Counter()
    for r in nocat:
        q=title_pred(r['BookName'],r['Description'],use_desc)
        if q:cov[q]+=1
    title_stats['name_desc' if use_desc else 'name_only']={'eligible_validation':e,'accuracy_primary_pct':round(cp*100/e,2) if e else None,'accuracy_anytopic_pct':round(ca*100/e,2) if e else None,'coverage_no_categories':sum(cov.values()),'coverage_by_topic':dict(cov),'precision_by_topic':{k:{'eligible':v['eligible'],'accuracy_anytopic_pct':round(v['correct']*100/v['eligible'],2)} for k,v in by.items()}}
report={'pdf_rows':len(rows),'donor_rows':len(donors),'no_category_rows':len(nocat),'sweeps':sweeps,'title_heuristics':title_stats}
Path('/kaggle/working/classification_tuning.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
print('ROWS',len(rows),'DONORS',len(donors),'NO_CAT',len(nocat))
for kind in ['author','series_author','exact_title_author']:
    print('SWEEP',kind,json.dumps([x for x in sweeps if x['kind']==kind],ensure_ascii=False))
print('TITLE',json.dumps(title_stats,ensure_ascii=False))
print('DONE tuning only; no Drive; no PDFs')
C.close()
