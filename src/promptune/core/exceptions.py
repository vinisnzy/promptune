class AppError(Exception):
    status_code = 400

    def __init__(self, message: str) -> None:
        super().__init__(message)
        self.message = message


class NotFoundError(AppError):
    status_code = 404


class InvalidInputError(AppError):
    status_code = 400


class ConflictError(AppError):
    status_code = 409


class UnauthorizedError(AppError):
    status_code = 401
