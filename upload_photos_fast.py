import json
import mimetypes
import os
import sqlite3
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow


# ============================================================
# AYARLAR
# ============================================================

SCOPES = ["https://www.googleapis.com/auth/photoslibrary.appendonly"]

BASE_DIR = Path(__file__).resolve().parent
TRANSFER_DIR = BASE_DIR / "transfer"
CREDENTIALS_FILE = BASE_DIR / "credentials.json"
TOKEN_FILE = BASE_DIR / "token_local.json"
DATABASE_FILE = BASE_DIR / "upload_state.db"
ERROR_LOG_FILE = BASE_DIR / "upload_errors.log"

# 50 Mbit bağlantı için 4 iyi bir başlangıçtır.
# Çok sayıda küçük dosyada 6 deneyebilirsiniz.
UPLOAD_WORKERS = 4

# Google mediaItems:batchCreate en fazla 50 öğe kabul eder.
BATCH_SIZE = 50

MAX_RETRIES = 7
CONNECT_TIMEOUT = 30
UPLOAD_TIMEOUT = 3600
CREATE_TIMEOUT = 300

# Geçici upload tokenlarını güvenli tarafta kalmak için 20 saat sonra yeniler.
UPLOAD_TOKEN_MAX_AGE_SECONDS = 20 * 60 * 60

SUPPORTED_EXTENSIONS = {
    # Fotoğraflar
    ".avif", ".bmp", ".gif", ".heic", ".heif", ".ico",
    ".jpg", ".jpeg", ".png", ".tif", ".tiff", ".webp",
    ".dng", ".raw", ".arw", ".cr2", ".cr3", ".nef", ".orf", ".rw2",

    # Videolar
    ".3gp", ".3g2", ".avi", ".m4v", ".mkv", ".mov",
    ".mp4", ".mpeg", ".mpg", ".mts", ".m2ts", ".ts",
    ".webm", ".wmv", ".vob",
}

CUSTOM_MIME_TYPES = {
    ".avif": "image/avif",
    ".heic": "image/heic",
    ".heif": "image/heif",
    ".dng": "image/x-adobe-dng",
    ".raw": "image/x-raw",
    ".arw": "image/x-sony-arw",
    ".cr2": "image/x-canon-cr2",
    ".cr3": "image/x-canon-cr3",
    ".nef": "image/x-nikon-nef",
    ".orf": "image/x-olympus-orf",
    ".rw2": "image/x-panasonic-rw2",
    ".mkv": "video/x-matroska",
    ".mts": "video/mp2t",
    ".m2ts": "video/mp2t",
    ".ts": "video/mp2t",
    ".3g2": "video/3gpp2",
    ".wmv": "video/x-ms-wmv",
    ".vob": "video/mpeg",
}

PRINT_LOCK = threading.Lock()
AUTH_LOCK = threading.Lock()


@dataclass(frozen=True)
class MediaFile:
    path: Path
    relative_path: str
    size: int
    mtime_ns: int


# ============================================================
# GENEL YARDIMCILAR
# ============================================================

def log(message: str, level: str = "INFO") -> None:
    stamp = time.strftime("%Y-%m-%d %H:%M:%S")
    with PRINT_LOCK:
        print(f"[{stamp}] [{level}] {message}", flush=True)


def human_bytes(value: float) -> str:
    units = ["B", "KB", "MB", "GB", "TB"]
    size = float(value)
    for unit in units:
        if size < 1024 or unit == units[-1]:
            return f"{size:.2f} {unit}"
        size /= 1024
    return f"{size:.2f} TB"


def format_duration(seconds: float) -> str:
    if seconds < 0 or seconds == float("inf"):
        return "--:--:--"
    seconds = int(seconds)
    hours, remainder = divmod(seconds, 3600)
    minutes, seconds = divmod(remainder, 60)
    return f"{hours:02d}:{minutes:02d}:{seconds:02d}"


def write_error_log(relative_path: str, error: str) -> None:
    record = {
        "time": time.strftime("%Y-%m-%d %H:%M:%S"),
        "file": relative_path,
        "error": error,
    }
    with ERROR_LOG_FILE.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(record, ensure_ascii=False) + "\n")


def get_mime_type(path: Path) -> str:
    guessed, _ = mimetypes.guess_type(str(path))
    return guessed or CUSTOM_MIME_TYPES.get(
        path.suffix.lower(), "application/octet-stream"
    )


# ============================================================
# SQLITE DURUM VERİTABANI
# ============================================================

