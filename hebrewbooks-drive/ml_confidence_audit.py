import re,json,sqlite3,urllib.request
from pathlib import Path
from collections import Counter,defaultdict
import numpy as np
import boto3
from botocore.config import Config
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.model_selection import GroupKFold
from sklearn.svm import LinearSVC
from sklearn.metrics import accuracy_score

PUB='https://raw.githubusercontent.com/yossi-computers/HebrewBooks-2026/main/src/HebrewBooks.Services/HebrewBooks.Services.Downloader/R2MirrorClient.cs'
src=urllib.request.urlopen(urllib.request.Request(PUB,headers={'User-Agent':'HB-MLAudit/1'}),timeout=60).read().decode()
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

TRACT={'ברכות','שבת','עירובין','פסחים','יומא','סוכה','ביצה','ראש השנה','תענית','מגילה','מועד קטן','חגיגה','יבמות','כתובות','נדרים','נזיר','סוטה','גיטין','קידושין','בבא קמא','בבא מציעא','בבא בתרא','סנהדרין','מכות','שבועות','עבודה זרה','הוריות','זבחים','מנחות','חולין','בכורות','ערכין','תמורה','כריתות','מעילה','נדה'}
RULES=[
('כתבי עת וירחונים',{'ירחון','כתב עת','גליון','שבועון','רבעון'}),('שו"ת',{'שו"ת'}),
('הלכה',{'הלכה','רמב"ם','כשרות','על השו"ע','על שולחן ערוך','שולחן ערוך','אורח חיים','ארח חיים','יורה דעה','אבן העזר','חושן משפט','בירורי הלכה','בירור הלכה','שחיטה','טריפות','ריבית','מקוואות','מקואות','תערובות','מנהגים','נישואין','ברית מילה','חלה','תרי"ג מצוות','תרי"ג מצות','מצוות','פסקי הלכה','פסקי דינים','טור','שטרות','נוסח שטרות','ציצית','תפילין','שביעית','תכלת','משנה ברורה'}),
('תלמוד וש"ס',TRACT|{'מסכת','על הש"ס','סוגיות','תלמוד בבלי','ירושלמי','אגדות הש"ס','אגדת הש"ס','ביאור הגמ','כללי הש"ס','כללים הש"ס','הדרנים','ברייתא','סוגיא','בירורי סוגיות','מסכתות קטנות'}),
('משנה',{'משניות','על המשניות','אבות','פרקי אבות','אבות דרבי נתן','אבות דר\' נתן','זרעים','מועד','נשים','נזיקין','קדשים','טהרות'}),
('תורה ומפרשים',{'עה"ת','על התורה','חומש','בראשית','שמות','ויקרא','במדבר','דברים','רש"י','אונקלוס','תרגום','מסורה','הפטרות','תורת כהנים','ספרא','על תהלים'}),
('תנ"ך ומגילות',{'נ"ך','נך','חמש מגילות','תנ"ך','על הנ"ך','תהלים','משלי','איוב','שיר השירים','קהלת','אסתר','מגילת אסתר','איכה','רות'}),
('חסידות',{'חסידות','ברסלב','חבד','חב"ד','אלכסנדר','מונקאטש','גור','ויזניץ','סאטמר','סאטמאר','צאנז','קרלין'}),
('קבלה',{'קבלה','זהר','זוהר','רמח"ל','רשב"י','קמיעות','סגולות','גלגולים'}),
('מוסר מחשבה ואמונה',{'מוסר','אמונה','השקפה','חיזוק','פילוסופיה','הדרכה','מידות','מדות','לשון הרע','בין אדם לחברו','גאולה','משיח','תשובה','פתגמים','שמירת העיניים','צניעות','קדושה'}),
('דרשות',{'דרשות','הספדים','דרוש','דרושים'}),('תפילה וסידורים',{'סידור','מחזור','תפילה','תפילות','פיוט','פיוטים','זמירות','פרק שירה','ביאורי תפילה'}),
('מועדים',{'מועדים','הגדה של פסח','ימים נוראים','חנוכה','פורים','פסח','סוכות','יום כיפור','יום הכיפורים','שבועות','חג השבועות','תשעה באב','ל"ג בעומר','שובבי"ם'}),
('מדרש ואגדה',{'מדרש','מדרשים','מדרש רבה','אגדה','ספרי'}),('תולדות וביוגרפיה',{'תולדות','ביוגרפיה','ארץ ישראל','יודאיקה','סיפורים','סיפור','היסטוריה','שואה','מסעות','אישים','זכרונות','זיכרון','מצבות','ירושלים','תימן','יוחסין','יחוס'}),
('גאונים וראשונים',{'גאונים','ראשונים'}),('לשון ודקדוק',{'דקדוק','לשון הקודש','מילון','פירוש המילים','שרשים','קונקורדנציה','שמות נרדפים','טעמי המקרא','טעמים','ראשי תיבות'}),
('לוחות זמנים ומדעים',{'לוח','זמנים','עיבור','תקופות','תכונה','חשבון','אסטרונומיה','קידוש החודש','ברכת החמה','קידוש החמה','קו התאריך','נץ נראה','שקיעה','אלגברה','טבע','חכמת הטבע','לוחות העיבור'}),
('פולמוסים',{'פולמוס','ריפורם','ציונות','שבתי צבי','חיון','דע מה שתשיב'}),('חינוך ולימוד',{'חינוך','תלמוד תורה','לימוד התורה','לימוד תורה','דרך הלימוד','בר מצוה','שיעורים','בני תורה','בית הספר'}),
('אגרות ומכתבים',{'אגרות','מכתבים','צוואה'}),('קבצים ואוספים',{'קובץ','ספר זכרון','ספר היובל','ספר יובל','מאמרים','ליקוט','ליקוטים','חידושים','פירוש','כללים','דברי תורה','פנינים','קושיות','הערות','בירורים','סיכומים'}),
('ספרנות ומקורות',{'כתב יד','כתבי יד','גנוזות','ביבליוגרפיה','מפתח','אנציקלופדיה','אנציקלופדיא','מראה מקומות'}),('שפות אחרות',{'english','יידיש','español','français','português','русский','לאדינו'})]
RULES=[(lab,{n(x) for x in tags}) for lab,tags in RULES]
def topic_set(cats):
    S={n(x) for x in cats};return {lab for lab,tags in RULES if S&tags}

