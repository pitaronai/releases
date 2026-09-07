import re,json,sqlite3,urllib.request,csv
from pathlib import Path
from collections import Counter,defaultdict
import numpy as np
import boto3
from botocore.config import Config
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.svm import LinearSVC
from sklearn.model_selection import StratifiedGroupKFold

PUB='https://raw.githubusercontent.com/yossi-computers/HebrewBooks-2026/main/src/HebrewBooks.Services/HebrewBooks.Services.Downloader/R2MirrorClient.cs'
src=urllib.request.urlopen(urllib.request.Request(PUB,headers={'User-Agent':'HB-FinalV29/1'}),timeout=60).read().decode()
cfg=dict(re.findall(r'(?:private|public)\s+const\s+string\s+(\w+)\s*=\s*"([^"]+)"',src))
s3=boto3.client('s3',endpoint_url=cfg['Endpoint'],aws_access_key_id=cfg['AccessKey'],aws_secret_access_key=cfg['SecretKey'],region_name='auto',config=Config(signature_version='s3v4',s3={'addressing_style':'path'}))
pref=cfg['AppPrefix'].rstrip('/')+'/'
keys=[]
for pg in s3.get_paginator('list_objects_v2').paginate(Bucket=cfg['Bucket'],Prefix=pref):keys += [o['Key'] for o in pg.get('Contents',[])]
ck=next((k for k in keys if k.lower().endswith('/katalog.db')),None) or next(k for k in keys if k.lower().endswith('katalog.db'))
db=Path('/kaggle/working/Katalog.db');s3.download_file(cfg['Bucket'],ck,str(db))
C=sqlite3.connect(f'file:{db}?mode=ro',uri=True);C.row_factory=sqlite3.Row

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
    x=re.sub(r'[^0-9a-zא-ת\s"\']+',' ',x);return ' '.join(x.split())
def series(x):
    x=n(x);old=None
    pats=[r'\s*(חלק|כרך|קונטרס|מחברת)\s+[א-ת0-9]{1,4}\s*$',r'\s*ח["״]?([אבגדהוזחטיכלמנסעפצקרשת])\s*$',r'\s*(חלקים|כרכים)\s+[א-ת0-9\s\-]+$',r'\s*(מהדורה|הוצאה)\s+.{1,40}$']
    while old!=x:
        old=x
        for p in pats:x=re.sub(p,'',x).strip()
    return x

def S(c):return {n(x) for x in c}
def has(s,*v):return any(n(x) in s for x in v)
def first(s,vals):
    for x in vals:
        if n(x) in s:return x
    return None

TRACT=['ברכות','שבת','עירובין','פסחים','יומא','סוכה','ביצה','ראש השנה','תענית','מגילה','מועד קטן','חגיגה','יבמות','כתובות','נדרים','נזיר','סוטה','גיטין','קידושין','בבא קמא','בבא מציעא','בבא בתרא','סנהדרין','מכות','שבועות','עבודה זרה','הוריות','זבחים','מנחות','חולין','בכורות','ערכין','תמורה','כריתות','מעילה','נדה']
SEDARIM=['זרעים','מועד','נשים','נזיקין','קדשים','טהרות']
SA=['אורח חיים','ארח חיים','יורה דעה','אבן העזר','חושן משפט']
HOL=['חנוכה','פורים','פסח','סוכות','יום כיפור','יום הכיפורים','תשעה באב','ל"ג בעומר','חג השבועות','ימים נוראים','שלוש רגלים']
CHASS=['ברסלב','חבד','חב"ד','אלכסנדר','מונקאטש','גור','ויזניץ','סאטמר','סאטמאר','צאנז','קרלין','דינאב','קוזניץ']
HAL={'הלכה','הלכות','רמב"ם','על הרמב"ם','כשרות','על השו"ע','על שולחן ערוך','שולחן ערוך','משנה ברורה','שחיטה','טריפות','ריבית','מקוואות','מקואות','תערובות','מנהגים','נישואין','ברית מילה','חלה','תרי"ג מצוות','תרי"ג מצות','מצוות','פסקי הלכה','פסקי דינים','טור','שטרות','נוסח שטרות','ציצית','תפילין','שביעית','תכלת','בירור הלכה','בירורי הלכה','דינים'}
TAL_STRONG={'מסכת','על הש"ס','על השס','תלמוד בבלי','תלמוד','ירושלמי','אגדות הש"ס','אגדת הש"ס','סוגיות הש"ס','גרסאות הש"ס','גמרא לכל השנה','מסכתות קטנות','ביאור הגמרא','ביאור הגמ','דף על הדף'}
MISH_STRONG={'משנה','משניות','על המשניות','פירוש המשנה','סדר משנה'}

