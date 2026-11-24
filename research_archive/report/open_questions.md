# Open questions — things I could not close

Grouped by who has to close them. Nothing here is optional padding; each item would change the report if resolved differently.

---

## 1. You have to write these (no draft exists, by design)

| # | Item | Where | Length | Why I did not draft it |
|---|---|---|---|---|
| 1.1 | **Self Reflection** | report.md §9 | 350–450 words (0.65–0.75 page) | The outline requires "the learning process during the course". A drafted version would be the one paragraph an examiner is most likely to recognise as not yours, and it is the cheapest thing to detect |
| 1.2 | **Acknowledgement: names and sponsor** | §10 | 3 lines | I do not know the supervisors' names, the sponsor entity, or whether the industrial supervisor should be named at all. Placeholders are marked |
| 1.3 | **AI-use acknowledgement: make it true** | §10 | 1 paragraph | It is written as a template. If the actual workflow differs (for example if you rewrote every section yourself), the text must change. Submitting a false declaration is worse than submitting none |
| 1.4 | **Cover page** | before Abstract | — | Name, student ID, course code, date, supervisor names |

## 2. Facts I could not verify from inside the repository (marked [TO VERIFY] in the report)

| # | Claim | Where in report | What would close it |
|---|---|---|---|
| 2.1 | Funding interval and mark-price formula for USDⓈ-M contracts | §3.1 | Binance's published contract specification. One page, one citation. Without it, soften to "a periodic payment sized to pull the perpetual toward the index" and drop the interval |
| 2.2 | The unit in which the consumed endpoint reports open interest (contracts vs base units) | §3.1 | The endpoint's own documentation, or a worked example from the archive: compare one contract's OI to its reported volume for a known hour |
| 2.3 | Market size | §3.3 | Deliberately left as a range-free statement. If you want a number, it needs a named source and a stated definition (notional vs contracts), and it must be dated |

## 3. Literature — closed

The folder now holds exactly one PDF per reference that has a local copy: 12 files, named by citekey, no duplicates and no uncited papers. The eleven original downloads were audited and then removed on 2026-11-19; they remain in git history if ever needed.

refs.bib holds 14 verified entries and Appendix A carries the formatted list. Every DOI was resolved against Crossref or DataCite, every arXiv ID against the arXiv API, on 2026-11-19. All 15 are cited in the body — the list and the in-text citations match one for one, which is the first thing a careful reader checks. Section 2 18 of them.

Three candidates remain dropped because their abstracts could not be opened: PERP3 (IREF, 10.1016/j.iref.2026.105967), Huang et al. on ML Bitcoin volatility (JIFMIM, 10.1016/j.intfin.2024.102064), and "Crypto carry" (BIS WP 1087, no DOI). The fourth was resolved: "Perpetual futures as predictors of Bitcoin volatility" was downloaded on 2026-11-19 and is now kim2026 in refs.bib, cited in Sections 2.1 and 6.1.

Kim's result is the closest external support this project has. Funding-rate measures improve HAR forecasts of Bitcoin spot volatility in and out of sample, with gains at weekly and monthly horizons; **open-interest change alone is insignificant**, while its interaction with funding is not (0.661 weekly, t = 2.70; 0.393 monthly, t = 2.41). That is the same asymmetry the four quadrants produce, from a different conditioning variable. Quote it in the viva if anyone asks whether the second-moment finding is an artefact of this sample or this frequency.

## 4. Format and submission

