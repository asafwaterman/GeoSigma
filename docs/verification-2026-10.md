# GeoSigma data verification report (2026-10-15)

Scope: all 17 surveys, 1,371 datasets, 2,390 sites in the database and viewer. Every check below was made against the original PDF pages, not against earlier extractions.

## 1. Coverage

- **Units:** checked for all 17 surveys from the report text, sheet axes or map legends (table below).
- **Values:** re-read against the source pages.
  - VES sheets: all of Revadim (8), Tel Dan (13), Shekhem (7), Klang Afiq-Lot (20 bands), Timna (6), and about 25 of the 28 Zin sheets.
  - Spot checks: Goldman (10 printouts, 40 layers), Yizreel (30 random stations and both two-layer models), N. Arava (2 sheets), S. Arava (7 sheets), Netanya (1 sheet), Carmel (both models).
- **Afek:** all 240 plots. Axis calibrations, depth ticks and titles were checked against the printed labels, and the traced curve was overlaid on 6 plots.
- **Rotstein MT:** depths of the crustal conductor compared with the author's Table 2 for all 8 sites.
- **Pipeline:**
  - Each extractor was re-run and reproduces the committed data.
  - The structure of every model was checked: layers are contiguous, start at the surface and end in a half-space.
  - Every survey's coordinates fall in the right area.
  - The conductivity conversion (σ = 1000/ρ mS/m) and how the depth slider looks up models were checked.
  - The database rebuilds and all 13 tests pass.
- **Not checked one by one:** the remaining N. Arava sheets (248 models) and S. Arava sheets (81 models), and about 590 of the 618 Yizreel stations. These were sampled, not checked in full.

## 2. Method

1. I found the unit printed in each source and confirmed it against a value quoted in the text, where the text quotes one.
2. I compared stored values with the printed CALC. RES. bands, tables or plotted models. Depths were checked the same way.
3. I set physical limits (0.1 to 100,000 Ω·m) and looked into every value outside them.
4. I compared related figures in the same report with each other, for example the S. Arava maps against the S. Arava sheets.
5. I added regression tests so that each error found cannot come back.

## 3. Errors found and fixed (PR on branch `claude/project-thread-tt3vsq`)

| # | Error | Evidence | Fix |
|---|---|---|---|
| 1 | Revadim DP1 and DP2 were missing their 0–1 m top layer | The value is written sideways left of the AB/2 = 1 m frame (pages 10 and 11) | Added 16 and 22 Ω·m |
| 2 | Rotstein MT, site BCH: the conductor was 4 km too deep | A misplaced 100 km tick on the inset depth axis; Table 2 gives 22 km | 26.8 km corrected to 22.7 km |
| 3 | S. Arava iso-resistivity "depth" maps (604 datasets) were stored as the author's model | The map values follow the measured curve, not the model. At 400-12 the maps show 2440 and 2810, the measured curve about 2500 and 2900, and the model 62 and 6.4 Ω·m. The N. Arava report says these maps are drawn by electrode spacing. | Reclassified as measured data (L1) and removed from the model depth slider |
| 4 | 257 models with depths measured below sea level were read on the slider as depths below ground | Pipeline check | These models are now kept off the depth axis |
| 5 | 6 Afek models drop below 0.1 Ω·m (as low as 0.0x) | Lower than any brine-saturated rock, so these are inversion artefacts | Confidence set to C, with a note on the affected depths |

