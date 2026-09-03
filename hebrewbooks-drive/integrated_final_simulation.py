import re,json,sqlite3,urllib.request,csv
from pathlib import Path
from collections import Counter,defaultdict
import numpy as np
import boto3
from botocore.config import Config
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.svm import LinearSVC

PUB='https://raw.githubusercontent.com/yossi-computers/HebrewBooks-2026/main/src/HebrewBooks.Services/HebrewBooks.Services.Downloader/R2MirrorClient.cs'
src=urllib.request.urlopen(urllib.request.Request(PUB,headers={'User-Agent':'HB-IntegratedFinal/1'}),timeout=60).read().decode()
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
    pats=[r'\s*(חלק|כרך|קונטרס|מחברת)\s+[א-ת0-9]{1,4}\s*$',r'\s*ח["״]?([אבגדהוזחטיכלמנסעפצקרשת])\s*$',r'\s*(חלקים|כרכים)\s+[א-ת0-9\s\-]+$',r'\s*(מהדורה|הוצאה)\s+.{1,40}$']
    while old!=x:
        old=x
        for p in pats:x=re.sub(p,'',x).strip()
    return x

TRACT=['ברכות','שבת','עירובין','פסחים','יומא','סוכה','ביצה','ראש השנה','תענית','מגילה','מועד קטן','חגיגה','יבמות','כתובות','נדרים','נזיר','סוטה','גיטין','קידושין','בבא קמא','בבא מציעא','בבא בתרא','סנהדרין','מכות','שבועות','עבודה זרה','הוריות','זבחים','מנחות','חולין','בכורות','ערכין','תמורה','כריתות','מעילה','נדה']
SA=['אורח חיים','ארח חיים','יורה דעה','אבן העזר','חושן משפט']
HOL=['חנוכה','פורים','פסח','סוכות','יום כיפור','יום הכיפורים','תשעה באב','ל"ג בעומר','חג השבועות']
CHASS=['ברסלב','חבד','חב"ד','אלכסנדר','מונקאטש','גור','ויזניץ','סאטמר','סאטמאר','צאנז','קרלין']

def S(cats):return {n(x) for x in cats}
def has(s,*v):return any(n(x) in s for x in v)
def first(s,vals):
    for x in vals:
        if n(x) in s:return x
    return None

