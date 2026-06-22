# New Strategy Parameter Sweeps

## Sweep A — Accelerated Momentum (top-15 by Sharpe)

Grid: lb∈[21, 42, 63, 84, 126] × win∈[5, 10, 15, 20] × ema∈[3, 5, 10, 21] × D1/D2  (160 runs)

| # | Config | CAGR | Sharpe | DD_mo | DD_d | Vol | TO/yr |
|---|--------|------|--------|-------|------|-----|-------|
| 1 | D1 | ema= 3 lb= 84 win=20 | 19.5% | 1.28 | -9.2% | -17.6% | 14.4% | 15.5× |
| 2 | D1 | ema= 5 lb= 84 win=15 | 19.3% | 1.27 | -9.0% | -16.0% | 14.4% | 13.6× |
| 3 | D1 | ema= 5 lb= 84 win=20 | 19.3% | 1.27 | -9.2% | -17.6% | 14.4% | 14.9× |
| 4 | D1 | ema= 3 lb= 84 win=15 | 19.0% | 1.25 | -9.0% | -17.6% | 14.4% | 14.2× |
| 5 | D1 | ema=10 lb= 63 win=20 | 18.5% | 1.25 | -13.7% | -19.2% | 14.1% | 15.1× |
| 6 | D2 | ema= 3 lb= 84 win=20 | 15.7% | 1.23 | -12.7% | -16.1% | 12.2% | 13.0× |
| 7 | D2 | ema= 5 lb= 84 win=20 | 15.6% | 1.22 | -12.7% | -16.1% | 12.2% | 12.9× |
| 8 | D1 | ema=10 lb= 84 win=15 | 18.2% | 1.21 | -11.1% | -19.6% | 14.4% | 12.5× |
| 9 | D1 | ema=10 lb= 84 win=20 | 18.3% | 1.20 | -11.9% | -19.6% | 14.5% | 14.5× |
| 10 | D2 | ema=10 lb= 84 win=20 | 14.9% | 1.17 | -9.9% | -16.1% | 12.2% | 12.9× |
| 11 | D1 | ema=10 lb= 84 win=10 | 17.1% | 1.15 | -9.8% | -17.8% | 14.2% | 12.7× |
| 12 | D1 | ema= 5 lb= 84 win=10 | 17.0% | 1.15 | -9.8% | -17.8% | 14.1% | 13.4× |
| 13 | D1 | ema=21 lb= 84 win=10 | 16.9% | 1.14 | -7.8% | -16.0% | 14.2% | 10.9× |
| 14 | D1 | ema=21 lb= 84 win=15 | 17.1% | 1.13 | -9.3% | -16.3% | 14.5% | 11.8× |
| 15 | D2 | ema=10 lb= 63 win=15 | 14.7% | 1.13 | -13.5% | -16.5% | 12.6% | 12.5× |

## Sweep B — Low-Corr Basket (top-15 by Sharpe)

Universe variants:
- `full_lc`: GLD in factor+sector, low-corr sectors (Energy/Util/ConsStap/Comms/HC)
- `no_gold`: normal factor sleeve, low-corr sectors without GLD
- `gold_only_sector`: normal factor sleeve, low-corr sectors with GLD

| # | Config | CAGR | Sharpe | DD_mo | DD_d | Vol | TO/yr |
|---|--------|------|--------|-------|------|-----|-------|
| 1 | D1 | no_gold              raw        sel= 84 | 18.2% | 1.30 | -10.7% | -15.5% | 13.3% | 11.3× |
| 2 | D2 | gold_only_sector     composite  sel= 84 | 14.5% | 1.26 | -10.3% | -13.4% | 10.9% | 11.1× |
| 3 | D1 | no_gold              accel      sel= 84 | 17.1% | 1.22 | -16.4% | -17.8% | 13.3% | 14.2× |
| 4 | D1 | gold_only_sector     composite  sel= 84 | 17.5% | 1.21 | -10.9% | -15.3% | 13.8% | 13.3× |
| 5 | D2 | gold_only_sector     raw        sel= 84 | 13.6% | 1.20 | -11.6% | -15.2% | 10.9% | 10.2× |
| 6 | D1 | no_gold              composite  sel= 84 | 16.9% | 1.19 | -10.9% | -15.3% | 13.5% | 12.7× |
| 7 | D2 | gold_only_sector     accel      sel= 84 | 13.4% | 1.19 | -13.8% | -15.0% | 10.9% | 12.8× |
| 8 | D1 | gold_only_sector     raw        sel= 84 | 16.1% | 1.17 | -10.7% | -15.5% | 13.2% | 11.5× |
| 9 | D2 | full_lc              raw        sel= 84 | 13.8% | 1.17 | -11.2% | -15.2% | 11.4% | 10.4× |
| 10 | D2 | no_gold              accel      sel= 84 | 13.1% | 1.14 | -13.8% | -14.6% | 11.1% | 12.8× |
| 11 | D1 | no_gold              raw        sel= 42 | 15.4% | 1.14 | -15.7% | -17.2% | 13.0% | 13.6× |
| 12 | D2 | full_lc              composite  sel= 84 | 13.5% | 1.12 | -11.5% | -14.8% | 11.6% | 11.2× |
| 13 | D2 | no_gold              composite  sel= 84 | 13.1% | 1.11 | -10.3% | -13.5% | 11.4% | 11.0× |
| 14 | D1 | gold_only_sector     accel      sel= 84 | 15.2% | 1.10 | -16.4% | -17.8% | 13.4% | 14.8× |
| 15 | D2 | full_lc              accel      sel= 84 | 12.9% | 1.10 | -13.8% | -15.0% | 11.3% | 13.0× |
