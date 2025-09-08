import os
import json
import inspect
from datetime import datetime
import pytz
from .models import TradingAlert
from django.http import JsonResponse
from coinbase.rest import RESTClient
from django.views.decorators.csrf import csrf_exempt

# List of supported quote currencies to detect multi-char quotes like USDC
quote_currencies = ['USD', 'USDT', 'USDC', 'EUR', 'GBP', 'BTC', 'ETH']


def split_symbol(symbol):
    """
    Split symbol into base and quote currency using quote_currencies list.
    Returns (base_currency, quote_currency)
    """
    for quote in quote_currencies:
        if symbol.endswith(quote):
            base = symbol[:-len(quote)]
            return base, quote
    # fallback: assume last 3 chars as quote currency
    return symbol[:-3], symbol[-3:]


def get_coinbase_client():
    api_key = os.getenv("COINBASE_API_KEY")
    private_key = os.getenv("COINBASE_PRIVATE_KEY")

    # Convert literal '\n' in env string to actual newlines
    private_key = private_key.replace("\\n", "\n")

    return RESTClient(api_key=api_key, api_secret=private_key)


def place_order(client, signal, symbol, amount):
    # Convert TradingView symbol like 'HBARUSD' to Coinbase format 'HBAR-USD' with correct split
    base_currency, quote_currency = split_symbol(symbol)
    product_id = f"{base_currency}-{quote_currency}"

    try:
        if signal.lower() == 'buy':
            order = client.market_order_buy(
                client_order_id=f"tv-buy-{datetime.utcnow().timestamp()}",
                product_id=product_id,
                quote_size=str(amount)  # amount in quote currency (e.g. USD)
            )
        elif signal.lower() == 'sell':
            order = client.market_order_sell(
                client_order_id=f"tv-sell-{datetime.utcnow().timestamp()}",
                product_id=product_id,
                base_size=str(amount)  # amount in base currency (e.g. HBAR)
            )
        else:
            return None, "Invalid signal"

        return order.to_dict(), None

    except Exception as e:
        return None, str(e)

def get_percentage_value(amount, percent):
    return amount * (percent / 100)
one_per = 1

