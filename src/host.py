"""Barındırma: görsel baytları → Instagram'ın erişebileceği public URL.

Instagram Graph API dosya yükleme kabul etmez, yalnızca URL ister. İki adapter:
  github (varsayılan) : output/ klasörüne yaz + (CI'daysa) commit&push → raw.githubusercontent URL
  r2                  : Cloudflare R2'ye (S3 uyumlu) yükle → public base URL
"""
from __future__ import annotations

import subprocess
from pathlib import Path

from . import config

log = config.get_logger("host")

ROOT = Path(__file__).resolve().parent.parent


def host_image(image_bytes: bytes, filename: str) -> str:
    """Görseli barındırır, public URL döndürür."""
    settings = config.settings()
    which = (config.env("HOST") or settings.get("host") or "github").lower()
    if which == "r2":
        return _host_r2(image_bytes, filename)
    return _host_github(image_bytes, filename, settings)


# ---------------------------------------------------------------------------
#  GitHub raw barındırma
# ---------------------------------------------------------------------------
def _host_github(image_bytes: bytes, filename: str, settings: dict) -> str:
    gh = settings.get("github_host", {}) or {}
    branch = gh.get("branch", "main")
    out_dir = gh.get("output_dir", "output")

    repo_slug = config.env("REPO_SLUG") or config.env("GITHUB_REPOSITORY")
    if not repo_slug:
        raise RuntimeError("REPO_SLUG (kullanici/repo) tanımlı değil — raw URL kurulamaz")

    dest = ROOT / out_dir / filename
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_bytes(image_bytes)
    log.info("görsel yazıldı: %s", dest.relative_to(ROOT))

    # CI ortamındaysak commit + push (URL'in canlı olması için gerekli)
    if config.env("GITHUB_ACTIONS") == "true":
        _git_commit_push(dest, out_dir, filename, branch)

    return f"https://raw.githubusercontent.com/{repo_slug}/{branch}/{out_dir}/{filename}"


def _git_commit_push(dest: Path, out_dir: str, filename: str, branch: str) -> None:
    rel = f"{out_dir}/{filename}"
    try:
        subprocess.run(["git", "config", "user.name", "cyberpunk-bot"], cwd=ROOT, check=True)
        subprocess.run(
            ["git", "config", "user.email", "bot@users.noreply.github.com"], cwd=ROOT, check=True
        )
        subprocess.run(["git", "add", rel], cwd=ROOT, check=True)
        subprocess.run(
            ["git", "commit", "-m", f"chore: add post image {filename}"], cwd=ROOT, check=True
        )
        subprocess.run(["git", "push", "origin", f"HEAD:{branch}"], cwd=ROOT, check=True)
        log.info("görsel commit&push edildi: %s", rel)
    except subprocess.CalledProcessError as exc:
        raise RuntimeError(f"git push başarısız: {exc}") from exc


# ---------------------------------------------------------------------------
#  Cloudflare R2 barındırma (opsiyonel adapter)
# ---------------------------------------------------------------------------
def _host_r2(image_bytes: bytes, filename: str) -> str:
    try:
        import boto3  # opsiyonel bağımlılık
    except ImportError as exc:
        raise RuntimeError("R2 için 'boto3' gerekli (pip install boto3)") from exc

    account = config.env("R2_ACCOUNT_ID")
    key_id = config.env("R2_ACCESS_KEY_ID")
    secret = config.env("R2_SECRET_ACCESS_KEY")
    bucket = config.env("R2_BUCKET")
    public_base = config.env("R2_PUBLIC_BASE").rstrip("/")
    if not all([account, key_id, secret, bucket, public_base]):
        raise RuntimeError("R2 ayarları eksik (R2_ACCOUNT_ID/KEY/SECRET/BUCKET/PUBLIC_BASE)")

    client = boto3.client(
        "s3",
        endpoint_url=f"https://{account}.r2.cloudflarestorage.com",
        aws_access_key_id=key_id,
        aws_secret_access_key=secret,
        region_name="auto",
    )
    client.put_object(Bucket=bucket, Key=filename, Body=image_bytes, ContentType="image/png")
    log.info("R2'ye yüklendi: %s", filename)
    return f"{public_base}/{filename}"
