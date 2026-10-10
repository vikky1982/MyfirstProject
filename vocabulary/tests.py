import os
import re
from datetime import date, datetime, timedelta, timezone as dt_timezone

from django.test import Client, SimpleTestCase, TestCase
from django.urls import reverse

from vocabulary.models import Assignment, Learner, QuizAttempt, Word
from vocabulary.words import DECOYS, iter_words
from vocabulary import services


class WordBankTests(SimpleTestCase):
    def test_bank_has_six_harder_levels_of_thirty(self):
        words = list(iter_words())
        self.assertEqual(len(words), 180)
        self.assertEqual(len({item["text"] for item in words}), 180)
        self.assertEqual(len({item["meaning"] for item in words}), 180)
        levels = [item["level"] for item in words]
        self.assertEqual(levels, sorted(levels))
        for level in range(1, 7):
            rows = [item for item in words if item["level"] == level]
            self.assertEqual(len(rows), 30)
            self.assertEqual([item["sequence"] for item in rows], list(range(1, 31)))
        lengths = []
        for level in range(1, 7):
            rows = [item for item in words if item["level"] == level]
            lengths.append(sum(len(item["text"]) for item in rows) / len(rows))
        self.assertGreater(lengths[-1], lengths[0])
        self.assertGreater(lengths[2], lengths[0])

    def test_examples_use_the_word_and_meanings_do_not(self):
        for item in iter_words():
            pattern = rf"\b{re.escape(item['text'])}\b"
            self.assertIsNotNone(
                re.search(pattern, item["example"], re.I),
                item["text"],
            )
            self.assertIsNone(re.search(pattern, item["meaning"], re.I), item["text"])
            self.assertNotIn(item["meaning"], DECOYS)


