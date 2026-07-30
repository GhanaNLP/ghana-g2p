# ghana-g2p

Grapheme-to-phoneme conversion for **Ghanaian languages**, built on
[africa-g2p](https://github.com/AfriSpeech/africa-g2p).

africa-g2p covers 400+ African languages from a single general registry. `ghana-g2p`
narrows that to the languages actually spoken in Ghana and fixes what breaks when you
run real Ghanaian text through it: missing rule sets, Unicode codepoint variants, and
a handful of incorrect or incomplete mappings.

```python
from ghana_g2p import GhanaG2P

tw = GhanaG2P("Asante Twi")
tw.ipa("Mfiase no Onyankopɔn bɔɔ ɔsoro.")        # 'mfiasenooɲankʰopʰɔnbɔɔɔsoɾo'
tw.grapheme("Mfiase no Onyankopɔn bɔɔ ɔsoro.")   # 'mfiasenoonyankopɔnbɔɔɔsoro'
tw.ipa("Akwaaba", sep=" ")                        # 'a kʷ a a b a'
```

## Install

Not on PyPI yet — install from GitHub:

```bash
pip install git+https://github.com/GhanaNLP/ghana-g2p
```

For development:

```bash
git clone https://github.com/GhanaNLP/ghana-g2p
cd ghana-g2p
pip install -e .
```

Note that africa-g2p is not on PyPI either, so install it from source first:

```bash
pip install git+https://github.com/AfriSpeech/africa-g2p
```

## Why this exists

Running the full [ghana-speech](https://huggingface.co/datasets/ghananlpcommunity/ghana-speech)
corpus through africa-g2p surfaced three classes of problem. Each is fixed here, and every
fix is recorded as data you can inspect rather than hidden in code.

**1. Ten Ghanaian languages have no rules at all.** Birifor, Buli, Konni, Lelemi, Ntrubo,
Sehwi, Sekpele, Selee, Tampulma and Tuwuli are simply absent. Each is mapped to a related
language chosen by linguistic classification first, then measured orthographic coverage —
never by character overlap alone, which ranks a Mande language above Dagaare for Birifor
purely because they share the Latin alphabet.

**2. Codepoint variants.** Ghanaian orthographies write the same vowel with different
Unicode characters. Birifor and Tem spell /ʊ/ as `ʊ` (U+028A); the matching rule sets use
`ʋ` (U+028B). Tumulung Sisaala writes `ɩ ʋ` where the `ssl` rules expect `ɪ ʊ`. Normalising
these lifts Tem from 0.97 to full coverage and Sisaala from 0.80 to 1.00.

**3. Incomplete and incorrect rule sets.** The `naw` rules contain no `p`; `bud` has no `e`
or `o`; `ada` has no `h` or `r`. Ewe's rules map orthographic `<y>` to IPA `y` — a front
rounded vowel — where it is the palatal glide `/j/`, as it is in every other language in the
set. Missing letters are filled from a patch table of conventional Ghanaian readings; the
Ewe error is corrected outright.

## Provenance is part of the output

A donor language gives *plausible* phonemes, not authoritative ones. Every result says
where its rules came from, so you can filter on it rather than guess:

```python
r = GhanaG2P("Sehwi").convert("kɔ ekyi")
r.phonemes    # the phonemes
r.tier        # 'donor'
r.rules       # 'any'  (Anyin — closely related Bia language)
r.is_donor    # True
r.dropped     # characters no rule could resolve
```

Tiers are:

| tier | meaning |
|---|---|
| `native` | the language's own africa-g2p rules |
| `equivalent` | the same language under a different code (Dagaare is `dgd`; Deg is `mfi`) |
| `donor` | a related language's rules, because africa-g2p has none for this one |

`GhanaG2P(...).info` carries the family, measured coverage, and a note explaining each
non-native choice.

## Languages

42 languages. Names, ISO codes, common alternates and `ghana-speech` config names all
resolve to the same entry, so you don't have to know the ISO code:

```python
GhanaG2P("Asante Twi")        # by name
GhanaG2P("twi")               # by code
GhanaG2P("Akuapem_Twi_twi")   # by ghana-speech config name
GhanaG2P("Frafra")            # by common alternate  -> gur (Ninkare)
```

```bash
ghana-g2p --list              # every language, donors marked
ghana-g2p --info Sehwi        # provenance for one language
```

### Donor mappings

| Language | Rules used | Coverage | Basis |
|---|---|---|---|
| Southern Birifor | Dagaare `dgd` | 1.00 | dialect continuum; `ʊ`→`ʋ` normalised |
| Buli | Dagaare `dgd` | 1.00 | Gur / Oti-Volta |
| Konni | Dagaare `dgd` | 1.00 | Buli-Konni branch, as Buli |
| Ntrubo | Kabiye `kbp` | 1.00 | neighbouring Gur language |
| Tampulma | Kasem `xsm` | 1.00 | Grusi branch |
| Lelemi | Avatime `avn` | 1.00 | GTM; Siwu is closer but drops `ƒ` |
| Sekpele | Ewe `ewe` | 1.00 | only donor covering `ǝ` |
| Selee | Siwu `akp` | 1.00 | Na-Togo branch |
| Tuwuli | Avatime `avn` | 1.00 | Ka-Togo branch |
| Sehwi | Anyin `any` | 1.00 | Central Tano / Bia |

Nawuri, Dangme and Bassar also use donors — not for lack of rules, but because their own
rule sets are missing core letters (`p`, `h`/`r`, and `e`/`o` respectively). They map to
Nkonya, Ga and Tem, each within the correct family.

## Output format

`ipa()` and `grapheme()` strip punctuation and whitespace. By default units run together;
pass `sep=" "` to keep the boundaries.

**Use `sep=" "` unless you have a reason not to.** Many units are more than one character —
`ny` `kp` `gb` `nw` `kʰ` `k͡p` — so the run-together form is ambiguous about where one
phoneme ends and the next begins. Twi `nw` is a single labialised nasal; a consumer that
splits on characters reads it as `n` + `w`.

This matters most for **forced alignment**. With
[ctc-forced-aligner](https://github.com/michsethowusu/ctc-forced-aligner), feed
space-separated units and align with `--split_size word`, so each phoneme unit gets one
timestamped span:

```python
from ghana_g2p import GhanaG2P
GhanaG2P("Asante Twi").ipa("Onyankopɔn nwoma", sep=" ")
# 'o ɲ a n kʰ o pʰ ɔ n nʷ o m a'   -> 13 units, 13 alignment spans
```

Run-together text would force `--split_size char`, which splits every multi-character unit.
(The aligner's normaliser folds modifier letters — `kʰ`→`kh`, `nʷ`→`nw` — but unit
boundaries survive because they are space-separated.)

### Keeping punctuation

Punctuation is stripped by default. Pass `punctuation=True` to keep it, with each mark as
its own unit — attaching it to a neighbouring phoneme would reintroduce the boundary
ambiguity that separating units avoids:

```python
GhanaG2P("twi").ipa("Wo ho te sɛn?", sep=" ", punctuation=True)
# 'w o h o tʰ e s ɛ n ?'
```

Useful when the marks carry prosody you want to model. Bracket pairs left empty once their
contents were dropped are removed, so the verse-number convention `(23)` does not leave a
bare `( )`; brackets around real content are kept.

Two more notes:

- Apostrophes are **not** punctuation in several of these orthographies — in Anyin and the
  Guang languages they mark glottal stop, and are phonemised as `ʔ`.
- Digits are dropped rather than verbalised; normalise numbers to words before phonemising
  if you need them spoken.

## Batch use

`batch()` caches per word, which matters on speech corpora where transcriptions repeat:

```python
GhanaG2P("Dagbani").batch(list_of_transcriptions)
```

## Relationship to africa-g2p

This is a wrapper, not a fork. africa-g2p does the segmentation and holds the rule data;
`ghana-g2p` adds the Ghanaian registry, the donor mappings, the normalisation and patch
layers, and the provenance reporting. Fixes that belong upstream are reported there.

## Licence

Apache-2.0. Underlying rule data is subject to africa-g2p's own licence.

## Upstream status

The defects found while building this were reported as
[AfriSpeech/africa-g2p#2](https://github.com/AfriSpeech/africa-g2p/issues/2) and fixed
upstream in [#3](https://github.com/AfriSpeech/africa-g2p/pull/3). Because the tests assert
correct output rather than the presence of a workaround, they kept passing across the change.

Now redundant (fixed upstream, kept only so older africa-g2p checkouts still work):
phonetic brackets, the Ga Greek epsilon, and the Ewe `<y>` mapping.

Still needed here: the Ninkare vowel-length correction, which is a per-language linguistic
judgement rather than a data defect, and the missing-letter patch table.

One upstream fix improved output beyond what this wrapper could do on its own — rule keys
containing combining marks are now reachable, so Ninkare `ẽ` yields `ɛ̃` (nasalization lowers
the vowel) instead of `e` plus a tilde.
