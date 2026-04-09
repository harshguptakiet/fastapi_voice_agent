export const RELIGIOUS_FALLBACK =
  "I can only help with Indian religion and spirituality. Please ask a related question.";
export const EDUCATION_FALLBACK =
  "I can only help with school and learning topics. Please ask an education-related question.";

const ALWAYS_ALLOWED_INTENT_PATTERNS = [
  /\b(hi|hello|hey|namaste)\b/i,
  /\bgood\s+(morning|afternoon|evening)\b/i,
  /\b(how are you|who are you|what can you do|can you help me|help me)\b/i,
  /\b(thank you|thanks)\b/i,
];

/** Continuation / deictic follow-ups (reference prior answer in the same session). */
const FOLLOW_UP_CONTINUATION_PATTERNS = [
  /\b(tell me more|more about|more on|more details|any more|go (deeper|further)|elaborate|expand on|expand\b|continue|what about|what else|how about)\b/i,
  /\b(the same|that (one|topic|answer|point|part)|previous|above|you (just )?said|last (answer|point|part))\b/i,
  /\babout (him|her|it|them|this|that|those|one)\b/i,
];

const CLEAR_OFF_TOPIC_INTENT_PATTERNS = [
  /\b(write|generate|debug|fix|review)\b.*\b(code|program|script|bug)\b/i,
  /\b(weather|temperature|forecast)\b/i,
  /\b(stock|share market|crypto|bitcoin|trading|investment tip)\b/i,
  /\b(book|reserve)\b.*\b(flight|hotel|ticket)\b/i,
  /\b(movie|series|netflix|song|lyrics)\b/i,
  /\b(score|match|team|ipl|fifa|nba|football|cricket)\b/i,
  /\b(recipe|cook|cooking)\b/i,
  /\b(election|prime minister|parliament|vote for|politic|political party|us president|presidential|war in|invasion|sports betting|casino|lottery)\b/i,
];

// “Explain this” wording — shared; combined with subject lexicon in each domain.
const INQUIRY_PHRASE_PATTERN =
  /\b(tell\s+(me\s+)?about|what\s+is|what\s+are|what\s+was|how\s+(do|does|to|can|would|is|are)|describe|define|explain|why\s+(is|are|do|does)|difference\s+between|compare)\b/i;

const EDUCATION_INTENT_PATTERNS = [
  INQUIRY_PHRASE_PATTERN,
  /\b(explain|teach|learn|study|revise|practice|solve|prepare|summari[sz]e)\b/i,
  /\b(homework|assignment|exam|question|syllabus|chapter|subject|class|lesson|student|teacher)\b/i,

  /\b(math|mathematics|algebra|geometry|geometric|calculus|trigonometry|trignometry|equation|integral|derivative|formula|graph|theorem|proof)\b/i,
  /\b(science|history|geography|physics|chemistry|biology|english|grammar|college|university)\b/i,
  /\b(circle|circular|triangle|quadrilateral|polygon|pentagon|hexagon|angle|angles|radian|radians|degree|perpendicular|parallel|chord|arc|sector|cone|cylinder|sphere|prism|pyramid|radius|diameter|circumference|perimeter|area|volume|surface\s+area|coordinate|plane|sine|cosine|tangent|cotangent|cosecant|secant|trig|logarithm|exponent|quadratic|polynomial|inequality|matrix|vector|determinant|series|sequence|probability|statistics|acid|base|reaction|element|compound|mixture|motion|force|velocity|acceleration|energy|wave|electric|magnetic|circuit|novel|poem|literature|essay|vocabulary|comprehension|cbse|ncert|board\s+exam)\b/i,
];

const RELIGIOUS_INTENT_PATTERNS = [
  /\b(explain|meaning|significance|story|guide|chant|prayer|mantra|ritual|festival|verse)\b/i,
  /\b(gita|ramayan|ramayana|mahabharat|upanishad|veda|vedas|temple|puja|aarti|dharma|karma|moksha|bhakti|hindu|hinduism|sanatan|bhagavad|puran|purana|sanskrit|upanishadic)\b/i,
  /\b(spiritual|spirituality|meditation|yoga|shloka|sloka|stotra|stotram|krishna|krsna|ram|rama|sita|shiva|mahadev|hanuman|ganesh|ganapati|vishnu|brahma|lakshmi|saraswati|durga|kali|devi|swami|guru|sadhu|ashram|pilgrimage|yatra|worship|bhajan|kirtan|fasting|vrat)\b/i,
  /\b(diwali|deepavali|holi|navratri|dussehra|janmashtami|mahashivaratri|raksha\s+bandhan|pongal|onam)\b/i,
];

function matchesAny(text, patterns) {
  return patterns.some((pattern) => pattern.test(text));
}

/** Replies to “Would you like to know more?” style prompts — no domain words, but in-session continuation. */
function isShortDialogContinuation(text) {
  const q = String(text || "").trim();
  if (!q || q.length > 120) return false;
  const low = q
    .toLowerCase()
    .replace(/\s+/g, " ")
    .replace(/[!?.]+$/g, "")
    .trim();
  const twoWord = new Set([
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
  ]);
  if (twoWord.has(low)) return true;
  const oneWord = new Set([
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
  ]);
  if (oneWord.has(low)) return true;
  if (/^(yes|yeah|sure)\s+please$/i.test(low)) return true;
  return false;
}

export function isReligiousTopicAllowedByIntent(text) {
  const q = String(text || "").trim();
  if (!q) return false;

  if (matchesAny(q, ALWAYS_ALLOWED_INTENT_PATTERNS)) return true;
  if (matchesAny(q, CLEAR_OFF_TOPIC_INTENT_PATTERNS)) return false;
  if (matchesAny(q, FOLLOW_UP_CONTINUATION_PATTERNS)) return true;
  if (isShortDialogContinuation(q)) return true;

  const educationIntent = matchesAny(q, EDUCATION_INTENT_PATTERNS);
  const religiousIntent = matchesAny(q, RELIGIOUS_INTENT_PATTERNS);
  if (educationIntent && !religiousIntent) return false;
  if (religiousIntent) return true;
  if (educationIntent && religiousIntent) return true;
  return false;
}

export function isEducationTopicAllowedByIntent(text) {
  const q = String(text || "").trim();
  if (!q) return false;

  if (matchesAny(q, ALWAYS_ALLOWED_INTENT_PATTERNS)) return true;
  if (matchesAny(q, CLEAR_OFF_TOPIC_INTENT_PATTERNS)) return false;
  if (matchesAny(q, FOLLOW_UP_CONTINUATION_PATTERNS)) return true;
  if (isShortDialogContinuation(q)) return true;

  const educationIntent = matchesAny(q, EDUCATION_INTENT_PATTERNS);
  const religiousIntent = matchesAny(q, RELIGIOUS_INTENT_PATTERNS);
  if (religiousIntent && !educationIntent) return false;
  if (educationIntent) return true;
  if (religiousIntent && educationIntent) return true;
  return false;
}
