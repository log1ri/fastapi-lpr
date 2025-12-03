import aioboto3
from botocore.config import Config
from app.core.config import get_settings 
from functools import lru_cache

settings = get_settings()

class DOService:
    def __init__(self):
        self.key = settings.DO_SPACES_KEY
        self.secret = settings.DO_SPACES_SECRET
        self.region = settings.DO_SPACES_REGION
        self.endpoint = settings.DO_SPACES_ENDPOINT
        self.bucket = settings.DO_SPACES_BUCKET
        self.config = Config(
            max_pool_connections=50,
            retries={"max_attempts": 3},
        )    
        # pretty log
        print("\n" + "=" * 60)
        print("✅  DO Spaces Service Initialized")
        print(f"🌍  Endpoint : {self.endpoint}")
        print(f"🪣  Bucket   : {self.bucket}")
        print("=" * 60 + "\n")
        
    @lru_cache
    def get_session(self):
        return aioboto3.Session()
    
    async def upload_bytes(self, file_bytes: bytes, file_path: str, content_type="image/jpeg"):
        session = self.get_session()

        try:
            async with session.client(
                "s3",
                region_name=self.region,
                endpoint_url=self.endpoint,
                aws_access_key_id=self.key,
                aws_secret_access_key=self.secret,
                config=self.config,
            ) as s3:
                await s3.put_object(
                    Bucket=self.bucket,
                    Key=file_path,
                    Body=file_bytes,
                    ContentType=content_type,
                    ACL="public-read"
                )
            return f"{self.endpoint}/{self.bucket}/{file_path}"

        except Exception as e:
            print(f"Error uploading to DO Spaces: {e}")
            raise e


    