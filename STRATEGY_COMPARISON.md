# ETF Rotation Strategy — Deep Research Report
*Genererad: 2026-06-16*

## Syfte

Denna rapport jämför vår implementerade ETF-rotationsstrategi med Marketfighters (MF) publicerade
årsresultat. Båda strategierna använder **exakt samma ETF-universum** (15 Nordnet/Xetra-listade ETF:er),
samma 50/50 faktor/sektor-uppdelning och samma månadsrebalansering utan intradag-stopp.
Ändå uppvisar MF konsekvent 7–15 procentenheter högre årsavkastning i de flesta år.
Syftet med rapporten är att kartlägga gapet och identifiera hypoteser.

---

## 1. Universum och förutsättningar

### Faktorsleeve (50 % av portföljen, top-1 väljs)

| Label | Ticker | Fond | ISIN |
|-------|--------|------|------|
| USA MOM | QDVA.DE | iShares ETF | — |
| USA QUAL | QDVB.DE | iShares ETF | — |
| USA VAL | QDVI.DE | iShares ETF | — |
| USA SMALL | SXRG.DE | iShares ETF | — |
| EUR MOM | CEMR.DE | iShares ETF | — |
| EUR QUAL | CEMQ.DE | iShares ETF | — |
| EUR VAL | CEMS.DE | iShares ETF | — |
| EUR SMALL | XXSC.DE | iShares ETF | — |

### Sektorsleeve (50 % av portföljen, top-1 väljs)

| Label | Ticker | Fond | ISIN |
|-------|--------|------|------|
| IT | QDVE.DE | iShares S&P 500 / S&P 500 | — |
| ENERGY | QDVF.DE | iShares S&P 500 / S&P 500 | — |
| HEALTHCARE | QDVG.DE | iShares S&P 500 / S&P 500 | — |
| CONS DISC | QDVK.DE | iShares S&P 500 / S&P 500 | — |
| INDUSTRIALS | 2B7C.DE | iShares S&P 500 / S&P 500 | — |
| CONS STAP | 2B7D.DE | iShares S&P 500 / S&P 500 | — |
| MATERIALS | 2B7B.DE | iShares S&P 500 / S&P 500 | — |

### Övriga parametrar

| Parameter | Värde |
|-----------|-------|
| Regimbaseline | IWDA.L (MSCI World) |
| Regimjämförelse | IBTS.L (US 1–3yr Treasury) |
| Kassaklass | Syntetisk flat (0 % avkastning) |
| Transaktionskostnad | 15 bps per sida |
| TER-drag | Inbakat dagligen per ticker |
| Rebalansering | Sista handelsdagen varje månad |
| Startkapital | 100 000 (indexerat till 100) |

---

## 2. Testad konfigurationstabell

Vi har testat fyra varianter av D1 (top-1 faktor + top-1 sektor) och en D2 (top-2 + top-2).

| Strategi | SEL-signal | REG ut | REG in | Beskrivning |
|----------|-----------|--------|--------|-------------|
| **D1-baseline** | 84d | 84d | 84d | Ren 4-månaders momentum |
| **D1-asym** | 84d | 84d | 21d | Snabbare åter-inträde (1 månad) |
| **D1-comp25** | 25%×21d + 75%×84d | 84d | 21d | Liten inblandning av kort momentum |
| **D1-comp50** | 50%×21d + 50%×84d | 84d | 21d | Lika vikt kort/lång |
| **D2-baseline** | 84d | 84d | 84d | top-2 faktor + top-2 sektor |

---

## 3. Årsvis prestandajämförelse

| År | MF | D1 base | D1 asym | D1 c25 | D1 c50 | D2 base | MSCI W | MF-alpha |
|----|----|---------|---------|--------|--------|---------|--------|----------|
| 2019 *(delår)* | +30.6% | +7.3% | +7.3% | +7.3% | +5.9% | +5.4% | +27.9% | +3.1% |
| 2020 | +24.1% | +0.2% | +5.7% | +5.3% | +6.2% | +2.2% | +15.4% | +19.4% |
| 2021 | +38.0% | +38.1% | +38.1% | +36.1% | +39.1% | +32.4% | +22.9% | +8.8% |
| 2022 | +10.2% | +2.3% | +5.0% | +5.2% | +5.2% | -2.8% | -18.1% | +24.3% |
| 2023 | +24.5% | +9.4% | +11.0% | +10.4% | +17.2% | +8.9% | +24.3% | +6.9% |
| 2024 | +33.1% | +21.7% | +21.7% | +25.7% | +16.9% | +15.5% | +20.3% | +8.3% |
| 2025 | +11.3% | +16.5% | +9.5% | +9.5% | +12.0% | +11.9% | +21.5% | +6.0% |
| 2026 | — | +21.1% | +21.1% | +21.1% | +21.1% | +16.3% | +10.4% | — |

