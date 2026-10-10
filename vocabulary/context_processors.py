from . import services


def hud(request):
    return {
        "learner": getattr(request, "learner", None),
        "seconds_remaining": getattr(request, "remaining", None),
        "show_timer": getattr(request, "show_timer", False),
        "daily_limit": services.DAILY_LIMIT_SECONDS,
        "locked": getattr(request, "locked", False),
    }