def talmud_context(s,title):
    if any(n(x) in s for x in TAL_STRONG):return True
    t=' '+n(title)+' '
    return any(x in t for x in [' מסכת ',' תלמוד ',' עמ"ס ',' על מסכת ',' גמרא '])
def mishnah_context(s,title):
    if any(n(x) in s for x in MISH_STRONG):return True
    t=' '+n(title)+' '
    return any(x in t for x in [' משניות ',' משנה על ',' פירוש המשנה '])

def signals(cats,title=''):
    s=S(cats);out=set()
    if not s:return out
    if has(s,'ירחון','כתב עת','גליון','שבועון','רבעון'):out.add('כתבי עת וירחונים')
    if has(s,'שו"ת'):out.add('שו"ת')
    if s&{n(x) for x in HAL} or first(s,SA):out.add('הלכה')
    if talmud_context(s,title):out.add('תלמוד וש"ס')
    if mishnah_context(s,title) or has(s,'אבות','פרקי אבות','אבות דרבי נתן',"אבות דר' נתן"):out.add('משנה')
    if first(s,['בראשית','שמות','ויקרא','במדבר','דברים']) or has(s,'עה"ת','על התורה','חומש','רש"י','אונקלוס','מסורה','הפטרות','תורת כהנים','ספרא'):out.add('תורה ומפרשים')
    if first(s,['תהלים','משלי','איוב','שיר השירים','קהלת','אסתר','מגילת אסתר','איכה','רות']) or has(s,'נ"ך','נך','חמש מגילות','מגילות','תנ"ך','על הנ"ך','על תהלים'):out.add('תנ"ך ומגילות')
    if first(s,CHASS) or has(s,'חסידות'):out.add('חסידות')
    if has(s,'קבלה','זהר','זוהר','רמח"ל','רשב"י','קמיעות','סגולות','גלגולים'):out.add('קבלה')
    if has(s,'מוסר','אמונה','השקפה','חיזוק','פילוסופיה','הדרכה','מידות','מדות','לשון הרע','בין אדם לחברו','גאולה','משיח','תשובה','שמירת העיניים','צניעות','קדושה'):out.add('מוסר מחשבה ואמונה')
    if has(s,'דרשות','הספדים','דרוש','דרושים'):out.add('דרשות')
    if has(s,'סידור','מחזור','תפילה','תפילות','פיוט','פיוטים','זמירות','פרק שירה','ביאורי תפילה','התפילה'):out.add('תפילה וסידורים')
    if first(s,HOL) or has(s,'מועדים','הגדה של פסח','חודשי השנה','ראש חודש','ספירת העומר','עומר','שובבי"ם'):out.add('מועדים')
    # Ambiguous holiday/tractate labels count as holiday only with explicit holiday context.
    if has(s,'שבועות') and (has(s,'מועדים','אקדמות','ספירת העומר','עומר','שלוש רגלים') or 'מתן תורה' in n(title)):out.add('מועדים')
    if has(s,'ראש השנה') and has(s,'מועדים','ימים נוראים','יום כיפור','יום הכיפורים','מחזור','שופר','תשליך','אלול'):out.add('מועדים')
    if has(s,'סוכה') and has(s,'סוכות','מועדים','ארבע מינים',"ד' מינים",'לולב'):out.add('מועדים')
    if has(s,'מגילה') and has(s,'פורים'):out.add('מועדים')
    if has(s,'מדרש','מדרשים','מדרש רבה','אגדה','ספרי'):out.add('מדרש ואגדה')
    if has(s,'תולדות','ביוגרפיה','ארץ ישראל','יודאיקה','סיפורים','סיפור','היסטוריה','שואה','מסעות','אישים','זכרונות','זיכרון','מצבות','ירושלים','תימן','יוחסין','יחוס'):out.add('תולדות וביוגרפיה')
    if has(s,'גאונים','ראשונים'):out.add('גאונים וראשונים')
    if has(s,'דקדוק','לשון הקודש','מילון','פירוש המילים','שרשים','קונקורדנציה','שמות נרדפים','טעמי המקרא','טעמים','ראשי תיבות'):out.add('לשון ודקדוק')
    if has(s,'לוח','זמנים','עיבור','תקופות','תכונה','חשבון','אסטרונומיה','קידוש החודש','ברכת החמה','קידוש החמה','קו התאריך','נץ נראה','שקיעה','אלגברה','טבע','חכמת הטבע','לוחות העיבור'):out.add('לוחות זמנים ומדעים')
    if has(s,'פולמוס','ריפורם','ציונות','שבתי צבי','חיון','דע מה שתשיב'):out.add('פולמוסים')
    if has(s,'חינוך','תלמוד תורה','לימוד התורה','לימוד תורה','דרך הלימוד','בר מצוה','שיעורים','בני תורה','בית הספר'):out.add('חינוך ולימוד')
    if has(s,'אגרות','מכתבים','צוואה'):out.add('אגרות ומכתבים')
    if has(s,'קובץ','ספר זכרון','ספר היובל','ספר יובל','מאמרים','ליקוט','ליקוטים','חידושים','פירוש','כללים','דברי תורה','פנינים','קושיות','הערות','בירורים','סיכומים'):out.add('קבצים ואוספים')
    if has(s,'כתב יד','כתבי יד','גנוזות','ביבליוגרפיה','מפתח','אנציקלופדיה','אנציקלופדיא','מראה מקומות'):out.add('ספרנות ומקורות')
    if has(s,'English','יידיש','Español','Français','Português','Русский','לאדינו'):out.add('שפות אחרות')
    return out