@csrf_exempt
def tradingview_webhook(request, profit_precentage=None):
    if request.method == 'POST':
        try:
            raw_body = request.body.decode('utf-8')
            print("Raw body:", raw_body)
            data = json.loads(raw_body)
            print("data : ", data)

            utc_time = datetime.fromisoformat(data['time'].replace("Z", "+00:00"))
            india_tz = pytz.timezone("Asia/Kolkata")
            india_time = utc_time.astimezone(india_tz)

            client = get_coinbase_client()
            accounts = client.get_accounts()

            symbol = data.get('symbol')  # e.g. 'HBARUSD'
            amount = float(data.get('amount'))
            signal = data.get('signal')
            price = float(data.get('price'))
            alert_utc_time_str = data.get('time')  # Example: "2025-08-13T10:30:00Z"
            format_utc_time = datetime.strptime(alert_utc_time_str, "%Y-%m-%dT%H:%M:%SZ")
            chicago_time = format_utc_time.replace(tzinfo=pytz.UTC)


            # Use improved split
            base_currency, quote_currency = split_symbol(symbol)

            balance = None
            for acc in accounts.accounts:
                print("Checking account currency:", acc.currency.upper())
                if acc.currency.upper() == base_currency.upper():
                    balance = float(acc.available_balance['value'])
                    break

            print(f"{base_currency} wallet balance : {balance}")

            order_id =None
            if signal.lower() == 'sell':
                profit_precentage = data.get('profit_precentage')
                if profit_precentage:
                    sell_profit_precentage = profit_precentage
                else:
                    sell_profit_precentage = one_per
                print("signal.lower()", signal.lower())
                last_buy = TradingAlert.objects.filter(symbol=symbol, signal='buy').order_by('-alert_chicago_time').first()
                print("last_buy DATA : ", last_buy)
                if last_buy:
                    order_details = client.get_order(order_id=last_buy.order_id)
                    print("order_details:", order_details)
                    if order_details.order.status.upper() == "FILLED":
                        filled_qty = float(order_details.order.filled_size)
                        print("filled_qty:",filled_qty)
                        total_buy_fees = float(order_details.order.total_fees)
                        # double_total_buy_fees = float(order_details.order.total_fees) * 2
                        print("total_buy_fees", total_buy_fees)
                        amount = filled_qty  # Store actual bought quantity
                        print("SELL amount:", amount)
                        per_sell_price = price
                        print("per_sell_price :",per_sell_price)
                        total_sell_price = per_sell_price * amount
                        print("total_sell_price :",total_sell_price)
                        # total_sell_price_with_fee = total_sell_price + total_buy_fees
                        # print("total_sell_price_with_fee :", total_sell_price_with_fee)
                        # buy_filled_value_without_fee = float(order_details.order.filled_value)
                        # total_buy_value_after_2fees = float(order_details.order.total_value_after_fees) + total_buy_fees
                        total_buy_value_after_fees = float(order_details.order.total_value_after_fees)
                        # print("total_buy_value_after_fees", total_buy_value_after_fees)
                        # profit_percentage_value = get_percentage_value(total_buy_value_after_fees,
                        #                                                sell_profit_precentage)
                        # print("profit_percentage_value :", profit_percentage_value)
                        # ex_total_buy_price_with_profit = total_buy_value_after_2fees + profit_percentage_value
                        # print("total_buy_price_with_profit:",ex_total_buy_price_with_profit)
                        if total_sell_price > total_buy_value_after_fees:
                            order_response, error = place_order(client, signal, symbol, amount)
                            order_id = order_response.get("success_response", {}).get("order_id")
                            print("order_id:", order_id)
                        else:
                            response_data = {
                                "status": "SELL Skipped",
                                "message": "sell price is not profitable",
                            }
                            print("Webhook Return Response for SELL: ", response_data)
                            return JsonResponse(response_data, status=201)
            else:
                # amount = amount
                # print("finelly sending amount",amount)
                # Place the order
                print("")
                try:
                    last_trading_alert = TradingAlert.objects.filter(symbol=symbol).order_by('-alert_chicago_time').first()
                except:
                    last_trading_alert = None

                if last_trading_alert:
                    last_signal = last_trading_alert.signal
                else:
                    last_signal = None

                if last_signal == "buy":
                    response_data = {
                        "status": "BUY Skipped",
                        "message": "Previous buy order still active, waiting for sell",
                    }
                    print("Webhook Return Response for BUY: ",response_data)
                    return JsonResponse(response_data, status=200)
                else:
                    order_response, error = place_order(client, signal, symbol, amount)
                    print("order_response:", order_response)

                    order_id = order_response.get("success_response", {}).get("order_id")
                    print("order_id:", order_id)

            if order_id:
                order_details = client.get_order(order_id=order_id)
                print("order_details >> ",order_details)

                order_status = order_details.order.status.upper()
                print("order_status:", order_status)

                filledqty = float(order_details.order.filled_size)
                print("filledQTY:", filledqty)

            if error:
                print("it goes ERROR!")
                response_data = {"status": "error", "message": f"Order failed: {error}"}
                print("Webhook error Response: ", response_data)
                return JsonResponse(response_data, status=400)

            # Save alert with wallet balance
            tradingalert_data = TradingAlert(
                order_id=order_id,
                signal=signal,
                symbol=symbol,
                amount=amount,
                price=price,
                filledQTY=filledqty,
                alert_chicago_time=chicago_time,
                secret=data.get('secret'),
                wallet_balance=balance,
                order_status=order_status
            )
            tradingalert_data.save()
            print("Data successfully stored with balance:", balance)
            response_data = {
                "status": "success",
                "message": "Alert processed and order placed",
                "order": order_response
            }
            print("Webhook success Return Response", response_data)

            return JsonResponse(response_data, status=200)

        except Exception as e:
            response_data = {"status": "error", "message": str(e)}
            print("Webhook Exception Response: ", response_data)

            return JsonResponse(response_data, status=400)

    return JsonResponse({"status": "error", "message": "Invalid request"}, status=405)







# if data.get('signal').lower() == 'buy':
#     account_currency_to_check = quote_currency
# else:
#     account_currency_to_check = base_currency
# print("quote_currency:", quote_currency)
# print("base_currency:", base_currency)


# if balance is None:
#     return JsonResponse({
#         "status": "error",
#         "message": f"No account found for currency {base_currency}"
#     }, status=400)
#
# # Check balance sufficiency before order
# if data.get('signal').lower() == 'buy':
#     required_amount = amount * float(data.get('price'))
#     if balance < required_amount:
#         return JsonResponse({
#             "status": "error",
#             "message": f"Insufficient {base_currency} balance to buy"
#         }, status=400)
# else:  # sell
#     if balance < amount:
#         return JsonResponse({
#             "status": "error",
#             "message": f"Insufficient {base_currency} balance to sell"
#         }, status=400)


# class TradingAlert(models.Model):
#     order_id = models.CharField(max_length=100)
#     order_status = models.CharField(max_length=50)
#     signal = models.CharField(max_length=10)  # buy / sell
#     symbol = models.CharField(max_length=20)
#     amount = models.DecimalField(max_digits=20, decimal_places=8)
#     price = models.DecimalField(max_digits=20, decimal_places=8)
#     filledQTY = models.DecimalField(max_digits=20, decimal_places=8)
#     alert_chicago_time = models.DateTimeField()  # UTC from TradingView JSON
#     # alert_time_india = models.DateTimeField()  # Converted to IST
#     secret = models.CharField(max_length=100)  # TradingView secret
#     wallet_balance = models.DecimalField(max_digits=30, decimal_places=8, null=True, blank=True)
#     alert_UTC_time = models.DateTimeField()
#
#     created_at = models.DateTimeField(auto_now_add=True)  # UTC when stored
#     updated_at = models.DateTimeField(auto_now=True)      # UTC when updated
