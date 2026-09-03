import re,json,sqlite3,urllib.request
from pathlib import Path
from collections import Counter,defaultdict
import boto3
from botocore.config import Config
PUB='https://raw.githubusercontent.com/yossi-computers/HebrewBooks-2026/main/src/HebrewBooks.Services/HebrewBooks.Services.Downloader/R2MirrorClient.cs'
src=urllib.request.urlopen(urllib.request.Request(PUB,headers={'User-Agent':'HB-PropAudit/1'}),timeout=60).read().decode()
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
    except:return [x.strip() for x in re.split(r'\s*[|;>]\s*',v) if x.strip()]
def n(x):
    x=str(x or '').replace('״','"').replace('“','"').replace('”','"').replace('׳',"'").lower()
    x=re.sub(r'[^0-9a-zא-ת\s"\']+',' ',x)
    return ' '.join(x.split())
def series(x):
    x=n(x)
    # strip common volume/part/edition suffixes, conservatively
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
# Broad topic classifier from explicit category tags only. Closed tree.
TRACT={'ברכות','שבת','עירובין','פסחים','יומא','סוכה','ביצה','ראש השנה','תענית','מגילה','מועד קטן','חגיגה','יבמות','כתובות','נדרים','נזיר','סוטה','גיטין','קידושין','בבא קמא','בבא מציעא','בבא בתרא','סנהדרין','מכות','שבועות','עבודה זרה','הוריות','זבחים','מנחות','חולין','בכורות','ערכין','תמורה','כריתות','מעילה','נדה'}
def broad(cats):
    S={n(x) for x in cats}
    if not S:return None
    if S & {'ירחון','כתב עת','גליון','שבועון','רבעון'}:return 'כתבי עת וירחונים'
    if 'שו"ת' in S:return 'שו"ת'
    if S & {'הלכה','רמב"ם','כשרות','על השו"ע','בירורי הלכה','בירור הלכה','שחיטה','טריפות','ריבית','מקוואות','תערובות','מנהגים','נישואין','ברית מילה','חלה','תרי"ג מצוות','מצוות','פסקי הלכה','פסקי דינים','טור'}:return 'הלכה'
    if S & TRACT or S & {'מסכת','על הש"ס','סוגיות','תלמוד בבלי','ירושלמי','אגדות הש"ס','ביאור הגמ','כללי הש"ס','הדרנים','ברייתא'}:return 'תלמוד וש"ס'
    if S & {'משניות','על המשניות','אבות','פרקי אבות','זרעים','מועד','נשים','נזיקין','קדשים','טהרות'}:return 'משנה'
    if S & {'עה"ת','על התורה','חומש','בראשית','שמות','ויקרא','במדבר','דברים','רש"י','אונקלוס','תרגום','מסורה','תנ"ך','על הנ"ך','הפטרות'}:return 'תורה תנ"ך ומפרשים'
    if S & {'נ"ך','חמש מגילות','תהלים','משלי','איוב','שיר השירים','קהלת','אסתר','איכה','רות','מגילת אסתר'}:return 'תורה תנ"ך ומפרשים'
    if S & {'חסידות','ברסלב','חבד','אלכסנדר','מונקאטש','גור','ויזניץ','סאטמר','סאטמאר','צאנז','קרלין'}:return 'חסידות'
    if S & {'קבלה','זהר','רמח"ל','רשב"י','קמיעות','סגולות'}:return 'קבלה'
    if S & {'מוסר','אמונה','השקפה','חיזוק','פילוסופיה','הדרכה','מידות','מדות','לשון הרע','בין אדם לחברו'}:return 'מוסר מחשבה ואמונה'
    if S & {'דרשות','הספדים'}:return 'דרשות'
    if S & {'סידור','מחזור','תפילה','תפילות','פיוט','פיוטים','זמירות'}:return 'תפילה וסידורים'
    if S & {'מועדים','הגדה של פסח','ימים נוראים','חנוכה','פורים','פסח','סוכות','יום כיפור','יום הכיפורים','שבועות','ל"ג בעומר'}:return 'מועדים'
    if S & {'מדרש','אגדה','ספרא','תורת כהנים'}:return 'מדרש ואגדה'
    if S & {'תולדות','ביוגרפיה','ארץ ישראל','יודאיקה','סיפורים','היסטוריה','שואה','מסעות','אישים','זכרונות','מצבות'}:return 'תולדות וביוגרפיה'
    if S & {'גאונים','ראשונים'}:return 'גאונים וראשונים'
    if S & {'דקדוק','לשון הקודש','מילון','פירוש המילים','שרשים','קונקורדנציה','שמות נרדפים'}:return 'לשון ודקדוק'
    if S & {'לוח','זמנים','עיבור','תקופות','תכונה','חשבון','אסטרונומיה','קידוש החודש','ברכת החמה','קו התאריך','נץ נראה','שקיעה'}:return 'לוחות זמנים ומדעים'
    if S & {'פולמוס','ריפורם','ציונות','שבתי צבי'}:return 'פולמוסים'
    if S & {'חינוך','תלמוד תורה','לימוד התורה','דרך הלימוד'}:return 'חינוך ולימוד'
    if S & {'אגרות','מכתבים','צוואה'}:return 'אגרות ומכתבים'
    if S & {'קובץ','ספר זכרון','ספר היובל','מאמרים','ליקוט','ליקוטים'}:return 'קבצים ואוספים'
    if S & {'כתב יד','כתבי יד','גנוזות','ביבליוגרפיה','מפתח','אנציקלופדיה'}:return 'ספרנות ומקורות'
    if S & {'english','יידיש','español','français'}:return 'שפות אחרות'
    return None
