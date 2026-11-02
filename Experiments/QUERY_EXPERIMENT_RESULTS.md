# Query experiment results

## Scope and method

This run covers queries Q4, Q8, Q11, Q14, Q22, Q23, Q36, Q39, Q47, Q52, Q59, Q64, Q67, Q74, Q78, Q95 at SF1, SF2, SF4, and SF8 (DuckDB databases already present in `duckdb/`). It generated 128 SQL files: one baseline and one experiment per query/scale. Baselines came from `Kit/DSGen-software-code-4.0.0/query_templates_old/`; experiments came from the current `query_templates/` files. Both generator calls used `-RNGSEED 19620718` so template parameters were reproducible between the pair. For Q74, the experiment SQL is wrapped with `disabled_optimizers = 'join_order'`, following the existing project query-generation script.

Several modified templates had CRLF endings, which the Linux `dsqgen` parser rejected. Only temporary copies used for generation were normalized to LF; the user-modified source templates were not changed.

Each benchmark used Docker / DuckDB 1.4.3, two warm-ups, and five measured executions per version. The runner compared result multisets first (order ignored; duplicate counts preserved), and alternated baseline/experiment execution order. Timings below are the arithmetic mean +/- sample standard deviation (`n=5`) of measured wall-clock seconds; warm-ups are excluded. The Q74 optimizer setup/reset overhead remains included, as in the shared runner. EXPLAIN elapsed is the utility's total wall-clock duration, including container startup, the warm-up, and plan capture.

**Correctness:** 60/64 query-scale pairs matched. 4 pairs did not match; the benchmark runner correctly withheld timings for those pairs. All 64 experiment EXPLAIN ANALYZE plans completed after one warm-up execution each. The plan file, metadata, and exact validation CSV paths for every pair are listed in the accompanying `query_experiment_summary.csv`.

Across the 60 validated pairs, the experiment mean was lower in 59, higher in 1, and equal in 0; median paired speedup by mean runtime was 1.961x. This comparison is descriptive and hardware-specific.

## Commands used

All benchmark and explain commands were run from WSL because the existing persistent DuckDB benchmark runner relies on subprocess pipe selectors that are not supported by the Windows Python runtime. The container used the project Docker image.

```bash
docker compose build tpcds
```

The batch generator ran inside the container from `/opt/tpcds-tools`; the baseline and experiment invocations were:

```bash
dsqgen -DIRECTORY /workspace/Kit/DSGen-software-code-4.0.0/query_templates_old -TEMPLATE "query${q}.tpl" -DIALECT duckdb -SCALE "$scale" -FILTER Y -RNGSEED 19620718
dsqgen -DIRECTORY /workspace/Experiments/.query_matrix_work/templates -TEMPLATE "query${q}.tpl" -DIALECT duckdb -SCALE "$scale" -FILTER Y -RNGSEED 19620718
```

The WSL commands below were run once per query/scale pair. This is the exact Q4/SF1 example; the same options and path pattern were used for each remaining pair:

```powershell
wsl.exe bash -lc 'cd /mnt/c/Users/Regina/TPCDS && python3 Experiments/run_benchmark.py --baseline Experiments/Experiments_Q4/SF1/query4_baseline.sql --experiment Experiments/Experiments_Q4/SF1/query4_experiment1.sql --name q4 --scale-gb 1 --warmups 2 --repeats 5 --runtime docker'
wsl.exe bash -lc 'cd /mnt/c/Users/Regina/TPCDS && python3 Experiments/run_explain_analyze.py Experiments/Experiments_Q4/SF1/query4_experiment1.sql --scale-gb 1 --warmups 1 --timeout-seconds 1800 --runtime docker'
```

## Results by query and scale

