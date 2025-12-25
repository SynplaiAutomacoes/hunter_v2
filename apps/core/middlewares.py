from django.shortcuts import redirect
from django.urls import resolve, reverse


class RequireFirstWorkshopMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if request.user.is_authenticated:
            if request.path.startswith("/admin/"):
                return self.get_response(request)

            match = resolve(request.path_info)
            current = f"{match.namespace}:{match.url_name}" if match.namespace else match.url_name

            allowed = {"workshops:create", "accounts:login", "accounts:register", "accounts:logout"}

            if current not in allowed:
                from apps.workshops.models import Workshop

                if not Workshop.objects.exists():
                    return redirect(reverse("workshops:create"))

        return self.get_response(request)
