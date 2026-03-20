import hashlib
import hmac
import json
from datetime import datetime, timezone

import aiosqlite

from config import REPORT_SIGNING_SECRET
from services.audit import fetch_audit_trail
from services.content import get_moderation_record
from services.moderation import to_moderation_state
from services.verdicts import normalize_verdict


def _canonical_payload(payload: dict) -> bytes:
    return json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")


def sign_report_payload(payload: dict) -> dict:
    canonical = _canonical_payload(payload)
    digest = hashlib.sha256(canonical).hexdigest()
    signature = hmac.new(
        REPORT_SIGNING_SECRET.encode("utf-8"),
        canonical,
        hashlib.sha256,
    ).hexdigest()
    return {
        "payload_hash": digest,
        "signature": signature,
        "signature_algorithm": "HMAC-SHA256",
    }


async def build_media_report(
    db: aiosqlite.Connection,
    analysis: dict,
    current_user: dict,
) -> dict:
    analysis_id = analysis["id"]
    cursor = await db.execute(
        "SELECT * FROM evidence_items WHERE analysis_id = ?",
        (analysis_id,),
    )
    evidence = [dict(row) for row in await cursor.fetchall()]
    moderation = await get_moderation_record(db, "media", analysis_id)
    audit_trail = await fetch_audit_trail(db, "media", analysis_id, limit=30)

    report_core = {
        "report_id": f"DS-{analysis_id:06d}",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "platform": "DeepShield AI",
        "version": "1.0.0",
        "analyst": current_user["username"],
        "media_info": {
            "original_filename": analysis["original_filename"],
            "media_type": analysis["media_type"],
            "file_size_bytes": analysis["file_size"],
            "file_size_mb": round(analysis["file_size"] / (1024 * 1024), 2),
            "uploaded_at": str(analysis["created_at"]),
        },
        "analysis_results": {
            "overall_score": analysis["overall_score"],
            "verdict": analysis["verdict"],
            "raw_verdict": analysis.get("raw_verdict"),
            "effective_verdict": normalize_verdict(
                moderation.get("manual_verdict") if moderation and moderation.get("manual_verdict") else analysis["verdict"]
            ),
            "confidence_percent": round((analysis["overall_score"] or 0) * 100, 1),
            "processing_time_seconds": analysis["processing_time"],
            "model_version": analysis["model_version"],
            "completed_at": str(analysis["completed_at"]),
        },
        "modality_scores": {
            "image": analysis["image_score"],
            "video": analysis["video_score"],
            "audio": analysis["audio_score"],
        },
        "forensic_evidence": [
            {
                "type": item["evidence_type"],
                "title": item["title"],
                "description": item["description"],
                "severity": item["severity"],
                "file": item["file_path"],
            }
            for item in evidence
        ],
        "moderation": to_moderation_state(moderation),
        "audit_trail": audit_trail,
        "integrity": {
            "analysis_id": analysis_id,
            "timestamp": str(analysis["created_at"]),
            "model_version": analysis["model_version"],
            "verification_hint": "Validate the payload hash and signature on export.",
        },
    }

    signatures = sign_report_payload(report_core)
    report_core["integrity"].update(signatures)
    return report_core


def _escape_pdf_text(value: str) -> str:
    return value.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")


def _split_lines(lines: list[str], lines_per_page: int = 40) -> list[list[str]]:
    pages = []
    current = []
    for line in lines:
        if len(line) <= 96:
            current.append(line)
        else:
            remaining = line
            while len(remaining) > 96:
                current.append(remaining[:96])
                remaining = remaining[96:]
        if len(current) >= lines_per_page:
            pages.append(current)
            current = []
    if current:
        pages.append(current)
    return pages or [["DeepShield AI Report"]]