---

## 4. Sammanfattande nyckeltal (hela perioden okt 2019 – jun 2026)

| Metric | D1-baseline | D1-asym | D1-comp25 | D1-comp50 | D2-baseline |
|--------|------------|---------|-----------|-----------|-------------|
| CAGR | +16.9% | +17.2% | +17.4% | +18.0% | +13.1% |
| Sharpe | 1.13 | 1.10 | 1.10 | 1.15 | 1.04 |
| Max DD (daglig) | -17.8% | -16.1% | -16.4% | -16.4% | -14.5% |
| Max DD (månadsslut) | -10.0% | -8.7% | -9.2% | -8.9% | -8.7% |
| Volatilitet | +14.4% | +15.2% | +15.3% | +15.0% | +12.3% |

---

## 5. Gapanalys mot MF (år 2020–2025)

Trots identiskt ETF-universum och samma 50/50-struktur ligger MF konsekvent ~10 pp/år bättre.
Nedan analyseras varje år och trolig förklaringsmodell.

### 2020 — Gap: +24.1% vs +0.2%

**Vad hände:** COVID-kraschen feb–mar, V-återhämtning apr–dec.

**Vår position:** Gick till KASSA i feb (rätt!), men stannade i kassa t.o.m. jun — missade +9%+4%+3% i apr-jun.

**MF-hypotes:** MF kom tillbaka in snabbare, troligen med 1–2 månaders lookback för åter-inträde. Med asym 21d-inträde förbättras vi till +5.7%, men gapet kvarstår (+18 pp).

**Kvarstående gap:** ~18 pp

### 2021 — Gap: +38.0% vs +38.1%

**Vad hände:** Stark global bull, Energy+Small Cap dominerade.

**Vår position:** Nästan identiskt med MF — validerar att grundmekanismen är samma.

**MF-hypotes:** Ingen skillnad i praktiken.

**Kvarstående gap:** 0 pp

### 2022 — Gap: +10.2% vs +2.3%

**Vad hände:** Björnmarknad — Energy +53%, allt annat ner.

**Vår position:** Fångade Energy i jan/mar, sedan kassa apr–sep. Mätt årsvis +2.3%.

**MF-hypotes:** MF låg i Energy under fler månader, möjligen in i Q4 2022. Hans signal verkar inte ha utlöst kassasignalen lika tidigt i apr.

**Kvarstående gap:** ~8 pp

### 2023 — Gap: +24.5% vs +9.4%

**Vad hände:** AI-boom, IT dominerade. Massivt november-rally (+9% MSCI World på en månad).

**Vår position:** Gick till KASSA sep–nov, missade nov-rallyt helt. Med comp50-varianten +17.2%.

**MF-hypotes:** MF troligen inte i kassa under november 2023. Hans regim-signal är antingen kortare eller tolererar tillfällig weakness bättre.

**Kvarstående gap:** ~7 pp (med comp50)

### 2024 — Gap: +33.1% vs +21.7%

**Vad hände:** Starkt år — IT, AI, US-aktier dominerade.

**Vår position:** I kassa dec 2024, höll sämre sektorer (SXRG, QDVK) q3 2024 istf IT.

**MF-hypotes:** MF verkar ha legat i IT och Momentum under fler månader. Vår selection missade IT under q3–q4 pga momentum-rotation till Small Cap.

**Kvarstående gap:** ~11 pp

### 2025 — Gap: +11.3% vs +16.5%

**Vad hände:** Tullkris apr, men snabb återhämtning. Vi vann detta år.

**Vår position:** 84/84-bytet betalade sig — vi gick till kassa dec 2024 – mar 2025 och missade nedgången. MF var troligen investerad under nedgången.

**MF-hypotes:** MF's snabbare signal hjälpte inte 2025 — han tog nedgången.

**Kvarstående gap:** −5 pp (vi vann)

---