@contextmanager
def connect_db():
    connection = sqlite3.connect(
        DATABASE_FILE,
        timeout=60,
        check_same_thread=False,
    )
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA journal_mode=WAL")
    connection.execute("PRAGMA synchronous=FULL")
    connection.execute("PRAGMA busy_timeout=60000")
    try:
        with connection:
            yield connection
    finally:
        connection.close()


def init_db() -> None:
    with connect_db() as db:
        db.execute(
            """
            CREATE TABLE IF NOT EXISTS files (
                relative_path TEXT PRIMARY KEY,
                absolute_path TEXT NOT NULL,
                size_bytes INTEGER NOT NULL,
                mtime_ns INTEGER NOT NULL,
                status TEXT NOT NULL DEFAULT 'pending',
                upload_token TEXT,
                token_created_at REAL,
                google_media_id TEXT,
                google_product_url TEXT,
                attempts INTEGER NOT NULL DEFAULT 0,
                last_error TEXT,
                updated_at REAL NOT NULL
            )
            """
        )
        db.execute(
            "CREATE INDEX IF NOT EXISTS idx_files_status ON files(status)"
        )


def register_files(media_files: list[MediaFile]) -> None:
    now = time.time()
    with connect_db() as db:
        for item in media_files:
            current = db.execute(
                """
                SELECT size_bytes, mtime_ns, status
                FROM files
                WHERE relative_path = ?
                """,
                (item.relative_path,),
            ).fetchone()

            if current is None:
                db.execute(
                    """
                    INSERT INTO files (
                        relative_path, absolute_path, size_bytes, mtime_ns,
                        status, updated_at
                    )
                    VALUES (?, ?, ?, ?, 'pending', ?)
                    """,
                    (
                        item.relative_path,
                        str(item.path),
                        item.size,
                        item.mtime_ns,
                        now,
                    ),
                )
            elif (
                current["size_bytes"] != item.size
                or current["mtime_ns"] != item.mtime_ns
            ):
                # Yerel dosya değiştiyse yeni dosya gibi tekrar yüklenir.
                db.execute(
                    """
                    UPDATE files
                    SET absolute_path = ?,
                        size_bytes = ?,
                        mtime_ns = ?,
                        status = 'pending',
                        upload_token = NULL,
                        token_created_at = NULL,
                        google_media_id = NULL,
                        google_product_url = NULL,
                        attempts = 0,
                        last_error = NULL,
                        updated_at = ?
                    WHERE relative_path = ?
                    """,
                    (
                        str(item.path),
                        item.size,
                        item.mtime_ns,
                        now,
                        item.relative_path,
                    ),
                )
            else:
                db.execute(
                    """
                    UPDATE files
                    SET absolute_path = ?, updated_at = ?
                    WHERE relative_path = ?
                    """,
                    (str(item.path), now, item.relative_path),
                )


def recover_interrupted_rows() -> None:
    now = time.time()
    with connect_db() as db:
        # Program yükleme sırasında kapandıysa bu satırlar yeniden denenir.
        db.execute(
            """
            UPDATE files
            SET status = 'pending', updated_at = ?
            WHERE status = 'uploading'
            """,
            (now,),
        )

        # Süresi geçmiş geçici tokenlar yeniden yüklenir.
        db.execute(
            """
            UPDATE files
            SET status = 'pending',
                upload_token = NULL,
                token_created_at = NULL,
                updated_at = ?
            WHERE status = 'uploaded_bytes'
              AND (
                    token_created_at IS NULL
                    OR ? - token_created_at > ?
                  )
            """,
            (now, now, UPLOAD_TOKEN_MAX_AGE_SECONDS),
        )


def fetch_work_rows() -> list[sqlite3.Row]:
    with connect_db() as db:
        return db.execute(
            """
            SELECT *
            FROM files
            WHERE status IN ('pending', 'failed', 'uploaded_bytes')
            ORDER BY relative_path
            """
        ).fetchall()


def set_uploading(relative_path: str) -> None:
    with connect_db() as db:
        db.execute(
            """
            UPDATE files
            SET status = 'uploading',
                attempts = attempts + 1,
                last_error = NULL,
                updated_at = ?
            WHERE relative_path = ?
            """,
            (time.time(), relative_path),
        )


def save_upload_token(relative_path: str, upload_token: str) -> None:
    with connect_db() as db:
        db.execute(
            """
            UPDATE files
            SET status = 'uploaded_bytes',
                upload_token = ?,
                token_created_at = ?,
                last_error = NULL,
                updated_at = ?
            WHERE relative_path = ?
            """,
            (upload_token, time.time(), time.time(), relative_path),
        )


