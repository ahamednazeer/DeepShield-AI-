import json

import aiosqlite

from config import DATABASE_PATH
from services.verdicts import normalize_verdict

DATABASE_URL = str(DATABASE_PATH)


async def get_db():
    """Get an async database connection."""
    db = await aiosqlite.connect(DATABASE_URL)
    db.row_factory = aiosqlite.Row
    try:
        yield db
    finally:
        await db.close()


async def _table_columns(db: aiosqlite.Connection, table: str) -> set[str]:
    cursor = await db.execute(f"PRAGMA table_info({table})")
    rows = await cursor.fetchall()
    return {row[1] for row in rows}


async def _ensure_column(db: aiosqlite.Connection, table: str, definition: str):
    column_name = definition.split()[0]
    columns = await _table_columns(db, table)
    if column_name not in columns:
        await db.execute(f"ALTER TABLE {table} ADD COLUMN {definition}")


async def _seed_admin_if_missing(db: aiosqlite.Connection):
    cursor = await db.execute("SELECT COUNT(*) FROM users WHERE role = 'admin'")
    admin_count = (await cursor.fetchone())[0]
    if admin_count:
        return

    cursor = await db.execute("SELECT id FROM users ORDER BY id ASC LIMIT 1")
    row = await cursor.fetchone()
    if row:
        await db.execute("UPDATE users SET role = 'admin' WHERE id = ?", (row[0],))


async def _seed_default_rules(db: aiosqlite.Connection):
    default_rules = [
        {
            "name": "Quarantine Manipulated Media",
            "description": "Block sharing and downloads for manipulated media and queue it for review.",
            "target_type": "media",
            "verdict_match": "MANIPULATED",
            "min_score": 0.65,
            "actions": [
                "flag",
                "quarantine",
                "block_share",
                "block_download",
                "notify_admin",
                "review_queue",
            ],
        },
        {
            "name": "Review Suspicious Media",
            "description": "Flag suspicious media for manual review.",
            "target_type": "media",
            "verdict_match": "SUSPICIOUS",
            "min_score": 0.35,
            "actions": ["flag", "review_queue", "notify_admin"],
        },
        {
            "name": "Block Manipulated Text",
            "description": "Quarantine manipulated text analyses and prevent distribution.",
            "target_type": "text",
            "verdict_match": "MANIPULATED",
            "min_score": 0.6,
            "actions": [
                "flag",
                "quarantine",
                "block_share",
                "block_download",
                "notify_admin",
                "review_queue",
            ],
        },
        {
            "name": "Review Suspicious Text",
            "description": "Send suspicious text analyses to the review queue.",
            "target_type": "text",
            "verdict_match": "SUSPICIOUS",
            "min_score": 0.45,
            "actions": ["flag", "review_queue", "notify_admin"],
        },
        {
            "name": "Block Unsafe Links",
            "description": "Quarantine malicious or phishing links and prevent sharing.",
            "target_type": "link",
            "verdict_match": "MANIPULATED",
            "min_score": 0.55,
            "actions": [
                "flag",
                "quarantine",
                "block_share",
                "notify_admin",
                "review_queue",
            ],
        },
        {
            "name": "Review Suspicious Links",
            "description": "Flag suspicious or spam-like links for manual review.",
            "target_type": "link",
            "verdict_match": "SUSPICIOUS",
            "min_score": 0.3,
            "actions": ["flag", "review_queue", "notify_admin"],
        },
    ]

    for rule in default_rules:
        cursor = await db.execute("SELECT id FROM moderation_rules WHERE name = ?", (rule["name"],))
        if await cursor.fetchone():
            continue
        await db.execute(
            """INSERT INTO moderation_rules
               (name, description, target_type, verdict_match, min_score, actions, enabled)
               VALUES (?, ?, ?, ?, ?, ?, 1)""",
            (
                rule["name"],
                rule["description"],
                rule["target_type"],
                rule["verdict_match"],
                rule["min_score"],
                json.dumps(rule["actions"]),
            ),
        )


