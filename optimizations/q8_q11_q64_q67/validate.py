"""Read-only, warmed, alternating-order comparison; uses existing generated SQL parameters."""
from pathlib import Path
import duckdb,time,json,statistics,collections,argparse,threading
p=argparse.ArgumentParser();p.add_argument('--repo',type=Path,default=Path(__file__).resolve().parents[2]);a=p.parse_args()
O=Path(__file__).resolve().parent;results=[]
for sf in [1,2,4,8]:
 c=duckdb.connect(str(a.repo/f'duckdb/tpcds_sf{sf}.duckdb'),read_only=True)
 c.execute('SET threads=4');c.execute("SET memory_limit='4GB'");c.execute(f"SET temp_directory='{O}/temp'")
 for q in [8,11,64,67]:
  sql={'original':(O/f'baseline/sf{sf}/query{q}.sql').read_text(),'candidate':(O/f'sql/sf{sf}/query{q}.sql').read_text()}
  times={k:[] for k in sql};rows={};plans={}
  for k,s in sql.items():
   plans[k]=c.execute('EXPLAIN '+s).fetchall()
   timer=threading.Timer(180,c.interrupt);timer.start()
   try: rows[k]=c.execute(s).fetchall()
   finally: timer.cancel()
  equal=collections.Counter(rows['original'])==collections.Counter(rows['candidate'])
  for rep in range(4):
   for k in (['original','candidate'] if rep%2==0 else ['candidate','original']):
    start=time.perf_counter();r=c.execute(sql[k]).fetchall();times[k].append(time.perf_counter()-start)
    assert collections.Counter(r)==collections.Counter(rows[k]),'unstable result'
  rec={'sf':sf,'query':q,'equal_multiset':equal,'ordered_equal':rows['original']==rows['candidate'],'rows':len(rows['original']),'seconds':times,'speedup':statistics.median(times['original'])/statistics.median(times['candidate'])}
  results.append(rec);(O/'measurements.json').write_text(json.dumps({'duckdb':duckdb.__version__,'threads':4,'memory_limit':'4GB','warmups_per_variant':1,'repeats':4,'results':results},indent=2))
  pd=O/f'plans/sf{sf}';pd.mkdir(parents=True,exist_ok=True)
  for k in sql:(pd/f'q{q}_{k}.txt').write_text('\n'.join(str(r[-1]) for r in plans[k]))
  print(json.dumps(rec),flush=True)
 c.close()
