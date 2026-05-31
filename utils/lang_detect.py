"""Language detection for response-language resolution.

Hybrid strategy (fast path first, statistical model only when needed):

1. Arabic is detected by Unicode script — unambiguous and instant.
2. A dependency-free Portuguese heuristic (distinctive diacritics + a
   high-frequency stopword ratio) settles the overwhelming majority of real
   inputs without touching the heavy model.
3. Only short, unaccented, genuinely ambiguous fragments (e.g. "info" vs
   "obrigado") fall through to lingua's n-gram model, which is restricted to
   English/Portuguese so it stays fast and never guesses an unsupported label.

Resolved values are full labels ("English", "Arabic", "European Portuguese")
because they are injected directly into the LLM prompt.
"""

import logging
import re
from functools import lru_cache

logger = logging.getLogger(__name__)

ENGLISH = "English"
ARABIC = "Arabic"
PORTUGUESE = "European Portuguese"

# Resolved label → BCP-47-ish short code surfaced in API response metadata.
_LABEL_TO_CODE = {ENGLISH: "en", ARABIC: "ar", PORTUGUESE: "pt"}


def to_code(label: str | None) -> str:
    """Map a resolved language label to its short code (defaults to ``en``)."""
    return _LABEL_TO_CODE.get(label or "", "en")


# Arabic Unicode block — script presence is a definitive signal.
_ARABIC = re.compile(r"[؀-ۿ]")

# Letters that occur in Portuguese but effectively never in plain English text.
_PORTUGUESE_DIACRITICS = frozenset("ãõáéíóúâêôàç")

# Word tokens (Latin letters incl. accented forms). Digits/punctuation ignored.
_WORD = re.compile(r"[a-zà-ÿ]+", re.IGNORECASE)

# Below this many words an unaccented string carries too little signal for the
# heuristic to be trusted, so it is deferred to the statistical detector.
_MIN_WORDS_FOR_RATIO = 4
# Share of tokens that must be Portuguese stopwords to call a sentence Portuguese.
_STOPWORD_RATIO = 0.5

# High-frequency Portuguese stopwords (NLTK `portuguese` list). Used as a
# corpus-frequency signal, never individually decisive.
_PORTUGUESE_STOPWORDS = frozenset(
    """
    de a o que e do da em um para com não uma os no se na por mais as dos como mas
    foi ao ele das tem à seu sua ou ser quando muito nos já está eu também só pelo
    pela até isso ela entre era depois sem mesmo aos ter seus quem nas me esse eles
    estão você tinha foram essa num nem suas meu às minha têm numa pelos elas havia
    seja qual será nós tenho lhe deles essas esses pelas este fosse dele tu te vocês
    vos lhes meus minhas teu tua teus tuas nosso nossa nossos nossas dela delas esta
    estes estas aquele aquela aqueles aquelas isto aquilo estou estamos estive esteve
    estivemos estiveram estava estávamos estavam estivera estivéramos esteja estejamos
    estejam estivesse estivéssemos estivessem estiver estivermos estiverem hei há
    havemos hão houve houvemos houveram houvera houvéramos haja hajamos hajam houvesse
    houvéssemos houvessem houver houvermos houverem houverei houverá houveremos houverão
    houveria houveríamos houveriam sou somos são éramos eram fui fomos fora fôramos
    sejamos sejam fôssemos fossem for formos forem serei seremos serão seria seríamos
    seriam temos tínhamos tinham tive teve tivemos tiveram tivera tivéramos tenha
    tenhamos tenham tivesse tivéssemos tivessem tiver tivermos tiverem terei terá
    teremos terão teria teríamos teriam
    """.split()
)


def _portuguese_heuristic(text: str) -> bool | None:
    """Fast, dependency-free Portuguese check.

    Returns ``True`` (confidently Portuguese), ``False`` (confidently not), or
    ``None`` when the signal is too weak to decide and the caller should defer
    to the statistical detector.
    """
    lowered = text.lower()

    # Any distinctive Portuguese letter is decisive on its own.
    if any(ch in _PORTUGUESE_DIACRITICS for ch in lowered):
        return True

    words = _WORD.findall(lowered)
    # Enough words to trust the stopword ratio: majority Portuguese -> pt,
    # otherwise treat as English. Single PT-stopword hits (e.g. the English word
    # "no", which is also a Portuguese stopword) cannot flip the verdict here.
    if len(words) >= _MIN_WORDS_FOR_RATIO:
        hits = sum(1 for w in words if w in _PORTUGUESE_STOPWORDS)
        return (hits / len(words)) > _STOPWORD_RATIO

    # Short, unaccented fragment — genuinely ambiguous.
    return None


@lru_cache(maxsize=1)
def _get_detector():
    """Build the lingua EN/PT detector once (model load is the expensive part)."""
    from lingua import Language, LanguageDetectorBuilder

    return LanguageDetectorBuilder.from_languages(Language.ENGLISH, Language.PORTUGUESE).build()


def _detect_pt_or_en(text: str) -> str:
    """Statistical fallback for ambiguous strings. Defaults to English on error."""
    try:
        from lingua import Language

        detected = _get_detector().detect_language_of(text)
    except Exception:  # pragma: no cover - missing model/lib must never crash a request
        logger.warning("lingua detection unavailable; defaulting ambiguous text to English")
        return ENGLISH
    return PORTUGUESE if detected == Language.PORTUGUESE else ENGLISH


def detect_language(text: str) -> str:
    """Resolve the response language label for a user message via the hybrid path."""
    if _ARABIC.search(text):
        return ARABIC

    heuristic = _portuguese_heuristic(text)
    if heuristic is True:
        return PORTUGUESE
    if heuristic is False:
        return ENGLISH

    # Heuristic abstained (short/unaccented) — let the model decide.
    return _detect_pt_or_en(text)
