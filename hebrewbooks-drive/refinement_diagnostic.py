import re,json,sqlite3,urllib.request
from pathlib import Path
from collections import Counter,defaultdict
import boto3
from botocore.config import Config

PUB='https://raw.githubusercontent.com/yossi-computers/HebrewBooks-2026/main/src/HebrewBooks.Services/HebrewBooks.Services.Downloader/R2MirrorClient.cs'
src=urllib.request.urlopen(urllib.request.Request(PUB,headers={'User-Agent':'HB-RefineDiag/1'}),timeout=60).read().decode()
cfg=dict(re.findall(r'(?:private|public)\s+const\s+string\s+(\w+)\s*=\s*"([^"]+)"',src))
s3=boto3.client('s3',endpoint_url=cfg['Endpoint'],aws_access_key_id=cfg['AccessKey'],aws_secret_access_key=cfg['SecretKey'],region_name='auto',config=Config(signature_version='s3v4',s3={'addressing_style':'path'}))
pref=cfg['AppPrefix'].rstrip('/')+'/'
keys=[]
for pg in s3.get_paginator('list_objects_v2').paginate(Bucket=cfg['Bucket'],Prefix=pref):keys += [o['Key'] for o in pg.get('Contents',[])]
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
('כתבי עת וירחונים',{'ירחון','כתב עת','גליון','שבועון','רבעון'}),('שו"ת',{'שו"ת'}),
('הלכה',{'הלכה','רמב"ם','כשרות','על השו"ע','בירורי הלכה','בירור הלכה','שחיטה','טריפות','ריבית','מקוואות','תערובות','מנהגים','נישואין','ברית מילה','חלה','תרי"ג מצוות','מצוות','פסקי הלכה','פסקי דינים','טור','שטרות','נוסח שטרות','ציצית','תפילין','שביעית','תכלת'}),
('תלמוד וש"ס',TRACT|{'מסכת','על הש"ס','סוגיות','תלמוד בבלי','ירושלמי','אגדות הש"ס','ביאור הגמ','כללי הש"ס','כללים הש"ס','הדרנים','ברייתא','סוגיא','בירורי סוגיות'}),
('משנה',{'משניות','על המשניות','אבות','פרקי אבות','זרעים','מועד','נשים','נזיקין','קדשים','טהרות'}),
('תורה ומפרשים',{'עה"ת','על התורה','חומש','בראשית','שמות','ויקרא','במדבר','דברים','רש"י','אונקלוס','תרגום','מסורה','הפטרות','תורת כהנים','ספרא'}),
('תנ"ך ומגילות',{'נ"ך','חמש מגילות','תנ"ך','על הנ"ך','תהלים','משלי','איוב','שיר השירים','קהלת','אסתר','מגילת אסתר','איכה','רות'}),
('חסידות',{'חסידות','ברסלב','חבד','חב"ד','אלכסנדר','מונקאטש','גור','ויזניץ','סאטמר','סאטמאר','צאנז','קרלין'}),
('קבלה',{'קבלה','זהר','רמח"ל','רשב"י','קמיעות','סגולות'}),
('מוסר מחשבה ואמונה',{'מוסר','אמונה','השקפה','חיזוק','פילוסופיה','הדרכה','מידות','מדות','לשון הרע','בין אדם לחברו','גאולה','משיח','תשובה'}),
('דרשות',{'דרשות','הספדים','דרוש','דרושים'}),('תפילה וסידורים',{'סידור','מחזור','תפילה','תפילות','פיוט','פיוטים','זמירות','פרק שירה'}),
('מועדים',{'מועדים','הגדה של פסח','ימים נוראים','חנוכה','פורים','פסח','סוכות','יום כיפור','יום הכיפורים','שבועות','תשעה באב','ל"ג בעומר'}),
('מדרש ואגדה',{'מדרש','אגדה'}),('תולדות וביוגרפיה',{'תולדות','ביוגרפיה','ארץ ישראל','יודאיקה','סיפורים','היסטוריה','שואה','מסעות','אישים','זכרונות','מצבות','ירושלים','תימן'}),
('גאונים וראשונים',{'גאונים','ראשונים'}),('לשון ודקדוק',{'דקדוק','לשון הקודש','מילון','פירוש המילים','שרשים','קונקורדנציה','שמות נרדפים','טעמי המקרא','טעמים'}),
('לוחות זמנים ומדעים',{'לוח','זמנים','עיבור','תקופות','תכונה','חשבון','אסטרונומיה','קידוש החודש','ברכת החמה','קו התאריך','נץ נראה','שקיעה','אלגברה','טבע','חכמת הטבע'}),
('פולמוסים',{'פולמוס','ריפורם','ציונות','שבתי צבי','חיון'}),('חינוך ולימוד',{'חינוך','תלמוד תורה','לימוד התורה','דרך הלימוד','בר מצוה','שיעורים'}),
('אגרות ומכתבים',{'אגרות','מכתבים','צוואה'}),('קבצים ואוספים',{'קובץ','ספר זכרון','ספר היובל','מאמרים','ליקוט','ליקוטים','חידושים','פירוש','כללים','דברי תורה'}),
('ספרנות ומקורות',{'כתב יד','כתבי יד','גנוזות','ביבליוגרפיה','מפתח','אנציקלופדיה','מראה מקומות'}),('שפות אחרות',{'english','יידיש','español','français'})]
RULES=[(lab,{n(x) for x in tags}) for lab,tags in RULES]
def topic_set(cats):
    S={n(x) for x in cats};return {lab for lab,tags in RULES if S&tags}
