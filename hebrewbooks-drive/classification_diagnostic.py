import re, json, sqlite3, urllib.request, csv
from pathlib import Path
from collections import Counter, defaultdict
import boto3
from botocore.config import Config

PUB = 'https://raw.githubusercontent.com/yossi-computers/HebrewBooks-2026/main/src/HebrewBooks.Services/HebrewBooks.Services.Downloader/R2MirrorClient.cs'
src = urllib.request.urlopen(urllib.request.Request(PUB, headers={'User-Agent':'HB-Diagnostic/1'}), timeout=60).read().decode()
cfg = dict(re.findall(r'(?:private|public)\s+const\s+string\s+(\w+)\s*=\s*"([^"]+)"', src))
S3 = boto3.client('s3', endpoint_url=cfg['Endpoint'], aws_access_key_id=cfg['AccessKey'], aws_secret_access_key=cfg['SecretKey'], region_name='auto', config=Config(signature_version='s3v4', s3={'addressing_style':'path'}))
pref = cfg['AppPrefix'].rstrip('/') + '/'
keys=[]
for pg in S3.get_paginator('list_objects_v2').paginate(Bucket=cfg['Bucket'], Prefix=pref):
    keys += [o['Key'] for o in pg.get('Contents', [])]
ck = next((k for k in keys if k.lower().endswith('/katalog.db')), None) or next(k for k in keys if k.lower().endswith('katalog.db'))
db = Path('/kaggle/working/Katalog.db')
S3.download_file(cfg['Bucket'], ck, str(db))
C = sqlite3.connect(f'file:{db}?mode=ro', uri=True)
C.row_factory = sqlite3.Row
C.create_collation('HEB', lambda a,b:(str(a)>str(b))-(str(a)<str(b)))

def parse(v):
    v=str(v or '').strip()
    if not v:return []
    try:
        j=json.loads(v); out=[]
        def walk(x):
            if isinstance(x,dict):
                for y in x.values(): walk(y)
            elif isinstance(x,list):
                for y in x: walk(y)
            elif x is not None and str(x).strip(): out.append(str(x).strip())
        walk(j); return out
    except Exception:
        return [x.strip() for x in re.split(r'\s*[|;>]\s*',v) if x.strip()]

def norm(x):
    return str(x or '').replace('״','"').replace('“','"').replace('”','"').replace('׳',"'").strip()

shelves=defaultdict(set)
for x in C.execute('select bm.BookID,m.MadafName from BookMadaf bm join Madaf m on m.MadafID=bm.MadafID'):
    if x['MadafName']: shelves[int(x['BookID'])].add(norm(x['MadafName']))

TRACT=['ברכות','שבת','עירובין','פסחים','יומא','סוכה','ביצה','ראש השנה','תענית','מגילה','מועד קטן','חגיגה','יבמות','כתובות','נדרים','נזיר','סוטה','גיטין','קידושין','בבא קמא','בבא מציעא','בבא בתרא','סנהדרין','מכות','שבועות','עבודה זרה','הוריות','זבחים','מנחות','חולין','בכורות','ערכין','תמורה','כריתות','מעילה','נדה']
HOL=['שבת','ראש השנה','יום כיפור','סוכות','חנוכה','פורים','פסח','שבועות','תשעה באב']
CHASS=['ברסלב','חבד','אלכסנדר','מונקאטש','גור','ויזניץ','סאטמר','צאנז','קרלין']
SA=['אורח חיים','יורה דעה','אבן העזר','חושן משפט']

def first(S,vals):
    for v in vals:
        if norm(v) in S:return v
    return None