def cat_class(cats,title=''):
    s=S(cats)
    if not s:return None
    # Very strong publication/form signals first.
    if has(s,'ירחון','כתב עת','גליון','שבועון','רבעון'):return ('כתבי עת וירחונים','ירחונים' if has(s,'ירחון') else ('גליונות' if has(s,'גליון') else 'כתבי עת'))
    if has(s,'שו"ת'):return ('שו"ת',first(s,SA) or 'כללי')
    if s&{n(x) for x in HAL} or first(s,SA):return ('הלכה',first(s,SA+['רמב"ם','כשרות','שחיטה','מנהגים']) or 'כללי')
    # Prayer and explicit holiday context outrank ambiguous tractate words.
    if has(s,'סידור','מחזור','תפילה','תפילות','פיוט','פיוטים','זמירות','פרק שירה','ביאורי תפילה','התפילה'):return ('תפילה וסידורים',first(s,['סידור','מחזור','תפילה']) or 'כללי')
    hh=first(s,HOL)
    holctx=hh or has(s,'מועדים','הגדה של פסח','חודשי השנה','ראש חודש','ספירת העומר','עומר','שובבי"ם')
    if has(s,'שבועות') and (has(s,'מועדים','אקדמות','ספירת העומר','עומר','שלוש רגלים') or 'מתן תורה' in n(title)):holctx=True;hh=hh or 'שבועות'
    if has(s,'ראש השנה') and has(s,'מועדים','ימים נוראים','יום כיפור','יום הכיפורים','שופר','תשליך','אלול'):holctx=True;hh=hh or 'ראש השנה'
    if has(s,'סוכה') and has(s,'סוכות','מועדים','ארבע מינים',"ד' מינים",'לולב'):holctx=True;hh=hh or 'סוכות'
    if has(s,'מגילה') and has(s,'פורים'):holctx=True;hh=hh or 'פורים'
    if holctx:return ('מועדים','הגדה של פסח' if has(s,'הגדה של פסח') else (hh or 'כללי'))
    # Tanakh/Megillot before the ambiguous word 'מגילה'.
    tnsub=first(s,['תהלים','משלי','איוב','שיר השירים','קהלת','אסתר','מגילת אסתר','איכה','רות'])
    if tnsub or has(s,'נ"ך','נך','חמש מגילות','מגילות','תנ"ך','על הנ"ך','על תהלים'):return ('תנ"ך ומגילות',tnsub or 'כללי')
    # A tractate name never classifies a book by itself. Require a strong Talmud signal.
    if talmud_context(s,title):
        tr=first(s,TRACT)
        return ('תלמוד וש"ס',tr or ('ירושלמי' if has(s,'ירושלמי') else 'כללי'))
    # 'מועד' and other seder names only mean Mishnah with explicit Mishnah context.
    if mishnah_context(s,title) or has(s,'אבות','פרקי אבות','אבות דרבי נתן',"אבות דר' נתן"):
        return ('משנה',first(s,['אבות']+SEDARIM) or 'כללי')
    tor=first(s,['בראשית','שמות','ויקרא','במדבר','דברים'])
    if tor or has(s,'עה"ת','על התורה','חומש','רש"י','אונקלוס','מסורה','הפטרות','תורת כהנים','ספרא'):return ('תורה ומפרשים',tor or 'כללי')
    ch=first(s,CHASS)
    if ch or has(s,'חסידות'):return ('חסידות',ch or 'כללי')
    if has(s,'קבלה','זהר','זוהר','רמח"ל','רשב"י','קמיעות','סגולות','גלגולים'):return ('קבלה','זוהר' if has(s,'זהר','זוהר') else 'כללי')
    if has(s,'מוסר','אמונה','השקפה','חיזוק','פילוסופיה','הדרכה','מידות','מדות','לשון הרע','בין אדם לחברו','גאולה','משיח','תשובה','שמירת העיניים','צניעות','קדושה'):return ('מוסר מחשבה ואמונה','מוסר' if has(s,'מוסר') else 'כללי')
    if has(s,'דרשות','הספדים','דרוש','דרושים'):return ('דרשות','כללי')
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