def mark_created(
    relative_path: str,
    media_id: Optional[str],
    product_url: Optional[str],
) -> None:
    with connect_db() as db:
        db.execute(
            """
            UPDATE files
            SET status = 'created',
                upload_token = NULL,
                token_created_at = NULL,
                google_media_id = ?,
                google_product_url = ?,
                last_error = NULL,
                updated_at = ?
            WHERE relative_path = ?
            """,
            (media_id, product_url, time.time(), relative_path),
        )


def mark_failed(relative_path: str, error: str, keep_token: bool = False) -> None:
    with connect_db() as db:
        if keep_token:
            db.execute(
                """
                UPDATE files
                SET status = 'uploaded_bytes',
                    last_error = ?,
                    updated_at = ?
                WHERE relative_path = ?
                """,
                (error[:4000], time.time(), relative_path),
            )
        else:
            db.execute(
                """
                UPDATE files
                SET status = 'failed',
                    upload_token = NULL,
                    token_created_at = NULL,
                    last_error = ?,
                    updated_at = ?
                WHERE relative_path = ?
                """,
                (error[:4000], time.time(), relative_path),
            )


def get_summary() -> dict[str, int]:
    with connect_db() as db:
        rows = db.execute(
            """
            SELECT status, COUNT(*) AS count
            FROM files
            GROUP BY status
            """
        ).fetchall()
    return {row["status"]: row["count"] for row in rows}


# ============================================================
# AUTHENTICATION
# ============================================================

def authenticate() -> Credentials:
    credentials: Optional[Credentials] = None

    if TOKEN_FILE.exists():
        try:
            credentials = Credentials.from_authorized_user_file(
                str(TOKEN_FILE), SCOPES
            )
        except Exception as error:
            log(f"token_local.json okunamadı: {error}", "WARNING")

    if credentials and credentials.expired and credentials.refresh_token:
        try:
            credentials.refresh(Request())
        except Exception as error:
            log(f"Token yenilenemedi: {error}", "WARNING")
            credentials = None

    if not credentials or not credentials.valid:
        if not CREDENTIALS_FILE.exists():
            raise FileNotFoundError(
                f"credentials.json bulunamadı: {CREDENTIALS_FILE}"
            )

        flow = InstalledAppFlow.from_client_secrets_file(
            str(CREDENTIALS_FILE), SCOPES
        )
        credentials = flow.run_local_server(
            port=0,
            access_type="offline",
            prompt="consent",
        )

    TOKEN_FILE.write_text(credentials.to_json(), encoding="utf-8")
    return credentials


def ensure_valid_token(credentials: Credentials) -> str:
    with AUTH_LOCK:
        if credentials.expired and credentials.refresh_token:
            credentials.refresh(Request())
            TOKEN_FILE.write_text(credentials.to_json(), encoding="utf-8")

        if not credentials.valid or not credentials.token:
            raise RuntimeError("Google erişim tokenı geçerli değil.")

        return credentials.token


# ============================================================
# HTTP
# ============================================================

def create_session() -> requests.Session:
    retries = Retry(
        total=MAX_RETRIES,
        connect=MAX_RETRIES,
        read=MAX_RETRIES,
        status=MAX_RETRIES,
        backoff_factor=1.5,
        status_forcelist=[429, 500, 502, 503, 504],
        allowed_methods=["POST"],
        respect_retry_after_header=True,
        raise_on_status=False,
    )
    adapter = HTTPAdapter(
        max_retries=retries,
        pool_connections=UPLOAD_WORKERS + 2,
        pool_maxsize=UPLOAD_WORKERS + 2,
    )
    session = requests.Session()
    session.mount("https://", adapter)
    return session


# ============================================================
# DOSYA TARAMA
# ============================================================

def scan_media_files() -> list[MediaFile]:
    TRANSFER_DIR.mkdir(parents=True, exist_ok=True)
    result: list[MediaFile] = []

    for path in TRANSFER_DIR.rglob("*"):
        if not path.is_file():
            continue
        if path.suffix.lower() not in SUPPORTED_EXTENSIONS:
            continue

        stat = path.stat()
        result.append(
            MediaFile(
                path=path,
                relative_path=str(path.relative_to(TRANSFER_DIR)),
                size=stat.st_size,
                mtime_ns=stat.st_mtime_ns,
            )
        )

    result.sort(key=lambda item: item.relative_path.lower())
    return result


