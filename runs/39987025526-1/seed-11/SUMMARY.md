# Published postcondition feasibility screen

Evaluation bounds use published soundness/power metadata. Author doc tests and post validation were executed in this run. No model inference or success claim.

Semantic caveat: doc filtering uses the original example inputs and expected output. Published power/soundness evaluates parameters after the subject call, which may mutate them. This screen cannot establish a method advantage; faithful wrapper replay and state review are required before inference comparison.

## first24: 24 tasks

Oracle ceiling: 109 naturally generated + 665 explicitly artificial faulty programs.

| Control | Natural | Artificial | False-alarm tasks | Unknown tasks | Ceiling misses |
|---|---:|---:|---:|---:|---:|
| all | 24 | 268 | 13 | 3 | 482 |
| dedup | 24 | 268 | 13 | 3 | 482 |
| doc_filter | 34 | 363 | 7 | 3 | 377 |
| doc_filter_dedup | 34 | 363 | 7 | 3 | 377 |
| shortest | 57 | 409 | 4 | 3 | 308 |
| dependencies | 34 | 391 | 5 | 3 | 349 |
| contrastive | 34 | 406 | 5 | 3 | 334 |
| author_docs | 84 | 641 | 0 | 4 | 49 |
| docs_plus_filtered | 41 | 417 | 7 | 4 | 316 |
| docs_plus_shortest | 86 | 519 | 4 | 4 | 169 |
| docs_plus_dependencies | 41 | 468 | 5 | 4 | 265 |
| docs_plus_contrastive | 41 | 469 | 5 | 4 | 264 |

## all164: 164 tasks

Oracle ceiling: 1266 naturally generated + 3436 explicitly artificial faulty programs.

| Control | Natural | Artificial | False-alarm tasks | Unknown tasks | Ceiling misses |
|---|---:|---:|---:|---:|---:|
| all | 291 | 1321 | 110 | 12 | 3090 |
| dedup | 291 | 1321 | 110 | 12 | 3090 |
| doc_filter | 212 | 966 | 20 | 12 | 3524 |
| doc_filter_dedup | 212 | 966 | 20 | 12 | 3524 |
| shortest | 230 | 1010 | 11 | 12 | 3462 |
| dependencies | 221 | 1036 | 12 | 12 | 3445 |
| contrastive | 223 | 1058 | 14 | 12 | 3421 |
| author_docs | 438 | 1530 | 9 | 20 | 2734 |
| docs_plus_filtered | 351 | 1132 | 28 | 20 | 3219 |
| docs_plus_shortest | 402 | 1299 | 20 | 20 | 3001 |
| docs_plus_dependencies | 362 | 1249 | 21 | 20 | 3091 |
| docs_plus_contrastive | 362 | 1245 | 22 | 20 | 3095 |

