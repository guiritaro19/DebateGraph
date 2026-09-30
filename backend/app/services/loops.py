"""Psycopg async requires SelectorEventLoop on Windows (Python 3.12+)."""

import asyncio


def postgres_loop():
    return asyncio.SelectorEventLoop()