class ServiceTests(TestCase):
    def setUp(self):
        services.ensure_word_bank()
        self.learner = Learner.objects.create(name="Maya", utc_offset_minutes=0)
        self.today = date(2026, 6, 1)

    def _finish_board(self, day):
        board = services.today_board(self.learner, day)
        pending = [item for item in board if not item.learned]
        self.assertTrue(pending)
        for item in pending:
            services.mark_learned(self.learner, item, day)
        return pending

    def _ace_quiz(self, day):
        attempt = services.start_quiz(self.learner)
        self.assertIsNotNone(attempt)
        while True:
            question = services.current_question(attempt)
            if question is None:
                break
            services.submit_answer(
                self.learner, attempt, question.id, question.correct_text, day
            )
            attempt.refresh_from_db()
        self.assertEqual(attempt.score, attempt.total)
        return attempt

    def test_only_ten_new_words_are_given_each_day(self):
        first = self._finish_board(self.today)
        self.assertEqual(len(first), 10)
        self.assertEqual(
            Assignment.objects.filter(learner=self.learner, assigned_on=self.today).count(),
            10,
        )
        services.ensure_daily_plan(self.learner, self.today)
        self.assertEqual(
            Assignment.objects.filter(learner=self.learner, assigned_on=self.today).count(),
            10,
        )
        self.assertEqual(
            [item.word.level for item in first],
            [1] * 10,
        )

    def test_unfinished_words_carry_and_new_ones_stay_in_order(self):
        board = services.today_board(self.learner, self.today)
        for item in board[:3]:
            services.mark_learned(self.learner, item, self.today)
        tomorrow = self.today + timedelta(days=1)
        next_board = services.today_board(self.learner, tomorrow)
        pending = [item for item in next_board if not item.learned]
        self.assertEqual(len(pending), 10)
        sequences = [item.word.sequence for item in pending]
        self.assertEqual(sequences, [4, 5, 6, 7, 8, 9, 10, 11, 12, 13])
        self.assertEqual(
            Assignment.objects.filter(learner=self.learner, assigned_on=tomorrow).count(),
            3,
        )

    def test_quiz_gates_the_next_harder_level(self):
        day = self.today
        for _ in range(3):
            self.assertFalse(services.quiz_is_due(self.learner))
            self._finish_board(day)
            day += timedelta(days=1)
        self.assertEqual(services.learned_count(self.learner), 30)
        self.assertTrue(services.quiz_is_due(self.learner))
        self.assertTrue(
            all(
                word.level == 1
                for word in Word.objects.filter(
                    assignments__learner=self.learner, assignments__learned=True
                )
            )
        )
        services.today_board(self.learner, day)
        self.assertEqual(Assignment.objects.filter(learner=self.learner).count(), 30)

        same_day = day
        self._ace_quiz(same_day)
        self.assertFalse(services.quiz_is_due(self.learner))
        unlocked = services.today_board(self.learner, same_day)
        new_words = [item.word for item in unlocked if not item.learned]
        self.assertEqual(len(new_words), 10)
        self.assertEqual([word.level for word in new_words], [2] * 10)
        self.assertEqual([word.sequence for word in new_words], list(range(1, 11)))
        learned_pairs = [
            (item.word.level, item.word.sequence)
            for item in Assignment.objects.filter(
                learner=self.learner, learned=True
            ).select_related("word").order_by("learned_on", "assigned_on", "position")
        ]
        self.assertEqual(learned_pairs, sorted(learned_pairs))

    def test_same_day_after_a_full_set_does_not_add_a_second_set(self):
        self._finish_board(self.today)
        services.ensure_daily_plan(self.learner, self.today)
        self.assertEqual(Assignment.objects.filter(learner=self.learner).count(), 10)

    def test_continue_opens_another_set_the_same_day(self):
        self._finish_board(self.today)
        services.continue_set(self.learner, self.today)
        pending = [
            item for item in services.today_board(self.learner, self.today) if not item.learned
        ]
        self.assertEqual(len(pending), 10)
        self.assertEqual(Assignment.objects.filter(learner=self.learner).count(), 20)
        self.assertEqual([item.word.sequence for item in pending], list(range(11, 21)))

    def test_first_choices_do_not_spoil_future_words(self):
        assignment = services.current_assignment(self.learner, self.today)
        choices = services.learn_choices(self.learner, assignment.word, self.today)
        self.assertIn(assignment.word.meaning, choices)
        self.assertEqual(len(choices), 4)
        future = set(
            Word.objects.exclude(pk=assignment.word_id).values_list("meaning", flat=True)
        )
        for choice in choices:
            if choice != assignment.word.meaning:
                self.assertIn(choice, DECOYS)
                self.assertNotIn(choice, future)

    def test_later_choices_use_learned_meanings_only(self):
        board = services.today_board(self.learner, self.today)
        for item in board[:3]:
            services.mark_learned(self.learner, item, self.today)
        current = services.current_assignment(self.learner, self.today)
        choices = services.learn_choices(self.learner, current.word, self.today)
        learned_ids = set(
            Assignment.objects.filter(learner=self.learner, learned=True).values_list(
                "word_id", flat=True
            )
        )
        future = set(
            Word.objects.exclude(pk=current.word_id)
            .exclude(pk__in=learned_ids)
            .values_list("meaning", flat=True)
        )
        for choice in choices:
            if choice != current.word.meaning:
                self.assertNotIn(choice, future)

    def test_streak_grows_on_consecutive_days_and_resets(self):
        self._finish_board(self.today)
        self.learner.refresh_from_db()
        self.assertEqual(services.current_streak(self.learner, self.today), 1)
        next_day = self.today + timedelta(days=1)
        self._finish_board(next_day)
        self.learner.refresh_from_db()
        self.assertEqual(services.current_streak(self.learner, next_day), 2)
        later = next_day + timedelta(days=3)
        self.assertEqual(services.current_streak(self.learner, later), 0)

    def test_active_time_is_capped_and_idle_gaps_do_not_count(self):
        start = datetime(2026, 6, 1, 15, 0, tzinfo=dt_timezone.utc)
        self.assertEqual(services.touch(self.learner, start, active=True), 15 * 60)
        services.touch(self.learner, start + timedelta(seconds=20), active=False)
        self.learner.refresh_from_db()
        self.assertEqual(self.learner.seconds_used, 0)
        services.touch(self.learner, start + timedelta(seconds=35), active=True)
        self.learner.refresh_from_db()
        self.assertEqual(self.learner.seconds_used, 15)

        services.touch(self.learner, start + timedelta(hours=3), active=True)
        self.learner.refresh_from_db()
        self.assertEqual(self.learner.seconds_used, 15)

        self.learner.seconds_used = services.DAILY_LIMIT_SECONDS - 10
        self.learner.last_seen = start
        self.learner.save(update_fields=["seconds_used", "last_seen"])
        remaining = services.touch(self.learner, start + timedelta(seconds=40), active=True)
        self.assertEqual(remaining, 0)
        self.learner.refresh_from_db()
        self.assertEqual(self.learner.seconds_used, services.DAILY_LIMIT_SECONDS)

    def test_local_day_follows_the_learner_clock(self):
        self.learner.utc_offset_minutes = 240
        moment = datetime(2026, 10, 10, 2, 0, tzinfo=dt_timezone.utc)
        self.assertEqual(services.local_today(self.learner, moment), date(2026, 10, 9))
        self.learner.utc_offset_minutes = -330
        moment = datetime(2026, 1, 1, 20, 0, tzinfo=dt_timezone.utc)
        self.assertEqual(services.local_today(self.learner, moment), date(2026, 1, 2))

    def test_a_new_local_day_resets_the_timer(self):
        start = datetime(2026, 6, 1, 23, 50, tzinfo=dt_timezone.utc)
        services.touch(self.learner, start, active=True)
        self.learner.seconds_used = 400
        self.learner.save(update_fields=["seconds_used"])
        services.touch(self.learner, start + timedelta(minutes=20), active=True)
        self.learner.refresh_from_db()
        self.assertEqual(self.learner.usage_on, date(2026, 6, 2))
        self.assertEqual(self.learner.seconds_used, 0)

    def test_progress_snapshot_counts_words_and_quizzes(self):
        self._finish_board(self.today)
        snap = services.snapshot(self.learner, self.today)
        self.assertEqual(snap["learned_count"], 10)
        self.assertEqual(snap["state"], "done")
        self.assertEqual(snap["words_until_quiz"], 20)
        self.assertEqual(snap["levels"][0]["learned"], 10)
        self.assertEqual(snap["levels"][1]["state"], "locked")


