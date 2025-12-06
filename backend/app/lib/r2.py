from dotenv import load_dotenv
import os
import boto3
from botocore.client import Config

load_dotenv()  # Load environment variables from a .env file if present 

r2_endpoint = os.getenv("R2_ENDPOINT")
access_key = os.getenv("R2_ACCESS_KEY_ID")
secret_key = os.getenv("R2_SECRET_ACCESS_KEY")

session = boto3.session.Session()

# s3 = session.client(
#     service_name="s3",
#     endpoint_url=os.getenv("R2_ENDPOINT"),  # e.g. https://<accountid>.r2.cloudflarestorage.com
#     aws_access_key_id=os.getenv("R2_ACCESS_KEY_ID"),
#     aws_secret_access_key=os.getenv("R2_SECRET_ACCESS_KEY"),
# )

s3 = session.client(
    service_name="s3",
    endpoint_url=r2_endpoint,  # e.g. https://<accountid>.r2.cloudflarestorage.com
    aws_access_key_id=access_key,
    aws_secret_access_key=secret_key,
    config=Config(signature_version="s3v4") 
)