def classify(r):
    A=[norm(x) for x in parse(r['Categories'])]; S=set(A); M={norm(x) for x in shelves.get(int(r['ID']),set())}
    txt=' '+norm(r['BookName'])+' '+norm(r['Description'])+' '
    def R(top,sub='כללי',src='categories'): return top,sub,src
    if S & {'ירחון','כתב עת','גליון'} or 'כתבי עת' in M:return R('כתבי עת וירחונים','ירחונים' if 'ירחון' in S else ('גליונות' if 'גליון' in S else 'כתבי עת'),'categories' if S & {'ירחון','כתב עת','גליון'} else 'madaf')
    if 'שו"ת' in S or 'שו"ת' in M or ' שו"ת ' in txt or ' שות ' in txt:return R('שו"ת',first(S,SA) or 'כללי','categories' if 'שו"ת' in S else ('madaf' if 'שו"ת' in M else 'title'))
    hal={'הלכה','רמב"ם','כשרות','על השו"ע','בירורי הלכה','בירור הלכה','שחיטה','טריפות','ריבית','מקוואות','תערובות','מנהגים','נישואין','ברית מילה','חלה','תרי"ג מצוות','מצוות'}
    if S & hal or 'הלכה' in M:return R('הלכה',first(S,SA+['רמב"ם','כשרות','שחיטה','מנהגים']) or 'כללי','categories' if S & hal else 'madaf')
    tr=first(S,TRACT)
    if tr or S & {'מסכת','על הש"ס','סוגיות','תלמוד בבלי','ירושלמי','אגדות הש"ס','ביאור הגמ'}:return R('תלמוד וש"ס',tr or ('ירושלמי' if 'ירושלמי' in S else 'כללי'))
    if S & {'משניות','על המשניות','אבות','זרעים','מועד','נשים','נזיקין','קדשים','טהרות'} or 'אבות' in M:return R('משנה',first(S,['אבות','זרעים','מועד','נשים','נזיקין','קדשים','טהרות']) or 'כללי')
    if S & {'עה"ת','על התורה','חומש','בראשית','שמות','ויקרא','במדבר','דברים','רש"י'}:return R('תורה ומפרשים',first(S,['בראשית','שמות','ויקרא','במדבר','דברים']) or 'כללי')
    if S & {'נ"ך','חמש מגילות','תהלים','משלי','איוב','שיר השירים','קהלת','אסתר','איכה','רות'}:return R('תנ"ך ומגילות',first(S,['תהלים','משלי','איוב','שיר השירים','קהלת','אסתר','איכה','רות']) or 'כללי')
    ch=first(S,CHASS)
    if ch or 'חסידות' in S or 'חסידות' in M:return R('חסידות',ch or 'כללי','categories' if ch or 'חסידות' in S else 'madaf')
    if S & {'קבלה','זהר'}:return R('קבלה','זוהר' if 'זהר' in S else 'כללי')
    if S & {'מוסר','אמונה','השקפה','חיזוק','פילוסופיה','הדרכה'}:return R('מוסר מחשבה ואמונה',first(S,['מוסר','אמונה','השקפה','חיזוק']) or 'כללי')
    if 'דרשות' in S:return R('דרשות')
    if S & {'סידור','מחזור','תפילה'}:return R('תפילה וסידורים',first(S,['סידור','מחזור','תפילה']) or 'כללי')
    hh=first(S,HOL)
    if hh or S & {'מועדים','הגדה של פסח','ימים נוראים'}:return R('מועדים','הגדה של פסח' if 'הגדה של פסח' in S else (hh or 'כללי'))
    if S & {'מדרש','אגדה'}:return R('מדרש ואגדה','מדרש' if 'מדרש' in S else 'אגדה')
    if S & {'תולדות','ביוגרפיה','ארץ ישראל','יודאיקה','סיפורים'} or 'ביוגרפיה' in M:return R('תולדות וביוגרפיה',first(S,['תולדות','ארץ ישראל','סיפורים']) or 'כללי','categories' if S & {'תולדות','ביוגרפיה','ארץ ישראל','יודאיקה','סיפורים'} else 'madaf')
    if S & {'גאונים','ראשונים'} or 'קדמונים' in M:return R('גאונים וראשונים','גאונים' if 'גאונים' in S else ('ראשונים' if 'ראשונים' in S else 'קדמונים'),'categories' if S & {'גאונים','ראשונים'} else 'madaf')
    checks=[('כתבי עת וירחונים','כללי',['ירחון','כתב עת','גליון']),('תפילה וסידורים','כללי',['סידור','מחזור']),('מועדים','הגדה של פסח',['הגדה של פסח']),('תלמוד וש"ס','כללי',['תלמוד','מסכת']),('משנה','כללי',['משנה','משניות']),('קבלה','כללי',['קבלה','זוהר','זהר']),('מדרש ואגדה','כללי',['מדרש']),('חסידות','כללי',['חסידות']),('מוסר מחשבה ואמונה','מוסר',['מוסר']),('דרשות','כללי',['דרוש','דרשות']),('הלכה','כללי',['הלכות','הלכה']),('תורה ומפרשים','כללי',['חומש','על התורה'])]
    for top,sub,words in checks:
        if any(w in txt for w in words):return R(top,sub,'title_description')
    if 'English' in S:return R('שפות אחרות','אנגלית')
    if 'יידיש' in S:return R('שפות אחרות','יידיש')
    if 'נדירים' in M:return R('אוספים מיוחדים','נדירים','madaf')
    return R('לא מסווג','כללי','unclassified')

