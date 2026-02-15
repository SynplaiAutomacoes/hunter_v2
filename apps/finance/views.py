from django.http import JsonResponse
from django.shortcuts import render
from django.views import View


# Create your views here.

class WebhookView(View):
    def get(self, request):
        return JsonResponse({"ok": True, "message": "Webhook online"}, status=200)