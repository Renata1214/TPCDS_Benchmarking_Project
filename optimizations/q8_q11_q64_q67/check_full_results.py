from pathlib import Path
import re,collections,json,duckdb,argparse
parser=argparse.ArgumentParser();parser.add_argument('--repo', type=Path, default=Path(__file__).resolve().parents[2]);R=parser.parse_args().repo;O=Path(__file__).resolve().parent;checks=[]
for sf in [1,2,4,8]:
 c=duckdb.connect(str(R/f'duckdb/tpcds_sf{sf}.duckdb'),read_only=True);c.execute('set threads=4');c.execute("set memory_limit='4GB'");c.execute(f"SET temp_directory='{O}/temp_full'")
 for q in [8,11,64,67]:
  data=[];types=[]
  for p in [O/f'baseline/sf{sf}/query{q}.sql',O/f'sql/sf{sf}/query{q}.sql']:
   s=re.sub(r'limit\s+100\s*;\s*$',';',p.read_text(),flags=re.I)
   cur=c.execute(s);types.append([str(v[1]) for v in cur.description]);data.append(collections.Counter(cur.fetchall()))
  assert data[0]==data[1],(sf,q,'result mismatch without LIMIT')
  assert types[0]==types[1],(sf,q,'type mismatch')
  checks.append({'sf':sf,'query':q,'without_limit_equal':True,'rows':sum(data[0].values()),'types_equal':True});print(checks[-1],flush=True)
 c.close()
(O/'full_result_checks.json').write_text(json.dumps(checks,indent=2))