u_tokens=Counter(); u_combos=Counter(); u_madaf=Counter(); u_titles=Counter(); u_authors=Counter(); u_withcat=0; u_nocat=0
u_desc=0; total=0; classified=0; examples=[]
all_u=[]
stop={'ספר','חלק','עם','על','של','בן','בת','הרב','רבי','רב','א','ב','ג','ד','ה','ו','ז','ח','ט','י','קונטרס','מהדורה'}
for r in C.execute("select ID,FileID,BookName,AuthorName,Description,Categories from Katalog where lower(SourceType)='pdf' order by ID"):
    total+=1
    top,sub,src=classify(r)
    if top!='לא מסווג': classified+=1; continue
    cats=[norm(x) for x in parse(r['Categories'])]
    if cats:
        u_withcat+=1; u_tokens.update(set(cats)); u_combos[tuple(cats)]+=1
    else:u_nocat+=1
    if str(r['Description'] or '').strip():u_desc+=1
    u_madaf.update(shelves.get(int(r['ID']),set()))
    words=[w for w in re.findall(r'[א-ת]{2,}',norm(r['BookName'])) if w not in stop]
    u_titles.update(words)
    if r['AuthorName']:u_authors[norm(r['AuthorName'])]+=1
    rec={'FileID':r['FileID'],'BookName':r['BookName'],'AuthorName':r['AuthorName'],'Categories':r['Categories'],'Description':str(r['Description'] or '')[:500],'Madaf':sorted(shelves.get(int(r['ID']),set()))}
    all_u.append(rec)
    if len(examples)<200:examples.append(rec)

report={
 'total_pdf':total,'classified':classified,'unclassified':total-classified,'unclassified_pct':round((total-classified)*100/total,2),
 'unclassified_with_categories':u_withcat,'unclassified_without_categories':u_nocat,'unclassified_with_description':u_desc,
 'top_unclassified_category_tokens':[{'value':k,'count':v} for k,v in u_tokens.most_common(500)],
 'top_unclassified_category_combinations':[{'values':list(k),'count':v} for k,v in u_combos.most_common(300)],
 'top_unclassified_madaf':[{'value':k,'count':v} for k,v in u_madaf.most_common(100)],
 'top_unclassified_title_words':[{'value':k,'count':v} for k,v in u_titles.most_common(300)],
 'top_unclassified_authors':[{'value':k,'count':v} for k,v in u_authors.most_common(100)],
 'examples':examples
}
Path('/kaggle/working/unclassified_diagnostic.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
with open('/kaggle/working/unclassified_all.csv','w',newline='',encoding='utf-8-sig') as f:
    w=csv.DictWriter(f,fieldnames=['FileID','BookName','AuthorName','Categories','Description','Madaf']); w.writeheader()
    for r in all_u:
        x=r.copy(); x['Madaf']=' | '.join(x['Madaf']); w.writerow(x)
print('TOTAL',total,'CLASSIFIED',classified,'UNCLASSIFIED',total-classified,report['unclassified_pct'])
print('UNCLASSIFIED WITH CATEGORIES',u_withcat,'WITHOUT',u_nocat,'WITH DESCRIPTION',u_desc)
print('TOP TOKENS',json.dumps(report['top_unclassified_category_tokens'][:150],ensure_ascii=False))
print('TOP COMBOS',json.dumps(report['top_unclassified_category_combinations'][:80],ensure_ascii=False))
print('TOP MADAF',json.dumps(report['top_unclassified_madaf'][:80],ensure_ascii=False))
print('TOP TITLE WORDS',json.dumps(report['top_unclassified_title_words'][:120],ensure_ascii=False))
print('DONE diagnostic only; no Drive; no PDFs')
C.close()