assigned={};source={};paths={}
for i,r in enumerate(rows):
    cc=cat_class(parse(r['Categories']),r['BookName'])
    if cc:assigned[i]=cc[0];paths[i]=cc;source[i]='categories_v29'

# Conservative donor rows for ML: exactly one independent broad topic signal.
clean=[i for i,r in enumerate(rows) if len(signals(parse(r['Categories']),r['BookName']))==1]
clean_y=np.array([next(iter(signals(parse(rows[i]['Categories']),rows[i]['BookName']))) for i in clean])

def feat(r):
    title=n(r['BookName'])[:240];author=n(r['AuthorName'])[:220];desc=n(r['Description'])[:1200];sh=' '.join(n(x) for x in sorted(shelves.get(int(r['ID']),set())))[:400]
    return f'שם {title} מחבר {author} מדף {sh} תיאור {desc}'
def grp(r):return (series(r['BookName'])+'|'+n(r['AuthorName']))[:500]
clean_groups=np.array([grp(rows[i]) for i in clean])

# Independent group holdout; calibration is separate from holdout.
outer=StratifiedGroupKFold(n_splits=5,shuffle=True,random_state=29)
trcal_pos,hold_pos=next(outer.split(np.zeros(len(clean)),clean_y,clean_groups))
trcal_idx=np.array(clean)[trcal_pos];hold_idx=np.array(clean)[hold_pos]
trcal_y=clean_y[trcal_pos];hold_y=clean_y[hold_pos];trcal_g=clean_groups[trcal_pos]
inner=StratifiedGroupKFold(n_splits=4,shuffle=True,random_state=290)
train_pos,cal_pos=next(inner.split(np.zeros(len(trcal_idx)),trcal_y,trcal_g))
train_idx=trcal_idx[train_pos];cal_idx=trcal_idx[cal_pos];train_y=trcal_y[train_pos];cal_y=trcal_y[cal_pos]
vec=TfidfVectorizer(analyzer='char_wb',ngram_range=(2,5),min_df=2,max_features=120000,sublinear_tf=True,dtype=np.float32)
Xtr=vec.fit_transform([feat(rows[i]) for i in train_idx]);clf=LinearSVC(C=1.2);clf.fit(Xtr,train_y)

