# Source manifest

Last audited: 2026-09-15 (Europe/Istanbul). S01 full text obtained and audited on that date; the licensed PDF stays in the gitignored private reference directory and is never committed or redistributed.

Source-access records below are historical evidence, not newly rechecked availability.
The [active masterplan v2.0](../GP_Attainability_Masterplan_TR.md) supersedes the old
milestone ordering. Independent implementation from attributed primary sources is allowed;
missing ECC full text blocks its specific reproduction only.

This ledger distinguishes a fully inspected primary text from metadata, an author summary,
or a planned source. `FULL` means the complete relevant text was available; it does not
mean that third-party figures or code may be redistributed.

| ID | Source | Access | Local copy | Repository use |
|---|---|---|---|---|
| S01 | [Suenaga et al., ECC 2025](https://doi.org/10.23919/ECC65951.2025.11187026) | `FULL_PDF`; IEEE Xplore via Technische Universitaet Muenchen subscription, obtained and audited 2026-09-15 | `references/private/suenaga_et_al_ecc2025.pdf` (gitignored), SHA-256 `BBA56A9059B7388305B33CCF08CC262A4ED85B0F9601B591C51B2E561652A15E` | Anchor; all nine audit topics closed with page/equation citations in [equation_map.md](equation_map.md) |
| S02 | [Hanif project explanation](https://mhd-hanif.github.io/portfolio/gp-environmental-sampling/) | `FULL_AUTHOR_SUMMARY` | No | Public setup and qualitative behaviour |
| S03 | [Hanif publication record](https://mhd-hanif.github.io/publication/2025-paper-suenaga-et-al) | `FULL_METADATA` | No | Citation and IEEE link |
| S04 | [Hatanaka Lab faculty page](https://hatanakalab.wixsite.com/website/faculty) | `FULL_WEB` | No | Lab research alignment |
| S05 | [Hatanaka Lab 2025 record](https://hatanakalab.wixsite.com/website/%E8%A4%87%E8%A3%BD-2024) | `FULL_WEB` | No | ECC paper and multi-drone SOGP overlap |
| S06 | [Hatanaka Lab 2026 record](https://hatanakalab.wixsite.com/website/%E8%A4%87%E8%A3%BD-2025) | `FULL_WEB` | No | Field-experiment continuation |
| S07 | [Tanaka et al., 2025](https://doi.org/10.1080/18824889.2025.2485496) | `FULL_PUBLISHER_HTML`; CC BY 4.0 | No | Adjacent convergence-speed method |
| S08 | [GPML Chapter 2](https://gaussianprocess.org/gpml/chapters/RW2.pdf) | `FULL_PDF` | No | Exact GP oracle equations |
| S09 | [Csató and Opper, 2002](https://eprints.soton.ac.uk/259182/1/gp2.pdf) | `FULL_PDF` | Personal temp only; SHA-256 `C768249BFDB50EABA62ED66752E09165C309874CFBAFA44022B0C2C8E52A3E8E` | Primary SOGP algorithm source; ECC-specific variant still requires audit |
| S10 | [Krause, Singh, and Guestrin, 2008](https://www.jmlr.org/papers/v9/krause08a.html) | `FULL_WEB/PDF` | No | MI/submodularity boundary |
| S11 | [Suryan and Tokekar, 2020](https://arxiv.org/abs/1909.01895) | `FULL_ARXIV` | No | Minimum-time field learning |
| S12 | [Jakkala and Akella, ICRA 2024](https://arxiv.org/abs/2309.07050) | `FULL_ARXIV` | No | Sparse-GP informative paths |
| S13 | [Jakkala et al., RSS 2026 v3](https://arxiv.org/abs/2602.05198) | `FULL_ARXIV` | No | Closest uncertainty-guaranteed IPP work |
| S14 | [Notomista and Egerstedt](https://arxiv.org/abs/1811.02465) | `FULL_ARXIV` | No | Constraint-driven coordinated control |
| S15 | [Wang, Ames, and Egerstedt, 2017](https://doi.org/10.1109/TRO.2017.2659727) | `FULL_PDF` | No | Multi-robot barrier certificates |
| S16 | [SGP-Tools](https://github.com/itskalvik/SGP-Tools) | `REPOSITORY_AUDIT_ONLY` | Not vendored | Optional external baseline; Apache-2.0 |
| S17 | [Uncertainty-guaranteed IPP experiments](https://github.com/itskalvik/uncertainty-guaranteed-ipp) | `REPOSITORY_AUDIT_ONLY` | Not vendored | Do not copy without a visible license |

## Anchor source lock

### M3 algorithm check — 15 September 2026

S09's Southampton URL returned 403 during the M3 check. The primary author-institution
[Aston NCRG/2001/014 PDF](https://publications.aston.ac.uk/id/eprint/40231/1/NCRG_2001_014.pdf)
was accessible (18 pages, corrected 9 October 2002 technical-report version).
Relevant representation, admission, projection/removal and Gaussian regression
equations 9, 11, 16, 23–27, 31 were inspected for independent implementation.
This is `ALGORITHM_SECTIONS_PDF`, not a new full-literature audit or a byte-equivalence
claim with the earlier S09 copy. No third-party PDF/code was vendored.
See [M3 implementation choices and forecast limits](M3_SOGP.md).

### ECC access boundary

At the recorded audit, the anchor DOI returned connection resets/blocked download responses
from the available browser and command-line routes. That search found no legitimate
author-hosted PDF.
The public author page supports the high-level architecture and experiment summary, but it
cannot establish exact equations, variance semantics, SOGP pruning, QP signs, or parameters.

For the ECC source audit within v2 M5, place a legally obtained copy at
`references/private/suenaga_et_al_ecc2025.pdf`, then record:

- file name and version;
- access method and UTC date;
- SHA-256;
- page count;
- supplementary/code/data links;
- license/redistribution status.

No private PDF is ever force-added to Git.
This input is not required for v2 M0 or the independent SOGP/DP/QP development milestones.
