"""Daily lessons, quizzes, and streaks.

A learner meets ten new words at a time, in level order, so later sets are harder.
Every 30 learned words, a quiz is required before the next words unlock.
There is no daily time limit.
"""

import random
import re
from datetime import timedelta

from django.db import IntegrityError, transaction

from django.conf import settings
from django.db.models import Max
from django.utils import timezone

from .codes import new_learner_code
from .models import Assignment, BankMeta, DailyPlan, Learner, QuizAnswer, QuizAttempt, Word
from .words import DECOYS, LEVELS, bank_signature, iter_words

WORDS_PER_DAY = getattr(settings, "VOCAB_WORDS_PER_DAY", 10)
QUIZ_EVERY = getattr(settings, "VOCAB_QUIZ_EVERY", 30)
QUIZ_LENGTH = getattr(settings, "VOCAB_QUIZ_LENGTH", 10)
DAILY_LIMIT_SECONDS = getattr(settings, "VOCAB_DAILY_LIMIT_SECONDS", 15 * 60)
MAX_TICK_SECONDS = getattr(settings, "VOCAB_MAX_TICK_SECONDS", 90)

NAME_RE = re.compile(r"^[A-Za-z][A-Za-z .'\-]{0,19}$")


def clean_name(raw):
    name = re.sub(r"\s+", " ", (raw or "").strip())
    if not NAME_RE.match(name):
        return None
    return name


def parse_offset(raw):
    try:
        value = int(raw)
    except (TypeError, ValueError):
        return 0
    if value < -14 * 60 or value > 14 * 60:
        return 0
    return value


def local_today(learner, now=None):
    now = now or timezone.now()
    if timezone.is_aware(now):
        now = now.astimezone(timezone.utc)
    shifted = now - timedelta(minutes=learner.utc_offset_minutes)
    return shifted.date()


def ensure_word_bank():
    signature = bank_signature()
    meta = BankMeta.objects.first()
    if meta and meta.version == signature:
        return
    with transaction.atomic():
        for item in iter_words():
            Word.objects.update_or_create(text=item["text"], defaults=item)
        BankMeta.objects.all().delete()
        BankMeta.objects.create(version=signature)


def seconds_remaining(learner, today):
    used = learner.seconds_used if learner.usage_on == today else 0
    return max(0, DAILY_LIMIT_SECONDS - used)


def touch(learner, now=None, active=True):
    """Add active time since the last ping, never more than one short tick."""
    now = now or timezone.now()
    today = local_today(learner, now)
    if learner.usage_on != today:
        learner.usage_on = today
        learner.seconds_used = 0
        learner.last_seen = now
        learner.last_played_on = today
        learner.save(
            update_fields=["usage_on", "seconds_used", "last_seen", "last_played_on"]
        )
        return DAILY_LIMIT_SECONDS

    if active and learner.last_seen and learner.seconds_used < DAILY_LIMIT_SECONDS:
        delta = (now - learner.last_seen).total_seconds()
        if 0 < delta <= MAX_TICK_SECONDS:
            learner.seconds_used = min(
                DAILY_LIMIT_SECONDS,
                learner.seconds_used + int(round(delta)),
            )
    learner.last_seen = now
    learner.last_played_on = today
    learner.save(update_fields=["seconds_used", "last_seen", "last_played_on"])
    return max(0, DAILY_LIMIT_SECONDS - learner.seconds_used)


def learned_count(learner):
    return Assignment.objects.filter(learner=learner, learned=True).count()


def last_completed_milestone(learner):
    value = QuizAttempt.objects.filter(
        learner=learner, completed_on__isnull=False
    ).aggregate(m=Max("milestone"))["m"]
    return value or 0


def next_gate(learner):
    return last_completed_milestone(learner) + QUIZ_EVERY


