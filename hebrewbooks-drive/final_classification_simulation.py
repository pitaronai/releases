import re, json, sqlite3, urllib.request, csv
from pathlib import Path
from collections import Counter, defaultdict
import boto3
from botocore.config import Config

PUB='https://raw.githubusercontent.com/yossi-computers/HebrewBooks-2026/main/src/HebrewBooks.Services/HebrewBooks.Services.Downloader/R2MirrorClient.cs'
src=urllib.request.urlopen(urllib.request.Request(PUB,headers={'User-Agent':'HB-FinalSimulation/1'}),timeout=60).read().decode()
cfg=dict(re.findall(r'(?:private|public)\s+const\s+string\s+(\w+)\s*=\s*"([^"]+)"',src))
s3=boto3.client('s3',endpoint_url=cfg['Endpoint'],aws_access_key_id=cfg['AccessKey'],aws_secret_access_key=cfg['SecretKey'],region_name='auto',config=Config(signature_version='s3v4',s3={'addressing_style':'path'}))
pref=cfg['AppPrefix'].rstrip('/')+'/'
keys=[]
for pg in s3.get_paginator('list_objects_v2').paginate(Bucket=cfg['Bucket'],Prefix=pref):
    keys += [o['Key'] for o in pg.get('Contents',[])]
ck=next((k for k in keys if k.lower().endswith('/katalog.db')),None) or next(k for k in keys if k.lower().endswith('katalog.db'))
db=Path('/kaggle/working/Katalog.db'); s3.download_file(cfg['Bucket'],ck,str(db))
C=sqlite3.connect(f'file:{db}?mode=ro',uri=True); C.row_factory=sqlite3.Row; C.create_collation('HEB',lambda a,b:(str(a)>str(b))-(str(a)<str(b)))

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
    except Exception:
        return [x.strip() for x in re.split(r'\s*[|;>]\s*',v) if x.strip()]

def n(x):
    x=str(x or '').replace('״','"').replace('“','"').replace('”','"').replace('׳',"'").lower()
    x=re.sub(r'[^0-9a-zא-ת\s"\']+',' ',x)
    return ' '.join(x.split())

# Book -> Madaf map.
shelves=defaultdict(set)
for x in C.execute('select bm.BookID,m.MadafName from BookMadaf bm join Madaf m on m.MadafID=bm.MadafID'):
    if x['MadafName']:shelves[int(x['BookID'])].add(str(x['MadafName']).strip())

TRACT=['ברכות','שבת','עירובין','פסחים','יומא','סוכה','ביצה','ראש השנה','תענית','מגילה','מועד קטן','חגיגה','יבמות','כתובות','נדרים','נזיר','סוטה','גיטין','קידושין','בבא קמא','בבא מציעא','בבא בתרא','סנהדרין','מכות','שבועות','עבודה זרה','הוריות','זבחים','מנחות','חולין','בכורות','ערכין','תמורה','כריתות','מעילה','נדה']
SA=['אורח חיים','יורה דעה','אבן העזר','חושן משפט']
CHASS=['ברסלב','חבד','חב"ד','אלכסנדר','מונקאטש','גור','ויזניץ','סאטמר','סאטמאר','צאנז','קרלין']
HOL=['ראש השנה','יום כיפור','יום הכיפורים','סוכות','חנוכה','פורים','פסח','שבועות','תשעה באב','ל"ג בעומר']
MISH=['אבות','פרקי אבות','זרעים','מועד','נשים','נזיקין','קדשים','טהרות']
TORAH=['בראשית','שמות','ויקרא','במדבר','דברים']
TANAKH=['תהלים','משלי','איוב','שיר השירים','קהלת','אסתר','מגילת אסתר','איכה','רות']

def ns(cats):return {n(x) for x in cats}
def has(S,*vals):return any(n(v) in S for v in vals)
def first(S,vals):
    for v in vals:
        if n(v) in S:return v
    return None

