from functools import wraps

from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from .models import Learner, QuizAttempt
from . import services


NOTE_KEYS = ("day_note", "level_note", "just_learned", "quiz_note")


def consume_notes(request):
    notes = {}
    for key in NOTE_KEYS:
        value = request.session.pop(key, None)
        if value:
            notes[key] = value
    return notes


def _learner_from_session(request):
    learner_id = request.session.get("learner_id")
    if not learner_id:
        return None
    return Learner.objects.filter(pk=learner_id).first()


def with_learner(timed=True):
    def decorator(view):
        @wraps(view)
        def wrapper(request, *args, **kwargs):
            services.ensure_word_bank()
            learner = _learner_from_session(request)
            if learner is None:
                return redirect("vocabulary:welcome")
            request.learner = learner
            today = services.local_today(learner)
            request.vocab_today = today
            if timed:
                before = services.seconds_remaining(learner, today)
                if before <= 0:
                    return redirect("vocabulary:timeup")
                request.remaining = services.touch(learner, active=True)
                request.show_timer = True
            else:
                request.remaining = services.seconds_remaining(learner, today)
                request.show_timer = False
            return view(request, *args, **kwargs)

        return wrapper

    return decorator


def welcome(request):
    services.ensure_word_bank()
    if _learner_from_session(request):
        return redirect("vocabulary:home")
    error = None
    if request.method == "POST":
        offset = services.parse_offset(request.POST.get("tz_offset"))
        raw_code = (request.POST.get("code") or "").strip()
        if raw_code:
            learner = services.learner_from_code(raw_code)
            if learner is None:
                error = "That return code was not found. Check it and try again."
            else:
                learner.utc_offset_minutes = offset
                learner.save(update_fields=["utc_offset_minutes"])
                request.session["learner_id"] = learner.id
                return redirect("vocabulary:home")
        else:
            name = services.clean_name(request.POST.get("name", ""))
            if not name:
                error = "Use a name with letters, like Maya or Jo."
            else:
                learner = services.create_learner(name, offset)
                request.session["learner_id"] = learner.id
                request.session["day_note"] = (
                    f"Your return code is {learner.code}. Write it down. "
                    "Type it on the first page to open this progress on another device."
                )
                return redirect("vocabulary:home")
    return render(
        request,
        "vocabulary/welcome.html",
        {"error": error},
    )


@require_POST
def switch(request):
    request.session.pop("learner_id", None)
    return redirect("vocabulary:welcome")


@with_learner()
def home(request):
    today = request.vocab_today
    snap = services.snapshot(request.learner, today)
    return render(
        request,
        "vocabulary/home.html",
        {"snap": snap, "today": today, "notes": consume_notes(request)},
    )


@with_learner()
def learn(request):
    learner = request.learner
    today = request.vocab_today
    if services.quiz_is_due(learner) and not services.has_unfinished(learner):
        return redirect("vocabulary:quiz")
    current = services.current_assignment(learner, today)
    if current is None:
        return redirect("vocabulary:home")
    word = current.word
    choices = services.learn_choices(learner, word, today)
    error = None
    show_meaning = False
    if request.method == "POST":
        choice = request.POST.get("choice", "")
        if choice not in choices:
            error = "Pick one of the meanings."
        elif choice == word.meaning:
            result = services.mark_learned(learner, current, today)
            if result["kind"] == "start":
                level = result["level"]
                request.session["level_note"] = (
                    f"{level['emoji']} {level['name']} words are friendly. "
                    "They will get harder as you grow."
                )
            elif result["kind"] == "up":
                level = result["level"]
                request.session["level_note"] = (
                    f"New level: {level['emoji']} {level['name']}. "
                    f"{level['blurb']}"
                )
            else:
                request.session["just_learned"] = word.text
            if services.quiz_is_due(learner) and not services.has_unfinished(learner):
                request.session["quiz_note"] = (
                    f"You have learned {services.learned_count(learner)} words. Quiz time!"
                )
                return redirect("vocabulary:quiz")
            if services.current_assignment(learner, today) is None:
                request.session["day_note"] = (
                    "Those are your words for today. Come back tomorrow for five more."
                )
                return redirect("vocabulary:home")
            return redirect("vocabulary:learn")
        else:
            error = "Not quite. Peek at the meaning, then try again."
            show_meaning = True
    board = services.today_board(learner, today)
    notes = consume_notes(request)
    return render(
        request,
        "vocabulary/learn.html",
        {
            "word": word,
            "choices": choices,
            "error": error,
            "show_meaning": show_meaning,
            "board": board,
            "current": current,
            "notes": notes,
            "level_meta": services.LEVELS[word.level],
        },
    )


