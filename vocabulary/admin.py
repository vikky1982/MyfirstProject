from django.contrib import admin

from .models import Assignment, DailyPlan, Learner, QuizAttempt, Word


@admin.register(Learner)
class LearnerAdmin(admin.ModelAdmin):
    list_display = ("name", "streak", "seconds_used", "usage_on", "last_played_on")
    search_fields = ("name",)


@admin.register(Word)
class WordAdmin(admin.ModelAdmin):
    list_display = ("text", "level", "sequence", "part_of_speech")
    list_filter = ("level",)
    search_fields = ("text", "meaning")


@admin.register(Assignment)
class AssignmentAdmin(admin.ModelAdmin):
    list_display = ("learner", "word", "assigned_on", "learned", "learned_on")
    list_filter = ("learned",)


@admin.register(DailyPlan)
class DailyPlanAdmin(admin.ModelAdmin):
    list_display = ("learner", "on", "target_count", "words_finished", "waiting_for_quiz")


@admin.register(QuizAttempt)
class QuizAttemptAdmin(admin.ModelAdmin):
    list_display = ("learner", "milestone", "score", "total", "completed_on")
