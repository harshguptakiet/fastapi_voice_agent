import re

RELIGIOUS_FALLBACK = "I can help with Indian religion and spirituality topics. Please ask a related question."

ALWAYS_ALLOWED_INTENT_PATTERNS = [
    re.compile(r"\b(hi|hello|hey|namaste)\b", re.I),
    re.compile(r"\bgood\s+(morning|afternoon|evening)\b", re.I),
    re.compile(r"\b(how are you|who are you|what can you do|can you help me|help me)\b", re.I),
    re.compile(r"\b(thank you|thanks)\b", re.I),
]
CLEAR_OFF_TOPIC_INTENT_PATTERNS = [
    re.compile(r"\b(write|generate|debug|fix|review)\b.*\b(code|program|script|bug)\b", re.I),
    re.compile(r"\b(weather|temperature|forecast)\b", re.I),
    re.compile(r"\b(stock|share market|crypto|bitcoin|trading|investment tip)\b", re.I),
    re.compile(r"\b(book|reserve)\b.*\b(flight|hotel|ticket)\b", re.I),
    re.compile(r"\b(movie|series|netflix|song|lyrics)\b", re.I),
    re.compile(r"\b(score|match|team|ipl|fifa|nba|football|cricket)\b", re.I),
    re.compile(r"\b(recipe|cook|cooking)\b", re.I),
]
RELIGIOUS_INTENT_PATTERNS = [
    re.compile(r"\b(explain|meaning|significance|story|guide|chant|prayer|mantra|ritual|festival|verse)\b", re.I),
    re.compile(r"\b(gita|ramayan|ramayana|mahabharat|upanishad|veda|temple|puja|aarti|dharma|karma|moksha|bhakti|hindu)\b", re.I),
    re.compile(r"\b(spiritual|spirituality|meditation|yoga|shloka|sloka|krishna|ram|shiva|hanuman|ganesh)\b", re.I),
]
EDUCATION_INTENT_PATTERNS = [
    re.compile(r"\b(explain|teach|learn|study|revise|practice|solve|prepare|summari[sz]e)\b", re.I),
    re.compile(r"\b(homework|assignment|exam|question|syllabus|chapter|subject|class|lesson|student|teacher)\b", re.I),
    re.compile(r"\b(math|mathematics|algebra|geometry|calculus|trigonometry|equation|integral|derivative)\b", re.I),
    re.compile(r"\b(science|history|geography|physics|chemistry|biology|english|grammar|college|university)\b", re.I),
]
def matches_any(text, patterns):
    return any(p.search(text) for p in patterns)
def is_religious_topic_allowed_by_intent(text):
    q = str(text or "").strip()
    if not q:
        return True
    if matches_any(q, ALWAYS_ALLOWED_INTENT_PATTERNS):
        return True
    if matches_any(q, CLEAR_OFF_TOPIC_INTENT_PATTERNS):
        return False
    education_intent = matches_any(q, EDUCATION_INTENT_PATTERNS)
    religious_intent = matches_any(q, RELIGIOUS_INTENT_PATTERNS)
    if education_intent and not religious_intent:
        return False
    return True
