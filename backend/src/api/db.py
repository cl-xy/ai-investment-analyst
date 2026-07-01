"""
MongoDB connection helpers for the Investment Analyst API.
"""

from motor.motor_asyncio import AsyncIOMotorClient, AsyncIOMotorCollection

from src.config import settings

_client: AsyncIOMotorClient | None = None


def get_client() -> AsyncIOMotorClient:
    global _client
    if _client is None:
        _client = AsyncIOMotorClient(settings.mongodb_uri)
    return _client


def get_collection(name: str) -> AsyncIOMotorCollection:
    return get_client()[settings.mongodb_db][name]


async def close_client() -> None:
    global _client
    if _client is not None:
        _client.close()
        _client = None