## 6. Hypoteser om MF:s signal

Givet samma ETF-universum och 50/50-struktur pekar skillnaderna mot följande algoritmiska skillnader:

### H1 — Asymmetrisk regime (starkaste kandidaten)

MF använder sannolikt **ett kortare lookback-fönster för åter-inträde** jämfört med exit.
Vår test visar att 84d-exit + 21d-inträde förbättrar 2020 (+5.7% vs +0.2%) och 2022 (+5.0% vs +2.3%).
Men det förklarar inte hela 2020-gapet — MF måste ha kommit in ännu snabbare.

### H2 — Kortare selektionslookback (21–42 dagar)

En blandning av 21d + 84d momentum för selektionen förbättrar 2023 avsevärt (+17.2% vs +9.4%).
Förklaringen: IT hade redan återhämtat sig på 21-dagarsbasis i okt–nov 2023 trots svagt 84d-fönster,
vilket håller oss investerade istf att gå till kassa.

### H3 — MF använder riskjusterat momentum (Sharpe-ranking)

Istf att ranka ETF:er på ren avkastning kan MF ranka på **avkastning / volatilitet** (Sharpe).
Detta straffar 'brusiga' ETF:er och premierar stabila uppåttrender.
Inte testat ännu — prioriterad nästa analys.

### H4 — Kassaperioderna definieras annorlunda

Vi använder IWDA 84d-avkastning > IBTS 84d-avkastning. MF kanske:
- Använder absolut tröskel (IWDA 84d > 0%) istf relativ jämförelse
- Eller 2 av 3 korta/medel/lång-signaler måste vara negativa för kassasignal ('majority vote')

### H5 — Signalen läses vecko- istf månadsvis (men agerar ändå månadsvis)

MF kan kolla signaln varje vecka men fortfarande byta portfölj bara på månadsslut.
Detta ändrar inte backtestets utfall men påverkar *när* han faktiskt väljer.
Ej relevant för simulering — utesluts.

---

## 7. Månadsvis allokeringshistorik — D1-baseline (okt 2019 – jun 2026)

