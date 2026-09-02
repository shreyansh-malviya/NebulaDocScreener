"""Database checks — watchlist + multiple-identity detection.

Runs after the modules, before fusion. Two accountability databases:
  * Watchlist: mock lost/stolen + lookout list (real LOC/Interpol SLTD are BoI/CBI-side and
    restricted — we mock them and flag the integration point).
  * Identity gallery: face templates + document numbers of prior screenings, to catch
    "same document, different face" (photo swap) and "same face, different document"
    (multiple identities — a named PS challenge). DPDP note: store TEMPLATES not images,
    with a short TTL in production.
"""
from __future__ import annotations

from .face import cosine
from ..models import Evidence, RecordsCheck


async def check_records(ev: Evidence, store, match_hi: float = 0.5, match_lo: float = 0.3) -> RecordsCheck:
    rc = RecordsCheck(checked=True)

    doc_number = None
    if ev.m1_ocr.mrz.present:
        doc_number = ev.m1_ocr.mrz.fields.get("doc_number")

    # --- watchlist (by document number) ---
    if doc_number:
        hit = await store.watchlist_check(doc_number)
        if hit:
            rc.watchlist_hit = True
            rc.watchlist_reason = f"Document {doc_number} is on the watchlist: {hit.get('reason', 'flagged')}"

    # --- identity gallery (multiple-identity / photo-swap) ---
    emb = ev.m4_face.doc_embedding
    if emb or doc_number:
        alerts: set[str] = set()
        for g in await store.gallery_all():
            g_doc, g_emb = g.get("doc_number"), g.get("embedding")
            if emb and g_emb:
                sim = cosine(emb, g_emb)
                if g_doc and doc_number and g_doc == doc_number and sim < match_lo:
                    alerts.add(f"Document {doc_number} was previously seen with a DIFFERENT face "
                               f"(similarity {sim:.2f}) — possible photo substitution / shared document.")
                elif g_doc and doc_number and g_doc != doc_number and sim > match_hi:
                    alerts.add(f"This face was previously seen under a DIFFERENT document number "
                               f"({g_doc}, similarity {sim:.2f}) — possible multiple identities.")
        rc.identity_alerts = sorted(alerts)
        # enrol the current screening into the gallery
        await store.gallery_add({"doc_number": doc_number, "embedding": emb,
                                 "session_id": ev.session_id, "ts": ev.created_at.isoformat()})

    return rc
