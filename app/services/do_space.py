import asyncio
import aioboto3
import logging
from botocore.config import Config
from app.core.config import get_settings 
from functools import lru_cache

logger = logging.getLogger("DO_service") 
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

        logger.info("==============================================") 
        logger.info("✅  DO Spaces Service Initialized") 
        logger.info(f"🌍  Endpoint : {self.endpoint}")
        logger.info(f"🪣  Bucket   : {self.bucket}")
        logger.info("=============================================="+"\n") 

        
    @lru_cache
    def get_session(self):
        return aioboto3.Session()
    
    async def upload_image(self, image: bytes, image_path: str, content_type="image/jpeg"):
        session = self.get_session()

        try:
            logger.info("Uploading image to DO Spaces...")
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
                    Key=image_path,
                    Body=image,
                    ContentType=content_type,
                    ACL="public-read"
                )
            return f"{self.endpoint}/{self.bucket}/{image_path}"

        except Exception as e:
            print(f"Error uploading to DO Spaces: {e}")
            raise e
        
    async def upload_two_images(
        self,
        original_bytes: bytes,
        cropped_bytes: bytes,
        path_original: str,
        path_cropped: str,
    ):
        try:
            logger.info("Uploading two images to DO Spaces...")
            url_original, url_cropped = await asyncio.gather(
                self.upload_image(original_bytes, path_original),
                self.upload_image(cropped_bytes, path_cropped),
            )
            return url_original, url_cropped
        except Exception as e:
            logger.error(f"Error uploading images to DO Spaces: {e}")
            raise e



    