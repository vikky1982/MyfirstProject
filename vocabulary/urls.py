from django.urls import path

from . import views

app_name = "vocabulary"

urlpatterns = [
    path("", views.home, name="home"),
    path("start/", views.welcome, name="welcome"),
    path("switch/", views.switch, name="switch"),
    path("learn/", views.learn, name="learn"),
    path("quiz/", views.quiz, name="quiz"),
    path("quiz/<int:attempt_id>/", views.quiz, name="quiz_attempt"),
    path("quiz/<int:attempt_id>/result/", views.quiz_result, name="quiz_result"),
    path("quiz/retake/", views.quiz_retake, name="quiz_retake"),
    path("progress/", views.progress, name="progress"),
    path("review/", views.review, name="review"),
    path("timeup/", views.timeup, name="timeup"),
    path("heartbeat/", views.heartbeat, name="heartbeat"),
]
