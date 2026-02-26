from typing import Any


def success_response(data: Any = None, message: str = "OK", code: str = "OK") -> dict[str, Any]:
    return {
        "code": code,
        "message": message,
        "data": data,
    }


def error_response(message: str, code: str, details: Any = None) -> dict[str, Any]:
    payload = {
        "code": code,
        "message": message,
    }
    if details is not None:
        payload["details"] = details
    return payload
