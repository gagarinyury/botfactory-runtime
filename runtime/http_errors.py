"""Unified HTTP error handling"""
from fastapi import HTTPException

def fail(code: int, name: str, msg: str = "", **details):
    """Raise HTTPException with consistent error format"""
    raise HTTPException(code, {
        "error": {
            "code": name,
            "message": msg,
            "details": details
        }
    })