def _quiz_attempt_or_redirect(request, attempt_id=None):
    learner = request.learner
    if attempt_id is None:
        attempt = services.start_quiz(learner)
        if attempt is None:
            return None, redirect("vocabulary:home")
        if request.resolver_match.url_name == "quiz":
            return attempt, redirect("vocabulary:quiz_attempt", attempt_id=attempt.id)
        return attempt, None
    attempt = get_object_or_404(QuizAttempt, pk=attempt_id, learner=learner)
    return attempt, None


@with_learner()
def quiz(request, attempt_id=None):
    learner = request.learner
    today = request.vocab_today
    attempt, early = _quiz_attempt_or_redirect(request, attempt_id)
    if early is not None and attempt_id is None:
        return early
    if attempt is None:
        return redirect("vocabulary:home")
    if attempt.completed_on:
        return redirect("vocabulary:quiz_result", attempt_id=attempt.id)
    error = None
    if request.method == "POST":
        before = services.current_question(attempt)
        choice = request.POST.get("choice", "")
        if before is None:
            return redirect("vocabulary:quiz_result", attempt_id=attempt.id)
        if choice not in before.choices:
            error = "Pick the meaning that fits."
        else:
            services.submit_answer(
                learner, attempt, request.POST.get("answer_id"), choice, today
            )
            attempt.refresh_from_db()
            if attempt.completed_on:
                return redirect("vocabulary:quiz_result", attempt_id=attempt.id)
            return redirect("vocabulary:quiz_attempt", attempt_id=attempt.id)
    question = services.current_question(attempt)
    if question is None:
        return redirect("vocabulary:quiz_result", attempt_id=attempt.id)
    return render(
        request,
        "vocabulary/quiz.html",
        {
            "attempt": attempt,
            "answer": question,
            "error": error,
            "notes": consume_notes(request),
        },
    )


@with_learner()
def quiz_result(request, attempt_id):
    attempt = get_object_or_404(
        QuizAttempt, pk=attempt_id, learner=request.learner, completed_on__isnull=False
    )
    answers = list(attempt.answers.select_related("word"))
    return render(
        request,
        "vocabulary/quiz_result.html",
        {"attempt": attempt, "answers": answers},
    )


@with_learner()
@require_POST
def quiz_retake(request):
    try:
        milestone = int(request.POST.get("milestone", "0"))
    except ValueError:
        milestone = 0
    attempt = services.retake_quiz(request.learner, milestone)
    if attempt is None:
        return redirect("vocabulary:progress")
    return redirect("vocabulary:quiz_attempt", attempt_id=attempt.id)


@with_learner()
def progress(request):
    snap = services.snapshot(request.learner, request.vocab_today)
    return render(request, "vocabulary/progress.html", {"snap": snap})


@with_learner()
def review(request):
    groups = services.review_groups(request.learner)
    return render(request, "vocabulary/review.html", {"groups": groups})


@with_learner(timed=False)
def timeup(request):
    if request.remaining >= 15:
        return redirect("vocabulary:home")
    request.locked = True
    snap = services.snapshot(request.learner, request.vocab_today)
    return render(request, "vocabulary/timeup.html", {"snap": snap})


@with_learner(timed=False)
@require_POST
def heartbeat(request):
    active = request.POST.get("active") == "1"
    remaining = services.touch(request.learner, active=active)
    return JsonResponse(
        {"remaining": remaining, "limit": services.DAILY_LIMIT_SECONDS}
    )
