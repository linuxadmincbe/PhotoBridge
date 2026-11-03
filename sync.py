import os
import io
import argparse
from pathlib import Path
import requests
from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseDownload


SCOPES = [
    'https://www.googleapis.com/auth/drive.readonly',
    'https://www.googleapis.com/auth/photoslibrary.appendonly'
]

BASE_DIR = Path(__file__).resolve().parent
FOLDER_ID = os.environ.get("DRIVE_FOLDER_ID", "")
LOG_FILE = BASE_DIR / "uploaded.log"
DOWNLOAD_DIR = BASE_DIR / "transfer"
TOKEN_FILE = BASE_DIR / "token.json"
CREDENTIALS_FILE = BASE_DIR / "credentials.json"


def log(msg):
    print(f"[INFO] {msg}")


def authenticate():
    log("Google authentication başlıyor...")
    creds = None
    if TOKEN_FILE.exists():
        creds = Credentials.from_authorized_user_file(str(TOKEN_FILE), SCOPES)

    if creds and creds.expired and creds.refresh_token:
        creds.refresh(Request())
    if not creds or not creds.valid:
        flow = InstalledAppFlow.from_client_secrets_file(str(CREDENTIALS_FILE), SCOPES)
        creds = flow.run_local_server(port=0)
    TOKEN_FILE.write_text(creds.to_json(), encoding="utf-8")

    log("Authentication tamam.")
    return creds



def get_all_files(service, folder_id, level=0):
    files = []
    query = f"'{folder_id}' in parents"
    page_token = None

    while True:
        response = service.files().list(
            q=query + " and trashed = false",
            spaces='drive',
            fields='nextPageToken, files(id, name, mimeType)',
            pageToken=page_token
        ).execute()

        for file in response.get('files', []):
            if file['mimeType'] == 'application/vnd.google-apps.folder':
                print("  " * level + f"[KLASÖR] {file['name']}")
                files.extend(get_all_files(service, file['id'], level+1))
            else:
                if 'image/' in file['mimeType'] or 'video/' in file['mimeType']:
                    print("  " * level + f"[DOSYA] {file['name']}")
                    files.append(file)

        page_token = response.get('nextPageToken')
        if not page_token:
            break

    return files

def download_file(service, file_id, file_name):
    os.makedirs(DOWNLOAD_DIR, exist_ok=True)
    file_path = os.path.join(DOWNLOAD_DIR, file_id + Path(file_name).suffix)

    if os.path.exists(file_path):
        log(f"SKIP (zaten var): {file_name}")
        return file_path

    request = service.files().get_media(fileId=file_id)
    partial_path = file_path + ".part"
    with io.FileIO(partial_path, 'wb') as fh:
        downloader = MediaIoBaseDownload(fh, request)
        done = False
        log(f"İndiriliyor: {file_name}")
        while not done:
            status, done = downloader.next_chunk()
    os.replace(partial_path, file_path)

    log(f"Tamamlandı: {file_name}")
    return file_path


def upload_to_photos(filepath, token, file_name):
    log(f"Google Foto'ya yükleniyor: {os.path.basename(filepath)}")

    headers = {
        "Authorization": f"Bearer {token}",
        "Content-type": "application/octet-stream",
        "X-Goog-Upload-Protocol": "raw",
    }

    upload_url = "https://photoslibrary.googleapis.com/v1/uploads"

    with open(filepath, "rb") as f:
        response = requests.post(upload_url, data=f, headers=headers, timeout=(30, 600))

    response.raise_for_status()
    upload_token = response.text.strip()
    if not upload_token:
        raise RuntimeError("Google Photos boş yükleme yanıtı döndürdü.")

    create_url = "https://photoslibrary.googleapis.com/v1/mediaItems:batchCreate"
    body = {
        "newMediaItems": [
            {
                "simpleMediaItem": {
                    "uploadToken": upload_token,
                    "fileName": file_name
                }
            }
        ]
    }

    headers["Content-type"] = "application/json"
    result = requests.post(create_url, json=body, headers=headers, timeout=(30, 120))
    result.raise_for_status()
    items = result.json().get("newMediaItemResults", [])
    if len(items) != 1 or items[0].get("status", {}).get("code", 0) != 0 or not items[0].get("mediaItem", {}).get("id"):
        raise RuntimeError("Google Photos medyayı oluşturamadı; başarı günlüğüne yazılmadı.")


def main():
    parser = argparse.ArgumentParser(description="Drive fotoğraf ve videolarını Google Photos'a kopyalar.")
    parser.add_argument("--folder-id", default=FOLDER_ID, help="Kaynak Drive klasör kimliği (veya DRIVE_FOLDER_ID).")
    args = parser.parse_args()
    if not args.folder_id or any(c not in "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_-" for c in args.folder_id):
        parser.error("Geçerli bir --folder-id verin veya DRIVE_FOLDER_ID ayarlayın.")
    creds = authenticate()
    service = build('drive', 'v3', credentials=creds)

    uploaded = set()
    if os.path.exists(LOG_FILE):
        with open(LOG_FILE, 'r') as f:
            uploaded = set(f.read().splitlines())
        log(f"{len(uploaded)} dosya daha önce yüklenmiş, atlanacak.")

    log("Drive klasörleri taranıyor (alt klasörler dahil)...")
    files = get_all_files(service, args.folder_id)
    log(f"Toplam {len(files)} foto/video bulundu.")

    for idx, file in enumerate(files, start=1):
        if file['id'] in uploaded:
            continue

        log(f"[{idx}/{len(files)}] İşleniyor: {file['name']}")

        file_path = download_file(service, file['id'], file['name'])
        if not creds.valid:
            creds.refresh(Request())
            TOKEN_FILE.write_text(creds.to_json(), encoding="utf-8")
        upload_to_photos(file_path, creds.token, file['name'])

        with open(LOG_FILE, 'a') as logf:
            logf.write(file['id'] + '\n')
        uploaded.add(file['id'])

    log("TÜM DOSYALAR BİTTİ ✅")


if __name__ == '__main__':
    main()
