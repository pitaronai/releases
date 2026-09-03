import urllib.request
BASE='https://raw.githubusercontent.com/pitaronai/releases/main/hebrewbooks-drive/integrated_final_simulation.py'
base=urllib.request.urlopen(BASE,timeout=60).read().decode('utf-8')

new_func=r'''def cat_class(cats,title=''):
    s=S(cats); tn=' '+n(title)+' '
    if not s:return None
    if has(s,'ירחון','כתב עת','גליון','שבועון','רבעון'):return ('כתבי עת וירחונים','ירחונים' if has(s,'ירחון') else ('גליונות' if has(s,'גליון') else 'כתבי עת'))
    if has(s,'שו"ת'):return ('שו"ת',first(s,SA) or 'כללי')

    hal={'הלכה','הלכות','רמב"ם','על הרמב"ם','כשרות','על השו"ע','על שולחן ערוך','שולחן ערוך','משנה ברורה','על המשנה ברורה','שחיטה','טריפות','ריבית','מקוואות','מקואות','תערובות','מנהגים','נישואין','ברית מילה','חלה','תרי"ג מצוות','תרי"ג מצות','מצוות','פסקי הלכה','פסקי דינים','טור','שטרות','נוסח שטרות','ציצית','תפילין','שביעית','תכלת','בירור הלכה','בירורי הלכה'}
    if s&{n(x) for x in hal} or first(s,SA):return ('הלכה',first(s,SA+['רמב"ם','כשרות','שחיטה','מנהגים']) or ('שבת' if has(s,'שבת') else 'כללי'))

    # Ambiguous words such as שבת/ברכות/שבועות/ראש השנה/סוכה/מגילה/תענית
    # are NOT treated as tractates without independent Talmud evidence.
    talctx=has(s,'מסכת','על הש"ס','סוגיות הש"ס','תלמוד בבלי','תלמוד','ירושלמי','אגדות הש"ס','אגדת הש"ס','ביאור הגמ','גמרא','גמרא לכל השנה','גרסאות הש"ס','כללי הש"ס','כללים הש"ס','הדרנים','ברייתא','סוגיא','בירורי סוגיות','מסכתות קטנות','תוספתא')
    title_tal=any(x in tn for x in [' מסכת ',' תלמוד ',' ש"ס ',' שס ',' עמ"ס ',' על מסכת ',' גמרא ',' דף על הדף '])
    ambig={'ברכות','שבת','שבועות','ראש השנה','סוכה','מגילה','תענית'}
    tr_all=first(s,TRACT)
    tr_safe=first(s,[x for x in TRACT if n(x) not in {n(y) for y in ambig}])
    if talctx or title_tal:
        return ('תלמוד וש"ס',tr_all or ('ירושלמי' if has(s,'ירושלמי') else 'כללי'))
    if tr_safe:return ('תלמוד וש"ס',tr_safe)

    # Mishnah only with an explicit Mishnah signal. Generic order names alone are not enough.
    if has(s,'משניות','על המשניות','פרקי אבות','אבות דרבי נתן',"אבות דר' נתן"):
        return ('משנה',first(s,['אבות','זרעים','מועד','נשים','נזיקין','קדשים','טהרות']) or 'כללי')
    if has(s,'אבות') and not has(s,'אבות האומה','אבות החסידות'):return ('משנה','אבות')

    tor=first(s,['בראשית','שמות','ויקרא','במדבר','דברים'])
    if tor or has(s,'עה"ת','על התורה','חומש','רש"י','אונקלוס','תרגום','מסורה','הפטרות','תורת כהנים','ספרא'):return ('תורה ומפרשים',tor or 'כללי')
    tnsub=first(s,['תהלים','משלי','איוב','שיר השירים','קהלת','אסתר','מגילת אסתר','איכה','רות'])
    if tnsub or has(s,'נ"ך','נך','חמש מגילות','מגילות','תנ"ך','על הנ"ך','על תהלים'):
        return ('תנ"ך ומגילות',tnsub or 'כללי')

    ch=first(s,CHASS)
    if ch or has(s,'חסידות'):return ('חסידות',ch or 'כללי')
    if has(s,'קבלה','זהר','זוהר','רמח"ל','רשב"י','קמיעות','סגולות','גלגולים'):return ('קבלה','זוהר' if has(s,'זהר','זוהר') else 'כללי')
    if has(s,'מוסר','אמונה','השקפה','חיזוק','פילוסופיה','הדרכה','מידות','מדות','לשון הרע','בין אדם לחברו','גאולה','משיח','תשובה','שמירת העיניים','צניעות','קדושה'):return ('מוסר מחשבה ואמונה','מוסר' if has(s,'מוסר') else 'כללי')
    if has(s,'דרשות','הספדים','דרוש','דרושים'):return ('דרשות','כללי')
    if has(s,'סידור','מחזור','תפילה','תפילות','פיוט','פיוטים','זמירות','פרק שירה','ביאורי תפילה'):return ('תפילה וסידורים',first(s,['סידור','מחזור','תפילה']) or 'כללי')

    # Holiday context comes only after explicit Talmud/Halacha/Tanakh evidence above.
    hh=first(s,HOL)
    if hh or has(s,'מועדים','הגדה של פסח','ימים נוראים','ראש השנה','שבועות','סוכות','פורים','חנוכה','יום כיפור','יום הכיפורים','שלוש רגלים','אקדמות','מתן תורה','שופר','תשליך','ספירת העומר'):
        sub='הגדה של פסח' if has(s,'הגדה של פסח') else (hh or ('ראש השנה' if has(s,'ראש השנה') else ('שבועות' if has(s,'שבועות') else ('סוכות' if has(s,'סוכות') else ('פורים' if has(s,'פורים') else 'כללי')))))
        return ('מועדים',sub)

    # שבת is often halacha/derash/chassidut and is intentionally left unresolved unless title is explicit.
    if has(s,'שבת') and any(x in tn for x in [' הלכות שבת ',' דיני שבת ',' שמירת שבת ',' שבת כהלכתו ',' מלאכות שבת ',' ל"ט מלאכות ']):return ('הלכה','שבת')
    # סוכה may be tractate or holiday law; without corroboration do not guess.
    if has(s,'סוכה') and (has(s,'לולב','ארבע מינים',"ד' מינים",'סוכות') or ' חג הסוכות ' in tn):return ('מועדים','סוכות')
    # מגילה may mean tractate or a biblical scroll; explicit Esther/Five Scrolls was handled above.
    if has(s,'מגילה') and has(s,'פורים'):return ('מועדים','פורים')
    # תענית may mean tractate or fast-day practice; explicit prayer/halacha/talmud was handled above.
    if has(s,'תענית') and has(s,'צום','תעניות','שובבי"ם'):return ('מועדים','כללי')

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
'''
pre,rest=base.split("def cat_class(cats,title=''):",1)
_,post=rest.split("rows=[dict(r)",1)
base=pre+new_func+"\nrows=[dict(r)"+post

