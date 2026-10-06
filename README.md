# greenhouse-person-detection

> **Status, October 2026.** This describes the August version of the system: YOLO11s proposes, a DINOv2 head verifies.
> Production has since moved to a D-FINE-M student trained in-house (the 21 September model, replaced for people by a newer
> one on 28 September). That code and the camera archive are not published. What this repo is still good for is the audit
> below and the merge of six copies of one forward pass without changing the numbers.

Person detection for a greenhouse that nobody is watching: YOLO11s proposes, a
DINOv2 embedding + logistic head verifies, and a fair amount of offline tooling
exists purely to answer one question — *does any of this actually work?*

This is the single-source package that replaced 64 scripts (~11,000 lines) of
copy-pasted logic. The refactor had one hard rule: **numerical behaviour must not
change.** Every function's docstring names the file it inherited from, and the one
measured deviation is written down (see below).

The system runs unattended on a low-power box next to a real greenhouse, pulling
frames from a DVR, so most design decisions here are about cost and silence:
bandwidth is expensive, nobody is looking at the logs, and a detector that quietly
degrades is worse than one that crashes.

---

## Why this repo might be worth a look

**`sera/dedektor.py`** — the same YOLO forward pass existed in six places, all
slightly different. The bugs lived in exactly those differences:

| source file | threshold | box clamp | multi-box | NMS |
|---|---|---|---|---|
| `hacim_kuru.py` | 0.05 | yes | no (max only) | no |
| `full_scan.py` | 0.05 | yes + round | no (max only) | no |
| `retro_build.py` | 0.03 | returns no box | no (max only) | no |
| `suphe_grid.py` | 0.03 | no | no (max only) | no |
| `coklu_kutu.py` | 0.03 | yes | yes | 0.45 |
| `olay_denetim2.py` | 0.03 | no | yes | no |

The merged module documents every choice it makes, including the two deliberate
differences from the production copy, and the single numerical change that survived
the merge: float32 vs float64 box arithmetic, worst case **0.000112 px on a 1202 px
coordinate** (~1e-10 relative). It disappears downstream because the crop rounds to
int anyway. Scores are bit-identical.

That table is the actual point of the repo. Merging duplicated logic is easy; merging
it *without changing what the numbers say* is the part that takes measurement.

---

## The part I got wrong first

The detector looked fine offline and still failed in production. The model was not
the problem — **the test set was.**

The validation split had been made file-by-file, so it shared scenes with training:
48% of validation frames also appeared in the training set, 42 of them pixel-identical.
MD5 does not catch near-duplicates, and a scene that appears on both sides turns
evaluation into memorisation. The reported v1 accuracy was inflated.

Two smaller defects surfaced in the same audit: a batch of boxes had been written at
**half scale** (a clean 0.50 ratio once plotted), and 115 different files had been
saved under the same `hd.jpg` name.

Rebuilding the split **by scene** rather than by file is what made the evaluation
capable of failing. That is when the real defects appeared.

`sera/olcum.py` (measurement) and `sera/retro.py` (retrospective re-scoring of the
archive) exist because of this, and they are deliberately the largest modules here.

---

## Layout

Dependency direction is top to bottom:

| module | what it does |
|---|---|
| `ayar` | paths, thresholds, constants — every value overridable via `SERA_*` env vars |
| `gorsel` | cropping, ImageNet normalisation, box drawing, contact sheets |
| `arsiv` | archive walker: timestamps, camera/day grouping, scene grouping, event frames |
| `dedektor` | YOLO11s forward pass (640 for substream, 960 for HD) |
| `dogrulayici` | DINOv2 embedding + logistic head + threshold policy |
| `etiket` | label store and label queue |
| `olcum` | metrics, matched operating points, honest comparison |
| `egitim` | training the verifier head, scene-aware splits |
| `retro` | re-scoring the existing archive without re-downloading from the DVR |
| `olay` | event assembly, best-frame selection, pre-roll handling |
| `sahne` | scene grouping ("if an object appeared or vanished, somebody moved it") |
| `dagit` | deploying the verifier head to the box, with rollback |
| `rapor` | reports |

Import is lazy: `import sera` costs nothing, `sera.gorsel` is what pulls in OpenCV.

```python
from sera import ayar, arsiv, gorsel
ayar.ozet(); ayar.dogrula()
frames = arsiv.kaynaklar()
gorsel.kontakt([gorsel.hucre(p) for p in frames[:10]], "/tmp/look.jpg", sutun=5)
```

---

## A note on language

Module and function names are Turkish (`dedektor` = detector, `olcum` = measurement,
`dogrulayici` = verifier, `sahne` = scene, `retro` = retrospective). This is a
personal system for a family greenhouse and it was written to be read by the person
maintaining it. Docstrings carry the reasoning; the table above is the map.

Model weights (`.onnx`) and the image archive are not in this repo. `weights/`
contains only the logistic verifier head — a few hundred coefficients.

## License

MIT.
