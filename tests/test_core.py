"""Tests for ghana-g2p.

Several of these pin down specific defects found in the upstream africa-g2p rule data.
They are written so that if upstream fixes a defect, the test still passes — they assert
the correct output, not the presence of our workaround.
"""
from __future__ import annotations

import pytest

from ghana_g2p import GhanaG2P, UnknownLanguage, g2p, languages, resolve


# -- registry -------------------------------------------------------------

def test_registry_has_42_languages():
    assert len(languages()) == 42


def test_every_language_constructs():
    for info in languages():
        g = GhanaG2P(info["code"])
        assert g.ipa("aba") or g.grapheme("aba")


@pytest.mark.parametrize(
    "alias,expected",
    [
        ("twi", "twi"),
        ("Asante Twi", "twi"),
        ("Akuapem_Twi_twi", "twi"),      # ghana-speech config name
        ("Asante_Twi_twi", "twi"),
        ("Frafra", "gur"),               # common alternate name
        ("Gurene", "gur"),
        ("Likpe", "lip"),
        ("Santrokofi", "snw"),
        ("Sefwi", "sfw"),
        ("Builsa", "bwu"),
        ("Sisaala_Tumulung_sil", "sil"),
    ],
)
def test_resolve_aliases(alias, expected):
    assert resolve(alias) == expected


def test_unknown_language_lists_options():
    with pytest.raises(UnknownLanguage) as e:
        GhanaG2P("Klingon")
    assert "twi" in str(e.value)


# -- output format --------------------------------------------------------

def test_no_spaces_or_punctuation_by_default():
    out = GhanaG2P("twi").ipa("Mfiase no Onyankopɔn bɔɔ ɔsoro.")
    assert " " not in out
    assert not any(c in out for c in ".,;:!?\"")


def test_sep_gives_separated_units():
    assert GhanaG2P("twi").ipa("Akwaaba", sep=" ").split() == ["a", "kʷ", "a", "a", "b", "a"]


def test_grapheme_mode_stays_in_orthography():
    assert GhanaG2P("twi").grapheme("Onyankopɔn") == "onyankopɔn"


def test_batch_matches_single():
    g = GhanaG2P("dag")
    texts = ["Naawuni", "yɛlimaŋli", "Naawuni"]
    assert g.batch(texts) == [g.ipa(t) for t in texts]


def test_empty_and_whitespace():
    g = GhanaG2P("twi")
    assert g.ipa("") == ""
    assert g.ipa("   ") == ""
    assert g.batch(["", None or ""]) == ["", ""]


# -- multigraph handling --------------------------------------------------

def test_multigraphs_stay_single_units():
    # 'ny' is one unit /ɲ/, not n + y
    assert GhanaG2P("twi").convert("Onyankopɔn").units == [
        "o", "ɲ", "a", "n", "kʰ", "o", "pʰ", "ɔ", "n",
    ]


def test_multigraph_survives_patch_path():
    # 'ny' must stay /ɲ/ even though the Ewe <y> correction is active for this rule set
    assert GhanaG2P("ewe").convert("nyui").units == ["ɲ", "u", "i"]


# -- upstream defects -----------------------------------------------------

def test_ewe_y_is_palatal_glide():
    """africa-g2p maps Ewe <y> to IPA y (front rounded vowel); it is /j/."""
    assert GhanaG2P("ewe").ipa("yayra") == "jajra"


@pytest.mark.parametrize("lang", ["gur", "kbp", "ntr"])
def test_no_phonetic_brackets_in_output(lang):
    """gur and kbp rule values are written "[a]", "[k͡p]" — brackets must not leak."""
    out = GhanaG2P(lang).ipa("abadeŋ")
    assert "[" not in out and "]" not in out


def test_ga_epsilon_is_ipa_not_greek():
    """The gaa rules emit GREEK SMALL LETTER EPSILON U+03B5; IPA open-e is U+025B."""
    out = GhanaG2P("Dangme").ipa("nyɛmimɛ")
    assert "ε" not in out
    assert "ɛ" in out


def test_ninkare_vowels_not_spuriously_long():
    """gur marks e/i/o long while a/u/ɛ/ɔ stay short - an ATR contrast, not length."""
    assert GhanaG2P("Ninkare").ipa("botɩ") == "botɪ"


def test_ninkare_real_length_preserved():
    """The fix must not strip length from genuinely doubled vowels."""
    assert GhanaG2P("Ninkare").convert("baa").units == ["b", "aː"]


def test_nasal_vowel_uses_declared_value():
    """Ninkare's rules declare ẽ -> ɛ̃: nasalization lowers the vowel, it is not a suffix.

    Units carry combining marks rather than precomposed characters — many IPA
    combinations have no precomposed form, so the decomposed shape is the consistent one.
    """
    assert GhanaG2P("Ninkare").convert("wẽ").units == ["w", "ɛ̃"]
    assert "ː" not in GhanaG2P("Ninkare").ipa("wẽ")  # no spurious length


def test_ewe_voiced_bilabial_fricative_is_beta():
    """Ewe <ʋ> is /β/ - U+03B2 is the correct IPA codepoint here, not a defect."""
    assert GhanaG2P("ewe").ipa("aʋa") == "aβa"


def test_glottal_stop_is_ipa_codepoint():
    """gur uses U+0241; IPA glottal stop is U+0294."""
    out = GhanaG2P("Anyin").ipa("m'ɔ")
    assert "Ɂ" not in out
    assert "ʔ" in out


def test_apostrophe_is_glottal_not_punctuation():
    # in Anyin and the Guang languages the apostrophe is a letter, not punctuation
    assert "ʔ" in GhanaG2P("any").ipa("acɛdɩɛ'n")


# -- codepoint normalisation ----------------------------------------------

def test_birifor_upsilon_variant_resolved():
    """Birifor spells /ʊ/ U+028A; the Dagaare rules use U+028B."""
    r = GhanaG2P("Birifor").convert("kʊ̃ɔ")
    assert r.dropped == []


def test_tem_upsilon_variant_resolved():
    r = GhanaG2P("Tem").convert("ʊ")
    assert r.dropped == []
    assert r.phonemes


def test_sekpele_schwa_variant_resolved():
    """Sekpele writes U+01DD; the schwa the Ewe rules know is U+0259."""
    r = GhanaG2P("Sekpele").convert("əsuǝ")
    assert r.dropped == []


# -- patch layer ----------------------------------------------------------

def test_missing_letter_is_patched_not_dropped():
    """The nko rules have no r; Nkonya text uses it."""
    r = GhanaG2P("Nkonya").convert("ara")
    assert r.dropped == []
    assert "ɾ" in r.phonemes


def test_kabiye_gamma_patched():
    r = GhanaG2P("Kabiye").convert("ɣa")
    assert r.dropped == []
    assert "ɣ" in r.phonemes


# -- provenance -----------------------------------------------------------

def test_donor_is_reported():
    r = GhanaG2P("Sehwi").convert("kɔ")
    assert r.is_donor
    assert r.tier == "donor"
    assert r.rules == "any"


def test_native_is_not_donor():
    assert not GhanaG2P("twi").convert("kɔ").is_donor


def test_tiers_are_known_values():
    assert {i["tier"] for i in languages()} <= {"native", "equivalent", "donor"}


def test_non_native_entries_explain_themselves():
    for info in languages():
        if info["tier"] != "native":
            assert info.get("note") or info.get("family"), info["code"]


def test_oneshot_helper():
    assert g2p("Akwaaba", "twi") == GhanaG2P("twi").ipa("Akwaaba")
