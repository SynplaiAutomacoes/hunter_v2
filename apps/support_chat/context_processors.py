from django.conf import settings


def support_chat(request):
    return {
        "SUPPORT_CHAT_ENABLED": getattr(settings, "SUPPORT_CHAT_ENABLED", False),
    }
