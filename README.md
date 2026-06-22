# Stock Strategy — ETF & PPM Momentum Rotation

Backtesting, parameter sweeping, and live dashboard for two parallel momentum-rotation strategies:

1. **ETF-portfölj** — sector + factor ETFs traded on Xetra via Nordnet
2. **PPM-portfölj** — sector + factor funds on Pensionsmyndighetens fondtorg (zero transaction cost)

---

## Innehåll

- [Projektstruktur](#projektstruktur)
- [Data](#data)
- [ETF-strategier](#etf-strategier)
- [PPM-strategier](#ppm-strategier)
- [Dashboard](#dashboard)
- [Komma igång](#komma-igång)
- [Driftsättning (VPS)](#driftsättning-vps)

---

## Projektstruktur

```
Stock-strategy-1/
│
├── # ── ETF-backtests ────────────────────────────────────────────
├── etf_momentum_backtest.py      Fullständig multi-asset ETF-backtest (Strategy C)
├── backtest_engine.py            Enklare backtest-motor för ETF-sweeps
├── etf_sweep.py                  160-run parametersweep — ETF accel-signal
├── sweep_del123.py               DEL1–3-sweep (composite metric, 40 run)
├── sweep_lowcorr_combined.py     Sweep med low-corr sektorbegränsning
├── sweep_new_strategies.py       Sweep för nya strategivarianter
├── sweep_thematic.py             Tematisk ETF-sweep
│
├── # ── PPM-backtests ────────────────────────────────────────────
├── backtest_ppm.py               Komplett PPM-backtest med alla varianter
├── sweep_ppm.py                  Fullständig PPM-sweep (566 fonder, kategorikrav)
├── sweep_ppm_curated.py          1 440-konfigurationssweep, kurerat 14-fonds universum
├── monte_carlo_ppm.py            Monte Carlo (10 000 bootstrap-simuleringar)
│
├── # ── Data ─────────────────────────────────────────────────────
├── export_ppm_nav.py             Exporterar PPM-NAV från Supabase → ppm_all_nav.csv
├── ppm_all_nav.csv               ~676 000 rader daglig NAV för alla PPM-fonder
├── etf_ohlc.sqlite3              OHLCV för alla ETF:er (byggs av build_etf_price_db.py)
├── build_etf_price_db.py         Laddar ner och lagrar ETF-priser i SQLite
├── build_price_db.py             Laddar ner och lagrar svenska aktiepriser
├── etf_universe.csv              Universum av 26 ETF:er med metadata
│
├── # ── Dashboard ────────────────────────────────────────────────
└── dashboard/
    ├── backend/
    │   ├── engine.py             Huvudmotor — hämtar priser, kör strategier, skriver data.json
    │   ├── ppm_engine.py         PPM-rotationsmotor (kallad av engine.py)
    │   ├── main.py               FastAPI-server (API + statiska filer)
    │   ├── config.json           ETF-konfiguration (sleeves, tickers, TER)
    │   ├── screening_config.json Kandidat-ETF:er för screening-fliken
    │   └── requirements.txt      Python-beroenden
    └── frontend/
        ├── index.html            Single-page app (Tailwind + ECharts)
        └── static/
            ├── app.js            All frontend-logik
            └── data.json         Genererat av engine.py — läses av dashboarden
```

---

## Data

### ETF-priser

Hämtas live från **Yahoo Finance** via `yfinance` varje gång `engine.py` körs. Justerat stängningspris (adj. close) — automatiskt justerat för split och utdelning. Priser cachas i `_price_cache.pkl` för snabb återkörning med `--quick`-flaggan.

Varje ETF TER-justeras dagligen:
```
NAV(t) = NAV(t-1) × (1 + r(t)) × (1 − TER / 252)
```

### PPM-priser

Lagras i `ppm_all_nav.csv` (hämtas från Supabase med `export_ppm_nav.py`). Filen innehåller ~676 000 rader med kolumnerna `date`, `ppm_number` (str), `nav_sek`. Eftersom PPM-fondtorget inte handlas varje dag forward-fylls NAV till komplett affärsdagskalender med pandas `ffill()`.

**OBS:** `ppm_number` måste läsas in som `str` (inte `int64`) — annars tappas ledande nollor och joins fungerar inte.

### Supabase-export

```bash
python3 export_ppm_nav.py
```

Skriptet paginerar Supabase REST API (1 000 rader/anrop) och skriver `ppm_all_nav.csv`. Kräver inga environment-variabler — anonym API-nyckel är hårdkodad (publik read-only).

---

## ETF-strategier

Alla ETF-strategier delar samma **sleeve-struktur** och **regimfilter**. Det som varierar är rankingmetrik och antal picks per sleeve.

### Sleeve-struktur

Portföljen delas 50/50 mellan två sleeves:

| Sleeve | Innehåll |
|--------|----------|
| **Faktor** | USA MOM · USA QUAL · USA VAL · USA SMALL · EUR MOM · EUR QUAL · EUR VAL · EUR SMALL |
| **Sektor (full)** | IT · Energy · Healthcare · Consumer Discretionary · Industrials · Consumer Staples · Materials |
| **Sektor (low-corr)** | Energy · Utilities · Consumer Staples · Communication Services · Healthcare |

### Regimfilter

Varje månad jämförs 84-dagars avkastning för IWDA.L (MSCI World) mot IBTS.L (kortränta). Om IWDA underpresterar → hela sleeven parkeras i IBTS.L.

### Rankingmetriker

#### Raw return
```python
score = price[t] / price[t - 84] - 1
```

#### Composite (50/50)
```python
score = 0.5 * ret(21d) + 0.5 * ret(84d)
```

#### Accel-signal (bäst presterande)
```python
smooth = EMA(span=5, series=(High + Low) / 2)   # filtrerar dagsbrus
roc    = smooth[t] / smooth[t - 84] - 1          # 4-månaders momentum
accel  = roc[t] - roc[t - 15]                    # momentum-förändring
score  = roc + accel                              # = 2*roc(t) - roc(t-15)
```

Tillgångar vars momentum *ökar* (accel > 0) rankas dubbelt belönade. Optimerat via 160-run sweep: `ema=5, lb=84d, win=15d` gav Sharpe 1.27.

### Backtest-filer

| Fil | Syfte |
|-----|-------|
| `backtest_engine.py` | Enklare motor för snabba iterationer |
| `etf_momentum_backtest.py` | Fullständig Strategy C med alla features (inv-vol vikt, per-block caps, open-execution) |
| `etf_sweep.py` | 160-run accel-parametersweep |
| `sweep_del123.py` | Composite metric-sweep (DEL1–3, 40 run) |
| `sweep_lowcorr_combined.py` | Low-corr sektorbegränsning |

### Transaktionskostnader

15 bps per sida (0,15 %). Beräknas på den andel av portföljvärdet som omsätts varje månad.

---

## PPM-strategier

### Universum (14 fonder)

| PPM-nr | Namn | Roll |
|--------|------|------|
| 581371 | AP7 Aktiefond | Passiv global med hävstång — möjligt pick OCH benchmark |
| 283408 | Swedbank Robur Technology A | Sektor IT |
| 644005 | Handelsbanken Hälsovård Tema A1 | Sektor Healthcare |
| 517748 | BlackRock World Energy A2 | Sektor Energy |
| 481911 | BlackRock World Mining A2 | Sektor Mining |
| 479550 | Seligson Global Top 25 Brands A | Sektor Consumer |
| 768556 | BlackRock US Basic Value A2 | Faktor USA Value |
| 916354 | SEB Nordamerikafond Små/Medelstora A | Faktor USA Small |
| 456475 | Länsförsäkringar USA Aktiv A | Faktor USA Quality |
| 163923 | Öhman Global Growth A | Faktor USA Growth |
| 182759 | Lannebo Europa Småbolag A | Faktor EUR Small |
| 538462 | AMF Aktiefond Europa | Faktor EUR Value |
| 162099 | Storebrand Global Multifactor A | Faktor Global Multi |
| 545541 | AP7 Räntefond | Defensivt alternativ |

### Accel-signal (PPM)

Identisk logik som ETF-systemet, men med parametrar optimerade för PPM:s månadsdata:

```python
EMA_SPAN  = 5
ROC_DAYS  = 63    # 3 månader (~63 affärsdagar)
ACCEL_WIN = 10    # 10 dagars acceleration

smooth   = EMA(span=5, NAV)
roc      = smooth[t] / smooth[t - 63] - 1
accel    = roc[t] - roc[t - 10]
score    = roc + accel

raw_roc  = NAV[t] / NAV[t - 63] - 1   # för absolut momentum-filter
```

### Absolut momentum-filter

```python
if raw_roc[top_fund] < 0:
    picks = [CASH_PPM]   # 100 % AP7 Räntefond
else:
    picks = top_3_by_score   # likviktade
```

Baserat på Gary Antonaccis "Dual Momentum"-princip. Om den bästa fondens 3-månaders avkastning är negativ → hela portföljen parkeras defensivt. Detta är den enskilt viktigaste innovationen: reducerar MaxDD från −37 % (ren top-3) till −12 %.

### Parametersweep (`sweep_ppm_curated.py`)

1 440 konfigurationer testades:

| Parameter | Testvärden |
|-----------|-----------|
| EMA-span | 3, 5, 10 |
| ROC-fönster | 42d, 63d, 84d, 126d |
| Accel-fönster | 10d, 15d, 30d |
| Top-N | 1, 2, 3 |
| DD-stop | inget, −15 %, −20 % |
| Absolut momentum | av/på |
| ETF-cash-synk | av/på |

**Vinnare:** `EMA5 · ROC63d · accel10d · top3 · abs-mom=True`  
→ CAGR 26.6 % · Sharpe 1.38 · MaxDD −12.0 %

### ETF-cash-synk (alternativt läge)

Månader då D1-accel är 100 % i cash (hämtas från `data.json`) → PPM håller också AP7 Räntefond oavsett momentum-signal.  
Resultat: MaxDD −9.4 % (bättre) men CAGR 23.9 % (lägre).

### Monte Carlo (`monte_carlo_ppm.py`)

10 000 bootstrap-simuleringar med återläggning av månadsavkastningar:

```python
for i in range(10_000):
    s      = rng.choice(monthly_returns, size=N, replace=True)
    cagr   = np.prod(1 + s) ** (12/N) - 1
    sharpe = s.mean() * 12 / (s.std() * sqrt(12))
    mdd    = min drawdown of cumprod(1 + s)
```

**Resultat (top-3 + abs-mom):**
- P(slår AP7 Aktiefond): **88.2 %**
- P(CAGR > 0): **99.4 %**
- P(CAGR > 15 %): **83.7 %**
- P(DD < −15 %): **13.1 %** (vs AP7:s 48 %)

### Varför PPM > ETF-portfölj

| Faktor | PPM | ETF |
|--------|-----|-----|
| Sektorreinhet | 100 % mining-fond | Materials ETF utspädd med cement, glas m.m. |
| Defensivt alternativ | AP7 Räntefond (obligationsränta) | Kontant 0 % |
| Handelskostnad | 0 kr | 15 bps per sida |
| Universum | Sektorfonder utan kategori-constraints | Sleeve-baserat med regimfilter |

---

## Dashboard

### Arkitektur

```
Browser  ←→  nginx  ←→  uvicorn (FastAPI, port 8765)
                              ├── GET  /               → index.html
                              ├── GET  /static/*       → app.js, data.json
                              ├── GET  /api/config     → config.json
                              ├── POST /api/config     → spara + trigga engine.py
                              ├── GET  /api/status     → engine-status + senaste körning
                              ├── POST /api/recalculate → trigga engine.py
                              ├── GET  /api/screening  → screening_config.json
                              ├── POST /api/screening/add    → lägg till kandidat
                              └── DELETE /api/screening/{t} → ta bort kandidat
```

### `engine.py` — Huvudmotorn

Körs månadsvis (eller manuellt). Flöde:

1. **Ladda config** — `config.json` definierar ETF-universum, TER per fond, benchmarks
2. **Hämta priser** — `yfinance.download()` för alla tickers + benchmarks + screening-kandidater
3. **TER-justera** — multiplicerar daglig avkastning med `(1 − TER/252)`
4. **Bygg signaler** — beräknar raw-return, composite och accel-score per ETF
5. **Kör backtest** — för alla 8 strategivarianter (D1/D2 × raw/composite/accel/lowcorr)
6. **Kör PPM** — anropar `ppm_engine.run_ppm()` för PPM-strategin
7. **Screening** — beräknar accel-score för kandidater, jämför mot portföljtröskel
8. **Skriv `data.json`** — allt samlat i en fil som frontend läser

**Snabbkörning (utan download):**
```bash
python3 engine.py --quick
```

### `ppm_engine.py` — PPM-motorn

Fristående modul som kan importeras av `engine.py` eller köras via `backtest_ppm.py`. Exponerar en enda publik funktion:

```python
result = run_ppm(data_file: Path) -> dict | None
```

Returnerar `None` om CSV-filen saknas (graceful degradation). Annars returneras:

```python
{
    "label":          "PPM Top-3 + Abs-Mom",
    "nav":            [{"date": "2020-08-31", "value": 100000.0}, ...],  # daglig (ffill)
    "stats":          {"cagr": 0.266, "sharpe": 1.38, "mdd": -0.12, ...},
    "allocation":     {"dates": [...], "tickers": [...], "weights": [[...], ...]},
    "current_signal": [{"ppm": "283408", "name": "Tech", "weight": 0.333, "url": "..."}]
}
```

**Viktigt:** Nyckeltal beräknas på månadsavkastningar (inte dagliga forward-fill-värden). Annars ger `std ≈ 0` ett felaktigt Sharpe → ∞.

### `main.py` — FastAPI-servern

- Serverar `index.html` som catch-all route
- Statiska filer under `/static/`
- API-endpoints med valfri bearer-token-autentisering (miljövariabeln `DASHBOARD_SECRET`)
- POST `/api/config` sparar ny konfiguration och startar `engine.py` i bakgrunden
- POST `/api/screening/add` lägger till ticker i `screening_config.json` och triggar omberäkning

### `config.json` — ETF-konfiguration

```json
{
  "factor_sleeve": {
    "USA_MOM": {"ticker": "IMOM.L", "ter_pct": 0.30, "nordnet_name": "..."},
    ...
  },
  "sector_sleeve": {
    "IT": {"ticker": "IITU.L", "ter_pct": 0.35, ...},
    ...
  },
  "regime_baseline": {"ticker": "IWDA.L", "ter_pct": 0.20},
  "cash_proxy":      {"ticker": "IBTS.L", "ter_pct": 0.10}
}
```

### `screening_config.json` — Kandidat-ETF:er

```json
{
  "candidates": [
    {"ticker": "SEMI.DE", "label": "Semiconductors", "note": "Global semis"},
    ...
  ]
}
```

Kandidater utvärderas med D1-accel-signalen. `would_select = score > min(score för nuvarande portföljinnehav)`.

### Frontend (`index.html` + `app.js`)

Single-page app med fem flikar:

| Flik | Innehåll |
|------|----------|
| **Dashboard** | NAV-kurvor (ECharts), allokeringsdiagram, signalkort per strategi |
| **Settings** | Redigera ETF-universum live, trigga omberäkning |
| **Fondmappning** | ETF ↔ PPM-fond-mapping med ISIN och TER |
| **Screening** | Kandidat-ETF:er med accel-score, lägg till/ta bort |
| **Dokumentation** | Fullständig metodbeskrivning (renderas av `renderDocs()`) |

`data.json` laddas vid start och cachas i `DATA`-variabeln. Alla vyer renderas från detta objekt — ingen ytterligare nätverksanrop krävs utom vid inställningsändringar.

---

## Komma igång

### Förutsättningar

- Python 3.11+
- Internet (Yahoo Finance för ETF-priser)
- `ppm_all_nav.csv` (hämtas med `export_ppm_nav.py` eller kopieras manuellt)

### Installation

```bash
cd dashboard
python3 -m venv .venv
source .venv/bin/activate
pip install -r backend/requirements.txt
```

### Kör backtests lokalt

```bash
# PPM-parametersweep (1 440 konfigurationer, ~1–2 min)
python3 sweep_ppm_curated.py

# PPM-backtest med detaljerad rapport
python3 backtest_ppm.py

# Monte Carlo (10 000 sim, ~2–3 min)
python3 monte_carlo_ppm.py
```

### Starta dashboard lokalt

```bash
cd dashboard/backend
python3 engine.py            # bygg data.json (~1–2 min)
uvicorn main:app --reload --port 8765
```

Öppna `http://localhost:8765`.

**Snabbstart utan ny datahämtning:**
```bash
python3 engine.py --quick    # återanvänder cachade priser
```

### Uppdatera PPM-data

```bash
python3 export_ppm_nav.py    # skriver ppm_all_nav.csv
```

---

## Driftsättning (VPS)

### Automatisk installation

```bash
sudo bash dashboard/deploy/setup.sh /opt/etf-dashboard
```

Skriptet:
1. Installerar `python3`, `nginx` via apt
2. Kopierar app-filer till `/opt/etf-dashboard`
3. Skapar Python-venv och installerar beroenden
4. Installerar och startar systemd-tjänsten `etf-dashboard`
5. Konfigurerar nginx som reverse proxy
6. Installerar crontab för månadsvis omberäkning (sista vardagen 22:00 CET)
7. Kör initial `engine.py`

### Systemd-tjänst (`etf-dashboard.service`)

```ini
[Service]
ExecStart=/opt/etf-dashboard/venv/bin/uvicorn main:app --host 127.0.0.1 --port 8765
User=www-data
WorkingDirectory=/opt/etf-dashboard/backend
Restart=on-failure
```

```bash
systemctl status etf-dashboard
journalctl -u etf-dashboard -f
```

### Nginx

Konfigurationsfilen `deploy/nginx.conf` proxar all trafik till uvicorn på port 8765. Byt ut `your-domain.com` mot faktisk domän/IP.

**HTTPS (Let's Encrypt):**
```bash
certbot --nginx -d din-domain.com
```

### Autentisering

Skriv-API:erna (`POST /api/config`, `POST /api/recalculate`, screening-mutationer) kräver bearer-token om `DASHBOARD_SECRET` är satt:

```ini
# /etc/systemd/system/etf-dashboard.service
Environment=DASHBOARD_SECRET=byt-ut-till-starkt-lösenord
```

```bash
systemctl daemon-reload && systemctl restart etf-dashboard
```

Frontend skickar token automatiskt om man anger den i Settings-vyn.

### Månadsrutin

Crontab-jobbet kör `engine.py` sista vardagen varje månad kl. 22:00 CET. Loggas till `/var/log/etf-engine.log`. Manuell körning:

```bash
cd /opt/etf-dashboard/backend
./../../venv/bin/python3 engine.py
```

---

## Nyckelresultat

| Strategi | CAGR | Sharpe | MaxDD |
|----------|------|--------|-------|
| PPM top-3 + abs-mom | **26.6 %** | **1.38** | **−12.0 %** |
| PPM top-3 + abs-mom + ETF-cash | 23.9 % | 1.33 | −9.4 % |
| D1-accel (ETF) | ~16 % | ~1.27 | ~−19 % |
| D1-low-corr (ETF) | ~18 % | ~1.30 | ~−14 % |
| AP7 Aktiefond (benchmark) | 15.8 % | 1.24 | −16.7 % |

Monte Carlo (PPM): P(slår AP7) = **88.2 %** · P(DD < −15 %) = **13.1 %** vs AP7:s 48 %.