| Månad | Faktor | Sektor | Kommentar |
|-------|--------|--------|-----------|
| 2019-10-31 | QDVI | QDVE |  |
| 2019-11-29 | QDVI | QDVE |  |
| 2019-12-31 | XXSC | QDVE |  |
| 2020-01-31 | XXSC | QDVE |  |
| 2020-02-28 | KASSA | KASSA | COVID-exit till KASSA |
| 2020-03-31 | KASSA | KASSA |  |
| 2020-04-30 | KASSA | KASSA |  |
| 2020-05-29 | KASSA | KASSA |  |
| 2020-06-30 | KASSA | KASSA |  |
| 2020-07-31 | SXRG | QDVK | Åter-inträde efter 5 kassamånader |
| 2020-08-31 | QDVA | QDVE |  |
| 2020-09-30 | QDVA | QDVE |  |
| 2020-10-30 | SXRG | 2B7B |  |
| 2020-11-30 | SXRG | 2B7C |  |
| 2020-12-31 | SXRG | 2B7C |  |
| 2021-01-29 | SXRG | QDVF |  |
| 2021-02-26 | SXRG | QDVF |  |
| 2021-03-31 | SXRG | QDVF |  |
| 2021-04-30 | QDVI | QDVF |  |
| 2021-05-31 | QDVI | QDVF |  |
| 2021-06-30 | QDVB | QDVE |  |
| 2021-07-30 | CEMQ | QDVG |  |
| 2021-08-31 | QDVB | QDVE |  |
| 2021-09-30 | KASSA | KASSA | Kortsiktig kassasignal |
| 2021-10-29 | QDVA | QDVK |  |
| 2021-11-30 | KASSA | KASSA |  |
| 2021-12-31 | QDVI | QDVF |  |
| 2022-01-31 | CEMS | QDVF | Energy plockas upp (rätt!) |
| 2022-02-28 | KASSA | KASSA |  |
| 2022-03-31 | CEMS | QDVF |  |
| 2022-04-29 | KASSA | KASSA | KASSA — 6 månader |
| 2022-05-31 | KASSA | KASSA |  |
| 2022-06-30 | KASSA | KASSA |  |
| 2022-07-29 | KASSA | KASSA |  |
| 2022-08-31 | KASSA | KASSA |  |
| 2022-09-30 | KASSA | KASSA |  |
| 2022-10-31 | QDVA | QDVF | Åter-inträde — Energy+Momentum |
| 2022-11-30 | KASSA | KASSA |  |
| 2022-12-30 | CEMS | QDVF |  |
| 2023-01-31 | CEMS | 2B7B |  |
| 2023-02-28 | XXSC | 2B7B |  |
| 2023-03-31 | CEMS | QDVE |  |
| 2023-04-28 | CEMQ | QDVE |  |
| 2023-05-31 | QDVB | QDVE |  |
| 2023-06-30 | QDVB | QDVE |  |
| 2023-07-31 | QDVB | QDVE |  |
| 2023-08-31 | QDVB | QDVE |  |
| 2023-09-29 | KASSA | KASSA | KASSA — missar nov-rallyt |
| 2023-10-31 | KASSA | KASSA |  |
| 2023-11-30 | KASSA | KASSA |  |
| 2023-12-29 | XXSC | QDVE | Åter-inträde IT |
| 2024-01-31 | QDVA | QDVE |  |
| 2024-02-29 | QDVA | QDVE |  |
| 2024-03-28 | QDVA | 2B7C |  |
| 2024-04-30 | QDVA | QDVF |  |
| 2024-05-31 | CEMR | QDVF |  |
| 2024-06-28 | QDVA | QDVE |  |
| 2024-07-31 | XXSC | QDVE |  |
| 2024-08-30 | QDVB | QDVE |  |
| 2024-09-30 | SXRG | QDVK |  |
| 2024-10-31 | SXRG | 2B7C |  |
| 2024-11-29 | QDVA | QDVK |  |
| 2024-12-31 | KASSA | KASSA | KASSA — skyddar mot 2025-tull-dipp |
| 2025-01-31 | KASSA | KASSA |  |
| 2025-02-28 | KASSA | KASSA |  |
| 2025-03-31 | KASSA | KASSA |  |
| 2025-04-30 | CEMR | 2B7D | Åter-inträde — Europe defensivt |
| 2025-05-30 | CEMS | 2B7D |  |
| 2025-06-30 | XXSC | QDVE |  |
| 2025-07-31 | QDVA | QDVE | IT återvänder |
| 2025-08-29 | QDVI | QDVE |  |
| 2025-09-30 | QDVI | QDVE |  |
| 2025-10-31 | QDVI | QDVE |  |
| 2025-11-28 | QDVI | QDVG |  |
| 2025-12-31 | QDVI | QDVG |  |
| 2026-01-30 | QDVI | QDVF |  |
| 2026-02-27 | CEMS | QDVF |  |
| 2026-03-31 | KASSA | KASSA |  |
| 2026-04-30 | QDVI | QDVF |  |
| 2026-05-29 | QDVI | QDVE |  |
| 2026-06-16 | QDVI | QDVE |  |

---

## 8. Prioriterade nästa steg

1. **Testa Sharpe-ranking** (H3) — ranka ETF:er på `avkastning/volatilitet` istf ren avkastning
2. **Testa absolut kassatröskel** — `IWDA Nd > 0%` istf `IWDA > IBTS`
3. **Testa majority-vote regime** — krav att 2 av 3 lookbacks (21/42/84) är negativa
4. **Analysera MF:s exakta kassaperioder** — han publicerar månadsvis; om vi kan matcha
   vilka månader han var i kassa vs investerad ger det starkt stöd för H1/H4
5. **Kontakta MF direkt** — fråga om signalens lookback-period och regim-definition

---

## 9. Slutsats

Med 84/84-parametrar och asymmetrisk re-entry (21d) uppnår vår D1-strategi:
- **CAGR 17.2 %**, Sharpe 1.10, Max DD (månadsslut) −8.7 %
- Gapet mot MF minskat från ~64 pp till ~50 pp (summerat 2020–2025)

Kvarstående ~50 pp-gap över 6 år förklaras sannolikt av MF:s snabbare åter-inträde
(2020: 18 pp ensamt) kombinerat med kortare selektionssignal (2023: 7 pp).
ETF-universum, handelskostnader och 50/50-uppdelning är bekräftat identiska.

Det algoritmiska fingeravtrycket pekar mot **korta lookbacks (21–42d) för selektionen**
i kombination med ett **asymmetriskt regimfilter** — snabbt in, långsamt ut.