a_by_id=defaultdict(set)
for x in C.execute('select bm.BookID,m.MadafName from BookMadaf bm join Madaf m on m.MadafID=bm.MadafID'):
    if x['MadafName']:a_by_id[int(x['BookID'])].add(str(x['MadafName']).strip())
rows=[dict(r) for r in C.execute("select ID,FileID,BookName,AuthorName,Description,Categories from Katalog where lower(SourceType)='pdf' order by ID")]

def feat(r):
    title=n(r['BookName'])[:240];author=n(r['AuthorName'])[:220];desc=n(r['Description'])[:1200]
    shelf=' '.join(n(x) for x in sorted(a_by_id.get(int(r['ID']),set())))[:400]
    return f'שם {title} מחבר {author} מדף {shelf} תיאור {desc}'

all_topics=[];clean_idx=[];clean_y=[];groups=[]
for i,r in enumerate(rows):
    ts=topic_set(parse(r['Categories']));all_topics.append(ts)
    if len(ts)==1:
        clean_idx.append(i);clean_y.append(next(iter(ts)))
        groups.append(series(r['BookName'])+'|'+n(r['AuthorName']) if series(r['BookName']) else 'id:'+str(r['FileID']))
texts=[feat(r) for r in rows]
train_text=[texts[i] for i in clean_idx]
y=np.array(clean_y);groups=np.array(groups)
print('PDF',len(rows),'CLEAN SINGLE TOPIC',len(clean_idx),'CLASSES',len(set(clean_y)))
vec=TfidfVectorizer(analyzer='char_wb',ngram_range=(2,5),min_df=2,max_features=120000,sublinear_tf=True,dtype=np.float32)
X=vec.fit_transform(train_text)
classes=np.array(sorted(set(clean_y)))
oof_pred=np.empty(len(y),dtype=object);oof_conf=np.full(len(y),np.nan,dtype=float)
gkf=GroupKFold(n_splits=3)
folds=[]
for fi,(tr,va) in enumerate(gkf.split(X,y,groups),1):
    clf=LinearSVC(C=1.2)
    clf.fit(X[tr],y[tr])
    dec=clf.decision_function(X[va])
    order=np.argsort(dec,axis=1)
    pred=clf.classes_[order[:,-1]];margin=dec[np.arange(len(va)),order[:,-1]]-dec[np.arange(len(va)),order[:,-2]]
    oof_pred[va]=pred;oof_conf[va]=margin
    folds.append({'fold':fi,'n':len(va),'accuracy_pct':round(accuracy_score(y[va],pred)*100,2)})
base_acc=float(np.mean(oof_pred==y))
# confidence coverage table
quant=[]
for q in [0.0,.25,.5,.6,.7,.75,.8,.85,.9,.92,.94,.95,.96,.97,.98,.99]:
    th=float(np.quantile(oof_conf,q));mask=oof_conf>=th;n=int(mask.sum());acc=float(np.mean(oof_pred[mask]==y[mask])) if n else 0
    quant.append({'quantile':q,'margin_threshold':round(th,6),'validation_n':n,'validation_coverage_pct':round(n*100/len(y),2),'accuracy_pct':round(acc*100,2)})
