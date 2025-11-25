import os
import boto3
from app.core.config import get_settings

settings = get_settings()

# session = boto3.session.Session()
# client = session.client('s3',
#                         region_name=settings.DO_SPACES_REGION,
#                         endpoint_url=settings.DO_SPACES_ENDPOINT,
#                         aws_access_key_id=settings.DO_SPACES_KEY,
#                         aws_secret_access_key=settings.DO_SPACES_SECRET)

@lru_cache
def get_spaces_client():
    """
    Create and cache a DigitalOcean Spaces S3 client.
    - Loaded only once (lazy loading).
    - Reused across the entire application.
    """
    settings = get_settings()
    session = boto3.session.Session()

    return session.client(
        "s3",
        region_name=settings.DO_SPACES_REGION,
        endpoint_url=settings.DO_SPACES_ENDPOINT,
        aws_access_key_id=settings.DO_SPACES_KEY,
        aws_secret_access_key=settings.DO_SPACES_SECRET,
    )