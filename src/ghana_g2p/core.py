"""Grapheme-to-phoneme conversion for Ghanaian languages."""
from __future__ import annotations

import json
import unicodedata
from dataclasses import dataclass, field
from functools import lru_cache
from importlib.resources import files
from typing import Iterable, Literal

from africa_g2p import G2P
from africa_g2p.normalizer import normalize_text, tokenize

Output = Literal["ipa", "grapheme"]
MARK = "�"  # africa-g2p's unknown='mark' sentinel


def _drop_empty_brackets(units: list[str]) -> list[str]:
    """Remove bracket pairs left empty once their contents were dropped.

    Digits are not verbalised, so "(23)" — the verse-number convention throughout this
    kind of corpus — would otherwise leave a bare "( )" carrying no prosody. Only an
    opening mark immediately followed by its closing mark is removed, so brackets around
    real content are untouched.
    """
    def cat(u: str) -> str:
        # phoneme units may be multi-character (kʰ, k͡p); only single marks can bracket
        return unicodedata.category(u) if len(u) == 1 else ""

    out: list[str] = []
    for u in units:
        if out and cat(u) == "Pe" and cat(out[-1]) == "Ps":
            out.pop()
            continue
        out.append(u)
    return out


class UnknownLanguage(KeyError):
    """Raised for a language code/name that isn't in the Ghanaian registry."""


@lru_cache(maxsize=1)
def _registry() -> dict:
    raw = json.loads((files("ghana_g2p.data") / "languages.json").read_text("utf-8"))
    return {k: v for k, v in raw.items() if not k.startswith("_")}


@lru_cache(maxsize=1)
def _patches() -> dict:
    return json.loads((files("ghana_g2p.data") / "patches.json").read_text("utf-8"))


@lru_cache(maxsize=1)
def _lookup() -> dict[str, str]:
    """code / name / alias / dataset-config-name -> canonical code."""
    out: dict[str, str] = {}
    for code, info in _registry().items():
        keys = [code, info["name"], *info.get("aliases", [])]
        for k in keys:
            out[_key(k)] = code
    return out


def _key(s: str) -> str:
    return "".join(ch for ch in s.lower().replace("_", " ").replace("-", " ") if not ch.isspace())


def languages() -> list[dict]:
    """Every Ghanaian language in the registry, with how its rules were obtained."""
    return [{"code": c, **i} for c, i in sorted(_registry().items())]


def resolve(lang: str) -> str:
    """Canonical code for an ISO code, name, alias, or ghana-speech config name."""
    try:
        return _lookup()[_key(lang)]
    except KeyError:
        raise UnknownLanguage(
            f"{lang!r} is not a known Ghanaian language. "
            f"Try one of: {', '.join(sorted(_registry()))}"
        ) from None


@dataclass
class Result:
    """Phonemes plus the provenance needed to judge how far to trust them."""

    phonemes: str
    units: list[str]
    language: str
    rules: str
    tier: str
    dropped: list[str] = field(default_factory=list)

    @property
    def is_donor(self) -> bool:
        """True when these phonemes come from a related language's rules."""
        return self.tier == "donor"

    def __str__(self) -> str:
        return self.phonemes