new_ml=r'''# ML train on category-labelled rows, recalibrated after the ambiguity-rule change.
from sklearn.model_selection import GroupKFold
def feat(r):
    title=n(r['BookName'])[:240];authorx=n(r['AuthorName'])[:220];desc=n(r['Description'])[:1200];sh=' '.join(n(x) for x in sorted(shelves.get(int(r['ID']),set())))[:400]
    return f'שם {title} מחבר {authorx} מדף {sh} תיאור {desc}'
train_idx=[i for i,r in enumerate(rows) if source.get(i)=='categories']
Xtxt=[feat(rows[i]) for i in train_idx];y=np.array([assigned[i] for i in train_idx],dtype=object)
groups=np.array([(series(rows[i]['BookName'])+'|'+n(rows[i]['AuthorName'])) or ('fid|'+str(rows[i]['FileID'])) for i in train_idx],dtype=object)
oof_pred=np.empty(len(train_idx),dtype=object);oof_margin=np.zeros(len(train_idx),dtype=float)
gkf=GroupKFold(n_splits=3)
folds=[]
for fold,(trn,val) in enumerate(gkf.split(np.zeros(len(train_idx)),y,groups),1):
    vv=TfidfVectorizer(analyzer='char_wb',ngram_range=(2,5),min_df=2,max_features=120000,sublinear_tf=True,dtype=np.float32)
    Xt=vv.fit_transform([Xtxt[j] for j in trn]);Xv=vv.transform([Xtxt[j] for j in val])
    cc=LinearSVC(C=1.2);cc.fit(Xt,y[trn]);dec=cc.decision_function(Xv);oo=np.argsort(dec,axis=1)
    pp=cc.classes_[oo[:,-1]];mm=dec[np.arange(len(val)),oo[:,-1]]-dec[np.arange(len(val)),oo[:,-2]]
    oof_pred[val]=pp;oof_margin[val]=mm
    folds.append({'fold':fold,'n':len(val),'accuracy_pct':round(float(np.mean(pp==y[val]))*100,2)})
base_acc=float(np.mean(oof_pred==y))
best_thr=None;best_n=-1;best_acc=None
for q in np.linspace(0,0.99,100):
    t=float(np.quantile(oof_margin,q));sel=oof_margin>=t;nn=int(sel.sum())
    if nn<500:continue
    ac=float(np.mean(oof_pred[sel]==y[sel]))
    if ac>=0.995 and nn>best_n:
        best_thr=t;best_n=nn;best_acc=ac
if best_thr is None:
    best_thr=1e9;best_n=0;best_acc=0.0
print('ML_FOLDS',json.dumps(folds,ensure_ascii=False))
print('ML_OOF_BASE',round(base_acc*100,2))
print('ML_SELECTED',json.dumps({'margin_threshold':round(best_thr,6),'validation_n':best_n,'validation_coverage_pct':round(best_n*100/len(train_idx),2) if train_idx else 0,'accuracy_pct':round(best_acc*100,2)},ensure_ascii=False))
vec=TfidfVectorizer(analyzer='char_wb',ngram_range=(2,5),min_df=2,max_features=120000,sublinear_tf=True,dtype=np.float32)
X=vec.fit_transform(Xtxt);clf=LinearSVC(C=1.2);clf.fit(X,y)
rem=[i for i in range(len(rows)) if i not in assigned]
if rem and best_n:
    Xu=vec.transform([feat(rows[i]) for i in rem]);dec=clf.decision_function(Xu);ordr=np.argsort(dec,axis=1)
    pred=clf.classes_[ordr[:,-1]];margin=dec[np.arange(len(rem)),ordr[:,-1]]-dec[np.arange(len(rem)),ordr[:,-2]]
    for pos,i in enumerate(rem):
        if float(margin[pos])>=best_thr:
            t=str(pred[pos]);assigned[i]=t;paths[i]=(t,'כללי');source[i]='ml_revalidated_99_5'
'''
pre,rest=base.split('# ML train only on category-labelled rows; conservative global margin threshold validated in v24.',1)
_,post=rest.split('# finish unclassified',1)
base=pre+new_ml+'\n# finish unclassified'+post
# Add targeted rule checks before closing the DB.
needle="print('DONE integrated simulation only; no Drive; no PDFs')"
check="""checks=[]\nfor fid in ['2576','2664','9721','4247','20400','32653','42079','64265']:\n    for i,r in enumerate(rows):\n        if str(r['FileID'])==fid:\n            checks.append({'FileID':fid,'BookName':r['BookName'],'Top':paths[i][0],'Sub':paths[i][1],'Source':source[i]});break\nprint('RULE_CHECK',json.dumps(checks,ensure_ascii=False))\nprint('DONE integrated simulation v29 only; no Drive; no PDFs')"""
base=base.replace(needle,check)
exec(compile(base,'integrated_final_simulation_v29_patched.py','exec'),globals(),globals())
