from django.urls import path
from .views import tradingview_webhook

urlpatterns = [
    path("webhook/", tradingview_webhook, name="tradingview_webhook"),
]
