"""Storage abstraction.

Two backends behind one async interface:
  - MemoryStore : default, zero setup — the spine runs with no database installed.
  - MongoStore  : used when STORAGE_BACKEND=mongo and a MONGO_URI is reachable.

This is the blocker-protocol done right: build & verify everything now on memory; the
user stands up MongoDB in parallel and we flip STORAGE_BACKEND with no code change.
Blobs (document / face images) are stored keyed by SHA-256 (GridFS in the mongo backend).
"""
from __future__ import annotations

import hashlib
from typing import Any, Optional

from ..config import settings


def _sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


class MemoryStore:
    """In-process store. Data lives for the life of the server process only."""

    backend = "memory"

    def __init__(self) -> None:
        self._sessions: dict[str, dict] = {}
        self._session_order: list[str] = []
        self._ledger: list[dict] = []
        self._blobs: dict[str, bytes] = {}
        self._watchlist: list[dict] = []
        self._gallery: list[dict] = []

    async def ping(self) -> bool:
        return True

    # --- watchlist (mock lost/stolen + lookout list) ---
    async def watchlist_add(self, entry: dict) -> None:
        self._watchlist.append(entry)

    async def watchlist_all(self) -> list[dict]:
        return list(self._watchlist)

    async def watchlist_check(self, value: str) -> Optional[dict]:
        v = (value or "").upper().replace("<", "")
        for e in self._watchlist:
            if (e.get("value", "").upper().replace("<", "")) == v:
                return e
        return None

    # --- identity gallery (multiple-identity / photo-swap detection) ---
    async def gallery_add(self, entry: dict) -> None:
        self._gallery.append(entry)

    async def gallery_all(self) -> list[dict]:
        return list(self._gallery)

    # --- sessions ---
    async def save_session(self, ev_dict: dict) -> None:
        sid = ev_dict["session_id"]
        if sid not in self._sessions:
            self._session_order.append(sid)
        self._sessions[sid] = ev_dict

    async def get_session(self, sid: str) -> Optional[dict]:
        return self._sessions.get(sid)

    async def list_sessions(self, limit: int = 50) -> list[dict]:
        ids = self._session_order[-limit:][::-1]
        return [self._sessions[i] for i in ids]

    # --- ledger ---
    async def ledger_append(self, record: dict) -> None:
        self._ledger.append(record)

    async def ledger_last(self) -> Optional[dict]:
        return self._ledger[-1] if self._ledger else None

    async def ledger_all(self) -> list[dict]:
        return list(self._ledger)

    async def ledger_mutate(self, seq: int, patch: dict) -> None:
        # DEMO helper: alter a stored record in place (used to show the chain breaking).
        for r in self._ledger:
            if r.get("seq") == seq:
                r.update(patch)
                return

    # --- blobs ---
    async def put_blob(self, data: bytes, meta: Optional[dict] = None) -> tuple[str, str]:
        digest = _sha256_bytes(data)
        self._blobs[digest] = data
        return f"mem://{digest}", digest

    async def get_blob(self, ref: str) -> Optional[bytes]:
        key = ref.split("://", 1)[-1]
        return self._blobs.get(key)


class MongoStore:
    """MongoDB / GridFS backend. Imported lazily so `motor` is optional."""

    backend = "mongo"

    def __init__(self, uri: str, db_name: str) -> None:
        from motor.motor_asyncio import AsyncIOMotorClient, AsyncIOMotorGridFSBucket

        # Generous timeouts: Render's free tier (0.1 CPU, cold container) + Atlas TLS/SRV
        # handshake can take several seconds — a short timeout caused a silent memory fallback.
        self._client = AsyncIOMotorClient(uri, serverSelectionTimeoutMS=20000,
                                          connectTimeoutMS=20000, socketTimeoutMS=20000)
        self._db = self._client[db_name]
        self._sessions = self._db["sessions"]
        self._ledger = self._db["ledger"]
        self._watchlist_c = self._db["watchlist"]
        self._gallery_c = self._db["gallery"]
        self._fs = AsyncIOMotorGridFSBucket(self._db)

    async def ping(self) -> bool:
        await self._client.admin.command("ping")
        return True

    async def save_session(self, ev_dict: dict) -> None:
        await self._sessions.replace_one({"session_id": ev_dict["session_id"]}, ev_dict, upsert=True)

    async def get_session(self, sid: str) -> Optional[dict]:
        return await self._sessions.find_one({"session_id": sid}, {"_id": 0})

    async def list_sessions(self, limit: int = 50) -> list[dict]:
        cur = self._sessions.find({}, {"_id": 0}).sort("created_at", -1).limit(limit)
        return [d async for d in cur]

    async def ledger_append(self, record: dict) -> None:
        await self._ledger.insert_one(dict(record))

    async def ledger_last(self) -> Optional[dict]:
        return await self._ledger.find_one({}, {"_id": 0}, sort=[("seq", -1)])

    async def ledger_all(self) -> list[dict]:
        cur = self._ledger.find({}, {"_id": 0}).sort("seq", 1)
        return [d async for d in cur]

    async def ledger_mutate(self, seq: int, patch: dict) -> None:
        await self._ledger.update_one({"seq": seq}, {"$set": patch})

    async def watchlist_add(self, entry: dict) -> None:
        await self._watchlist_c.insert_one(dict(entry))

    async def watchlist_all(self) -> list[dict]:
        return [d async for d in self._watchlist_c.find({}, {"_id": 0})]

    async def watchlist_check(self, value: str) -> Optional[dict]:
        v = (value or "").upper().replace("<", "")
        async for e in self._watchlist_c.find({}, {"_id": 0}):
            if e.get("value", "").upper().replace("<", "") == v:
                return e
        return None

    async def gallery_add(self, entry: dict) -> None:
        await self._gallery_c.insert_one(dict(entry))

    async def gallery_all(self) -> list[dict]:
        return [d async for d in self._gallery_c.find({}, {"_id": 0})]

    async def put_blob(self, data: bytes, meta: Optional[dict] = None) -> tuple[str, str]:
        digest = _sha256_bytes(data)
        gid = await self._fs.upload_from_stream(digest, data, metadata=meta or {})
        return f"gridfs://{gid}", digest

    async def get_blob(self, ref: str) -> Optional[bytes]:
        from bson import ObjectId

        gid = ref.split("://", 1)[-1]
        stream = await self._fs.open_download_stream(ObjectId(gid))
        return await stream.read()


async def get_store():
    """Return the configured store, falling back to memory if mongo is unreachable."""
    if settings.STORAGE_BACKEND == "mongo" and settings.MONGO_URI:
        try:
            store = MongoStore(settings.MONGO_URI, settings.MONGO_DB)
            await store.ping()
            return store
        except Exception as exc:  # pragma: no cover - depends on external mongo
            print(f"[storage] MongoDB unreachable ({exc}); falling back to in-memory store.")
    return MemoryStore()
