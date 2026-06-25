# app/services/email_service.py

import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

from app.core.config import settings



def send_otp_email(to_email: str, otp: str):

    subject =  "Roadoz Courier - OTP Verification Code"

    body =f"""
    Dear User,

    We received a request to verify your email address.

    Your One-Time Password (OTP) is: {otp}

    This OTP is valid for 5 minutes. Please do not share this code with anyone for security reasons.

    If you did not request this OTP, please ignore this email.

    Regards,
    Roadoz Courier Team
    """

    message = MIMEMultipart()
    message["From"] =  f"Roadoz-Courier <{settings.SMTP_USERNAME}>"
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