def score(indices):
    X=vec.transform([feat(rows[i]) for i in indices]);dec=clf.decision_function(X);ordr=np.argsort(dec,axis=1);pred=clf.classes_[ordr[:,-1]];margin=dec[np.arange(len(indices)),ordr[:,-1]]-dec[np.arange(len(indices)),ordr[:,-2]];return pred,margin
cal_pred,cal_margin=score(cal_idx)
# Choose largest calibration coverage meeting 99.7% precision, >=200 rows.
selected=None
for q in np.linspace(0,0.99,100):
    th=float(np.quantile(cal_margin,q));mask=cal_margin>=th;nmask=int(mask.sum())
    if nmask<200:continue
    acc=float(np.mean(cal_pred[mask]==cal_y[mask]))
    if acc>=0.997:
        cand={'quantile':float(q),'threshold':th,'n':nmask,'coverage_pct':round(100*nmask/len(cal_y),2),'precision_pct':round(100*acc,3)}
        if selected is None or cand['n']>selected['n']:selected=cand
if selected is None:selected={'quantile':1.0,'threshold':999.0,'n':0,'coverage_pct':0,'precision_pct':0}
hold_pred,hold_margin=score(hold_idx);hm=hold_margin>=selected['threshold'];hold_n=int(hm.sum());hold_acc=float(np.mean(hold_pred[hm]==hold_y[hm])) if hold_n else 0.0
ml_gate=hold_n>=200 and hold_acc>=0.995
print('ML SPLIT',json.dumps({'clean':len(clean),'train':len(train_idx),'calibration':len(cal_idx),'holdout':len(hold_idx),'calibration_selected':selected,'holdout_accept':hold_n,'holdout_coverage_pct':round(100*hold_n/len(hold_y),2),'holdout_precision_pct':round(100*hold_acc,3),'gate':ml_gate},ensure_ascii=False))

# Strict author and shelf propagation based on explicit category assignments only.
author=defaultdict(Counter)
for i,r in enumerate(rows):
    if source.get(i)=='categories_v29':
        a=n(r['AuthorName'])
        if a:author[a][assigned[i]]+=1
trusted_author={a:next(iter(c)) for a,c in author.items() if sum(c.values())>=10 and len(c)==1}
shelf_eval=defaultdict(Counter)
for i,r in enumerate(rows):
    if source.get(i)=='categories_v29':
        for m in shelves.get(int(r['ID']),set()):shelf_eval[m][assigned[i]]+=1
trusted_shelf={}
for m,c in shelf_eval.items():
    tot=sum(c.values());top,k=c.most_common(1)[0]
    if tot>=100 and k/tot>=.99:trusted_shelf[m]=top
for i,r in enumerate(rows):
    if i in assigned:continue
    votes={trusted_shelf[m] for m in shelves.get(int(r['ID']),set()) if m in trusted_shelf}
    if len(votes)==1:
        t=next(iter(votes));assigned[i]=t;paths[i]=(t,'כללי');source[i]='validated_madaf';continue
    a=n(r['AuthorName'])
    if a in trusted_author:
        t=trusted_author[a];assigned[i]=t;paths[i]=(t,'כללי');source[i]='author_10_unanimous'