# ============================================================
# GOOGLE PHOTOS YÜKLEME
# ============================================================

def upload_bytes_worker(
    row: sqlite3.Row,
    credentials: Credentials,
    session: requests.Session,
) -> dict:
    relative_path = row["relative_path"]
    path = Path(row["absolute_path"])

    # Daha önce byte upload tamamlandıysa mevcut tokenı koru.
    if row["status"] == "uploaded_bytes" and row["upload_token"]:
        return {
            "relative_path": relative_path,
            "filename": path.name,
            "size_bytes": row["size_bytes"],
            "upload_token": row["upload_token"],
            "reused_token": True,
        }

    if not path.exists():
        raise FileNotFoundError(f"Yerel dosya bulunamadı: {path}")

    current_stat = path.stat()
    if (
        current_stat.st_size != row["size_bytes"]
        or current_stat.st_mtime_ns != row["mtime_ns"]
    ):
        raise RuntimeError(
            "Dosya taramadan sonra değişmiş. Programı yeniden çalıştırın."
        )

    set_uploading(relative_path)

    token = ensure_valid_token(credentials)
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/octet-stream",
        "X-Goog-Upload-Content-Type": get_mime_type(path),
        "X-Goog-Upload-Protocol": "raw",
    }

    with path.open("rb") as file_handle:
        response = session.post(
            "https://photoslibrary.googleapis.com/v1/uploads",
            data=file_handle,
            headers=headers,
            timeout=(CONNECT_TIMEOUT, UPLOAD_TIMEOUT),
        )

    if response.status_code != 200:
        raise RuntimeError(
            f"Byte upload HTTP {response.status_code}: {response.text[:1000]}"
        )

    upload_token = response.text.strip()
    if not upload_token:
        raise RuntimeError("Google boş uploadToken döndürdü.")

    # Token diske yazılmadan görev başarılı sayılmaz.
    save_upload_token(relative_path, upload_token)

    return {
        "relative_path": relative_path,
        "filename": path.name,
        "size_bytes": row["size_bytes"],
        "upload_token": upload_token,
        "reused_token": False,
    }


def create_media_batch(
    items: list[dict],
    credentials: Credentials,
    session: requests.Session,
) -> tuple[int, int]:
    if not items:
        return 0, 0

    token = ensure_valid_token(credentials)
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
    }
    body = {
        "newMediaItems": [
            {
                "simpleMediaItem": {
                    "uploadToken": item["upload_token"],
                    "fileName": item["filename"][:255],
                }
            }
            for item in items
        ]
    }

    response = session.post(
        "https://photoslibrary.googleapis.com/v1/mediaItems:batchCreate",
        json=body,
        headers=headers,
        timeout=(CONNECT_TIMEOUT, CREATE_TIMEOUT),
    )

    if response.status_code != 200:
        error = (
            f"batchCreate HTTP {response.status_code}: "
            f"{response.text[:2000]}"
        )
        for item in items:
            mark_failed(item["relative_path"], error, keep_token=True)
            write_error_log(item["relative_path"], error)
        return 0, len(items)

    payload = response.json()
    results = payload.get("newMediaItemResults", [])

    successful = 0
    failed = 0

    for index, item in enumerate(items):
        if index >= len(results):
            error = "batchCreate yanıtında bu dosya için sonuç bulunamadı."
            mark_failed(item["relative_path"], error, keep_token=True)
            write_error_log(item["relative_path"], error)
            failed += 1
            continue

        result = results[index]
        status = result.get("status", {})
        status_code = status.get("code", 0)

        if status_code == 0 and result.get("mediaItem"):
            media_item = result["mediaItem"]
            mark_created(
                item["relative_path"],
                media_item.get("id"),
                media_item.get("productUrl"),
            )
            successful += 1
        else:
            error = (
                f"Google Photos kod={status_code}, "
                f"mesaj={status.get('message', 'Bilinmeyen hata')}"
            )
            # Token bazlı medya oluşturma hatasında aynı token yeniden denenebilir.
            mark_failed(item["relative_path"], error, keep_token=True)
            write_error_log(item["relative_path"], error)
            failed += 1

    return successful, failed


# ============================================================
# ANA PROGRAM
# ============================================================