def primary(cats):
    T=topic_set(cats)
    for lab,_ in RULES:
        if lab in T:return lab
    return None

def title_hint(book,desc=''):
    name=' '+n(book)+' ';both=name+' '+n(desc)+' '
    # Strong-ish topic cues; never used alone in this diagnostic except for agreement tests.
    if ' שו"ת ' in both or ' שאלות ותשובות ' in both or ' תשובות ' in name:return 'שו"ת'
    if any(x in both for x in [' ירחון ',' כתב עת ',' שבועון ',' רבעון ',' גליון ']):return 'כתבי עת וירחונים'
    if ' משניות ' in name or ' פרקי אבות ' in name:return 'משנה'
    if any(x in name for x in [' תלמוד בבלי ',' תלמוד ירושלמי ',' מסכת ',' על הש"ס ',' חידושי הש"ס ',' סוגיות ']):return 'תלמוד וש"ס'
    if any(x in name for x in [' שלחן ערוך ',' שולחן ערוך ',' הלכות ',' פסקי הלכה ',' משנה ברורה ',' כף החיים ',' קיצור שלחן ערוך ']):return 'הלכה'
    if any(x in name for x in [' חומש ',' על התורה ',' פירוש התורה ',' פרשת ']):return 'תורה ומפרשים'
    if any(x in name for x in [' תנ"ך ',' תהלים ',' משלי ',' איוב ',' שיר השירים ',' קהלת ',' מגילת אסתר ',' איכה ',' רות ']):return 'תנ"ך ומגילות'
    if any(x in both for x in [' ליקוטי מוהר"ן ',' לקוטי מוהר"ן ',' תניא ',' חסידות ',' ברסלב ',' חב"ד ']):return 'חסידות'
    if any(x in both for x in [' זוהר ',' קבלה ',' עץ חיים ',' שער הכוונות ']):return 'קבלה'
    if any(x in both for x in [' מוסר ',' אמונה ובטחון ',' אמונה וביטחון ']):return 'מוסר מחשבה ואמונה'
    if any(x in name for x in [' דרשות ',' דרושים ',' דרוש ']):return 'דרשות'
    if any(x in name for x in [' סידור ',' מחזור ',' סדר תפילות ',' פיוטים ']):return 'תפילה וסידורים'
    if ' הגדה של פסח ' in both:return 'מועדים'
    if any(x in both for x in [' חנוכה ',' פורים ',' פסח ',' סוכות ',' יום כיפור ',' יום הכיפורים ',' ראש השנה ',' תשעה באב ',' ל"ג בעומר ']):return 'מועדים'
    if any(x in name for x in [' מדרש ',' ילקוט שמעוני ']):return 'מדרש ואגדה'
    if any(x in name for x in [' תולדות ',' ביוגרפיה ',' זכרונות ',' זכרונות ',' מסעות ']):return 'תולדות וביוגרפיה'
    if any(x in name for x in [' דקדוק ',' מילון ',' לשון הקודש ']):return 'לשון ודקדוק'
    if any(x in name for x in [' לוח ',' קידוש החודש ',' אסטרונומיה ',' חשבון תקופות ']):return 'לוחות זמנים ומדעים'
    if any(x in name for x in [' אגרות ',' מכתבים ']):return 'אגרות ומכתבים'
    if any(x in name for x in [' אנציקלופדיה ',' ביבליוגרפיה ',' מפתח ']):return 'ספרנות ומקורות'
    return None