def quiz_is_due(learner):
    learned = learned_count(learner)
    due = (learned // QUIZ_EVERY) * QUIZ_EVERY
    return due > last_completed_milestone(learner)


def room_for_new_words(learner):
    assigned = Assignment.objects.filter(learner=learner).count()
    return max(0, next_gate(learner) - assigned)


def unfinished_qs(learner):
    return Assignment.objects.filter(learner=learner, learned=False).select_related("word")


def has_unfinished(learner):
    return unfinished_qs(learner).exists()


def _ordered_assignments(qs):
    return qs.order_by("assigned_on", "position", "id")


def _fill_plan(learner, today, plan):
    carry = list(
        _ordered_assignments(
            unfinished_qs(learner).exclude(assigned_on=today)
        )
    )
    already_new = Assignment.objects.filter(learner=learner, assigned_on=today).count()
    if quiz_is_due(learner) and not carry and already_new == 0:
        plan.waiting_for_quiz = True
        plan.target_count = 0
        plan.words_finished = False
        return

    room = room_for_new_words(learner)
    open_slots = max(0, WORDS_PER_DAY - len(carry) - already_new)
    need = min(room, open_slots)
    created = 0
    if need:
        next_words = list(
            Word.objects.exclude(
                id__in=Assignment.objects.filter(learner=learner).values("word_id")
            ).order_by("level", "sequence")[:need]
        )
        for offset, word in enumerate(next_words, start=1):
            Assignment.objects.create(
                learner=learner,
                word=word,
                assigned_on=today,
                position=already_new + offset,
            )
            created += 1
    plan.waiting_for_quiz = False
    plan.target_count = len(carry) + already_new + created
    if created:
        plan.words_finished = False
    if plan.target_count == 0:
        plan.words_finished = False


def ensure_daily_plan(learner, today):
    with transaction.atomic():
        plan = (
            DailyPlan.objects.select_for_update()
            .filter(learner=learner, on=today)
            .first()
        )
        if plan is None:
            plan = DailyPlan(learner=learner, on=today)
            _fill_plan(learner, today, plan)
            plan.save()
            return plan
        if plan.waiting_for_quiz and not quiz_is_due(learner):
            _fill_plan(learner, today, plan)
            plan.waiting_for_quiz = False
            plan.save()
    return plan


def today_board(learner, today):
    ensure_daily_plan(learner, today)
    unfinished = list(_ordered_assignments(unfinished_qs(learner)))
    if unfinished:
        return unfinished[:WORDS_PER_DAY]
    learned = list(
        _ordered_assignments(
            Assignment.objects.filter(learner=learner, learned=True).select_related("word")
        )
    )
    return learned[-WORDS_PER_DAY:]


def continue_set(learner, today):
    """Open another set of words immediately, or start the bank over."""
    if quiz_is_due(learner) and not has_unfinished(learner):
        return
    if not words_remaining_in_bank(learner) and not has_unfinished(learner):
        Assignment.objects.filter(learner=learner).delete()
        QuizAttempt.objects.filter(learner=learner).delete()
        DailyPlan.objects.filter(learner=learner).delete()
        ensure_daily_plan(learner, today)
        return
    plan = ensure_daily_plan(learner, today)
    if has_unfinished(learner) or plan.waiting_for_quiz:
        return
    room = room_for_new_words(learner)
    need = min(room, WORDS_PER_DAY)
    if need <= 0:
        plan.waiting_for_quiz = True
        plan.words_finished = False
        plan.save(update_fields=["waiting_for_quiz", "words_finished"])
        return
    already = Assignment.objects.filter(learner=learner).count()
    next_words = list(
        Word.objects.exclude(
            id__in=Assignment.objects.filter(learner=learner).values("word_id")
        ).order_by("level", "sequence")[:need]
    )
    for offset, word in enumerate(next_words, start=1):
        Assignment.objects.create(
            learner=learner,
            word=word,
            assigned_on=today,
            position=already + offset,
        )
    learned_today = Assignment.objects.filter(learner=learner, learned_on=today).count()
    plan.words_finished = False
    plan.waiting_for_quiz = False
    plan.target_count = learned_today + len(next_words)
    plan.save(update_fields=["words_finished", "waiting_for_quiz", "target_count"])


def current_assignment(learner, today):
    for item in today_board(learner, today):
        if not item.learned:
            return item
    # Carry words are included above. If the board is only finished
    # assignments, there is nothing left to study.
    return None


def learn_choices(learner, word, today):
    rng = random.Random(f"{learner.id}-{word.id}-{today.isoformat()}")
    learned_meanings = list(
        Assignment.objects.filter(learner=learner, learned=True)
        .exclude(word=word)
        .values_list("word__meaning", flat=True)
    )
    rng.shuffle(learned_meanings)
    options = []
    for meaning in learned_meanings:
        if meaning and meaning != word.meaning and meaning not in options:
            options.append(meaning)
        if len(options) == 3:
            break
    if len(options) < 3:
        decoys = [item for item in DECOYS if item != word.meaning and item not in options]
        rng.shuffle(decoys)
        options.extend(decoys[: 3 - len(options)])
    options.append(word.meaning)
    rng.shuffle(options)
    return options


def _refresh_words_finished(learner, today):
    plan = DailyPlan.objects.filter(learner=learner, on=today).first()
    if plan is None or plan.target_count <= 0 or plan.waiting_for_quiz:
        return
    if has_unfinished(learner):
        return
    learned_today = Assignment.objects.filter(learner=learner, learned_on=today).count()
    if learned_today >= plan.target_count and not plan.words_finished:
        plan.words_finished = True
        plan.save(update_fields=["words_finished"])
        mark_day_complete(learner, today)


def mark_learned(learner, assignment, today):
    with transaction.atomic():
        assignment = (
            Assignment.objects.select_for_update()
            .select_related("word")
            .get(pk=assignment.pk, learner=learner)
        )
        word = assignment.word
        newly = not assignment.learned
        max_before = None
        if newly:
            max_before = Assignment.objects.filter(
                learner=learner, learned=True
            ).aggregate(m=Max("word__level"))["m"]
            assignment.learned = True
            assignment.learned_on = today
            assignment.save(update_fields=["learned", "learned_on"])
            _refresh_words_finished(learner, today)
    kind = None
    if newly:
        if max_before is None:
            kind = "start"
        elif word.level > max_before:
            kind = "up"
    return {"kind": kind, "level": LEVELS[word.level], "word": word}


def mark_day_complete(learner, today):
    if learner.last_completed_on == today:
        return
    yesterday = today - timedelta(days=1)
    if learner.last_completed_on == yesterday:
        learner.streak += 1
    else:
        learner.streak = 1
    learner.last_completed_on = today
    learner.save(update_fields=["streak", "last_completed_on"])


def current_streak(learner, today):
    if learner.last_completed_on in (today, today - timedelta(days=1)):
        return learner.streak
    return 0


def streak_message(learner, today):
    streak = current_streak(learner, today)
    if learner.last_completed_on == today and streak:
        return f"{streak}-day streak. You showed up!"
    if learner.last_completed_on == today - timedelta(days=1) and streak:
        return f"Finish today to keep your {streak}-day streak!"
    return "Finish today's words to start a streak."


def words_remaining_in_bank(learner):
    return Word.objects.exclude(
        id__in=Assignment.objects.filter(learner=learner).values("word_id")
    ).exists()


def _level_progress(learner):
    learned_rows = Assignment.objects.filter(
        learner=learner, learned=True
    ).select_related("word")
    by_level = {level: [] for level in LEVELS}
    for row in learned_rows:
        by_level[row.word.level].append(row.word)
    for words in by_level.values():
        words.sort(key=lambda item: item.sequence)
    next_word = (
        Word.objects.exclude(
            id__in=Assignment.objects.filter(learner=learner, learned=True).values(
                "word_id"
            )
        )
        .order_by("level", "sequence")
        .first()
    )
    if quiz_is_due(learner):
        latest = (
            Assignment.objects.filter(learner=learner, learned=True)
            .select_related("word")
            .order_by("-learned_on", "-id")
            .first()
        )
        current_level = latest.word.level if latest else 1
    else:
        current_level = next_word.level if next_word else max(LEVELS)
    cards = []
    for level, meta in LEVELS.items():
        learned = by_level[level]
        if len(learned) >= 30:
            state = "done"
        elif level == current_level:
            state = "current"
        elif level > current_level:
            state = "locked"
        else:
            state = "done" if learned else "locked"
        cards.append(
            {
                "level": level,
                "name": meta["name"],
                "emoji": meta["emoji"],
                "blurb": meta["blurb"],
                "learned": len(learned),
                "total": 30,
                "state": state,
                "words": learned if state != "locked" else [],
            }
        )
    return cards, current_level


def quiz_summaries(learner):
    attempts = QuizAttempt.objects.filter(
        learner=learner, completed_on__isnull=False
    ).order_by("milestone", "-score", "-id")
    best = {}
    for attempt in attempts:
        slot = best.get(attempt.milestone)
        if slot is None or attempt.score > slot["score"]:
            best[attempt.milestone] = {
                "milestone": attempt.milestone,
                "score": attempt.score,
                "total": attempt.total,
                "on": attempt.completed_on,
                "id": attempt.id,
            }
    return [best[key] for key in sorted(best)]


def latest_misses(learner, limit=5):
    latest = (
        QuizAttempt.objects.filter(learner=learner, completed_on__isnull=False)
        .order_by("-completed_at", "-id")
        .first()
    )
    if latest is None:
        return []
    return list(
        latest.answers.filter(is_correct=False).select_related("word")[:limit]
    )


def snapshot(learner, today):
    plan = ensure_daily_plan(learner, today)
    board = today_board(learner, today)
    current = next((item for item in board if not item.learned), None)
    levels, current_level = _level_progress(learner)
    learned = learned_count(learner)
    last_gate = last_completed_milestone(learner)
    into = learned - last_gate
    due = quiz_is_due(learner)
    bank_left = words_remaining_in_bank(learner) or has_unfinished(learner)
    if due:
        state = "quiz"
    elif not bank_left and not has_unfinished(learner):
        state = "champion"
    elif plan.words_finished:
        state = "done"
    else:
        state = "learn"
    meta = LEVELS[current_level]
    return {
        "plan": plan,
        "board": board,
        "current": current,
        "learned_count": learned,
        "total_words": Word.objects.count(),
        "levels": levels,
        "current_level": meta,
        "current_level_number": current_level,
        "words_until_quiz": 0 if due else max(0, QUIZ_EVERY - into),
        "quiz_ready": due,
        "state": state,
        "streak": current_streak(learner, today),
        "streak_message": streak_message(learner, today),
        "quizzes": quiz_summaries(learner),
        "misses": latest_misses(learner),
        "seconds_remaining": seconds_remaining(learner, today),
        "seconds_used": learner.seconds_used if learner.usage_on == today else 0,
    }


def _batch_words(learner, milestone):
    rows = list(
        Assignment.objects.filter(learner=learner, learned=True)
        .select_related("word")
        .order_by("learned_on", "assigned_on", "position", "id")
    )
    start = milestone - QUIZ_EVERY
    return [row.word for row in rows[start:milestone]]


def open_attempt(learner):
    return (
        QuizAttempt.objects.filter(learner=learner, completed_on__isnull=True)
        .order_by("-id")
        .first()
    )


def _build_attempt(learner, milestone):
    words = _batch_words(learner, milestone)
    if len(words) < QUIZ_EVERY:
        return None
    attempt = QuizAttempt.objects.create(
        learner=learner,
        milestone=milestone,
        total=QUIZ_LENGTH,
    )
    rng = random.Random(attempt.id)
    chosen = words[:]
    rng.shuffle(chosen)
    chosen = chosen[:QUIZ_LENGTH]
    meanings = []
    for word in words:
        if word.meaning not in meanings:
            meanings.append(word.meaning)
    for position, word in enumerate(chosen, start=1):
        distractors = [meaning for meaning in meanings if meaning != word.meaning]
        rng.shuffle(distractors)
        options = distractors[:3] + [word.meaning]
        rng.shuffle(options)
        QuizAnswer.objects.create(
            attempt=attempt,
            position=position,
            word=word,
            choices=options,
            correct_text=word.meaning,
        )
    return attempt


def start_quiz(learner):
    existing = open_attempt(learner)
    if existing:
        return existing
    if not quiz_is_due(learner):
        return None
    milestone = (learned_count(learner) // QUIZ_EVERY) * QUIZ_EVERY
    return _build_attempt(learner, milestone)


def retake_quiz(learner, milestone):
    if open_attempt(learner):
        return open_attempt(learner)
    if learned_count(learner) < milestone or milestone % QUIZ_EVERY != 0 or milestone <= 0:
        return None
    if not QuizAttempt.objects.filter(
        learner=learner, milestone=milestone, completed_on__isnull=False
    ).exists():
        return None
    return _build_attempt(learner, milestone)


def current_question(attempt):
    return (
        attempt.answers.filter(selected="")
        .order_by("position")
        .select_related("word")
        .first()
    )


def submit_answer(learner, attempt, answer_id, choice, today):
    if attempt.learner_id != learner.id or attempt.completed_on:
        return attempt
    current = current_question(attempt)
    if current is None or str(current.id) != str(answer_id):
        return attempt
    if choice not in current.choices:
        return attempt
    current.selected = choice
    current.is_correct = choice == current.correct_text
    current.save(update_fields=["selected", "is_correct"])
    if not attempt.answers.filter(selected="").exists():
        score = attempt.answers.filter(is_correct=True).count()
        now = timezone.now()
        first_for_milestone = not QuizAttempt.objects.filter(
            learner=learner,
            milestone=attempt.milestone,
            completed_on__isnull=False,
        ).exists()
        attempt.score = score
        attempt.completed_at = now
        attempt.completed_on = today
        attempt.save(update_fields=["score", "completed_at", "completed_on"])
        if first_for_milestone:
            mark_day_complete(learner, today)
    return attempt


def review_groups(learner):
    groups = []
    for level, meta in LEVELS.items():
        items = list(
            Assignment.objects.filter(
                learner=learner, learned=True, word__level=level
            )
            .select_related("word")
            .order_by("word__sequence")
        )
        if items:
            groups.append({"level": level, "meta": meta, "items": items})
    return groups


def create_learner(name, offset):
    for _ in range(8):
        try:
            with transaction.atomic():
                return Learner.objects.create(
                    name=name,
                    utc_offset_minutes=offset,
                    code=new_learner_code(),
                )
        except IntegrityError:
            continue
    raise RuntimeError("Could not create a return code.")


def learner_from_code(raw):
    code = re.sub(r"[^a-z0-9]", "", (raw or "").lower())
    if not code:
        return None
    return Learner.objects.filter(code=code).first()
