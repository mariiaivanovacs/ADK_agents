# BRICS+ University Satellite Constellation: university contact database (plan)

Goal: a ranked, contactable list of about 1,500 universities in BRICS+ countries, prioritised by
space and innovation capability. The list feeds the outreach waves (1A / 1B / 2 / 3) described in
the project questionnaire ("Университетская спутниковая группировка БРИКС", А.Н. Кальченко, 18.09.2026).

## 1. Country scope and quotas (proposed, total ≈1,500)

| Group | Country | Quota | Why |
|---|---|---|---|
| Members | China | 200 | very large system with many CubeSat universities (HIT, Tsinghua, BUAA, NUAA, NWPU, Zhejiang…) |
| | India | 200 | IITs, NITs, IIST and many student satellite teams |
| | Russia | 200 | supplied by the client; foreign universities go first in Wave 1A |
| | Brazil | 150 | federal universities, ITA, INPE partners; useful southern ground-station sites |
| | Iran | 110 | strong technical universities (Sharif, Amirkabir, KNTU, IUST) |
| | Indonesia | 110 | ITB, ITS, UI, UGM; equatorial ground-station sites |
| | Egypt | 80 | Cairo University, EgSA partners, new national universities |
| | Saudi Arabia* | 50 | KAUST, KACST partners, KSU, KFUPM (*membership status to be confirmed) |
| | South Africa | 40 | all 26 public universities plus key institutes (CPUT/F'SATI, Stellenbosch, SANSA partners) |
| | UAE | 40 | Khalifa University, AUS, UAEU, Sharjah (MBRSC CubeSat programme) |
| | Ethiopia | 40 | AAU, AASTU, ASTU, Bahir Dar, Mekelle; ESSTI/SSGI partners |
| Partners | Kazakhstan 40, Malaysia 50, Thailand 50, Vietnam 40, Belarus 30, Uzbekistan 30, Nigeria 40, Uganda 15, Cuba 10, Bolivia 10 | 315 | BRICS partner countries; several already fly CubeSats (Thailand, Malaysia, Vietnam, Kazakhstan, Nigeria, Uganda, Belarus) |
| | **Total** | **≈1,515** | |

Each quota is a maximum. A country stops at its last university that is real and relevant;
filler rows are not added to reach a number.

## 2. Columns

Required (stage 1, as specified):
1. Страна / Country
2. Вуз: official name (original language plus English)
3. Profile type, using the questionnaire's categories (1.3): классический / технический-аэрокосмический /
   аграрный-экологический / морской / НИИ-центр / гуманитарный / медицинский / другое
4. Main fields of study (top 3–6)
5. Postal address
6. E-mail (general / rectorate)
7. Rector / President / Director (name and title; for China, the President 校长, with the Party Secretary noted separately)

Added because they make outreach possible:
8. Website · 9. Phone · 10. International office e-mail (usually the fastest reply)
11. Ranking: QS 2026 / THE 2026 / national ranking (NIRF, RAEX, BCUR/ShanghaiRanking, RUF, ISC…)
12. Space evidence: CubeSats launched (count and names), satellites in development, ground station (bands),
    cleanroom or test facilities, aerospace/radio/remote-sensing departments, links with the space agency
13. Space score (0–100), with the formula in section 3
14. Outreach wave: 1A / 1B / 2 / 3
15. Source URL(s) · Date verified · Confidence (high / medium / low)

## 3. Scoring (space and innovation readiness)

| Signal | Points | Source |
|---|---|---|
| Launched own satellite / CubeSat | 35 (+5 per additional, cap 45) | nanosats.eu DB, Gunter's Space Page, UNOOSA registry |
| Satellite in development / funded mission | 15 | university news, national agency announcements |
| Ground station (SatNOGS node, own UHF/S/X station) | 10 | SatNOGS network, university sites |
| Aerospace / space / radio / remote-sensing faculty or institute | 10 | university site |
| Formal partnership with the national space agency or industry | 10 | Roscosmos, CNSA, ISRO, AEB/INPE, SANSA, EgSA, SSGI, ISA, UAESA/MBRSC, BRIN, KazCosmos… |
| Global ranking tier (QS/THE top-500 = 10, top-1000 = 6, ranked = 3) | ≤10 | QS / THE |
| National ranking top-decile | 5 | national rankings |
| International networks (UNISEC, IAF member, BRICS Network University, SCO University) | 5 | network member lists |

Wave mapping (matches the questionnaire's mailing strategy):
- **1A, anchor technology leaders**: has launched a satellite (score ≥ 60). Foreign universities are contacted before Russian ones.
- **1B, BRICS+ specifics**: leading national universities of the new members (UAE, Egypt, Ethiopia, Iran,
  Indonesia, Saudi Arabia) and universities in good ground-station locations (South Africa, Brazil, equatorial belt).
- **2, ready to start**: strong engineering, radio, remote-sensing or astronomy base but no satellite yet.
- **3, data users and education partners**: agrarian, ecological, classical and humanities-leaning universities.

## 4. Method

1. **Backbone (scripted)**: ROR registry (names, websites, IDs) + Wikidata SPARQL (heads of institution,
   addresses, type) + ranking tables → candidate pool of ~2–3× quota per country, deduplicated by ROR ID.
2. **Space signal sweep (scripted plus manual)**: match the nanosats.eu and SatNOGS lists to ROR IDs. Search for
   aerospace faculties and agency partnerships.
3. **Selection**: rank by score and take the country quota.
4. **Contact enrichment (agents, per country batch)**: read the official site (contacts page, rectorate,
   international office) for address, e-mail, phone and current rector. Every row records its source URL.
   Nothing is guessed: a missing field stays empty and is marked.
5. **QA**: e-mail syntax plus MX-record check of the domain, rector cross-check (site vs Wikipedia/news ≤ 12 months),
   dedupe, and a 5% random manual spot-check per country.
6. **Deliverable**: Excel workbook with a summary sheet, a Wave 1A/1B shortlist sheet and one sheet per country.
   A CSV copy is provided as well.

## 5. Realistic expectations

- Fill rates expected: name/type/website ~100%, address ~95%, head of institution ~90%, general e-mail ~80%
  (lower for China and Iran, where sites often only give phone numbers or web forms).
- Rector data goes out of date quickly (terms of 4–5 years), so every row is dated.
- Prefer generic institutional addresses (rectorate, international office) over personal ones.
  This respects anti-spam and data-protection law (LGPD, POPIA, PIPL, 152-FZ) and these addresses get answered.
- Some Chinese and Iranian aerospace universities are on US/EU restricted lists (e.g. "Seven Sons of National
  Defence"). This is flagged in a column because it can affect whether partners from Brazil, India, UAE or South Africa
  are willing to share a consortium with them.

## 6. Execution order

Pilot first: one small country (South Africa, ~40 rows) to validate columns and quality → client review →
remaining countries in batches, starting with the Wave 1A/1B shortlist across all countries so that
outreach can start before the full 1,500 list is finished.
