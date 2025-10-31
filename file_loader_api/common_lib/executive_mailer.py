# Core libraries
from dotenv import load_dotenv
import email
from email.mime.text import MIMEText
from email.mime.image import MIMEImage
from email.mime.multipart import MIMEMultipart
from email.mime.application import MIMEApplication
import os
import smtplib
import sys
from RPA_MODULES.common_lib.logging_config import get_logger

load_dotenv()
# Get a logger for this script
logger = get_logger("executive_mailer.py")
IS_TEST=os.getenv("EXECUTIVE_MAILER_IS_TEST").lower()=="true"
TEST_EMAIL=os.getenv("EXECUTIVE_MAILER_TEST_EMAIL")


def attachment(msg, attach_path):
    fo = open(attach_path, "rb")
    file_type = attach_path.split(".")[-1]
    attach_file = email.mime.application.MIMEApplication(fo.read(), _subtype=file_type)
    fo.close()
    attach_file.add_header('Content-Disposition', 'attachment', filename=attach_path.split("\\")[-1])
    msg.attach(attach_file)
    return msg


def send_email(to, cc, subject, body, sender="TSOperationsAnalyticsandManagementInformation@colt.net", attach_path=None, img_path=None):
    msg = MIMEMultipart()
    msg["From"] = sender
    msg["Subject"] = subject
    message = body if len(body) > 0 else "<br>Regards,<br>RPA Team"
    #Modified by Santhana on 1-10-24 for removing extra comma at the first & last position of email id's
    
    # Use test recipient if IS_TEST is True
    if IS_TEST:
        msg["To"] = TEST_EMAIL
        msg["Cc"] = TEST_EMAIL
        msg["Subject"] = "TEST: " + subject
        message = "This is a test email. The original recipient was: " + to + " and CC was: " + cc + "<br><br>" + "Original message: <br>" + message
    else:
        msg["To"] = to.replace(';',',').strip(',').rstrip().rstrip(',')
        msg["Cc"] = cc.replace(';',',').strip(',').rstrip().rstrip(',')
        
        
    if attach_path:
        if isinstance(attach_path, list):
            for files in attach_path:
                attachment(msg, files)
        elif isinstance(attach_path, str):
            attachment(msg, attach_path)
    msg.attach(MIMEText(message, "html"))
    if img_path:
        img_data = open(img_path, 'rb').read()
        msg.attach(MIMEImage(img_data, name=os.path.basename(img_path)))
        
    s = smtplib.SMTP("unixmailrelay.internal.colt.net", 25)
    s.send_message(msg, rcpt_options=['NOTIFY=NEVER'])
    s.quit()
    del msg


def take_screenshot(driver, to, cc, subject, err):
    img_name = sys.argv[0].split(".")[0] + "_screenshot.png"
    driver.get_screenshot_as_file(img_name)
    send_email(to=to, cc=cc, subject=subject, body='Screenshot for :' + str(err), img_path=img_name)
    if os.path.isfile(img_name):
        os.remove(img_name)


# if __name__ == "__main__":
#     # Test the SMTP connection
#     server = "unixmailrelay.internal.colt.net"
#     port = 25
#     try:
#         with smtplib.SMTP(server, port) as smtp:
#             smtp.noop()
#             test_msg = MIMEMultipart()
#             test_msg["To"]  = "test.email@colt.net"
#             test_msg["Cc"] = ""
#             test_msg["From"] = "TSOperationsAnalyticsandManagementInformation@colt.net"
#             test_msg["Subject"] = "Test Email"
#             body = "This is a test email."
#             test_msg.attach(MIMEText(body, "html"))
#             smtp.send_message(test_msg, rcpt_options=['NOTIFY=NEVER'])
#         print("SMTP connection successful")
        
        
    # except Exception as e:
    #     print(f"SMTP connection failed: {e}")
        
    