class GhanaG2P:
    """G2P for one Ghanaian language.

    Wraps africa-g2p with a Ghana-specific registry, Unicode normalisation for
    orthographic variants, and a patch layer for letters the upstream rule sets omit.

    Output is punctuation-free and space-free by default. Note that many units are more
    than one character (``ny`` ``kp`` ``gb`` ``kʰ`` ``k͡p``), so the run-together form is
    ambiguous: nothing marks where one phoneme ends and the next begins. Pass ``sep=" "``
    whenever a consumer needs to know the unit boundaries — forced alignment especially,
    where a character-level split would map ``nw`` to two sounds instead of one.

        >>> GhanaG2P("Asante Twi").ipa("Mfiase no Onyankopɔn bɔɔ ɔsoro.")
        'mfiasenooɲankʰopʰɔnbɔɔɔsoɾo'
        >>> GhanaG2P("Asante Twi").ipa("Onyankopɔn", sep=" ")
        'o ɲ a n kʰ o pʰ ɔ n'

    ``convert(...).units`` gives the same segmentation as a list.
    """

    def __init__(self, lang: str) -> None:
        self.code = resolve(lang)
        self.info = _registry()[self.code]
        self.rules = self.info["rules"]
        self.tier = self.info["tier"]
        self._norm: dict[str, str] = self.info.get("normalise", {})
        self._g = {
            "ipa": G2P(self.rules, output="ipa", unknown="mark"),
            "grapheme": G2P(self.rules, output="grapheme", unknown="mark"),
        }
        p = _patches()
        self._patch = dict(p["universal"])
        forced = p.get("per_rules", {}).get(self.rules, {})
        self._patch.update(forced)
        # Map the unit the rule set *currently* emits for a mis-mapped character to the
        # correct one, so the fix is a substitution on output units and never disturbs
        # multigraph segmentation.
        self._wrong: dict[str, dict[str, str]] = {}
        for ch, spec in forced.items():
            if not spec.get("force"):
                continue
            for mode in ("ipa", "grapheme"):
                cur = self._g[mode].phonemes(ch)
                if len(cur) == 1 and cur[0] != spec[mode]:
                    self._wrong.setdefault(mode, {})[cur[0]] = spec[mode]

    # -- internals ---------------------------------------------------------

    def _normalise(self, text: str) -> str:
        text = unicodedata.normalize("NFC", text)
        if self._norm:
            text = "".join(self._norm.get(ch, ch) for ch in text)
        return text

    def _units(self, text: str, output: Output) -> list[str]:
        return [u for u in self._g[output].phonemes(text) if u]

    def _known(self, ch: str, output: Output) -> bool:
        got = self._g[output].phonemes(ch)
        return bool(got) and not any(MARK in u for u in got)

    def _fix_forced(self, units: list[str], output: Output) -> list[str]:
        """Replace units the rule set maps wrongly (e.g. gur marking e/i/o long).

        africa-g2p strips diacritics before matching and re-attaches them, so a
        precomposed vowel like ẽ arrives as the base vowel's value plus a combining
        tilde. Substitutions therefore have to match the base of a unit, not only the
        whole unit, or the fix silently misses every nasalised vowel.
        """
        sub = self._wrong.get(output)
        if not sub:
            return units
        out = []
        for u in units:
            if u in sub:
                out.append(sub[u])
                continue
            for wrong, right in sub.items():
                rest = u[len(wrong):]
                if u.startswith(wrong) and rest and all(unicodedata.combining(c) for c in rest):
                    u = right + rest
                    break
            out.append(u)
        return out

    def _convert_word(self, word: str, output: Output) -> tuple[list[str], list[str]]:
        units = self._units(word, output)
        if not any(MARK in u for u in units):
            return self._fix_forced(units, output), []

        # Some character has no rule. Split the word at exactly those characters and
        # phonemise the runs between them normally, so multigraphs (ny, kp, gb, tsy…)
        # inside the known runs are still segmented as single units.
        out: list[str] = []
        dropped: list[str] = []
        run: list[str] = []

        def flush() -> None:
            if run:
                out.extend(self._fix_forced(self._units("".join(run), output), output))
                run.clear()

        for ch in word:
            if self._known(ch, output):
                run.append(ch)
                continue
            flush()
            low = ch.lower()
            patch = self._patch.get(ch) or self._patch.get(low)
            if patch:
                out.append(patch[output])
            elif low.isalpha() or unicodedata.combining(ch):
                dropped.append(ch)
        flush()
        return out, dropped

    # -- public API --------------------------------------------------------

    def _tokenized_units(self, text: str, output: Output,
                         keep_punctuation: bool) -> tuple[list[str], list[str]]:
        """Phoneme units for a whole text, optionally keeping punctuation as its own units.

        Punctuation is emitted separately rather than attached to the neighbouring
        phoneme, so the "one token = one unit" property still holds — attaching it would
        reintroduce exactly the boundary ambiguity that separating units avoids.

        Tokenizing is what makes the apostrophe behave: it counts as word-internal only
        when letters surround it, so an elision mark inside a word becomes ʔ while a
        quotation mark stands alone and is treated as punctuation. Splitting on whitespace
        instead would hand trailing quotes to the patch layer, which would read them as
        glottal stops.
        """
        units: list[str] = []
        dropped: list[str] = []
        for tok in tokenize(normalize_text(text)):
            if tok.is_word:
                u, d = self._convert_word(tok.text, output)
                units.extend(u)
                dropped.extend(d)
            elif keep_punctuation:
                units.extend(c for c in tok.text if unicodedata.category(c).startswith("P"))
        return _drop_empty_brackets(units), dropped

    def convert(self, text: str, output: Output = "ipa", sep: str = "",
                punctuation: bool = False) -> Result:
        """Phonemise `text`, returning phonemes plus provenance.

        Set `punctuation=True` to keep punctuation marks as units of their own — useful
        when the marks carry prosody (pauses, phrase breaks) you want to model. Digits are
        dropped either way; they need per-language verbalisation, which this cannot do.
        """
        units, dropped = self._tokenized_units(self._normalise(text), output, punctuation)
        return Result(
            phonemes=sep.join(units),
            units=units,
            language=self.code,
            rules=self.rules,
            tier=self.tier,
            dropped=sorted(set(dropped)),
        )

    def ipa(self, text: str, sep: str = "", punctuation: bool = False) -> str:
        """IPA phonemes, spaces stripped; punctuation stripped unless punctuation=True."""
        return self.convert(text, "ipa", sep, punctuation).phonemes

    def grapheme(self, text: str, sep: str = "", punctuation: bool = False) -> str:
        """Native-orthography units, spaces stripped; punctuation kept only on request."""
        return self.convert(text, "grapheme", sep, punctuation).phonemes

    def batch(self, texts: Iterable[str], output: Output = "ipa", sep: str = "",
              punctuation: bool = False) -> list[str]:
        """Phonemise many strings; caches per word, which matters on speech corpora."""
        cache: dict[str, list[str]] = {}
        out = []
        for t in texts:
            if not t:
                out.append("")
                continue
            units: list[str] = []
            # tokenizing (rather than splitting on whitespace) is what keeps a quotation
            # mark from being read as a glottal stop; only word tokens are worth caching
            for tok in tokenize(normalize_text(self._normalise(t))):
                if not tok.is_word:
                    if punctuation:
                        units.extend(c for c in tok.text
                                     if unicodedata.category(c).startswith("P"))
                    continue
                if tok.text not in cache:
                    cache[tok.text] = self._convert_word(tok.text, output)[0]
                units.extend(cache[tok.text])
            out.append(sep.join(_drop_empty_brackets(units)))
        return out


def g2p(text: str, lang: str, output: Output = "ipa", sep: str = "",
        punctuation: bool = False) -> str:
    """One-shot conversion."""
    return GhanaG2P(lang).convert(text, output, sep, punctuation).phonemes
