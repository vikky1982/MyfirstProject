import os

from django.http import HttpResponseNotFound


class PublicGateMiddleware:
    """Hide the old employee tools when Word Quest is shared on the internet."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if os.environ.get("DJANGO_PUBLIC") == "1":
            if request.path.startswith("/employee") or request.path.startswith("/admin"):
                return HttpResponseNotFound("Not available.")
        return self.get_response(request)