rows=[dict(r) for r in C.execute('select ID,FileID,BookName,AuthorName,Description,Categories,SourceType,Folder,RelativePath from Katalog')]
pdf=[r for r in rows if str(r['SourceType']).lower()=='pdf'];nonpdf=[r for r in rows if str(r['SourceType']).lower()!='pdf']
pdf_d=[]
for r in pdf:
    p=primary(parse(r['Categories']))
    if p:pdf_d.append((r,p,topic_set(parse(r['Categories']))))
non_d=[]
for r in nonpdf:
    p=primary(parse(r['Categories']))
    if p:non_d.append((r,p))

# Shelf map and calibration from PDF donors.
shelves=defaultdict(set)
for x in C.execute('select bm.BookID,m.MadafName from BookMadaf bm join Madaf m on m.MadafID=bm.MadafID'):
    if x['MadafName']:shelves[int(x['BookID'])].add(str(x['MadafName']).strip())
shelf_counts=defaultdict(Counter)
for r,p,aset in pdf_d:
    for m in shelves.get(int(r['ID']),set()):shelf_counts[m][p]+=1

def dominant(c,min_n=1,min_ratio=0.0):
    tot=sum(c.values())
    if tot<min_n or not c:return None
    b,k=c.most_common(1)[0]
    return b if k/tot>=min_ratio else None

def minus(c,label):
    z=c.copy();z[label]-=1
    if z[label]<=0:del z[label]
    return z

# Author counters for agreement experiments.
author=defaultdict(Counter)
for r,p,aset in pdf_d:
    a=n(r['AuthorName'])
    if a:author[a][p]+=1

# Cross-source donor maps: non-PDF -> PDF.
xf=defaultdict(Counter);xta=defaultdict(Counter);xt=defaultdict(Counter);xsa=defaultdict(Counter)
for r,p in non_d:
    fid=str(r['FileID'] or '').strip();t=n(r['BookName']);a=n(r['AuthorName']);s=series(r['BookName'])
    if fid:xf[fid][p]+=1
    if t and a:xta[(t,a)][p]+=1
    if t:xt[t][p]+=1
    if s and a:xsa[(s,a)][p]+=1

def unanimous(c,min_n=1):return dominant(c,min_n,1.0)

def cross_pred(r,method):
    fid=str(r['FileID'] or '').strip();t=n(r['BookName']);a=n(r['AuthorName']);s=series(r['BookName'])
    if method=='fileid' and fid:return unanimous(xf.get(fid,Counter()),1)
    if method=='title_author' and t and a:return unanimous(xta.get((t,a),Counter()),1)
    if method=='series_author' and s and a:return unanimous(xsa.get((s,a),Counter()),1)
    if method=='title' and t:return unanimous(xt.get(t,Counter()),1)
    return None

cross={}
for method in ['fileid','title_author','series_author','title']:
    e=cp=ca=0
    for r,p,aset in pdf_d:
        q=cross_pred(r,method)
        if q:e+=1;cp+=q==p;ca+=q in aset
    cov_no=0;cov_unmapped=0
    for r in pdf:
        q=cross_pred(r,method)
        if not q:continue
        if not str(r['Categories'] or '').strip():cov_no+=1
        elif not primary(parse(r['Categories'])):cov_unmapped+=1
    cross[method]={'eligible_validation':e,'accuracy_primary_pct':round(cp*100/e,2) if e else None,'accuracy_anytopic_pct':round(ca*100/e,2) if e else None,'coverage_no_categories':cov_no,'coverage_unmapped_categories':cov_unmapped}

