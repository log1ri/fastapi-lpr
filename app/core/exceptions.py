class AppError(Exception):
    status_code = 500
    code = "APP_ERROR"

    def __init__(self, message: str, *, extra: dict | None = None):
        self.message = message
        self.extra = extra
        super().__init__(message)


class BusinessLogicError(AppError):
    status_code = 400
    code = "BUSINESS_ERROR"


class StorageServiceError(AppError):
    status_code = 503
    code = "STORAGE_ERROR"


class MongoLogError(AppError):
    status_code = 500
    code = "MONGO_ERROR"


class OCRServiceError(AppError):
    status_code = 502
    code = "OCR_ERROR"