def cat_class(cats):
    S=ns(cats)
    if not S:return None
    if has(S,'ירחון','כתב עת','גליון','שבועון','רבעון'):
        sub='ירחונים' if has(S,'ירחון') else ('גליונות' if has(S,'גליון') else 'כתבי עת')
        return ('כתבי עת וירחונים',sub)
    if has(S,'שו"ת'):return ('שו"ת',first(S,SA) or 'כללי')
    hal=['הלכה','רמב"ם','כשרות','על השו"ע','בירורי הלכה','בירור הלכה','שחיטה','טריפות','ריבית','מקוואות','תערובות','מנהגים','נישואין','ברית מילה','חלה','תרי"ג מצוות','מצוות','פסקי הלכה','פסקי דינים','טור','שטרות','נוסח שטרות','ציצית','תפילין','שביעית','תכלת']
    if any(n(x) in S for x in hal):return ('הלכה',first(S,SA+['רמב"ם','כשרות','שחיטה','מנהגים']) or 'כללי')
    tr=first(S,TRACT)
    if tr or has(S,'מסכת','על הש"ס','סוגיות','תלמוד בבלי','ירושלמי','אגדות הש"ס','ביאור הגמ','כללי הש"ס','הדרנים','ברייתא','סוגיא','בירורי סוגיות'):
        return ('תלמוד וש"ס',tr or ('ירושלמי' if has(S,'ירושלמי') else 'כללי'))
    mi=first(S,MISH)
    if mi or has(S,'משניות','על המשניות'):return ('משנה',mi or 'כללי')
    tor=first(S,TORAH)
    if tor or has(S,'עה"ת','על התורה','חומש','רש"י','אונקלוס','תרגום','מסורה','הפטרות','תורת כהנים','ספרא'):
        return ('תורה ומפרשים',tor or 'כללי')
    tn=first(S,TANAKH)
    if tn or has(S,'נ"ך','חמש מגילות','תנ"ך','על הנ"ך'):return ('תנ"ך ומגילות',tn or 'כללי')
    ch=first(S,CHASS)
    if ch or has(S,'חסידות'):return ('חסידות',ch or 'כללי')
    if has(S,'קבלה','זהר','רמח"ל','רשב"י','קמיעות','סגולות'):return ('קבלה','זוהר' if has(S,'זהר') else 'כללי')
    mm=['מוסר','אמונה','השקפה','חיזוק','פילוסופיה','הדרכה','מידות','מדות','לשון הרע','בין אדם לחברו','גאולה','משיח','תשובה']
    if any(n(x) in S for x in mm):return ('מוסר מחשבה ואמונה',first(S,['מוסר','אמונה','השקפה','חיזוק']) or 'כללי')
    if has(S,'דרשות','הספדים'):return ('דרשות','כללי')
    if has(S,'סידור','מחזור','תפילה','תפילות','פיוט','פיוטים','זמירות','פרק שירה'):return ('תפילה וסידורים',first(S,['סידור','מחזור','תפילה']) or 'כללי')
    hh=first(S,HOL)
    if hh or has(S,'מועדים','הגדה של פסח','ימים נוראים'):
        return ('מועדים','הגדה של פסח' if has(S,'הגדה של פסח') else (hh or 'כללי'))
    if has(S,'מדרש','אגדה'):return ('מדרש ואגדה','מדרש' if has(S,'מדרש') else 'אגדה')
    bio=['תולדות','ביוגרפיה','ארץ ישראל','יודאיקה','סיפורים','היסטוריה','שואה','מסעות','אישים','זכרונות','מצבות','ירושלים','תימן']
    if any(n(x) in S for x in bio):return ('תולדות וביוגרפיה',first(S,['תולדות','ארץ ישראל','סיפורים']) or 'כללי')
    if has(S,'גאונים','ראשונים'):return ('גאונים וראשונים','גאונים' if has(S,'גאונים') else 'ראשונים')
    if has(S,'דקדוק','לשון הקודש','מילון','פירוש המילים','שרשים','קונקורדנציה','שמות נרדפים','טעמי המקרא','טעמים'):
        return ('לשון ודקדוק','כללי')
    if has(S,'לוח','זמנים','עיבור','תקופות','תכונה','חשבון','אסטרונומיה','קידוש החודש','ברכת החמה','קו התאריך','נץ נראה','שקיעה','אלגברה','טבע','חכמת הטבע'):
        return ('לוחות זמנים ומדעים','כללי')
    if has(S,'פולמוס','ריפורם','ציונות','שבתי צבי','חיון'):return ('פולמוסים','כללי')
    if has(S,'חינוך','תלמוד תורה','לימוד התורה','דרך הלימוד','בר מצוה','שיעורים'):return ('חינוך ולימוד','כללי')
    if has(S,'אגרות','מכתבים','צוואה'):return ('אגרות ומכתבים','כללי')
    if has(S,'קובץ','ספר זכרון','ספר היובל','מאמרים','ליקוט','ליקוטים','חידושים','פירוש','כללים','דברי תורה'):
        return ('קבצים ואוספים','כללי')
    if has(S,'כתב יד','כתבי יד','גנוזות','ביבליוגרפיה','מפתח','אנציקלופדיה','מראה מקומות'):
        return ('ספרנות ומקורות','כללי')
    if has(S,'English','יידיש','Español','Français'):
        sub='אנגלית' if has(S,'English') else ('יידיש' if has(S,'יידיש') else 'שפות אחרות')
        return ('שפות אחרות',sub)
    return None

rows=[dict(r) for r in C.execute("select ID,FileID,BookName,AuthorName,Description,Categories from Katalog where lower(SourceType)='pdf' order by ID")]
# Explicit-category donors.
donors=[]
for r in rows:
    cc=cat_class(parse(r['Categories']))
    if cc:donors.append((r,cc[0]))

# Strict author inheritance: >=10 explicit-category donor books and 100% same top-level topic.
author=defaultdict(Counter)
for r,top in donors:
    a=n(r['AuthorName'])
    if a:author[a][top]+=1
trusted_author={a:next(iter(c)) for a,c in author.items() if sum(c.values())>=10 and len(c)==1}

# Calibrate each Madaf against explicit-category donors. Only use shelves with >=30 comparable records and >=98% agreement.
shelf_eval=defaultdict(Counter)
for r,top in donors:
    for m in shelves.get(int(r['ID']),set()):shelf_eval[m][top]+=1