def _build_pdf(text_pages: list[list[str]]) -> bytes:
    objects: list[bytes] = []

    def add_object(content: bytes) -> int:
        objects.append(content)
        return len(objects)

    font_id = add_object(b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>")
    content_ids = []
    page_ids = []

    for page_lines in text_pages:
        stream_lines = ["BT", "/F1 10 Tf", "50 780 Td", "14 TL"]
        for index, line in enumerate(page_lines):
            escaped = _escape_pdf_text(line)
            if index == 0:
                stream_lines.append(f"({escaped}) Tj")
            else:
                stream_lines.append(f"T* ({escaped}) Tj")
        stream_lines.append("ET")
        stream = "\n".join(stream_lines).encode("latin-1", errors="replace")
        content_id = add_object(
            f"<< /Length {len(stream)} >>\nstream\n".encode("latin-1") + stream + b"\nendstream"
        )
        content_ids.append(content_id)
        page_id = add_object(
            f"<< /Type /Page /Parent 0 0 R /MediaBox [0 0 612 792] "
            f"/Resources << /Font << /F1 {font_id} 0 R >> >> /Contents {content_id} 0 R >>".encode("latin-1")
        )
        page_ids.append(page_id)

    kids = " ".join(f"{page_id} 0 R" for page_id in page_ids)
    pages_id = add_object(
        f"<< /Type /Pages /Kids [{kids}] /Count {len(page_ids)} >>".encode("latin-1")
    )

    for page_id in page_ids:
        objects[page_id - 1] = objects[page_id - 1].replace(b"/Parent 0 0 R", f"/Parent {pages_id} 0 R".encode("latin-1"))

    catalog_id = add_object(f"<< /Type /Catalog /Pages {pages_id} 0 R >>".encode("latin-1"))

    buffer = bytearray(b"%PDF-1.4\n%\xe2\xe3\xcf\xd3\n")
    xref = [0]
    for index, content in enumerate(objects, start=1):
        xref.append(len(buffer))
        buffer.extend(f"{index} 0 obj\n".encode("latin-1"))
        buffer.extend(content)
        buffer.extend(b"\nendobj\n")

    xref_start = len(buffer)
    buffer.extend(f"xref\n0 {len(objects) + 1}\n".encode("latin-1"))
    buffer.extend(b"0000000000 65535 f \n")
    for offset in xref[1:]:
        buffer.extend(f"{offset:010d} 00000 n \n".encode("latin-1"))
    buffer.extend(
        (
            f"trailer\n<< /Size {len(objects) + 1} /Root {catalog_id} 0 R >>\n"
            f"startxref\n{xref_start}\n%%EOF"
        ).encode("latin-1")
    )
    return bytes(buffer)


def render_report_pdf(report: dict) -> bytes:
    lines = [
        "DeepShield AI Forensic Report",
        f"Report ID: {report['report_id']}",
        f"Generated: {report['generated_at']}",
        "",
        "Media",
        f"Filename: {report['media_info']['original_filename']}",
        f"Type: {report['media_info']['media_type']}",
        f"Size MB: {report['media_info']['file_size_mb']}",
        "",
        "Results",
        f"Verdict: {report['analysis_results']['effective_verdict'] or report['analysis_results']['verdict']}",
        f"Detector verdict: {report['analysis_results'].get('raw_verdict') or report['analysis_results']['verdict']}",
        f"Score: {report['analysis_results']['overall_score']}",
        f"Confidence %: {report['analysis_results']['confidence_percent']}",
        f"Processing seconds: {report['analysis_results']['processing_time_seconds']}",
        "",
        "Moderation",
        f"Flagged: {report['moderation']['is_flagged']}",
        f"Quarantined: {report['moderation']['is_quarantined']}",
        f"Review status: {report['moderation']['review_status']}",
        "",
        "Integrity",
        f"Payload hash: {report['integrity']['payload_hash']}",
        f"Signature: {report['integrity']['signature']}",
        "",
        "Evidence",
    ]

    for item in report.get("forensic_evidence", []):
        lines.append(f"- {item['title']} [{item['severity']}]")
        if item.get("description"):
            lines.append(f"  {item['description']}")

    lines.extend(["", "Audit Trail"])
    for event in report.get("audit_trail", [])[:20]:
        actor = event.get("actor_username") or "system"
        lines.append(f"- {event['created_at']} {actor}: {event['action']}")

    return _build_pdf(_split_lines(lines))
