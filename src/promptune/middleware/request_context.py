from uuid import uuid4

from fastapi import FastAPI, Request

from promptune.core.logging import request_id_context


def register_request_context_middleware(app: FastAPI) -> None:
    @app.middleware("http")
    async def correlate_request(request: Request, call_next):
        request_id = str(uuid4())
        request.state.request_id = request_id
        token = request_id_context.set(request_id)
        try:
            response = await call_next(request)
            response.headers["X-Request-ID"] = request_id
            return response
        finally:
            request_id_context.reset(token)
