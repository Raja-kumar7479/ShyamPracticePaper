"""Dependency-free content-relevance analysis for open-ended communication
answers (THINK_SPEAK topic speech, WRITING essays/emails).

No ML model to download — uses a TF cosine-similarity to the prompt plus
lexical-quality signals (vocabulary richness, sentence structure, fillers,
length adequacy). Good enough to give a student an honest, explainable score
and specific guidance, and it deploys with zero extra packages.
"""
import math
import re
from collections import Counter

FILLERS = {'um', 'uh', 'umm', 'uhh', 'hmm', 'like', 'basically', 'actually',
           'you know', 'i mean', 'sort of', 'kind of'}

STOPWORDS = {
    'the', 'a', 'an', 'and', 'or', 'but', 'if', 'of', 'to', 'in', 'on', 'for',
    'is', 'are', 'was', 'were', 'be', 'been', 'being', 'am', 'i', 'you', 'he',
    'she', 'it', 'we', 'they', 'me', 'him', 'her', 'them', 'my', 'your', 'his',
    'its', 'our', 'their', 'this', 'that', 'these', 'those', 'as', 'at', 'by',
    'with', 'from', 'so', 'do', 'does', 'did', 'have', 'has', 'had', 'will',
    'would', 'can', 'could', 'should', 'may', 'might', 'not', 'no', 'yes',
    'about', 'up', 'out', 'then', 'than', 'too', 'very', 'just', 'also',
}

STRONG_CONNECTORS = {
    'because', 'therefore', 'however', 'moreover', 'furthermore', 'although',
    'whereas', 'consequently', 'additionally', 'firstly', 'secondly', 'finally',
    'for example', 'in conclusion', 'on the other hand', 'as a result',
}


def _tokens(text):
    return re.findall(r"[a-z']+", re.sub(r'<[^>]+>', ' ', (text or '').lower()))


def _content_words(tokens):
    return [t for t in tokens if t not in STOPWORDS and len(t) > 2]


def _cosine(a_counter, b_counter):
    if not a_counter or not b_counter:
        return 0.0
    common = set(a_counter) & set(b_counter)
    dot = sum(a_counter[t] * b_counter[t] for t in common)
    na = math.sqrt(sum(v * v for v in a_counter.values()))
    nb = math.sqrt(sum(v * v for v in b_counter.values()))
    return dot / (na * nb) if na and nb else 0.0


def analyse_content(prompt_text, answer_text, mode='writing',
                    word_limit=0, duration_seconds=0):
    """mode: 'writing' or 'speaking'. Returns an explainable relevance report."""
    ans_tokens = _tokens(answer_text)
    if not ans_tokens:
        return {
            'relevance_pct': 0, 'quality_pct': 0, 'overall_pct': 0,
            'verdict': 'No Response', 'word_count': 0,
            'covered_keywords': [], 'missing_keywords': [],
            'unique_ratio': 0, 'connectors': [], 'fillers': [],
            'tips': ['No response was captured. Attempt every question — an empty answer scores zero.'],
        }

    prompt_content = _content_words(_tokens(prompt_text))
    ans_content = _content_words(ans_tokens)

    # topic keywords = distinctive words from the prompt
    keyword_set = list(dict.fromkeys(prompt_content))[:12]
    ans_set = set(ans_content)
    covered = [k for k in keyword_set if k in ans_set]
    missing = [k for k in keyword_set if k not in ans_set]

    # relevance = keyword coverage blended with TF cosine similarity
    coverage = (len(covered) / len(keyword_set)) if keyword_set else None
    cosine = _cosine(Counter(ans_content), Counter(prompt_content))
    if coverage is None:
        relevance = round(cosine * 100)
    else:
        relevance = round((0.6 * coverage + 0.4 * cosine) * 100)

    # quality signals
    words = ans_tokens
    wc = len(words)
    unique_ratio = round(len(set(words)) / wc, 2) if wc else 0
    connectors = sorted({c for c in STRONG_CONNECTORS
                         if c in ' '.join(words) or c in ans_set})
    fillers = sorted({f for f in FILLERS if f in ans_set})
    sentences = [s for s in re.split(r'[.!?]+', re.sub(r'<[^>]+>', ' ', answer_text or '')) if s.strip()]
    avg_sentence = round(wc / len(sentences), 1) if sentences else wc

    # length adequacy
    target = word_limit or (55 if mode == 'speaking' else 90)
    length_ratio = min(1.0, wc / target) if target else 1.0

    quality = round(100 * (
        0.35 * length_ratio +
        0.25 * min(1.0, unique_ratio / 0.6) +
        0.20 * min(1.0, len(connectors) / 3.0) +
        0.20 * (1.0 - min(1.0, len(fillers) / 4.0))
    ))

    overall = round(0.6 * relevance + 0.4 * quality)

    if overall >= 80:
        verdict = 'Excellent'
    elif overall >= 60:
        verdict = 'Good'
    elif overall >= 40:
        verdict = 'Average'
    else:
        verdict = 'Needs Practice'

    tips = []
    if relevance < 60 and missing:
        tips.append("Stay on topic — you didn't address: " + ', '.join(missing[:5]) +
                    ". Read the prompt and cover its key ideas.")
    if length_ratio < 0.6:
        tips.append(f"Your answer is short ({wc} words). Aim for around {target} words with fuller explanations.")
    if not connectors:
        tips.append("Use connectors (because, however, for example) to structure your ideas clearly.")
    if fillers:
        tips.append("Avoid filler words like " + ', '.join(list(fillers)[:3]) + " for a more professional tone.")
    if unique_ratio < 0.4 and wc > 20:
        tips.append("You repeated many words — vary your vocabulary to sound more fluent.")
    if not tips:
        tips.append("Strong, relevant response. Keep practising to maintain this standard.")

    return {
        'relevance_pct': relevance, 'quality_pct': quality, 'overall_pct': overall,
        'verdict': verdict, 'word_count': wc,
        'covered_keywords': covered, 'missing_keywords': missing[:6],
        'unique_ratio': unique_ratio, 'connectors': connectors, 'fillers': fillers,
        'avg_sentence': avg_sentence, 'tips': tips,
    }
