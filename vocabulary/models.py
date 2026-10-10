from django.db import models

from .codes import new_learner_code


class Learner(models.Model):
    name = models.CharField(max_length=20)
    code = models.CharField(max_length=12, unique=True, default=new_learner_code)
    utc_offset_minutes = models.IntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)
    usage_on = models.DateField(null=True, blank=True)
    seconds_used = models.PositiveIntegerField(default=0)
    last_seen = models.DateTimeField(null=True, blank=True)
    last_played_on = models.DateField(null=True, blank=True)
    streak = models.PositiveIntegerField(default=0)
    last_completed_on = models.DateField(null=True, blank=True)

    class Meta:
        ordering = ["-last_played_on", "-id"]

    def __str__(self):
        return self.name


class Word(models.Model):
    text = models.CharField(max_length=40, unique=True)
    part_of_speech = models.CharField(max_length=24)
    pronunciation = models.CharField(max_length=48)
    meaning = models.TextField()
    tip = models.CharField(max_length=160)
    example = models.TextField()
    level = models.PositiveSmallIntegerField()
    sequence = models.PositiveSmallIntegerField()

    class Meta:
        ordering = ["level", "sequence"]
        constraints = [
            models.UniqueConstraint(
                fields=["level", "sequence"],
                name="uniq_word_level_sequence",
            )
        ]

    def __str__(self):
        return self.text


class BankMeta(models.Model):
    version = models.CharField(max_length=64)

    def __str__(self):
        return self.version


class DailyPlan(models.Model):
    learner = models.ForeignKey(Learner, on_delete=models.CASCADE, related_name="plans")
    on = models.DateField()
    target_count = models.PositiveSmallIntegerField(default=0)
    waiting_for_quiz = models.BooleanField(default=False)
    words_finished = models.BooleanField(default=False)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["learner", "on"], name="uniq_plan_day")
        ]

    def __str__(self):
        return f"{self.learner} · {self.on}"


class Assignment(models.Model):
    learner = models.ForeignKey(
        Learner, on_delete=models.CASCADE, related_name="assignments"
    )
    word = models.ForeignKey(Word, on_delete=models.CASCADE, related_name="assignments")
    assigned_on = models.DateField()
    position = models.PositiveSmallIntegerField()
    learned = models.BooleanField(default=False)
    learned_on = models.DateField(null=True, blank=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["learner", "word"],
                name="uniq_learner_word",
            ),
            models.UniqueConstraint(
                fields=["learner", "assigned_on", "position"],
                name="uniq_learner_day_position",
            ),
        ]
        indexes = [
            models.Index(fields=["learner", "learned"]),
        ]

    def __str__(self):
        return f"{self.learner} · {self.word}"


class QuizAttempt(models.Model):
    learner = models.ForeignKey(Learner, on_delete=models.CASCADE, related_name="quizzes")
    milestone = models.PositiveIntegerField()
    total = models.PositiveSmallIntegerField(default=10)
    score = models.PositiveSmallIntegerField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    completed_on = models.DateField(null=True, blank=True)

    class Meta:
        ordering = ["milestone", "-id"]

    def __str__(self):
        return f"{self.learner} quiz {self.milestone}"


class QuizAnswer(models.Model):
    attempt = models.ForeignKey(
        QuizAttempt, on_delete=models.CASCADE, related_name="answers"
    )
    position = models.PositiveSmallIntegerField()
    word = models.ForeignKey(Word, on_delete=models.CASCADE)
    choices = models.JSONField()
    correct_text = models.TextField()
    selected = models.TextField(blank=True, default="")
    is_correct = models.BooleanField(null=True)

    class Meta:
        ordering = ["position"]
        constraints = [
            models.UniqueConstraint(
                fields=["attempt", "position"],
                name="uniq_answer_position",
            )
        ]