| # | Question | Current state | Needed |
|---|---|---|---|
| 4.1 | Page count — **the arithmetic still does not close** | Body prose is 7,008 words today, of which 538 are placeholder scaffolding. Filling the L2 slots adds roughly 410 words, taking the body to ~7,420 words, or **~13.5 pages** at 550 words per page, before tables are counted for the vertical space they consume | Cut 1.4 pages before filling anything. In this order: §3 trim from 0.8 to 0.5 (drop the substitutes paragraph), §6.5 from 400 to 300 words, §5.2 merge into §5.1, §8 from 0.4 to 0.3. That lands at ~12.4 and leaves Section 2 intact, which is where the marks are |
| 4.2 | Citation style | APA 7 author–year chosen, with refs.bib for LaTeX | Confirm your LaTeX setup uses natbib/biblatex with an author–year style, otherwise the .bib keys still work but the in-text form changes |
| 4.3 | The [N##] tags | Left in the markdown on purpose | Strip them before submission. They are the link to numbers_audit.md, which is an internal document, not an appendix |
| 4.4 | Tables count toward the page limit | The outline exempts "figures" and "references" but not tables | Keep exactly two body tables (Table 1 and Table 2). Everything else goes to Appendix E |
| 4.5 | Signed declaration | Required, or the work is not graded | Print, sign, submit with the soft copy |

## 5. Figures

| # | Item | State |
|---|---|---|
| 5.1 | Figures 1–5 (D5 board) | Re-rendered on 2026-11-23 at 13:48 from the rebuilt board, after R2 (short covering) was added as its own list: the page now has seven sections, and Figure 2 shows four lists instead of three. All five are renders of the file being submitted |
| 5.2 | Figure 6 (f03_volatility.png) | Referenced but not inspected. Check the axis labels before captioning; the caption says "forward volatility response by cell" and must match the plot |
| 5.3 | Figure 7 (f01_equity.png) and Figure 8 (f02_cost_hurdle.png) | Same: referenced by path, captions drafted, not visually confirmed |
| 5.4 | PDFs in research_archive/literature/ | All 14 references now have a local PDF, named by citekey, one file per paper. Seven are working-paper or repository versions and will not match the published pagination: cameron2011 (cemmap), christensen2023 (Aarhus repository), cong2023, hou2020, jensen2023, petersen2009 (NBER), harvey2020 (arXiv). Three more (he2022, jadouli2026, naredla2026) exist only as preprints, so their page numbers are the only ones there are. The five publisher PDFs are brauneis2021, giagkiozis2024, kim2026, seo2020 and zaremba2021. Quote a page number only from the last five |
| 5.5 | Section 5.3 architecture | A table in the markdown, marked **[TIKZ — at LaTeX conversion]**. Replace with a drawn diagram: shared modules on top, six stage nodes in a chain, one-way arrows, each node annotated with its output directory |
| 5.6 | Cropping | figs/d5_*.png are crops of one 1600 x 5010 full-page render. Any change to the board's default date or layout invalidates all five and requires a re-render of the whole page, not a patch |

## 6. Decisions that are still reversible but expensive later

| # | Decision | Current choice | Reversal cost |
|---|---|---|---|
| 6.1 | Headline framing | "The framework is the contribution; the negative result is the evidence" | Rewriting Abstract, §7 and the presentation. Low now, high after the slides exist |
| 6.2 | The non-member divergence (N30) | Reported in §6.5 as an observation, with no causal claim | If a supervisor reads it as data-mining, it can be cut to one clause. Keeping it is the riskier but more honest choice |
| 6.3 | One-week horizon | Absent | The pipeline stops at 24 h. Adding it means re-running Phase 3 and invalidating the in-sample declaration |
| 6.4 | Title | "Price × Open-Interest Regimes in Binance Perpetual Futures" | Free to change until the cover page is fixed |

## 7. Things the report deliberately does not claim

- No out-of-sample validation. The chain is in-sample end to end.
- No claim that the regimes are useless. They predict volatility, and that result is robust.
- No claim about capacity, slippage beyond 20 bp, or live performance.
- No claim that the retail four-quadrant reading is wrong about who is trading. It may well be right about that, and still useless for prediction.

## 8. Removed on 2026-11-23 (audit sweep)

| Item | Why it went |
|---|---|
| `research_archive/_backup/` (2 files, 6.3 MB) | Superseded copies of a docx and the original Phase 3 deck |
| `research_archive/literature/cong2023.pdf` | Cong was dropped from `refs.bib`; the paper is cited nowhere in the report, the audit or the docx |
| `research_archive/report/figs/d5_panel_v2.png` | Older full-board render, replaced by `d5_full.png` |
| `data/08_strategy/tables/p5_luna.csv` | No writer in the code: an orphan from an earlier eval that was removed |
| 4 `__pycache__/` directories | Build cache |
| `backtest.trailing_vol()`, `backtest.sigma_at()` (38 lines) | Leftovers from the deleted V1 sizing layer; no caller in the repository |

After the sweep: `selftest` passes 10/10, `build all` finishes in 21.8 s, and A1/B1 still produce 10.94 / 9.86 bp gross. No file in the repository references any deleted name.