async def init_db():
    """Initialize database tables and run lightweight migrations."""
    async with aiosqlite.connect(DATABASE_URL) as db:
        await db.executescript(
            """
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT UNIQUE NOT NULL,
                email TEXT UNIQUE NOT NULL,
                password_hash TEXT NOT NULL,
                role TEXT DEFAULT 'analyst',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );

            CREATE TABLE IF NOT EXISTS analyses (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                filename TEXT NOT NULL,
                original_filename TEXT NOT NULL,
                media_type TEXT NOT NULL,
                file_size INTEGER NOT NULL,
                status TEXT DEFAULT 'pending',
                overall_score REAL,
                verdict TEXT,
                raw_verdict TEXT,
                image_score REAL,
                video_score REAL,
                audio_score REAL,
                processing_time REAL,
                model_version TEXT DEFAULT '1.0.0',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                completed_at TIMESTAMP,
                FOREIGN KEY (user_id) REFERENCES users(id)
            );

            CREATE TABLE IF NOT EXISTS evidence_items (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                analysis_id INTEGER NOT NULL,
                evidence_type TEXT NOT NULL,
                title TEXT NOT NULL,
                description TEXT,
                severity TEXT DEFAULT 'info',
                data TEXT,
                file_path TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (analysis_id) REFERENCES analyses(id)
            );

            CREATE TABLE IF NOT EXISTS text_analyses (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                input_text TEXT NOT NULL,
                source_url TEXT,
                status TEXT DEFAULT 'pending',
                nlp_score REAL,
                fact_score REAL,
                credibility_score REAL,
                final_score REAL,
                verdict TEXT,
                raw_verdict TEXT,
                verdict_label TEXT,
                claims TEXT,
                evidence TEXT,
                explanation TEXT,
                semantic_results TEXT,
                processing_time REAL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                completed_at TIMESTAMP,
                FOREIGN KEY (user_id) REFERENCES users(id)
            );

            CREATE TABLE IF NOT EXISTS link_analyses (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                input_url TEXT NOT NULL,
                normalized_url TEXT,
                final_url TEXT,
                domain TEXT,
                status TEXT DEFAULT 'pending',
                risk_score REAL,
                verdict TEXT,
                raw_verdict TEXT,
                signals TEXT,
                provider_summary TEXT,
                redirect_chain TEXT,
                page_metadata TEXT,
                processing_time REAL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                completed_at TIMESTAMP,
                FOREIGN KEY (user_id) REFERENCES users(id)
            );

            CREATE TABLE IF NOT EXISTS moderation_rules (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                description TEXT,
                target_type TEXT DEFAULT 'all',
                verdict_match TEXT,
                min_score REAL,
                actions TEXT NOT NULL,
                enabled INTEGER DEFAULT 1,
                created_by INTEGER,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (created_by) REFERENCES users(id)
            );

            CREATE TABLE IF NOT EXISTS content_moderation (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                content_type TEXT NOT NULL,
                content_id INTEGER NOT NULL,
                owner_user_id INTEGER NOT NULL,
                effective_verdict TEXT,
                auto_actions TEXT,
                is_flagged INTEGER DEFAULT 0,
                is_quarantined INTEGER DEFAULT 0,
                share_blocked INTEGER DEFAULT 0,
                download_blocked INTEGER DEFAULT 0,
                review_status TEXT DEFAULT 'clear',
                manual_verdict TEXT,
                review_notes TEXT,
                reviewed_by INTEGER,
                reviewed_at TIMESTAMP,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(content_type, content_id),
                FOREIGN KEY (owner_user_id) REFERENCES users(id),
                FOREIGN KEY (reviewed_by) REFERENCES users(id)
            );

            CREATE TABLE IF NOT EXISTS notifications (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                title TEXT NOT NULL,
                message TEXT NOT NULL,
                severity TEXT DEFAULT 'info',
                kind TEXT DEFAULT 'system',
                target_type TEXT,
                target_id INTEGER,
                read_at TIMESTAMP,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (user_id) REFERENCES users(id)
            );

            CREATE TABLE IF NOT EXISTS audit_logs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                actor_user_id INTEGER,
                action TEXT NOT NULL,
                target_type TEXT NOT NULL,
                target_id INTEGER,
                details TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (actor_user_id) REFERENCES users(id)
            );

            CREATE TABLE IF NOT EXISTS shared_links (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                token TEXT UNIQUE NOT NULL,
                content_type TEXT NOT NULL,
                content_id INTEGER NOT NULL,
                created_by INTEGER NOT NULL,
                expires_at TIMESTAMP,
                revoked_at TIMESTAMP,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (created_by) REFERENCES users(id)
            );

            CREATE INDEX IF NOT EXISTS idx_analyses_user ON analyses(user_id);
            CREATE INDEX IF NOT EXISTS idx_analyses_status ON analyses(status);
            CREATE INDEX IF NOT EXISTS idx_evidence_analysis ON evidence_items(analysis_id);
            CREATE INDEX IF NOT EXISTS idx_text_analyses_user ON text_analyses(user_id);
            CREATE INDEX IF NOT EXISTS idx_text_analyses_status ON text_analyses(status);
            CREATE INDEX IF NOT EXISTS idx_text_analyses_verdict ON text_analyses(verdict);
            CREATE INDEX IF NOT EXISTS idx_link_analyses_user ON link_analyses(user_id);
            CREATE INDEX IF NOT EXISTS idx_link_analyses_status ON link_analyses(status);
            CREATE INDEX IF NOT EXISTS idx_link_analyses_verdict ON link_analyses(verdict);
            CREATE INDEX IF NOT EXISTS idx_content_moderation_target ON content_moderation(content_type, content_id);
            CREATE INDEX IF NOT EXISTS idx_content_moderation_owner ON content_moderation(owner_user_id);
            CREATE INDEX IF NOT EXISTS idx_notifications_user ON notifications(user_id, read_at);
            CREATE INDEX IF NOT EXISTS idx_audit_logs_target ON audit_logs(target_type, target_id);
            CREATE INDEX IF NOT EXISTS idx_shared_links_token ON shared_links(token);
            """
        )

        await _ensure_column(db, "users", "status TEXT DEFAULT 'active'")
        await _ensure_column(db, "users", "last_login_at TIMESTAMP")
        await _ensure_column(db, "analyses", "raw_verdict TEXT")
        await _ensure_column(db, "text_analyses", "raw_verdict TEXT")

        cursor = await db.execute("SELECT id, verdict, raw_verdict FROM analyses WHERE verdict IS NOT NULL")
        for analysis_id, verdict, raw_verdict in await cursor.fetchall():
            normalized = normalize_verdict(verdict)
            if normalized != verdict or raw_verdict is None:
                await db.execute(
                    "UPDATE analyses SET verdict = ?, raw_verdict = ? WHERE id = ?",
                    (normalized, raw_verdict or verdict, analysis_id),
                )

        cursor = await db.execute("SELECT id, verdict, raw_verdict FROM text_analyses WHERE verdict IS NOT NULL")
        for analysis_id, verdict, raw_verdict in await cursor.fetchall():
            normalized = normalize_verdict(verdict)
            if normalized != verdict or raw_verdict is None:
                await db.execute(
                    "UPDATE text_analyses SET verdict = ?, raw_verdict = ? WHERE id = ?",
                    (normalized, raw_verdict or verdict, analysis_id),
                )

        cursor = await db.execute("SELECT id, verdict, raw_verdict FROM link_analyses WHERE verdict IS NOT NULL")
        for analysis_id, verdict, raw_verdict in await cursor.fetchall():
            normalized = normalize_verdict(verdict)
            if normalized != verdict or raw_verdict is None:
                await db.execute(
                    "UPDATE link_analyses SET verdict = ?, raw_verdict = ? WHERE id = ?",
                    (normalized, raw_verdict or verdict, analysis_id),
                )

        cursor = await db.execute(
            "SELECT id, effective_verdict, manual_verdict FROM content_moderation WHERE effective_verdict IS NOT NULL OR manual_verdict IS NOT NULL"
        )
        for moderation_id, effective_verdict, manual_verdict in await cursor.fetchall():
            normalized_effective = normalize_verdict(effective_verdict)
            normalized_manual = normalize_verdict(manual_verdict)
            await db.execute(
                "UPDATE content_moderation SET effective_verdict = ?, manual_verdict = ? WHERE id = ?",
                (normalized_effective, normalized_manual, moderation_id),
            )

        cursor = await db.execute("SELECT id, verdict_match FROM moderation_rules WHERE verdict_match IS NOT NULL")
        for rule_id, verdict_match in await cursor.fetchall():
            normalized = normalize_verdict(verdict_match)
            if normalized != verdict_match:
                await db.execute(
                    "UPDATE moderation_rules SET verdict_match = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?",
                    (normalized, rule_id),
                )

        await _seed_admin_if_missing(db)
        await _seed_default_rules(db)
        await db.commit()