def main() -> None:
    log("=" * 76)
    log("HIZLI GOOGLE FOTOĞRAFLAR AKTARIMI")
    log(f"Paralel byte upload işçisi: {UPLOAD_WORKERS}")
    log("Yerel dosyalar ASLA silinmez, taşınmaz veya değiştirilmez.")
    log("=" * 76)

    init_db()

    media_files = scan_media_files()
    if not media_files:
        log(f"Medya bulunamadı: {TRANSFER_DIR}", "WARNING")
        return

    register_files(media_files)
    recover_interrupted_rows()

    credentials = authenticate()
    upload_session = create_session()
    create_session_http = create_session()

    work_rows = fetch_work_rows()
    already_created = get_summary().get("created", 0)

    if not work_rows:
        log(f"Tüm dosyalar daha önce tamamlanmış. Toplam: {already_created}")
        return

    total_files = len(media_files)
    pending_files = len(work_rows)
    pending_bytes = sum(row["size_bytes"] for row in work_rows)
    completed_bytes = 0
    start_time = time.time()

    log(
        f"Bulunan: {total_files} | Tamamlanmış: {already_created} | "
        f"İşlenecek: {pending_files} ({human_bytes(pending_bytes)})"
    )

    upload_tokens: list[dict] = []
    upload_failures = 0
    created_success = 0
    create_failures = 0

    try:
        with ThreadPoolExecutor(max_workers=UPLOAD_WORKERS) as executor:
            future_map = {
                executor.submit(
                    upload_bytes_worker,
                    row,
                    credentials,
                    upload_session,
                ): row
                for row in work_rows
            }

            for completed_count, future in enumerate(
                as_completed(future_map), start=1
            ):
                row = future_map[future]
                relative_path = row["relative_path"]

                try:
                    item = future.result()
                    upload_tokens.append(item)
                    completed_bytes += item["size_bytes"]

                    elapsed = max(time.time() - start_time, 0.001)
                    speed = completed_bytes / elapsed
                    remaining = max(pending_bytes - completed_bytes, 0)
                    eta = remaining / speed if speed > 0 else float("inf")

                    log(
                        f"[BYTE {completed_count}/{pending_files}] "
                        f"{relative_path} | "
                        f"{human_bytes(speed)}/sn | "
                        f"ETA {format_duration(eta)}"
                    )

                except Exception as error:
                    upload_failures += 1
                    error_text = str(error)
                    mark_failed(relative_path, error_text, keep_token=False)
                    write_error_log(relative_path, error_text)
                    log(f"HATA: {relative_path} -> {error_text}", "ERROR")

                # Google önerisine uygun olarak batchCreate seri çalışır.
                # Elimizde 50 token biriktiğinde tek API isteğiyle oluşturur.
                while len(upload_tokens) >= BATCH_SIZE:
                    batch = upload_tokens[:BATCH_SIZE]
                    del upload_tokens[:BATCH_SIZE]

                    success, failed = create_media_batch(
                        batch, credentials, create_session_http
                    )
                    created_success += success
                    create_failures += failed
                    log(
                        f"[CREATE] Başarılı: {success}, Hatalı: {failed}, "
                        f"Paket: {len(batch)}"
                    )

        # Kalan tokenları son paket olarak gönder.
        if upload_tokens:
            success, failed = create_media_batch(
                upload_tokens, credentials, create_session_http
            )
            created_success += success
            create_failures += failed
            log(
                f"[CREATE] Başarılı: {success}, Hatalı: {failed}, "
                f"Paket: {len(upload_tokens)}"
            )

    except KeyboardInterrupt:
        log(
            "Kullanıcı işlemi durdurdu. Veritabanındaki durum korunmuştur; "
            "yeniden çalıştırınca devam eder.",
            "WARNING",
        )

    finally:
        upload_session.close()
        create_session_http.close()

    elapsed = max(time.time() - start_time, 0.001)
    summary = get_summary()

    log("=" * 76)
    log("SONUÇ")
    log(f"Bu çalıştırmada oluşturulan : {created_success}")
    log(f"Byte upload hatası          : {upload_failures}")
    log(f"Media create hatası         : {create_failures}")
    log(f"Toplam tamamlanan           : {summary.get('created', 0)}")
    log(f"Bekleyen                    : {summary.get('pending', 0)}")
    log(f"Yeniden denenecek           : {summary.get('failed', 0)}")
    log(f"Tokenı hazır                : {summary.get('uploaded_bytes', 0)}")
    log(f"Toplam süre                 : {format_duration(elapsed)}")
    log(f"Ortalama aktarım            : {human_bytes(completed_bytes / elapsed)}/sn")
    log("Yerel fotoğraf ve videolara dokunulmadı.")
    log("=" * 76)


if __name__ == "__main__":
    main()