| Query | Scale | Result check | Baseline mean +/- SD (s) | Experiment mean +/- SD (s) | EXPLAIN elapsed (s) |
|---|---:|---|---:|---:|---:|
| Q4 | SF1 | [PASS](Experiments_Q4/SF1/results_q4_20261102_021536_776799/benchmark/result_validation.csv) | 0.230869 +/- 0.009233 | 0.104979 +/- 0.006878 | 2.390 |
| Q4 | SF2 | [PASS](Experiments_Q4/SF2/results_q4_20261102_021723_251538/benchmark/result_validation.csv) | 0.604252 +/- 0.015185 | 0.207601 +/- 0.007854 | 3.334 |
| Q4 | SF4 | [PASS](Experiments_Q4/SF4/results_q4_20261102_021911_120082/benchmark/result_validation.csv) | 1.188775 +/- 0.044711 | 0.425610 +/- 0.027307 | 4.223 |
| Q4 | SF8 | [PASS](Experiments_Q4/SF8/results_q4_20261102_022258_482015/benchmark/result_validation.csv) | 3.325409 +/- 0.301554 | 1.347867 +/- 0.274082 | 7.088 |
| Q8 | SF1 | [PASS](Experiments_Q8/SF1/results_q8_20261102_021614_616473/benchmark/result_validation.csv) | 0.139426 +/- 0.006999 | 0.020949 +/- 0.000881 | 2.248 |
| Q8 | SF2 | [PASS](Experiments_Q8/SF2/results_q8_20261102_021732_866511/benchmark/result_validation.csv) | 0.212142 +/- 0.020799 | 0.024469 +/- 0.001646 | 1.512 |
| Q8 | SF4 | [PASS](Experiments_Q8/SF4/results_q8_20261102_021928_295811/benchmark/result_validation.csv) | 0.351019 +/- 0.050968 | 0.033996 +/- 0.005507 | 2.095 |
| Q8 | SF8 | [PASS](Experiments_Q8/SF8/results_q8_20261102_022347_577915/benchmark/result_validation.csv) | 0.722824 +/- 0.036077 | 0.125961 +/- 0.023045 | 2.972 |
| Q11 | SF1 | [PASS](Experiments_Q11/SF1/results_q11_20261102_021618_584050/benchmark/result_validation.csv) | 0.195802 +/- 0.015210 | 0.075319 +/- 0.007656 | 2.764 |
| Q11 | SF2 | [PASS](Experiments_Q11/SF2/results_q11_20261102_021737_148329/benchmark/result_validation.csv) | 0.467189 +/- 0.012624 | 0.146693 +/- 0.009580 | 3.167 |
| Q11 | SF4 | [PASS](Experiments_Q11/SF4/results_q11_20261102_021933_687612/benchmark/result_validation.csv) | 0.847073 +/- 0.062963 | 0.268301 +/- 0.013817 | 3.554 |
| Q11 | SF8 | [PASS](Experiments_Q11/SF8/results_q11_20261102_022402_043879/benchmark/result_validation.csv) | 1.988107 +/- 0.092248 | 0.706508 +/- 0.016086 | 5.357 |
| Q14 | SF1 | [PASS](Experiments_Q14/SF1/results_q14_20261102_021623_273444/benchmark/result_validation.csv) | 0.274650 +/- 0.043123 | 0.205907 +/- 0.021945 | 2.431 |
| Q14 | SF2 | [PASS](Experiments_Q14/SF2/results_q14_20261102_021745_027977/benchmark/result_validation.csv) | 0.402999 +/- 0.024899 | 0.313468 +/- 0.010115 | 3.331 |
| Q14 | SF4 | [PASS](Experiments_Q14/SF4/results_q14_20261102_021945_963182/benchmark/result_validation.csv) | 0.760847 +/- 0.013687 | 0.630899 +/- 0.044636 | 4.587 |
| Q14 | SF8 | [PASS](Experiments_Q14/SF8/results_q14_20261102_022434_102635/benchmark/result_validation.csv) | 2.581414 +/- 0.529113 | 1.656430 +/- 0.146835 | 6.767 |
| Q22 | SF1 | [PASS](Experiments_Q22/SF1/results_q22_20261102_021629_434590/benchmark/result_validation.csv) | 0.249526 +/- 0.010464 | 0.035573 +/- 0.002442 | 2.275 |
| Q22 | SF2 | [PASS](Experiments_Q22/SF2/results_q22_20261102_021753_705571/benchmark/result_validation.csv) | 0.337584 +/- 0.006769 | 0.051833 +/- 0.004357 | 2.381 |
| Q22 | SF4 | [PASS](Experiments_Q22/SF4/results_q22_20261102_022000_366814/benchmark/result_validation.csv) | 1.869810 +/- 0.105830 | 0.263736 +/- 0.032235 | 2.995 |
| Q22 | SF8 | [PASS](Experiments_Q22/SF8/results_q22_20261102_022517_572130/benchmark/result_validation.csv) | 5.251923 +/- 0.146337 | 0.655971 +/- 0.057186 | 3.371 |
| Q23 | SF1 | [PASS](Experiments_Q23/SF1/results_q23_20261102_021634_437033/benchmark/result_validation.csv) | 0.553515 +/- 0.071580 | 0.270593 +/- 0.038870 | 3.010 |
| Q23 | SF2 | [PASS](Experiments_Q23/SF2/results_q23_20261102_021759_392600/benchmark/result_validation.csv) | 1.062733 +/- 0.110003 | 0.529566 +/- 0.048084 | 3.961 |
| Q23 | SF4 | [PASS](Experiments_Q23/SF4/results_q23_20261102_022020_595087/benchmark/result_validation.csv) | 2.528419 +/- 0.115415 | 1.098920 +/- 0.016398 | 4.772 |
| Q23 | SF8 | [PASS](Experiments_Q23/SF8/results_q23_20261102_022613_195673/benchmark/result_validation.csv) | 9.250407 +/- 0.974298 | 3.603389 +/- 0.271180 | 9.683 |
| Q36 | SF1 | [PASS](Experiments_Q36/SF1/results_q36_20261102_021643_685232/benchmark/result_validation.csv) | 0.094409 +/- 0.002152 | 0.024427 +/- 0.000714 | 2.109 |
| Q36 | SF2 | [PASS](Experiments_Q36/SF2/results_q36_20261102_021814_868640/benchmark/result_validation.csv) | 0.158454 +/- 0.001877 | 0.037315 +/- 0.001294 | 1.928 |
| Q36 | SF4 | [PASS](Experiments_Q36/SF4/results_q36_20261102_022052_681783/benchmark/result_validation.csv) | 0.398151 +/- 0.067482 | 0.103302 +/- 0.011610 | 2.404 |
| Q36 | SF8 | [PASS](Experiments_Q36/SF8/results_q36_20261102_022801_589326/benchmark/result_validation.csv) | 1.148994 +/- 0.118789 | 0.275684 +/- 0.029384 | 3.849 |
| Q39 | SF1 | [6/6 diff](Experiments_Q39/SF1/results_q39_20261102_021647_250094/benchmark/result_validation.csv) | +/- (not timed) | +/- (not timed) | 2.565 |
| Q39 | SF2 | [33/33 diff](Experiments_Q39/SF2/results_q39_20261102_021819_304636/benchmark/result_validation.csv) | +/- (not timed) | +/- (not timed) | 2.474 |
| Q39 | SF4 | [59/59 diff](Experiments_Q39/SF4/results_q39_20261102_022100_055101/benchmark/result_validation.csv) | +/- (not timed) | +/- (not timed) | 2.812 |
| Q39 | SF8 | [120/120 diff](Experiments_Q39/SF8/results_q39_20261102_022822_760271/benchmark/result_validation.csv) | +/- (not timed) | +/- (not timed) | 2.981 |
| Q47 | SF1 | [PASS](Experiments_Q47/SF1/results_q47_20261102_021649_116288/benchmark/result_validation.csv) | 0.081280 +/- 0.001454 | 0.070888 +/- 0.003426 | 2.583 |
| Q47 | SF2 | [PASS](Experiments_Q47/SF2/results_q47_20261102_021821_265843/benchmark/result_validation.csv) | 0.154710 +/- 0.006650 | 0.137632 +/- 0.002823 | 2.856 |
| Q47 | SF4 | [PASS](Experiments_Q47/SF4/results_q47_20261102_022102_641047/benchmark/result_validation.csv) | 0.287257 +/- 0.008903 | 0.258615 +/- 0.007664 | 3.299 |
| Q47 | SF8 | [PASS](Experiments_Q47/SF8/results_q47_20261102_022830_157621/benchmark/result_validation.csv) | 0.889695 +/- 0.030078 | 0.835645 +/- 0.028425 | 3.960 |
| Q52 | SF1 | [PASS](Experiments_Q52/SF1/results_q52_20261102_021652_999845/benchmark/result_validation.csv) | 0.010225 +/- 0.001706 | 0.009555 +/- 0.000824 | 2.407 |
| Q52 | SF2 | [PASS](Experiments_Q52/SF2/results_q52_20261102_021826_486685/benchmark/result_validation.csv) | 0.014195 +/- 0.000840 | 0.013350 +/- 0.000326 | 1.863 |
| Q52 | SF4 | [PASS](Experiments_Q52/SF4/results_q52_20261102_022110_225591/benchmark/result_validation.csv) | 0.023522 +/- 0.001659 | 0.022947 +/- 0.001949 | 2.768 |
| Q52 | SF8 | [PASS](Experiments_Q52/SF8/results_q52_20261102_022851_948482/benchmark/result_validation.csv) | 0.060734 +/- 0.003839 | 0.058731 +/- 0.002281 | 3.265 |
| Q59 | SF1 | [PASS](Experiments_Q59/SF1/results_q59_20261102_021655_685218/benchmark/result_validation.csv) | 0.060889 +/- 0.001854 | 0.039532 +/- 0.001407 | 2.610 |
| Q59 | SF2 | [PASS](Experiments_Q59/SF2/results_q59_20261102_021829_351629/benchmark/result_validation.csv) | 0.138978 +/- 0.006694 | 0.084442 +/- 0.006351 | 2.630 |
| Q59 | SF4 | [PASS](Experiments_Q59/SF4/results_q59_20261102_022113_625344/benchmark/result_validation.csv) | 0.274630 +/- 0.043899 | 0.143409 +/- 0.017589 | 3.008 |
| Q59 | SF8 | [PASS](Experiments_Q59/SF8/results_q59_20261102_022902_028078/benchmark/result_validation.csv) | 0.613828 +/- 0.032948 | 0.362523 +/- 0.044812 | 3.504 |
| Q64 | SF1 | [PASS](Experiments_Q64/SF1/results_q64_20261102_021658_913684/benchmark/result_validation.csv) | 0.067719 +/- 0.005129 | 0.064176 +/- 0.003931 | 3.060 |
| Q64 | SF2 | [PASS](Experiments_Q64/SF2/results_q64_20261102_021833_693271/benchmark/result_validation.csv) | 0.130803 +/- 0.028155 | 0.108223 +/- 0.011243 | 3.032 |
| Q64 | SF4 | [PASS](Experiments_Q64/SF4/results_q64_20261102_022119_732640/benchmark/result_validation.csv) | 0.237969 +/- 0.040310 | 0.176419 +/- 0.021740 | 3.505 |
| Q64 | SF8 | [PASS](Experiments_Q64/SF8/results_q64_20261102_022917_247722/benchmark/result_validation.csv) | 1.338631 +/- 0.548672 | 1.753519 +/- 1.681454 | 5.244 |
| Q67 | SF1 | [PASS](Experiments_Q67/SF1/results_q67_20261102_021702_681010/benchmark/result_validation.csv) | 0.420006 +/- 0.056652 | 0.263478 +/- 0.007514 | 2.605 |
| Q67 | SF2 | [PASS](Experiments_Q67/SF2/results_q67_20261102_021838_637574/benchmark/result_validation.csv) | 0.976802 +/- 0.121672 | 0.694113 +/- 0.109300 | 4.055 |
| Q67 | SF4 | [PASS](Experiments_Q67/SF4/results_q67_20261102_022126_973129/benchmark/result_validation.csv) | 3.310706 +/- 0.183802 | 1.966091 +/- 0.038191 | 6.307 |
| Q67 | SF8 | [PASS](Experiments_Q67/SF8/results_q67_20261102_053122_056541/benchmark/result_validation.csv) | 5.898291 +/- 0.556022 | 3.703692 +/- 0.527235 | 11.168 |
| Q74 | SF1 | [PASS](Experiments_Q74/SF1/results_q74_20261102_021710_921612/benchmark/result_validation.csv) | 0.125430 +/- 0.006834 | 0.071665 +/- 0.010429 | 2.563 |
| Q74 | SF2 | [PASS](Experiments_Q74/SF2/results_q74_20261102_021854_491102/benchmark/result_validation.csv) | 0.306773 +/- 0.009680 | 0.124763 +/- 0.013469 | 2.268 |
| Q74 | SF4 | [PASS](Experiments_Q74/SF4/results_q74_20261102_022210_971576/benchmark/result_validation.csv) | 0.839360 +/- 0.069260 | 0.350881 +/- 0.028870 | 3.301 |
| Q74 | SF8 | [PASS](Experiments_Q74/SF8/results_q74_20261102_053250_389951/benchmark/result_validation.csv) | 1.313336 +/- 0.052720 | 0.716767 +/- 0.040549 | 4.414 |
| Q78 | SF1 | [PASS](Experiments_Q78/SF1/results_q78_20261102_021715_061727/benchmark/result_validation.csv) | 0.109478 +/- 0.007028 | 0.090528 +/- 0.004413 | 2.742 |
| Q78 | SF2 | [PASS](Experiments_Q78/SF2/results_q78_20261102_021900_698977/benchmark/result_validation.csv) | 0.215825 +/- 0.004734 | 0.176389 +/- 0.008543 | 3.261 |
| Q78 | SF4 | [PASS](Experiments_Q78/SF4/results_q78_20261102_022229_148544/benchmark/result_validation.csv) | 0.681440 +/- 0.028248 | 0.525533 +/- 0.023858 | 3.909 |
| Q78 | SF8 | [PASS](Experiments_Q78/SF8/results_q78_20261102_053317_133531/benchmark/result_validation.csv) | 1.482825 +/- 0.199354 | 1.158374 +/- 0.115933 | 6.084 |
| Q95 | SF1 | [PASS](Experiments_Q95/SF1/results_q95_20261102_021719_412167/benchmark/result_validation.csv) | 0.144884 +/- 0.004396 | 0.015904 +/- 0.000676 | 2.290 |
| Q95 | SF2 | [PASS](Experiments_Q95/SF2/results_q95_20261102_021906_910855/benchmark/result_validation.csv) | 0.185063 +/- 0.015386 | 0.032836 +/- 0.004309 | 2.116 |
| Q95 | SF4 | [PASS](Experiments_Q95/SF4/results_q95_20261102_022247_371918/benchmark/result_validation.csv) | 0.487243 +/- 0.008769 | 0.071151 +/- 0.005060 | 2.792 |
| Q95 | SF8 | [PASS](Experiments_Q95/SF8/results_q95_20261102_053347_875212/benchmark/result_validation.csv) | 0.957098 +/- 0.071241 | 0.131328 +/- 0.029127 | 2.325 |

## Correctness exceptions

Q39 did not produce identical result multisets at any scale, so its benchmark timings were not recorded. The baseline and experiment returned the same number of rows, but those rows differed:

| Query | Scale | Rows each | Baseline-only | Experiment-only |
|---|---:|---:|---:|---:|
| Q39 | SF1 | 153 | 6 | 6 |
| Q39 | SF2 | 190 | 33 | 33 |
| Q39 | SF4 | 487 | 59 | 59 |
| Q39 | SF8 | 1164 | 120 | 120 |

Inspect the linked per-run validation CSVs before interpreting Q39 performance. The output comparison preserves duplicates and ignores row ordering. The Q39 experiment is included in EXPLAIN ANALYZE output, but it should not be treated as a correct equivalent rewrite until the result mismatch is resolved.

Detailed machine-readable measurements, exact run folders, validation CSV paths, and EXPLAIN plan paths are in [`query_experiment_summary.csv`](./query_experiment_summary.csv). Each per-run `benchmark/` directory also contains raw five-round measurements and summary CSVs.
