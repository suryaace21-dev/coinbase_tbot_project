from django.db import models


class TradingAlert(models.Model):
    order_id = models.CharField(max_length=100)
    signal = models.CharField(max_length=10)  # buy / sell
    symbol = models.CharField(max_length=20)
    amount = models.DecimalField(max_digits=20, decimal_places=8)
    price = models.DecimalField(max_digits=20, decimal_places=8)
    filledQTY = models.DecimalField(max_digits=20, decimal_places=8, null=True, blank=True)
    alert_chicago_time = models.DateTimeField()  # CHICAGO from TradingView JSON
    secret = models.CharField(max_length=100)  # TradingView secret
    wallet_balance = models.DecimalField(max_digits=30, decimal_places=8, null=True, blank=True)
    order_status = models.CharField(max_length=50)
    created_at = models.DateTimeField(auto_now_add=True)  # UTC when stored
    updated_at = models.DateTimeField(auto_now=True)      # UTC when updated

    def __str__(self):
        return f"{self.signal.upper()} {self.symbol} @ {self.price}"


class AllAlertLogs(models.Model):
    signal = models.CharField(max_length=10)  # buy / sell
    symbol = models.CharField(max_length=20)
    alert_date_time = models.DateTimeField()
    amount = models.DecimalField(max_digits=20, decimal_places=8)
    price = models.DecimalField(max_digits=20, decimal_places=8)




