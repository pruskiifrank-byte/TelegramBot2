
import requests
import json

url = 'https://api.oxapay.com/v1/payment/invoice'

data = {
   "amount": 100,
   "currency": "USD",
   "lifetime": 30,
   "fee_paid_by_payer": 1,
   "under_paid_coverage": 2.5,
   "to_currency": "USDT",
   "auto_withdrawal": False,
   "mixed_payment": True,
   "return_url": "https://example.com/success",
   "order_id": "ORD-12345",
   "thanks_message": "Thanks message",
   "description": "Order #12345",
   "sandbox": False
}

headers = {
   'merchant_api_key': 'MD8GIN-TNR7WJ-TXN18N-62DE3D',
   'Content-Type': 'application/json'
}

response = requests.post(url, data=json.dumps(data), headers=headers)
result = response.json()
print(result)