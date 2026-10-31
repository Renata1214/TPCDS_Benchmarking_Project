"""Check substitutions against the existing SQL parameter sets, without changing RNG state."""
from pathlib import Path
import re,json
O=Path(__file__).resolve().parent
R=Path(__file__).resolve().parents[2]
checks=[]
for sf in [1,2,4,8]:
 for q in [8,11,64,67]:
  original=(O/f'baseline/sf{sf}/query{q}.sql').read_text()
  tpl=(O/f'templates/query{q}.tpl').read_text()
  # Definitions are a dsqgen preamble, not SQL.
  start=tpl.index('with ')
  rendered=tpl[start:]
  values={'_LIMITA':'','_LIMITB':'','_LIMITC':'limit 100'}
  if q==8:
   values['YEAR']=re.search(r'd_year = (\d+)',original)[1];values['QOY']=re.search(r'd_qoy = (\d+)',original)[1]
   zips=re.findall(r"'([0-9]+)'",original)
   values.update({f'ZIP.{i}':z for i,z in enumerate(zips,1)})
  elif q==11:
   values['YEAR']=re.search(r't_s_firstyear.dyear = (\d+)',original)[1]
   values['SELECTONE']=re.search(r',\s*(t_s_secyear.customer_\w+)\s+from year_total',original)[1]
  elif q==64:
   values['YEAR']=re.search(r'cs1.syear = (\d+)',original)[1]
   values['PRICE']=re.search(r'i_current_price between (\d+)',original)[1]
   colors=re.findall(r"'([^']+)'",re.search(r'i_color in \(([^)]+)\)',original)[1])
   values.update({f'COLOR.{i}':v for i,v in enumerate(colors,1)})
  else:values['DMS']=re.search(r'd_month_seq between (\d+)',original)[1]
  for key,value in values.items():rendered=rendered.replace('['+key+']',value)
  assert not re.search(r'\[\w',rendered),(q,sf,'unresolved token')
  normalize=lambda s:re.sub(r'\s+','',s).lower()
  assert normalize(rendered)==normalize((O/f'sql/sf{sf}/query{q}.sql').read_text()),(q,sf,'template mismatch')
  checks.append({'sf':sf,'query':q,'matches':True})
(O/'template_checks.json').write_text(json.dumps(checks,indent=2));print('16 template/SQL comparisons passed')