class PageTests(TestCase):
    def setUp(self):
        services.ensure_word_bank()
        self.client = Client()

    def _join(self, name="Maya"):
        response = self.client.post(
            reverse("vocabulary:welcome"),
            {"name": name, "tz_offset": "0"},
        )
        self.assertRedirects(response, reverse("vocabulary:home"))
        return Learner.objects.get(name=name)

    def test_return_code_reopens_progress_and_names_are_not_shared(self):
        first = self._join("O'Neil")
        self.client.post(reverse("vocabulary:switch"))
        same_name = self.client.post(
            reverse("vocabulary:welcome"),
            {"name": "o'neil", "tz_offset": "0"},
        )
        self.assertRedirects(same_name, reverse("vocabulary:home"))
        self.assertEqual(Learner.objects.count(), 2)
        self.client.post(reverse("vocabulary:switch"))
        again = self.client.post(
            reverse("vocabulary:welcome"),
            {"code": first.code.upper(), "tz_offset": "60"},
        )
        self.assertRedirects(again, reverse("vocabulary:home"))
        self.assertEqual(Learner.objects.count(), 2)
        first.refresh_from_db()
        self.assertEqual(first.utc_offset_minutes, 60)
        rejected = Client().post(reverse("vocabulary:welcome"), {"name": "Maya2"})
        self.assertContains(rejected, "Use a name")
        missing = Client().post(reverse("vocabulary:welcome"), {"code": "nope"})
        self.assertContains(missing, "not found")

    def test_learning_stops_at_ten_and_records_progress(self):
        self._join()
        for _ in range(10):
            page = self.client.get(reverse("vocabulary:learn"))
            self.assertEqual(page.status_code, 200)
            word = page.context["word"]
            done = self.client.post(
                reverse("vocabulary:learn"),
                {"choice": word.meaning},
            )
            self.assertEqual(done.status_code, 302)
        self.assertEqual(Assignment.objects.filter(learned=True).count(), 10)
        extra = self.client.get(reverse("vocabulary:learn"))
        self.assertRedirects(extra, reverse("vocabulary:home"))
        self.assertEqual(Assignment.objects.count(), 10)
        home = self.client.get(reverse("vocabulary:home"))
        self.assertContains(home, "Ten words are done")
        progress = self.client.get(reverse("vocabulary:progress"))
        self.assertContains(progress, "10 words learned")
        review = self.client.get(reverse("vocabulary:review"))
        self.assertContains(review, Assignment.objects.get(position=1).word.text)

    def test_wrong_choice_does_not_count_as_learned(self):
        self._join()
        page = self.client.get(reverse("vocabulary:learn"))
        word = page.context["word"]
        wrong = next(choice for choice in page.context["choices"] if choice != word.meaning)
        retry = self.client.post(
            reverse("vocabulary:learn"),
            {"choice": wrong},
        )
        self.assertEqual(retry.status_code, 200)
        self.assertContains(retry, "Not quite")
        self.assertFalse(Assignment.objects.filter(learned=True).exists())

    def test_timer_blocks_the_lesson(self):
        learner = self._join()
        today = services.local_today(learner)
        learner.usage_on = today
        learner.seconds_used = services.DAILY_LIMIT_SECONDS
        learner.save(update_fields=["usage_on", "seconds_used"])
        response = self.client.get(reverse("vocabulary:learn"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Hear it")

    def test_quiz_page_after_thirty_words(self):
        learner = self._join()
        day = services.local_today(learner)
        for _ in range(3):
            board = services.today_board(learner, day)
            for item in board:
                if not item.learned:
                    services.mark_learned(learner, item, day)
            day += timedelta(days=1)
        start = self.client.get(reverse("vocabulary:quiz"))
        attempt = QuizAttempt.objects.get()
        self.assertRedirects(
            start,
            reverse("vocabulary:quiz_attempt", args=[attempt.id]),
        )
        while True:
            attempt.refresh_from_db()
            question = services.current_question(attempt)
            if question is None:
                break
            self.client.post(
                reverse("vocabulary:quiz_attempt", args=[attempt.id]),
                {"answer_id": question.id, "choice": question.correct_text},
            )
        attempt.refresh_from_db()
        self.assertEqual(attempt.score, 10)
        result = self.client.get(reverse("vocabulary:quiz_result", args=[attempt.id]))
        self.assertContains(result, "10 / 10")
        # The day already had its ten words, so the harder set waits until tomorrow.
        self.assertEqual(Assignment.objects.filter(learner=learner).count(), 30)
        blocked = self.client.get(reverse("vocabulary:learn"))
        self.assertRedirects(blocked, reverse("vocabulary:home"))

    def test_employee_pages_still_open(self):
        response = self.client.get("/employee/")
        self.assertEqual(response.status_code, 200)

    def test_public_site_hides_employee_pages(self):
        os.environ["DJANGO_PUBLIC"] = "1"
        try:
            response = self.client.get("/employee/")
            self.assertEqual(response.status_code, 404)
            admin = self.client.get("/admin/")
            self.assertEqual(admin.status_code, 404)
        finally:
            del os.environ["DJANGO_PUBLIC"]
