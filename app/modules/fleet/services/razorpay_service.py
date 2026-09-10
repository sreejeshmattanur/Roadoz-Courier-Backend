import razorpay

from app.core.config import settings


class RazorpayService:

    def __init__(self):
        self.client = razorpay.Client(
            auth=(settings.RAZORPAY_KEY_ID,settings.RAZORPAY_KEY_SECRET,))
    def create_qr(self,*,amount: int,order_number: str,description: str,):
        """
        amount = paise
        Example:
        ₹160.00 -> 16000
        """
        payload = {
            "type": "upi_qr",
            "name": "Roadoz Courier",
            "usage": "single_use",
            "fixed_amount": True,
            "payment_amount": amount,
            "description": description,
            "notes": {
                "order_number": order_number,
            },
        }
        return self.client.qr_code.create(payload)
    def fetch_qr(self, qr_id: str):
        return self.client.qr_code.fetch(qr_id)
    def fetch_qr_payments(self, qr_id: str):
        return self.client.qr_code.fetch_payments(qr_id)