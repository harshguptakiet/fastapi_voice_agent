
# CONTROLLED AI ASSISTANT: Strict domain and safety enforcement
import re

RELIGIOUS_FALLBACK = (
    "I can only help with Indian religion and spirituality. "
    "Please ask a related question."
)
EDUCATION_FALLBACK = (
    "I can only help with school and learning topics. "
    "Please ask an education-related question."
)

# Keep harmful-intent phrases tight; avoid matching harmless words like "attack" in "heart attack"
# or "hack" in "life hack" by requiring security/crime adjacency.
UNSAFE_PATTERNS = [
    re.compile(
        r"\b("
        r"kill\s+(yourself|myself|him|her|them|someone|people)|"
        r"suicide|self[- ]harm|commit\s+suicide|"
        r"(make|build|buy)\s+a\s+bomb|how\s+to\s+bomb|"
        r"\bhack\s+into\b|\bhacking\s+into\b|sql\s+injection|"
        r"xss\b|csrf\b|ddos\b|ransomware|keylogger|"
        r"child\s+porn|pedophil|"
        r"\brape\b|\bmolest\b"
        r")\b",
        re.I,
    ),
]

def is_unsafe(text):
    q = str(text or "").strip()
    return any(p.search(q) for p in UNSAFE_PATTERNS)


def _is_short_dialog_continuation(text: str) -> bool:
    """Replies to assistant follow-ups like 'Would you like to know more?' (yes / sure / go on)."""
    q = str(text or "").strip()
    if not q or len(q) > 120:
        return False
    low = re.sub(r"\s+", " ", q.lower()).strip(" !.,?")
    two = {
        "yes please",
        "go on",
        "go ahead",
        "of course",
        "no thanks",
        "no thank you",
        "not now",
        "that's all",
        "tell me more",
        "i would",
        "id like",
        "i'd like",
    }
    if low in two:
        return True
    one = {
        "yes",
        "no",
        "yeah",
        "yep",
        "yup",
        "sure",
        "ok",
        "okay",
        "please",
        "continue",
        "more",
        "absolutely",
        "alright",
        "nope",
        "nah",
    }
    if low in one:
        return True
    if re.fullmatch(r"(yes|yeah|sure)\s+please", low):
        return True
    return False


def is_religious_topic_allowed_by_intent(text):
    """Match Tekurious Darshan rules: block pure education / generic trivia; allow greetings."""
    q = str(text or "").strip()
    if not q:
        return False
    if _matches_any(q, _ALWAYS_ALLOWED_INFER):
        return True
    if _matches_any(q, _CLEAR_OFF_TOPIC):
        return False
    if _matches_any(q, _FOLLOW_UP):
        return True
    if _is_short_dialog_continuation(q):
        return True
    edu_hit = _matches_any(q, _EDUCATION_INFER)
    rel_hit = _matches_any(q, _RELIGIOUS_INFER)
    if edu_hit and not rel_hit:
        return False
    if rel_hit:
        return True
    if edu_hit and rel_hit:
        return True
    return False


def is_education_topic_allowed_by_intent(text):
    """Match Eduthum rules: block pure religion / generic trivia; allow greetings."""
    q = str(text or "").strip()
    if not q:
        return False
    if _matches_any(q, _ALWAYS_ALLOWED_INFER):
        return True
    if _matches_any(q, _CLEAR_OFF_TOPIC):
        return False
    if _matches_any(q, _FOLLOW_UP):
        return True
    if _is_short_dialog_continuation(q):
        return True
    edu_hit = _matches_any(q, _EDUCATION_INFER)
    rel_hit = _matches_any(q, _RELIGIOUS_INFER)
    if rel_hit and not edu_hit:
        return False
    if edu_hit:
        return True
    if rel_hit and edu_hit:
        return True
    return False