trusted_shelf={}
shelf_report=[]
for m,c in shelf_eval.items():
    tot=sum(c.values()); top,k=c.most_common(1)[0]
    prec=k/tot if tot else 0
    shelf_report.append({'Madaf':m,'comparable':tot,'topic':top,'precision_pct':round(prec*100,2),'distribution':dict(c)})
    if tot>=30 and prec>=0.98:trusted_shelf[m]=top
shelf_report.sort(key=lambda x:(-x['precision_pct'],-x['comparable'],x['Madaf']))

# High-precision title heuristics from the previous holdout tuning:
# periodicals using name+description ~=99.5%; holidays using name+description ~=98.5%; Mishnah name-only ~=99.35%.
def title_high_precision(r):
    name=' '+n(r['BookName'])+' '; desc=' '+n(r['Description'])+' '; both=name+desc
    if any(x in both for x in [' ירחון ',' כתב עת ',' שבועון ',' רבעון ']):return ('כתבי עת וירחונים','כללי')
    if ' הגדה של פסח ' in both:return ('מועדים','הגדה של פסח')
    for h in [' חנוכה ',' פורים ',' פסח ',' סוכות ',' יום כיפור ',' יום הכיפורים ',' ראש השנה ',' שבועות ',' תשעה באב ',' ל"ג בעומר ']:
        if h in both:return ('מועדים',h.strip())
    if ' משניות ' in name:return ('משנה','כללי')
    return None

# For inherited top-level topics we keep subfolder fixed and conservative.
def inherited_path(top):return (top,'כללי')

source=Counter(); tree=Counter(); top_counts=Counter(); un=[]; all_out=[]
for r in rows:
    cats=parse(r['Categories']); cc=cat_class(cats)
    if cc:
        path=cc;src='categories'
    else:
        path=None;src=None
        # Madaf only if the shelf itself proved >=98% precise against category-labelled books.
        votes=Counter(trusted_shelf[m] for m in shelves.get(int(r['ID']),set()) if m in trusted_shelf)
        if votes:
            top,k=votes.most_common(1)[0]
            # require no trusted-shelf conflict
            if len(votes)==1:path=inherited_path(top);src='validated_madaf'
        if path is None:
            a=n(r['AuthorName'])
            if a in trusted_author:path=inherited_path(trusted_author[a]);src='author_10_unanimous'
        if path is None:
            tp=title_high_precision(r)
            if tp:path=tp;src='high_precision_title'
    if path is None:
        path=('לא מסווג','כללי');src='unclassified'
    source[src]+=1;tree[path]+=1;top_counts[path[0]]+=1
    rec={'FileID':r['FileID'],'BookName':r['BookName'],'AuthorName':r['AuthorName'],'Categories':r['Categories'],'Madaf':sorted(shelves.get(int(r['ID']),set())),'Top':path[0],'Sub':path[1],'Source':src}
    all_out.append(rec)
    if src=='unclassified' and len(un)<250:un.append(rec)

report={
 'total_pdf':len(rows),'rows_with_explicit_category_mapping':source['categories'],
 'source_counts':dict(source),'top_counts':dict(top_counts),
 'unclassified':source['unclassified'],'unclassified_pct':round(source['unclassified']*100/len(rows),2),
 'trusted_author_count':len(trusted_author),'trusted_shelves':trusted_shelf,'shelf_validation':shelf_report,
 'tree':[{'Top':a,'Sub':b,'Count':c} for (a,b),c in sorted(tree.items(),key=lambda x:(-x[1],x[0][0],x[0][1]))],
 'unclassified_examples':un
}
Path('/kaggle/working/final_classification_simulation.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
with open('/kaggle/working/final_classification_tree.csv','w',newline='',encoding='utf-8-sig') as f:
    w=csv.DictWriter(f,fieldnames=['Top','Sub','Count']);w.writeheader();w.writerows(report['tree'])
with open('/kaggle/working/final_classification_assignments.csv','w',newline='',encoding='utf-8-sig') as f:
    fields=['FileID','BookName','AuthorName','Categories','Madaf','Top','Sub','Source'];w=csv.DictWriter(f,fieldnames=fields);w.writeheader()
    for r in all_out:
        x=r.copy();x['Madaf']=' | '.join(x['Madaf']);w.writerow(x)
print('TOTAL',len(rows))
print('SOURCE',json.dumps(source,ensure_ascii=False))
print('TOP',json.dumps(top_counts.most_common(),ensure_ascii=False))
print('UNCLASSIFIED',source['unclassified'],report['unclassified_pct'],'%')
print('TRUSTED AUTHORS',len(trusted_author))
print('TRUSTED MADAF',json.dumps(trusted_shelf,ensure_ascii=False))
print('TOP SHELF VALIDATION',json.dumps(shelf_report[:25],ensure_ascii=False))
print('TREE',json.dumps(report['tree'][:100],ensure_ascii=False))
print('UNCLASSIFIED EXAMPLES',json.dumps(un[:40],ensure_ascii=False))
print('DONE final simulation only; no Drive; no PDFs')
C.close()
