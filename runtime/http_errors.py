"""Unified HTTP error handling"""
from fastapi import HTTPException

def fail(status: int, msg: str, **extra):
    """Raise HTTPException with consistent error format"""
    raise HTTPException(status, {"error": msg, **extra})