rows=[dict(r) for r in C.execute("select ID,FileID,BookName,AuthorName,Description,Categories,SourceType from Katalog")]
# donor maps from explicit categories only
donors=[]
for r in rows:
    b=broad(parse(r['Categories']))
    if b:donors.append((r,b))
exact_ta=defaultdict(Counter);exact_t=defaultdict(Counter);series_a=defaultdict(Counter);series_only=defaultdict(Counter);author=defaultdict(Counter)
series_a_n=Counter();series_n=Counter();author_n=Counter()
for r,b in donors:
    t=n(r['BookName']);a=n(r['AuthorName']);s=series(r['BookName'])
    if t and a:exact_ta[(t,a)][b]+=1
    if t:exact_t[t][b]+=1
    if s and a:series_a[(s,a)][b]+=1;series_a_n[(s,a)]+=1
    if s:series_only[s][b]+=1;series_n[s]+=1
    if a:author[a][b]+=1;author_n[a]+=1
def consensus(c,min_n=1,ratio=1.0):
    tot=sum(c.values())
    if tot<min_n or not c:return None
    b,k=c.most_common(1)[0]
    return b if k/tot>=ratio else None
stats=Counter();resolved=Counter();examples=defaultdict(list)
for r in rows:
    if str(r['SourceType']).lower()!='pdf' or str(r['Categories'] or '').strip():continue
    stats['pdf_no_categories']+=1
    t=n(r['BookName']);a=n(r['AuthorName']);s=series(r['BookName'])
    cand=None;method=None
    if t and a:
        cand=consensus(exact_ta.get((t,a),Counter()),1,1.0)
        if cand:method='exact_title_author'
    if not cand and t:
        cand=consensus(exact_t.get(t,Counter()),1,1.0)
        if cand:method='exact_title'
    if not cand and s and a and s!=t:
        cand=consensus(series_a.get((s,a),Counter()),1,1.0)
        if cand:method='series_title_author'
    if not cand and s and s!=t:
        cand=consensus(series_only.get(s,Counter()),2,1.0)
        if cand:method='series_title_consensus'
    if cand:
        resolved[method]+=1;resolved['high_conf_total']+=1;resolved['topic_'+cand]+=1
        if len(examples[method])<30:examples[method].append({'FileID':r['FileID'],'BookName':r['BookName'],'AuthorName':r['AuthorName'],'topic':cand})
        continue
    # author-only shown separately as an optional, lower-confidence signal
    if a:
        ac=author.get(a,Counter());tot=sum(ac.values())
        if tot>=5:
            b,k=ac.most_common(1)[0]
            if k/tot>=0.9:
                resolved['author_90pct_5plus']+=1;resolved['author_topic_'+b]+=1
                if len(examples['author_90pct_5plus'])<30:examples['author_90pct_5plus'].append({'FileID':r['FileID'],'BookName':r['BookName'],'AuthorName':r['AuthorName'],'topic':b,'author_donors':dict(ac)})
report={'stats':dict(stats),'resolved':dict(resolved),'remaining_after_high_conf':stats['pdf_no_categories']-resolved['high_conf_total'],'examples':dict(examples),'donor_records':len(donors),'donor_topic_counts':dict(Counter(b for _,b in donors))}
Path('/kaggle/working/propagation_audit.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
print('PDF NO CATEGORIES',stats['pdf_no_categories'])
print('DONORS',len(donors),json.dumps(report['donor_topic_counts'],ensure_ascii=False))
print('HIGH CONF PROPAGATION',resolved['high_conf_total'])
print('METHODS',json.dumps({k:v for k,v in resolved.items() if not k.startswith('topic_') and not k.startswith('author_topic_')},ensure_ascii=False))
print('REMAINING HIGH-CONF',report['remaining_after_high_conf'])
print('EXAMPLES',json.dumps(report['examples'],ensure_ascii=False)[:20000])
print('DONE propagation audit only; no Drive; no PDFs')
C.close()
