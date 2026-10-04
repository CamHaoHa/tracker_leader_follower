| Metric | V1 (baseline) | V2 (search after loss) | Significance |
|---|---|---|---|
| Tracking time recorded | 305 s | 112 s |  |
| Losses (n) | 70 | 37 |  |
| Losses per tracking minute | 13.8 | 19.9 |  |
| Fix from 2+ boxes | 70 % | 67 % |  |
| Reacquire time, median | 0.51 s | 0.21 s | p = 0.016 |
| Reacquire time, mean | 0.79 s | 0.47 s | p = 0.032 |
| Reacquire time, 90th percentile | 2.25 s | 1.12 s |  |
| Reacquire time, longest | 6.13 s | 2.45 s |  |
| Losses longer than 1 s | 20 % | 16 % |  |
| Losses longer than 2 s | 10 % | 3 % | p = 0.163 |
| Losses longer than 3 s | 4 % | 0 % |  |

Data: `jump-v1-3.csv` (V1) and `jump-v2-1.csv` (V2), three boxes, same calibration and field config. p = one-sided permutation test (20 000 shuffles), V1 slower than V2. Times are resolved to about 0.1 s (recording interval).
