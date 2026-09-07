import urllib.request
BASE='https://raw.githubusercontent.com/pitaronai/releases/main/hebrewbooks-drive/transfer_smoke_v26.py'
code=urllib.request.urlopen(BASE,timeout=60).read().decode('utf-8')
code=code.replace("SMOKE_NAME='_HB_SMOKE_V26'","SMOKE_NAME='_HB_SMOKE_V31'")
code=code.replace("hb_smoke_v26","hb_smoke_v31")
code=code.replace("HB-SmokeV26/1","HB-SmokeV31/1")
code=code.replace("integrated_final_simulation.py","integrated_final_v29.py")
code=code.replace("integrated_final_assignments.csv","integrated_final_assignments_v29.csv")
code=code.replace("'hb_schema':'26'","'hb_schema':'31'")
code=code.replace("'schema':26","'schema':31")
code=code.replace("readback.get('schema')!=26","readback.get('schema')!=31")
# Critical fix: run classifier in a separate namespace so its variable `clean` cannot overwrite the smoke filename sanitizer.
code=code.replace("exec(compile(code,CLASSIFIER,'exec'),globals(),globals())","_cls_ns={'__name__':'__main__'}; exec(compile(code,CLASSIFIER,'exec'),_cls_ns,_cls_ns)")
# No deletion in smoke.
start=code.index("# Remove stale smoke folder")
end=code.index("# Run the exact integrated classifier",start)
code=code[:start]+"# No deletion in V31 smoke.\n"+code[end:]
# Fixed regression smoke set from V29 plus one unclassified file.
start=code.index("# Pick one small representative")
end=code.index("C=sqlite3.connect",start)
selection='''# Fixed regression smoke set from V29.\nregression_expected={\n '2576':'מועדים',\n '9721':'תלמוד וש"ס',\n '4247':'מועדים',\n '47141':'הלכה',\n '64265':'משנה',\n '55985':'תלמוד וש"ס',\n '31423':'תנ"ך ומגילות',\n '20400':'תפילה וסידורים'\n}\nchosen=[]\nfor fid,exp in regression_expected.items():\n    if fid not in manifest:raise RuntimeError('missing regression PDF '+fid)\n    if assign[fid]['Top']!=exp:raise RuntimeError(f'regression classify mismatch {fid}: {assign[fid]["Top"]} != {exp}')\n    chosen.append(manifest[fid])\nuc=[e for fid,e in manifest.items() if assign[fid]['Top']=='לא מסווג' and e['size']>0]\nif uc:chosen.append(min(uc,key=lambda x:x['size']))\nlog('CHOSEN',json.dumps([{'fid':x['fid'],'size':x['size'],'top':assign[x['fid']]['Top'],'sub':assign[x['fid']]['Sub']} for x in chosen],ensure_ascii=False))\n\n'''
code=code[:start]+selection+code[end:]
# No destructive cleanup in smoke.
cut=code.index("# Deleting the non-empty smoke folder")
code=code[:cut]+'''after=root_snapshot('AFTER')\nreport={'smoke_ok':True,'delete_attempted':False,'drive_name':root.get('name'),'root_before':before,'root_after':after,'uploaded':uploaded,'state_ok':True,'rename_ok':True,'assignment_count':len(assign),'regression_expected':regression_expected}\nPath('/kaggle/working/transfer_smoke_v31.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')\nprint('SMOKE_V31_OK',json.dumps({'uploaded':len(uploaded),'state_ok':True,'rename_ok':True,'folder_id':smoke_id},ensure_ascii=False))\nprint('REGRESSION_SMOKE',json.dumps([{'fid':u['fid'],'top':u['top'],'sub':u['sub'],'name':u['name']} for u in uploaded],ensure_ascii=False))\nprint('ROOT_BEFORE',json.dumps(before,ensure_ascii=False))\nprint('ROOT_AFTER',json.dumps(after,ensure_ascii=False))\nprint('DONE smoke v31; no deletion performed; old library untouched')\nC.close()\n'''
exec(compile(code,BASE,'exec'),globals(),globals())
