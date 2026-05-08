# app/services/email_service.py

import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

from app.core.config import settings



def send_otp_email(to_email: str, otp: str):

    subject = "Your OTP Verification Code"

    body = f"""
    Hello,

    Your OTP code is: {otp}

    This OTP is valid for 5 minutes.

    Thank you.
    """

    message = MIMEMultipart()
    message["From"] = settings.SMTP_USERNAME
    message["To"] = to_email
    message["Subject"] = subject
    message.attach(MIMEText(body, "plain"))
    try:
        server = smtplib.SMTP(settings.SMTP_HOST, int(settings.SMTP_PORT))
        server.starttls()
        server.login(settings.SMTP_USERNAME,settings.SMTP_PASSWORD)
        server.sendmail(settings.SMTP_USERNAME,to_email,message.as_string())
        server.quit()

        return True

    except Exception as e:
        print("EMAIL ERROR:", e)
        return False