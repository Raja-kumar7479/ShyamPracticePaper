import re
from difflib import SequenceMatcher

FILLERS = {'um', 'uh', 'umm', 'uhh', 'hmm', 'like', 'basically', 'actually'}
IDEAL_WPM_LOW = 100
IDEAL_WPM_HIGH = 160


def _words(text):
    return re.findall(r"[a-z0-9']+", (text or '').lower())


def analyse_speech(target_text, transcription, duration_seconds=0):
    target = _words(re.sub(r'<[^>]+>', ' ', target_text or ''))
    spoken = _words(transcription or '')

    if not spoken:
        return {
            'accuracy_pct': 0.0, 'matched': 0, 'target_words': len(target),
            'spoken_words': 0, 'missed_words': target[:20], 'extra_words': [],
            'fillers': [], 'wpm': 0, 'pace': 'no speech',
            'verdict': 'No Speech Detected',
            'tips': ['We could not detect any speech. Check your microphone and speak clearly next time.'],
        }

    if len(target) < 8:
        target = []

    matcher = SequenceMatcher(None, target, spoken, autojunk=False)
    matched = sum(b.size for b in matcher.get_matching_blocks())

    matched_target_idx = set()
    matched_spoken_idx = set()
    for b in matcher.get_matching_blocks():
        matched_target_idx.update(range(b.a, b.a + b.size))
        matched_spoken_idx.update(range(b.b, b.b + b.size))

    missed = [w for i, w in enumerate(target) if i not in matched_target_idx]
    extra = [w for i, w in enumerate(spoken) if i not in matched_spoken_idx]
    fillers = [w for w in spoken if w in FILLERS]

    accuracy = round(100.0 * matched / len(target), 1) if target else None

    duration = float(duration_seconds or 0)
    wpm = round(len(spoken) / (duration / 60.0)) if duration > 2 else 0
    if wpm == 0:
        pace = 'unknown'
    elif wpm < IDEAL_WPM_LOW:
        pace = 'slow'
    elif wpm > IDEAL_WPM_HIGH:
        pace = 'fast'
    else:
        pace = 'good'

    if accuracy is None:
        verdict = 'Response Recorded'
    elif accuracy >= 90:
        verdict = 'Excellent'
    elif accuracy >= 75:
        verdict = 'Good'
    elif accuracy >= 50:
        verdict = 'Average'
    else:
        verdict = 'Needs Practice'

    tips = []
    if accuracy is not None and accuracy < 90 and missed:
        tips.append(f"You missed {len(missed)} word(s) from the passage. Practise reading it aloud slowly before recording.")
    if pace == 'slow':
        tips.append(f"Your pace was {wpm} words/min. Aim for {IDEAL_WPM_LOW}-{IDEAL_WPM_HIGH} words/min for natural speech.")
    elif pace == 'fast':
        tips.append(f"Your pace was {wpm} words/min - a little fast. Slow down slightly so every word is clear.")
    if fillers:
        tips.append(f"Avoid filler words like {', '.join(sorted(set(fillers))[:4])}. Pause silently instead.")
    if extra and accuracy is not None and len(extra) > max(2, len(target) // 10):
        tips.append("Stick to the given text - extra words reduce your accuracy score.")
    if not tips:
        tips.append("Great work! Keep practising daily to maintain your fluency.")

    return {
        'accuracy_pct': accuracy, 'matched': matched, 'target_words': len(target),
        'spoken_words': len(spoken), 'missed_words': missed[:20], 'extra_words': extra[:12],
        'fillers': sorted(set(fillers)), 'wpm': wpm, 'pace': pace,
        'verdict': verdict, 'tips': tips,
    }