def cat_class(cats,title=''):
    s=S(cats);tn=' '+n(title)+' '
    if not s:return None
    if has(s,'ירחון','כתב עת','גליון','שבועון','רבעון'):return ('כתבי עת וירחונים','ירחונים' if has(s,'ירחון') else ('גליונות' if has(s,'גליון') else 'כתבי עת'))
    if has(s,'שו"ת'):return ('שו"ת',first(s,SA) or 'כללי')
    hal={'הלכה','רמב"ם','על הרמב"ם','כשרות','על השו"ע','על שולחן ערוך','שולחן ערוך','משנה ברורה','שחיטה','טריפות','ריבית','מקוואות','מקואות','תערובות','מנהגים','נישואין','ברית מילה','חלה','תרי"ג מצוות','תרי"ג מצות','מצוות','פסקי הלכה','פסקי דינים','טור','שטרות','נוסח שטרות','ציצית','תפילין','שביעית','תכלת'}
    if s&{n(x) for x in hal} or first(s,SA):return ('הלכה',first(s,SA+['רמב"ם','כשרות','שחיטה','מנהגים']) or 'כללי')
    # שבועות alone is ambiguous: only Talmud if title/context says tractate.
    tr=first(s,[x for x in TRACT if x!='שבועות'])
    talctx=has(s,'מסכת','על הש"ס','סוגיות','תלמוד בבלי','ירושלמי','אגדות הש"ס','אגדת הש"ס','ביאור הגמ','כללי הש"ס','כללים הש"ס','כללי הש"ס על פי א"ב','הדרנים','ברייתא','סוגיא','בירורי סוגיות','מסכתות קטנות')
    if tr or talctx or (has(s,'שבועות') and any(x in tn for x in [' מסכת ',' תלמוד ',' חידושי ',' סוגיות '])):return ('תלמוד וש"ס',tr or ('שבועות' if has(s,'שבועות') else ('ירושלמי' if has(s,'ירושלמי') else 'כללי')))
    if has(s,'משניות','על המשניות','אבות','פרקי אבות','אבות דרבי נתן',"אבות דר' נתן",'זרעים','מועד','נשים','נזיקין','קדשים','טהרות'):return ('משנה',first(s,['אבות','זרעים','מועד','נשים','נזיקין','קדשים','טהרות']) or 'כללי')
    tor=first(s,['בראשית','שמות','ויקרא','במדבר','דברים'])
    if tor or has(s,'עה"ת','על התורה','חומש','רש"י','אונקלוס','תרגום','מסורה','הפטרות','תורת כהנים','ספרא'):return ('תורה ומפרשים',tor or 'כללי')
    tnsub=first(s,['תהלים','משלי','איוב','שיר השירים','קהלת','אסתר','מגילת אסתר','איכה','רות'])
    if tnsub or has(s,'נ"ך','נך','חמש מגילות','תנ"ך','על הנ"ך','על תהלים'):return ('תנ"ך ומגילות',tnsub or 'כללי')
    ch=first(s,CHASS)
    if ch or has(s,'חסידות'):return ('חסידות',ch or 'כללי')
    if has(s,'קבלה','זהר','זוהר','רמח"ל','רשב"י','קמיעות','סגולות','גלגולים'):return ('קבלה','זוהר' if has(s,'זהר','זוהר') else 'כללי')
    if has(s,'מוסר','אמונה','השקפה','חיזוק','פילוסופיה','הדרכה','מידות','מדות','לשון הרע','בין אדם לחברו','גאולה','משיח','תשובה','שמירת העיניים','צניעות','קדושה'):return ('מוסר מחשבה ואמונה','מוסר' if has(s,'מוסר') else 'כללי')
    if has(s,'דרשות','הספדים','דרוש','דרושים'):return ('דרשות','כללי')
    if has(s,'סידור','מחזור','תפילה','תפילות','פיוט','פיוטים','זמירות','פרק שירה','ביאורי תפילה'):return ('תפילה וסידורים',first(s,['סידור','מחזור','תפילה']) or 'כללי')
    hh=first(s,HOL)
    if hh or has(s,'מועדים','הגדה של פסח','ימים נוראים','שבועות'):
        return ('מועדים','הגדה של פסח' if has(s,'הגדה של פסח') else (hh or ('שבועות' if has(s,'שבועות') else 'כללי')))
    if has(s,'מדרש','מדרשים','מדרש רבה','אגדה','ספרי'):return ('מדרש ואגדה','מדרש' if has(s,'מדרש','מדרשים','מדרש רבה') else 'אגדה')
    if has(s,'תולדות','ביוגרפיה','ארץ ישראל','יודאיקה','סיפורים','סיפור','היסטוריה','שואה','מסעות','אישים','זכרונות','זיכרון','מצבות','ירושלים','תימן','יוחסין','יחוס'):return ('תולדות וביוגרפיה','תולדות' if has(s,'תולדות') else 'כללי')
    if has(s,'גאונים','ראשונים'):return ('גאונים וראשונים','גאונים' if has(s,'גאונים') else 'ראשונים')
    if has(s,'דקדוק','לשון הקודש','מילון','פירוש המילים','שרשים','קונקורדנציה','שמות נרדפים','טעמי המקרא','טעמים','ראשי תיבות'):return ('לשון ודקדוק','כללי')
    if has(s,'לוח','זמנים','עיבור','תקופות','תכונה','חשבון','אסטרונומיה','קידוש החודש','ברכת החמה','קידוש החמה','קו התאריך','נץ נראה','שקיעה','אלגברה','טבע','חכמת הטבע','לוחות העיבור'):return ('לוחות זמנים ומדעים','כללי')
    if has(s,'פולמוס','ריפורם','ציונות','שבתי צבי','חיון','דע מה שתשיב'):return ('פולמוסים','כללי')
    if has(s,'חינוך','תלמוד תורה','לימוד התורה','לימוד תורה','דרך הלימוד','בר מצוה','שיעורים','בני תורה','בית הספר'):return ('חינוך ולימוד','כללי')
    if has(s,'אגרות','מכתבים','צוואה'):return ('אגרות ומכתבים','כללי')
    if has(s,'קובץ','ספר זכרון','ספר היובל','ספר יובל','מאמרים','ליקוט','ליקוטים','חידושים','פירוש','כללים','דברי תורה','פנינים','קושיות','הערות','בירורים','סיכומים'):return ('קבצים ואוספים','כללי')
    if has(s,'כתב יד','כתבי יד','גנוזות','ביבליוגרפיה','מפתח','אנציקלופדיה','אנציקלופדיא','מראה מקומות'):return ('ספרנות ומקורות','כללי')
    if has(s,'English','יידיש','Español','Français','Português','Русский','לאדינו'):return ('שפות אחרות','אנגלית' if has(s,'English') else ('יידיש' if has(s,'יידיש') else 'שפות אחרות'))
    return None

rows=[dict(r) for r in C.execute("select ID,FileID,BookName,AuthorName,Description,Categories from Katalog where lower(SourceType)='pdf' order by ID")]
shelves=defaultdict(set)
for x in C.execute('select bm.BookID,m.MadafName from BookMadaf bm join Madaf m on m.MadafID=bm.MadafID'):
    if x['MadafName']:shelves[int(x['BookID'])].add(str(x['MadafName']).strip())
# explicit broad topic sets for model training
def topics(cats,title=''):
    cc=cat_class(cats,title);return {cc[0]} if cc else set()
