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

            allowed = {
                "workshops:create",
                "accounts:login",
                "accounts:register",
                "accounts:logout",
                "iam:role_list",
                "iam:role_create",
                "iam:role_update",
                "iam:role_delete",
            }

            if current not in allowed:
                if not getattr(request.user, "account_id", None):
                    return redirect(reverse("accounts:logout"))

                if request.user.account.owner_id == request.user.id:
                    from apps.workshops.models import Workshop

                    if not Workshop.objects.filter(
                        account=request.user.account,
                        is_active=True,
                    ).exists():
                        return redirect(reverse("workshops:create"))
                else:
                    from apps.workshops.models import WorkshopMember

                    if not WorkshopMember.objects.filter(
                        user=request.user,
                        is_active=True,
                        workshop__account=request.user.account,
                        workshop__is_active=True,
                    ).exists():
                        return redirect(reverse("accounts:logout"))

        return self.get_response(request)
