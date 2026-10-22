# StegoForge Detector Evaluation

Measured with `scripts/eval_detectors.py --roc` on 2026-10-22.

Corpus: stock `tests/fixtures` images x depths {1,2} x {keyless,keyed} = 16 stego + 4 clean. Detectors run via `op_detect` defaults. **n is tiny (4 clean, 16 stego) and most fixtures are noise-like images, so every rate below has a very wide error bar.** Treat the table as a smoke test, not a benchmark.

## ROC (image carriers, small payloads)

| Detector | TPR | FPR | Guidance |
|---|---|---|---|
| blind | 0.625 | 0.000 | high precision; finds only unkeyed embeds and StegoForge's own layout, so keyed embeds are invisible to it |
| chi2 | 0.125 | 0.000 | triage only; says *inconclusive* (not clean) when the image's pair statistics are already equalised |
| rs | 0.250 | 0.250 | triage only; one of four clean files is flagged |
| exif | 0.000 | 0.000 | triage only; LSB embeds leave no metadata |
| fingerprint | 0.000 | 0.000 | PRNU-only; silent for non-adaptive embeds by design |
| ml | 0.000 | 0.000 | the bundled weights are an ImageNet classifier; only the heuristic fallback runs (`MODEL-CARD.md`) |

Earlier revisions of this file and of the changelog reported "zero false positives on every detector" and a blind TPR of 1.000. Neither held: RS flags 1 of 4 clean files, and blind TPR dropped once keyed embeds were counted correctly.

## What changed on 2026-10-22

- **chi2** now (1) skips pairs with fewer than 10 samples, (2) ignores constant planes such as an opaque alpha channel, which used to add a term as large as the pixel count and hide every embed in RGBA images, (3) scans prefix windows because StegoForge's sequential embed only touches a prefix of the sample stream, (4) uses the untouched tail of the image as its reference and reports `reliable: false` (shown as INCONCLUSIVE) when the tail is equalised too, and (5) ignores the spatial verdict for JPEG, where decoded pixels carry no LSB information. The JPEG-DCT sub-signal is unchanged and bit-identical to the old loop, now vectorised.
- **binary** counts only non-zero, non-uniform bytes in padding that linkers leave zero-filled (ELF section gaps, PE section tails). NOTE sections and overlays hold real data and are ignored. All nine system ELFs checked (`ls`, `cat`, `python3`, `ffmpeg`, `zsh`, `git`, `libc.so.6`, `gcc`, `bash`) were flagged before; none are now. A validated payload extraction is still a definitive positive.
- **video-anomaly** no longer scores frames against their own mean (an estimated one clean clip in three tripped it). It reports a positive only for a validated, unkeyed `video-dct`/`video-motion` extraction and otherwise says *inconclusive*.

## Threshold guidance

- `blind.confidence >= 0.8` (about a magic-header hit) is actionable on its own.
- An INCONCLUSIVE or CLEAN result never proves a file is clean; chi-square and RS are weak against small or adaptive payloads.
- The ML score is not a verdict.
- Re-run after any detector change: `python scripts/eval_detectors.py --roc`.

## Limitations

Small corpus (n=20), one payload size, no JPEG-recompress or adaptive-method variants. See `scripts/make_survival_fixtures.py` for the recompress corpus.
