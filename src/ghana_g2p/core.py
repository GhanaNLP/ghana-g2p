"""Grapheme-to-phoneme conversion for Ghanaian languages."""
from __future__ import annotations

import json
import unicodedata
from dataclasses import dataclass, field
from functools import lru_cache
from importlib.resources import files
from typing import Iterable, Literal

from africa_g2p import G2P

Output = Literal["ipa", "grapheme"]
MARK = "�"  # africa-g2p's unknown='mark' sentinel


# Some africa-g2p rule sets carry phonetic brackets in their values (every gur and kbp
# value is written "[a]", "[k͡p]" …) and a few use U+0241 for the glottal stop instead of
# the IPA U+0294. Neither is detectable as an "unknown" character, so we clean the units.
_SANITISE = str.maketrans({"[": None, "]": None, "Ɂ": "ʔ"})


def _sanitise(unit: str) -> str:
    return unit.translate(_SANITISE)


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

    Output defaults to the run-together form (no spaces, no punctuation) that speech
    pipelines want; pass sep=" " for space-separated units.

        >>> GhanaG2P("Asante Twi").ipa("Mfiase no Onyankopɔn bɔɔ ɔsoro.")
        'mfiasenooɲankʰopʰɔnbɔɔɔsoɾo'
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
                cur = [_sanitise(u) for u in self._g[mode].phonemes(ch)]
                if len(cur) == 1 and cur[0] != spec[mode]:
                    self._wrong.setdefault(mode, {})[cur[0]] = spec[mode]

    # -- internals ---------------------------------------------------------

    def _normalise(self, text: str) -> str:
        text = unicodedata.normalize("NFC", text)
        if self._norm:
            text = "".join(self._norm.get(ch, ch) for ch in text)
        return text

    def _units(self, text: str, output: Output) -> list[str]:
        return [s for s in (_sanitise(u) for u in self._g[output].phonemes(text)) if s]

    def _known(self, ch: str, output: Output) -> bool:
        got = self._g[output].phonemes(ch)
        return bool(got) and not any(MARK in u for u in got)

    def _fix_forced(self, units: list[str], output: Output) -> list[str]:
        """Replace units the rule set maps wrongly (e.g. Ewe <y> -> IPA y, not j)."""
        sub = self._wrong.get(output)
        if not sub:
            return units
        return [sub.get(u, u) for u in units]

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

    def convert(self, text: str, output: Output = "ipa", sep: str = "") -> Result:
        """Phonemise `text`, returning phonemes plus provenance."""
        units: list[str] = []
        dropped: list[str] = []
        for word in self._normalise(text).split():
            u, d = self._convert_word(word, output)
            units.extend(u)
            dropped.extend(d)
        return Result(
            phonemes=sep.join(units),
            units=units,
            language=self.code,
            rules=self.rules,
            tier=self.tier,
            dropped=sorted(set(dropped)),
        )

    def ipa(self, text: str, sep: str = "") -> str:
        """IPA phonemes, punctuation and spaces stripped."""
        return self.convert(text, "ipa", sep).phonemes

    def grapheme(self, text: str, sep: str = "") -> str:
        """Native-orthography phoneme units, punctuation and spaces stripped."""
        return self.convert(text, "grapheme", sep).phonemes

    def batch(self, texts: Iterable[str], output: Output = "ipa", sep: str = "") -> list[str]:
        """Phonemise many strings; caches per word, which matters on speech corpora."""
        cache: dict[str, list[str]] = {}
        out = []
        for t in texts:
            if not t:
                out.append("")
                continue
            units: list[str] = []
            for w in self._normalise(t).split():
                if w not in cache:
                    cache[w] = self._convert_word(w, output)[0]
                units.extend(cache[w])
            out.append(sep.join(units))
        return out


def g2p(text: str, lang: str, output: Output = "ipa", sep: str = "") -> str:
    """One-shot conversion."""
    return GhanaG2P(lang).convert(text, output, sep).phonemes