# category classification first
assigned={};source={};paths={}
for i,r in enumerate(rows):
    cc=cat_class(parse(r['Categories']),r['BookName'])
    if cc:assigned[i]=cc[0];paths[i]=cc;source[i]='categories'
# strict author pattern from category-labelled PDFs
author=defaultdict(Counter)
for i,r in enumerate(rows):
    if i in assigned:
        a=n(r['AuthorName'])
        if a:author[a][assigned[i]]+=1
trusted_author={a:next(iter(c)) for a,c in author.items() if sum(c.values())>=10 and len(c)==1}
# calibrated shelf topics (only robust shelves with >=100 labelled and >=99% agreement)
shelf_eval=defaultdict(Counter)
for i,r in enumerate(rows):
    if i in assigned:
        for m in shelves.get(int(r['ID']),set()):shelf_eval[m][assigned[i]]+=1
trusted_shelf={}
for m,c in shelf_eval.items():
    tot=sum(c.values());top,k=c.most_common(1)[0]
    if tot>=100 and k/tot>=.99:trusted_shelf[m]=top
# Apply trusted shelves first, then strict author.
for i,r in enumerate(rows):
    if i in assigned:continue
    votes={trusted_shelf[m] for m in shelves.get(int(r['ID']),set()) if m in trusted_shelf}
    if len(votes)==1:
        t=next(iter(votes));assigned[i]=t;paths[i]=(t,'כללי');source[i]='validated_madaf';continue
    a=n(r['AuthorName'])
    if a in trusted_author:
        t=trusted_author[a];assigned[i]=t;paths[i]=(t,'כללי');source[i]='author_10_unanimous'
# ML train only on category-labelled rows; conservative global margin threshold validated in v24.
def feat(r):
    title=n(r['BookName'])[:240];authorx=n(r['AuthorName'])[:220];desc=n(r['Description'])[:1200];sh=' '.join(n(x) for x in sorted(shelves.get(int(r['ID']),set())))[:400]
    return f'שם {title} מחבר {authorx} מדף {sh} תיאור {desc}'
train_idx=[i for i,r in enumerate(rows) if source.get(i)=='categories']
Xtxt=[feat(rows[i]) for i in train_idx];y=np.array([assigned[i] for i in train_idx])
vec=TfidfVectorizer(analyzer='char_wb',ngram_range=(2,5),min_df=2,max_features=120000,sublinear_tf=True,dtype=np.float32)
X=vec.fit_transform(Xtxt);clf=LinearSVC(C=1.2);clf.fit(X,y)
rem=[i for i in range(len(rows)) if i not in assigned]
if rem:
    Xu=vec.transform([feat(rows[i]) for i in rem]);dec=clf.decision_function(Xu);ordr=np.argsort(dec,axis=1)
    pred=clf.classes_[ordr[:,-1]];margin=dec[np.arange(len(rem)),ordr[:,-1]]-dec[np.arange(len(rem)),ordr[:,-2]]
    for pos,i in enumerate(rem):
        if float(margin[pos])>=1.859419:
            t=str(pred[pos]);assigned[i]=t;paths[i]=(t,'כללי');source[i]='ml_99_75';
# finish unclassified
for i in range(len(rows)):
    if i not in assigned:
        assigned[i]='לא מסווג';paths[i]=('לא מסווג','כללי');source[i]='unclassified'
sc=Counter(source.values());tc=Counter(assigned.values());tree=Counter(paths.values())
report={'total_pdf':len(rows),'source_counts':dict(sc),'top_counts':dict(tc),'unclassified':sc['unclassified'],'unclassified_pct':round(sc['unclassified']*100/len(rows),2),'trusted_shelves':trusted_shelf,'trusted_author_count':len(trusted_author),'tree':[{'Top':a,'Sub':b,'Count':c} for (a,b),c in sorted(tree.items(),key=lambda x:(-x[1],x[0][0],x[0][1]))]}
Path('/kaggle/working/integrated_final_simulation.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
with open('/kaggle/working/integrated_final_assignments.csv','w',newline='',encoding='utf-8-sig') as f:
    fields=['FileID','BookName','AuthorName','Top','Sub','Source'];w=csv.DictWriter(f,fieldnames=fields);w.writeheader()
    for i,r in enumerate(rows):w.writerow({'FileID':r['FileID'],'BookName':r['BookName'],'AuthorName':r['AuthorName'],'Top':paths[i][0],'Sub':paths[i][1],'Source':source[i]})
print('TOTAL',len(rows))
print('SOURCE',json.dumps(sc,ensure_ascii=False))
print('TOP',json.dumps(tc.most_common(),ensure_ascii=False))
print('UNCLASSIFIED',sc['unclassified'],report['unclassified_pct'],'%')
print('TRUSTED SHELVES',json.dumps(trusted_shelf,ensure_ascii=False))
print('TRUSTED AUTHORS',len(trusted_author))
print('TREE',json.dumps(report['tree'][:100],ensure_ascii=False))
print('DONE integrated simulation only; no Drive; no PDFs')
C.close()