# Use only the independently validated model/threshold, and the SAME trained model to preserve margin calibration.
rem=[i for i in range(len(rows)) if i not in assigned]
ml_accept=0
if ml_gate and rem:
    pred,margin=score(rem)
    for pos,i in enumerate(rem):
        if float(margin[pos])>=selected['threshold']:
            t=str(pred[pos]);assigned[i]=t;paths[i]=(t,'כללי');source[i]='ml_independent_99_5';ml_accept+=1
for i in range(len(rows)):
    if i not in assigned:assigned[i]='לא מסווג';paths[i]=('לא מסווג','כללי');source[i]='unclassified'

# Regression checks for the ambiguity bug discovered by smoke V27.
checks={
 '2576':'מועדים',       # אוצר החגים והמועדים + שבת
 '9721':'תלמוד וש"ס', # מסכת שבועות
 '4247':'מועדים',       # אוצר המועדים - שבועות
 '47141':'הלכה',        # דיני חג הסוכות
 '64265':'משנה',        # משניות ... מועד
 '55985':'תלמוד וש"ס', # על הש"ס + מועד/שבת
 '31423':'תנ"ך ומגילות', # חמש מגילות/קהלת
 '20400':'תפילה וסידורים' # מחזור לראש השנה
}
reg=[]
for fid,exp in checks.items():
    ii=next((i for i,r in enumerate(rows) if str(r['FileID'])==fid),None)
    if ii is not None:reg.append({'FileID':fid,'BookName':rows[ii]['BookName'],'expected':exp,'actual':assigned[ii],'source':source[ii],'pass':assigned[ii]==exp})
reg_ok=all(x['pass'] for x in reg)
sc=Counter(source.values());tc=Counter(assigned.values());tree=Counter(paths.values())
report={'schema':29,'total_pdf':len(rows),'source_counts':dict(sc),'top_counts':dict(tc),'unclassified':sc['unclassified'],'unclassified_pct':round(sc['unclassified']*100/len(rows),2),'trusted_shelves':trusted_shelf,'trusted_author_count':len(trusted_author),'ml':{'clean':len(clean),'calibration':selected,'holdout_accept':hold_n,'holdout_precision_pct':round(100*hold_acc,3),'gate':ml_gate,'unknown_accept':ml_accept},'regression':reg,'regression_ok':reg_ok,'tree':[{'Top':a,'Sub':b,'Count':c} for (a,b),c in sorted(tree.items(),key=lambda x:(-x[1],x[0][0],x[0][1]))]}
Path('/kaggle/working/integrated_final_v29.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
with open('/kaggle/working/integrated_final_assignments_v29.csv','w',newline='',encoding='utf-8-sig') as f:
    fields=['FileID','BookName','AuthorName','Top','Sub','Source'];w=csv.DictWriter(f,fieldnames=fields);w.writeheader()
    for i,r in enumerate(rows):w.writerow({'FileID':r['FileID'],'BookName':r['BookName'],'AuthorName':r['AuthorName'],'Top':paths[i][0],'Sub':paths[i][1],'Source':source[i]})
print('TOTAL',len(rows))
print('SOURCE',json.dumps(sc,ensure_ascii=False))
print('TOP',json.dumps(tc.most_common(),ensure_ascii=False))
print('UNCLASSIFIED',sc['unclassified'],report['unclassified_pct'],'%')
print('TRUSTED SHELVES',json.dumps(trusted_shelf,ensure_ascii=False))
print('TRUSTED AUTHORS',len(trusted_author))
print('ML ACCEPT UNKNOWN',ml_accept)
print('REGRESSION',json.dumps(reg,ensure_ascii=False),'OK',reg_ok)
print('DONE final v29 simulation only; no Drive; no PDFs')
C.close()
