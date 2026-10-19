class BusinessError(Exception):
    def __init__(self, code: str, message: str, status: int = 422,
                 question_id: str | None = None, field: str | None = None):
        self.code = code
        self.message = message
        self.status = status
        self.question_id = question_id
        self.field = field
        super().__init__(message)