# Validate combined signals: shelf dominant + title hint; shelf dominant + author signal; title hint + author signal.
combo=[]
for shelf_ratio in [0.80,0.90,0.95]:
  for author_min,author_ratio in [(3,.8),(5,.9),(8,.95),(10,1.0)]:
    stats={k:Counter() for k in ['shelf_title','shelf_author','title_author']}
    # leave-one-out validation
    for r,p,aset in pdf_d:
        th=title_hint(r['BookName'],r['Description'])
        a=n(r['AuthorName']);ac=minus(author[a],p) if a else Counter();ap=dominant(ac,author_min,author_ratio)
        spreds=[]
        for m in shelves.get(int(r['ID']),set()):
            sc=minus(shelf_counts[m],p);q=dominant(sc,30,shelf_ratio)
            if q:spreds.append(q)
        sp=spreds[0] if spreds and len(set(spreds))==1 else None
        tests={'shelf_title':sp if sp and th==sp else None,'shelf_author':sp if sp and ap==sp else None,'title_author':th if th and ap==th else None}
        for k,q in tests.items():
            if q:
                stats[k]['eligible']+=1;stats[k]['correct_primary']+=q==p;stats[k]['correct_any']+=q in aset
    # coverage on category-less PDFs using full counters
    cov={k:0 for k in stats}
    for r in pdf:
        if str(r['Categories'] or '').strip():continue
        th=title_hint(r['BookName'],r['Description']);a=n(r['AuthorName']);ap=dominant(author.get(a,Counter()),author_min,author_ratio) if a else None
        spreds=[]
        for m in shelves.get(int(r['ID']),set()):
            q=dominant(shelf_counts[m],30,shelf_ratio)
            if q:spreds.append(q)
        sp=spreds[0] if spreds and len(set(spreds))==1 else None
        tests={'shelf_title':sp if sp and th==sp else None,'shelf_author':sp if sp and ap==sp else None,'title_author':th if th and ap==th else None}
        for k,q in tests.items():cov[k]+=bool(q)
    for k,c in stats.items():
        e=c['eligible'];combo.append({'method':k,'shelf_ratio':shelf_ratio,'author_min':author_min,'author_ratio':author_ratio,'eligible_validation':e,'accuracy_primary_pct':round(c['correct_primary']*100/e,2) if e else None,'accuracy_anytopic_pct':round(c['correct_any']*100/e,2) if e else None,'coverage_no_categories':cov[k]})

# Remaining category tokens/combinations after expanded closed mapping.
tok=Counter();comb=Counter();unmapped_examples=[];unmapped_rows=0
for r in pdf:
    cats=parse(r['Categories'])
    if cats and not primary(cats):
        unmapped_rows+=1;vals=tuple(sorted(set(cats)))
        comb[vals]+=1
        for x in vals:tok[x]+=1
        if len(unmapped_examples)<100:unmapped_examples.append({'FileID':r['FileID'],'BookName':r['BookName'],'AuthorName':r['AuthorName'],'Categories':cats,'Madaf':sorted(shelves.get(int(r['ID']),set()))})

# FileID overlaps regardless of category, useful schema fact.
pdf_fids={str(r['FileID']) for r in pdf};non_fids={str(r['FileID']) for r in nonpdf}
report={'counts':{'all_rows':len(rows),'pdf_rows':len(pdf),'nonpdf_rows':len(nonpdf),'pdf_donors':len(pdf_d),'nonpdf_donors':len(non_d),'shared_fileids_pdf_nonpdf':len(pdf_fids&non_fids),'pdf_unmapped_category_rows':unmapped_rows},'cross_source':cross,'combined_signals':combo,'top_unmapped_tokens':[{'value':x,'count':c} for x,c in tok.most_common(150)],'top_unmapped_combinations':[{'values':list(x),'count':c} for x,c in comb.most_common(100)],'unmapped_examples':unmapped_examples,'shelf_summary':[{'Madaf':m,'n':sum(c.values()),'top':c.most_common(1)[0][0],'precision_pct':round(c.most_common(1)[0][1]*100/sum(c.values()),2)} for m,c in shelf_counts.items()]}
Path('/kaggle/working/refinement_diagnostic.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
print('COUNTS',json.dumps(report['counts'],ensure_ascii=False))
print('CROSS',json.dumps(cross,ensure_ascii=False))
print('BEST COMBOS',json.dumps(sorted(combo,key=lambda x:(-(x['accuracy_anytopic_pct'] or 0),-x['coverage_no_categories']))[:30],ensure_ascii=False))
print('TOP UNMAPPED TOKENS',json.dumps(report['top_unmapped_tokens'][:100],ensure_ascii=False))
print('TOP UNMAPPED COMBOS',json.dumps(report['top_unmapped_combinations'][:60],ensure_ascii=False))
print('UNMAPPED EXAMPLES',json.dumps(unmapped_examples[:30],ensure_ascii=False))
print('DONE refinement diagnostic only; no Drive; no PDFs')
C.close()