The earlier ohm·cm error at Shekhem (PR #7) was confirmed as correctly fixed. All four ohm·cm surveys are now protected by a test.

## 4. Per-dataset reliability

Status key: **Verified** means values were re-read and match the source. **Sampled** means a spot check matched. **Partial** means it holds with the caveat shown.

| Survey | Unit in source (evidence) | Checks | Status |
|---|---|---|---|
| Afek 2013 CSAMT | Ω·m (plot axes) | All 240 calibrations and titles; 6 overlays | Verified; 6 artefacts flagged |
| Goldman 2000 TDEM | Ω·m (table header) | 10 printouts, 40 layers, exact match | Sampled |
| Rotstein 1979 MT | Ω·m (inset axes "OHM-M") | 8 conductor depths vs Table 2 | Verified after BCH fix; DAZ 10.4 vs 12 km |
| Rotstein Carmel MT | Ω·m (text "480 אוהם מטר", sheet) | Both models | Verified |
| Klang 1970 Afiq-Lot MT | Ω·cm (sheet axis and text "220–800 Ω·cm"), ÷100 | All 20 bands and depths | Verified |
| Klang 1970 Timna-Ramon MT | Ω·cm (bands), ÷100 | All 6 | Verified |
| Klang 1974 S. Netanya MT | Ω·m (sheets, text "ohm-meters") | 1 sheet | Sampled |
| Klang 1979 Tamar MT | Ω·m (text) | Qualitative only | Verified (no numbers stored) |
| Paparo 1977 Revadim VES | Ω·m (text p.3 "30–36 ohm meter") | All 8 | Verified after fix 1 |
| Paparo 1977 Tel Dan VES | Ω·m (text) | All 13 | Verified |
| Paparo 1970 Shekhem VES | Ω·cm (text "אוהם ס״מ"), ÷100 | All 7 | Verified |
| Paparo 1978 Zin-Amazyahu-Sedom VES | Ω·m (text, 850–1300 matches) | About 25 of 28 | Verified |
| N. Arava VES (Vol 1–2) | Ω·m (Vol 1 text) | 2 sheets; depths read by eye ±10–15% | Sampled |
| Paparo 1969 S. Arava VES and maps | Ω·cm (map legend), ÷100 | 7 sheets; 213 sheet-vs-map comparisons | Partial: map values are measured data (fix 3) |
| Rotstein 1977 Yizreel-Harod | Ω·m (text and sheets) | 30 stations; 2 models | Sampled |
| Geoelectric Atlas 1982 | Unlabelled; Ω·m taken from the 1981 companion text | Not re-read | Partial |
| 1981 seawater interface | Ω·m (text) | Depths only | Sampled |

## 5. Remaining uncertainties

- **S. Arava site 400-47:** the below-sea-level map prints 280, probably a drafting slip for 2800. It is stored as printed.
- **S. Arava sheets 250-12 and 250-13:** they carry identical values, which may be a copy in the original.
- **N. Arava depths:** read by eye to about ±10–15% (for example DP808: 80 m against 92 m stored). Resistivity values are exact.
- **Paparo depth convention:** reading the CALC. RES. band edges as depths is stated only in the Tel Dan text. It is assumed to hold for the other Paparo reports.
- **Geoelectric Atlas unit:** taken from the companion 1981 text, not printed on the plots.
- **Goldman:** the 3 Ω·m seawater criterion was not re-checked in the Hebrew text.
- **The authors' models:** no raw field data exists, so I can only confirm that we copied the models faithfully, not that the models themselves are right.

## 6. Confidence

- **Units:** high. Every survey has a printed unit. Every ohm·cm source agrees with a value quoted in its own text, or with a second figure in the same report. No unit error remains that I could find.
- **Values:** high for the surveys marked Verified. For the sampled surveys it is moderate to high: no value mismatches turned up, but most of their datasets were not checked one by one.
- **What argues against overconfidence:**
  - The earlier extraction had five real errors, two of them structural (fixes 3 and 4) rather than misread numbers. More of the same kind could remain in surveys that were only sampled.
  - The largest unchecked blocks are N. Arava (248 models) and Yizreel (about 590 stations).
  - Coordinates were checked only as plausible locations, not station by station.

## 7. Reports added from Drive (2026-10-24)

The same rules applied: only the author's interpreted models are stored, each with its page and a boxed crop, and every PDF is checked against its checksum in `data/sources/manifest.json` (now all 44 files).

| Report | Stored | Checks | Status |
|---|---|---|---|
| Goldman 1987 TDEM feasibility | 28 layered models | Read from the figures | Sampled |
| Goldman et al. 1990, stage B | 59 layered models | Every value re-read at 300 dpi; depths equal the running thickness sum | Verified; GS-5, GS-6 half-spaces of 0.01 Ω·m flagged as artefacts |
| Goldman & Ezersky 1999, N. Arava | 24 models traced from plots | Axes checked against tick labels; depths agree with the text | Verified |
| Bartov 1998, N. Arava | 137 boundary depths | Typed from the report tables | Sampled |
| Goldman, Gilad & Ezersky 1998, coast | 54 models, 81 interface depths | Two independent readings per row; Table 2 against printouts | Verified; HS406, HS423, HS424 differ, noted |
| Rabinovich et al. 1993, coast and Dead Sea | 64 models, 86 interface depths | Every row against printed elevation and conductance; Table 2 against printouts | Verified |
| Goldman 1995, Mediterranean and Dead Sea | 58 models, 68 interface depths | Read by eye at 400 dpi (OCR too poor); every row against depth and conductance | Verified; HS309, HS336 differ from Table 1A, noted |
| Goldman 1996, Ashqelon | 2 models | As above; positions from the 1993 stations they repeat | Verified |
| Goldman 2001, Nahal Hever South | 5 models | As above; positions from the location map (±5 m) | Verified |

Registered without values, because the source has no usable numeric model or no position:

- **Nahal Hever North 2001:** colour cross-sections only. The 6 stations are placed from the map.
- **Zafrir et al. 1991, Ramon:** drillhole verification, with no resistivities. Table 1 misprints two hole positions (6 is printed 10 km south), so the positions for 7-A and 6 are taken from Fig. 1.
- **Meidav 1963, Qiryat Hayyim:** 4 interpreted sections in ohm·cm, but the map has no grid, so they cannot be placed.
- **Meqbel et al. 2013, Dead Sea MT:** a 2-D colour section to about 20 km, which would need digitising and georeferencing.
- **Meidav & Klang 1965, Ezersky et al. 2011, Goldman & Kafri 2021:** a telluric study, a paper without station coordinates, and a review chapter.