# select most-covered global threshold with >=98.5% accuracy and >=200 validation examples
cands=[x for x in quant if x['validation_n']>=200 and x['accuracy_pct']>=98.5]
global_sel=max(cands,key=lambda x:x['validation_n']) if cands else max(quant,key=lambda x:x['accuracy_pct'])
# per-class thresholds: largest high-confidence prefix with cumulative precision >=98.5%, min 40 eval rows
class_thr={};class_eval={}
for cl in classes:
    ids=np.where(oof_pred==cl)[0]
    ids=ids[np.argsort(-oof_conf[ids])]
    correct=(y[ids]==cl).astype(int);cum=np.cumsum(correct)/np.arange(1,len(ids)+1)
    good=np.where((np.arange(1,len(ids)+1)>=40)&(cum>=.985))[0]
    if len(good):
        k=int(good[-1])+1;th=float(oof_conf[ids[k-1]])
        class_thr[cl]=th;class_eval[cl]={'validation_n':k,'precision_pct':round(float(cum[k-1])*100,2),'margin_threshold':round(th,6)}
# Train final classifier and score rows without usable mapped categories.
final=LinearSVC(C=1.2);final.fit(X,y)
unlab=[i for i,ts in enumerate(all_topics) if len(ts)==0]
Xu=vec.transform([texts[i] for i in unlab]);dec=final.decision_function(Xu);ordr=np.argsort(dec,axis=1)
pred=final.classes_[ordr[:,-1]];margin=dec[np.arange(len(unlab)),ordr[:,-1]]-dec[np.arange(len(unlab)),ordr[:,-2]]
accepted=[];accepted_global=[]
for pos,i in enumerate(unlab):
    p=str(pred[pos]);m=float(margin[pos])
    if m>=float(global_sel['margin_threshold']):accepted_global.append((i,p,m))
    th=class_thr.get(p)
    if th is not None and m>=th:accepted.append((i,p,m))
# Shelf any-topic precision and no-category coverage.
shelf_eval=defaultdict(lambda:{'n':0,'ok':Counter()})
for i,r in enumerate(rows):
    ts=all_topics[i]
    if not ts:continue
    for s in a_by_id.get(int(r['ID']),set()):
        z=shelf_eval[s];z['n']+=1
        for t in ts:z['ok'][t]+=1
shelf_rows=[]
for s,z in shelf_eval.items():
    if not z['ok']:continue
    t,k=z['ok'].most_common(1)[0];no=sum(1 for i,r in enumerate(rows) if not all_topics[i] and s in a_by_id.get(int(r['ID']),set()))
    shelf_rows.append({'Madaf':s,'labeled_n':z['n'],'topic':t,'anytopic_precision_pct':round(k*100/z['n'],2),'unmapped_coverage':no})
shelf_rows.sort(key=lambda x:(-x['anytopic_precision_pct'],-x['unmapped_coverage']))
examples=[]
for i,p,m in sorted(accepted,key=lambda x:-x[2])[:120]:
    r=rows[i];examples.append({'FileID':r['FileID'],'BookName':r['BookName'],'AuthorName':r['AuthorName'],'Madaf':sorted(a_by_id.get(int(r['ID']),set())),'prediction':p,'margin':round(m,4)})
report={'counts':{'pdf':len(rows),'clean_single_topic':len(clean_idx),'unmapped_or_no_category':len(unlab)},'folds':folds,'oof_base_accuracy_pct':round(base_acc*100,2),'confidence_table':quant,'global_selected':global_sel,'class_thresholds':class_eval,'accepted_per_class_thresholds':len(accepted),'accepted_global_threshold':len(accepted_global),'accepted_topics':dict(Counter(p for _,p,_ in accepted)),'top_shelf_anytopic':shelf_rows[:40],'examples':examples}
Path('/kaggle/working/ml_confidence_audit.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
print('FOLDS',json.dumps(folds,ensure_ascii=False))
print('OOF BASE ACC',report['oof_base_accuracy_pct'])
print('CONF',json.dumps(quant,ensure_ascii=False))
print('GLOBAL SELECTED',json.dumps(global_sel,ensure_ascii=False),'ACCEPTS',len(accepted_global))
print('CLASS THRESHOLDS',json.dumps(class_eval,ensure_ascii=False))
print('PER-CLASS ACCEPTS',len(accepted),json.dumps(report['accepted_topics'],ensure_ascii=False))
print('SHELF ANYTOPIC',json.dumps(shelf_rows[:30],ensure_ascii=False))
print('EXAMPLES',json.dumps(examples[:40],ensure_ascii=False))
print('DONE ML audit only; no Drive; no PDFs')
C.close()
