"""Tests for the hybrid language detector (heuristic + lingua fallback)."""

from unittest.mock import patch

from utils import lang_detect
from utils.lang_detect import (
    ARABIC,
    ENGLISH,
    PORTUGUESE,
    _portuguese_heuristic,
    detect_language,
)


class TestArabic:
    def test_arabic_script_is_detected(self):
        assert detect_language("ما هي سياسة الإرجاع؟") == ARABIC

    def test_arabic_wins_over_latin_when_mixed(self):
        assert detect_language("order رقم 12") == ARABIC


class TestHeuristicFastPath:
    def test_diacritics_are_decisive(self):
        # Single short word, but the tilde is unambiguously Portuguese.
        assert _portuguese_heuristic("pão") is True
        assert detect_language("pão") == PORTUGUESE

    def test_diacritic_sentence(self):
        assert detect_language("Qual é a política de devoluções?") == PORTUGUESE

    def test_unaccented_portuguese_sentence_via_stopword_ratio(self):
        # No diacritics, but a majority of tokens are Portuguese stopwords.
        assert _portuguese_heuristic("o que voce tem para me dizer de novo") is True

    def test_long_english_sentence_is_english(self):
        text = "please tell me about the return and refund policy today"
        assert _portuguese_heuristic(text) is False
        assert detect_language(text) == ENGLISH

    def test_single_shared_stopword_does_not_flip_to_portuguese(self):
        # "no" is both an English word and a Portuguese stopword — too short to
        # trust, so the heuristic must abstain rather than guess Portuguese.
        assert _portuguese_heuristic("no") is None


class TestLibraryFallback:
    def test_short_ambiguous_defers_to_library(self):
        # Heuristic abstains on a short unaccented fragment...
        assert _portuguese_heuristic("obrigado") is None
        # ...and lingua should recognise it as Portuguese.
        assert detect_language("obrigado") == PORTUGUESE

    def test_short_english_fragment_resolves_to_english(self):
        # Heuristic abstains (3 words, no diacritics, no stopword majority) and
        # lingua resolves the fragment to English.
        assert _portuguese_heuristic("track my order") is None
        assert detect_language("track my order") == ENGLISH

    def test_fallback_defaults_to_english_when_library_unavailable(self):
        lang_detect._get_detector.cache_clear()
        with patch.object(lang_detect, "_get_detector", side_effect=RuntimeError("no model")):
            assert detect_language("xyzq") == ENGLISH
        lang_detect._get_detector.cache_clear()