# When tenant / explicit domain is missing, infer from wording (aligned with standalone bots).
_ALWAYS_ALLOWED_INFER = [
    re.compile(r"\b(hi|hello|hey|namaste)\b", re.I),
    re.compile(r"\bgood\s+(morning|afternoon|evening)\b", re.I),
    re.compile(r"\b(how are you|who are you|what can you do|can you help me|help me)\b", re.I),
    re.compile(r"\b(thank you|thanks)\b", re.I),
]
_CLEAR_OFF_TOPIC = [
    re.compile(r"\b(write|generate|debug|fix|review)\b.*\b(code|program|script|bug)\b", re.I),
    re.compile(r"\b(weather|temperature|forecast)\b", re.I),
    re.compile(r"\b(stock|share market|crypto|bitcoin|trading|investment tip)\b", re.I),
    re.compile(r"\b(movie|series|netflix|song|lyrics)\b", re.I),
    re.compile(r"\b(score|match|team|ipl|fifa|nba|football|cricket)\b", re.I),
    re.compile(r"\b(recipe|cook|cooking)\b", re.I),
    re.compile(
        r"\b(election|prime minister|parliament|vote for|politic|political party|"
        r"us president|presidential|war in|invasion|sports betting|casino|lottery)\b",
        re.I,
    ),
]
# Continuation / deictic follow-ups (same session; model uses memory).
_FOLLOW_UP = [
    re.compile(
        r"\b("
        r"tell me more|more about|more on|more details|any more|"
        r"go (deeper|further)|elaborate|expand on|expand\b|continue|"
        r"what about|what else|how about"
        r")\b",
        re.I,
    ),
    re.compile(
        r"\b("
        r"the same|that (one|topic|answer|point|part)|previous|above|"
        r"you (just )?said|last (answer|point|part)"
        r")\b",
        re.I,
    ),
    re.compile(r"\babout (him|her|it|them|this|that|those|one)\b", re.I),
]
# Phrases that usually mean “explain this topic” (count as in-domain when paired with domain lexicon).
_INQUIRY_PHRASE = re.compile(
    r"\b("
    r"tell\s+(me\s+)?about|"
    r"what\s+is|what\s+are|what\s+was|"
    r"how\s+(do|does|to|can|would|is|are)|"
    r"describe|define|explain|why\s+(is|are|do|does)|"
    r"difference\s+between|compare"
    r")\b",
    re.I,
)
_RELIGIOUS_INFER = [
    re.compile(
        r"\b(explain|meaning|significance|story|guide|chant|prayer|mantra|ritual|festival|verse)\b",
        re.I,
    ),
    re.compile(
        r"\b(gita|ramayan|ramayana|mahabharat|upanishad|veda|vedas|temple|puja|aarti|"
        r"dharma|karma|moksha|bhakti|hindu|hinduism|sanatan|bhagavad|puran|purana|"
        r"sanskrit|upanishadic)\b",
        re.I,
    ),
    re.compile(
        r"\b(spiritual|spirituality|meditation|yoga|shloka|sloka|stotra|stotram|"
        r"krishna|krsna|ram|rama|sita|shiva|mahadev|hanuman|ganesh|ganapati|"
        r"vishnu|brahma|lakshmi|saraswati|durga|kali|devi|swami|guru|sadhu|"
        r"ashram|pilgrimage|yatra|worship|bhajan|kirtan|fasting|vrat)\b",
        re.I,
    ),
    re.compile(
        r"\b(diwali|deepavali|holi|navratri|dussehra|janmashtami|mahashivaratri|"
        r"raksha\s+bandhan|pongal|onam)\b",
        re.I,
    ),
]
_EDUCATION_INFER = [
    _INQUIRY_PHRASE,
    re.compile(r"\b(explain|teach|learn|study|revise|practice|solve|prepare|summari[sz]e)\b", re.I),
    re.compile(r"\b(homework|assignment|exam|question|syllabus|chapter|subject|class|lesson|student|teacher)\b", re.I),
    re.compile(
        r"\b(math|mathematics|algebra|geometry|geometric|calculus|trigonometry|trignometry|equation|"
        r"integral|derivative|formula|graph|theorem|proof)\b",
        re.I,
    ),
    re.compile(r"\b(science|history|geography|physics|chemistry|biology|english|grammar|college|university)\b", re.I),
    re.compile(
        r"\b(circle|circular|triangle|quadrilateral|polygon|pentagon|hexagon|angle|angles|radian|radians|"
        r"degree|perpendicular|parallel|chord|arc|sector|cone|cylinder|sphere|prism|pyramid|"
        r"radius|diameter|circumference|perimeter|area|volume|surface\s+area|coordinate|plane|"
        r"sine|cosine|tangent|cotangent|cosecant|secant|trig|logarithm|exponent|quadratic|"
        r"polynomial|inequality|matrix|vector|determinant|series|sequence|probability|statistics|"
        r"acid|base|reaction|element|compound|mixture|motion|force|velocity|acceleration|energy|"
        r"wave|electric|magnetic|circuit|novel|poem|literature|essay|vocabulary|comprehension|"
        r"cbse|ncert|board\s+exam)\b",
        re.I,
    ),
    re.compile(
        r"\b(photosynthesis|osmosis|mitosis|meiosis|ecosystem|cell|molecule|atom|"
        r"newton|gravity|renaissance|democracy|fraction|percentage)\b",
        re.I,
    ),
]


def _matches_any(text: str, patterns: list) -> bool:
    return any(p.search(text) for p in patterns)


def resolve_agent_domain(tenant_id: str | None, explicit_domain: str | None, user_text: str) -> str | None:
    """Pick religious vs education from request body, tenant id, or message wording."""
    d = (explicit_domain or "").strip().lower()
    if d in ("religious", "education"):
        return d

    t = (tenant_id or "").lower()
    # Longer / more specific substrings first where order matters
    tenant_rules = (
        ("religious", "religious"),
        ("darshan", "religious"),
        ("spiritual", "religious"),
        ("eduthum", "education"),
        ("education", "education"),
        ("tekurious", "education"),
        ("cbse", "education"),
        ("school", "education"),
        ("class10", "education"),
        ("class9", "education"),
        ("class12", "education"),
        ("class11", "education"),
        ("edu", "education"),
    )
    for needle, dom in tenant_rules:
        if needle in t:
            return dom

    q = str(user_text or "").strip()
    if not q:
        return None
    if _matches_any(q, _CLEAR_OFF_TOPIC):
        return None
    if _matches_any(q, _ALWAYS_ALLOWED_INFER):
        return "religious"
    edu_hit = _matches_any(q, _EDUCATION_INFER)
    rel_hit = _matches_any(q, _RELIGIOUS_INFER)
    if rel_hit and not edu_hit:
        return "religious"
    if edu_hit and not rel_hit:
        return "education"
    if rel_hit and edu_hit:
        return "religious"
    return None


def is_allowed_intent(text, domain):
    # PRIORITY 1: SAFETY
    if is_unsafe(text):
        return ("NO", "I cannot help with that request.")

    # PRIORITY 2: DOMAIN CONTROL
    if domain == "religious":
        if is_religious_topic_allowed_by_intent(text):
            return ("YES", "Religious domain: allowed.")
        else:
            return ("NO", RELIGIOUS_FALLBACK)
    elif domain == "education":
        if is_education_topic_allowed_by_intent(text):
            return ("YES", "Educational domain: allowed.")
        else:
            return ("NO", EDUCATION_FALLBACK)
    else:
        return ("NO", "I can only help with religious or school-related questions. Please ask something relevant.")