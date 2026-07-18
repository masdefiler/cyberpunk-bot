# Siberpunk Otonom Instagram İçerik Botu

Kendi kendine işleyen bir Instagram içerik üretim + paylaşım sistemi.
Tema: **siberpunk estetiği + alternatif tarih + spekülatif gelecek**.

Her çalışmada: fikir üretir → görsel üretir → 4:5'e işler → barındırır → caption yazar → Instagram'a yayınlar.
Zamanlama **GitHub Actions cron** ile (günde 2 kez). Aylık maliyet hedefi **0–5 USD**.

---

## Nasıl çalışır

```
state → ideate → generate → host → caption → publish → SQLite
```

| Modül | İş |
|-------|----|
| `state.py` | SQLite: sütun rotasyonu, tekrar önleme (son 50 başlık), 24s kotası |
| `ideate.py` | JSON konsept üretimi — zincir: gemini(ücretsiz)→pollinations(anahtarsız)→şablon |
| `generate.py` | Görsel üretimi (sağlayıcı zinciri) + Pillow son-işleme + filigran |
| `host.py` | Public URL: GitHub raw (varsayılan) veya Cloudflare R2 |
| `caption.py` | Mikro-kurgu + her seferinde farklı 15–25 hashtag |
| `publish.py` | Instagram Graph API iki adımlı yayın + 24s limiti |
| `pipeline.py` | Hepsini yöneten orkestratör (`--dry-run`, `--count`) |

**5 içerik sütunu** (sırayla döner): A) Alternatif Tarih · B) Yakın Gelecek Sokakları ·
C) Terkedilmiş Gelecek · D) Portre · E) Nesne/Artefakt. `config/pillars.yaml`'da tanımlı.

**Görsel kimlik** `config/style.yaml`'daki `style_suffix`'e bağlı — her görsel prompt'unun
sonuna otomatik eklenir, böylece hesap tutarlı görünür.

---

## Maliyet

| Kalem | Maliyet |
|-------|---------|
| Fikir (pollinations anahtarsız / gemini ücretsiz katman) | **0 USD** |
| Görsel (pollinations/cloudflare/together ücretsiz) | 0 USD |
| Barındırma (GitHub raw) | 0 USD |
| Zamanlama (GitHub Actions) | 0 USD (public repo) |

> Varsayılan kurulum **tamamen anahtarsız ve $0**'dır. İstersen kalite için ücretsiz
> Gemini anahtarı ya da (ücretli) Claude anahtarı ekleyebilirsin — ama şart değil.

---

## 1. Yerel kurulum & test (anahtarsız)

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

# Anahtar GEREKMEZ — dry-run yerel şablon + ücretsiz pollinations ile çalışır
python -m src.pipeline --count 3
```

Çıktılar `preview/` klasörüne düşer (`.png` görsel + `.txt` caption). Yayın YAPILMAZ.

`.env` istersen: `cp .env.example .env` ve doldur. Gerçek fikir üretimi için
`ANTHROPIC_API_KEY`, gerçek yayın için `IG_*` gerekir.

---

## 2. Instagram Business hesabı bağlama & token alma

Instagram içerik yayını **profesyonel (Business/Creator) hesap** + **Meta uygulaması** ister.

1. Instagram hesabını **Profesyonel** yap (Ayarlar → Hesap türü).
2. [developers.facebook.com](https://developers.facebook.com) → **Create App** → tür: **Business**.
3. Uygulamaya **Instagram** ürününü ekle → **Instagram API setup with Instagram login**.
4. **Instagram hesabını bağla** ve şu izinleri iste:
   `instagram_business_basic`, `instagram_business_content_publish`.
5. Bir **uzun ömürlü erişim token'ı** üret (IGAA… ile başlar, 60 gün geçerli).
6. **IG_USER_ID**'yi al: token ile
   `GET https://graph.instagram.com/me?fields=user_id&access_token=…`

> Bu proje varsayılan olarak **Instagram Login** akışını (`graph.instagram.com`) kullanır.
> Facebook Login akışı kullanıyorsan repo değişkeni `GRAPH_MODE=facebook` yap ve
> `GRAPH_BASE=https://graph.facebook.com/v21.0` ver.

---

## 3. GitHub Secrets

Repo → **Settings → Secrets and variables → Actions** → **New repository secret**:

| Secret | Zorunlu | Ne |
|--------|---------|----|
| `IG_USER_ID` | evet | Instagram profesyonel hesap ID'si |
| `IG_ACCESS_TOKEN` | evet | Uzun ömürlü token (IGAA…) |
| `GH_PAT` | token yenileme için | `secrets:write` izinli fine-grained PAT |
| `GEMINI_API_KEY` | opsiyonel | Fikir kalitesi için ücretsiz AI Studio anahtarı (yoksa anahtarsız pollinations) |
| `ANTHROPIC_API_KEY` | opsiyonel | Ücretli Claude ideation (chain'e "claude" eklenirse) |
| `CLOUDFLARE_ACCOUNT_ID` / `CLOUDFLARE_API_TOKEN` | opsiyonel | cloudflare sağlayıcısı |
| `TOGETHER_API_KEY` | opsiyonel | together sağlayıcısı |
| `FAL_KEY` | opsiyonel | fal (ücretli) sağlayıcısı |

**Variables** (secret değil) sekmesinde opsiyonel:
`PROVIDER` (varsayılan `pollinations`), `GRAPH_MODE`.

> `REPO_SLUG` otomatik dolar (`github.repository`) — elle girmene gerek yok.

---

## 4. Zamanlama (otomatik yayın)

`.github/workflows/post.yml` günde iki kez çalışır:

- **16:00 UTC** ≈ Vancouver 09:00 (yaz)
- **02:00 UTC** ≈ Vancouver 19:00 (yaz)

> GitHub cron **UTC**'dir ve yaz saatini (DST) bilmez; kışın Vancouver saatleri
> 1 saat kayar (08:00/18:00). İstersen cron değerlerini elle güncelle.

Manuel tetikleme: repo → **Actions → Gönderi Yayınla → Run workflow** (adet seçebilirsin).

---

## 5. Token'ı otomatik yenileme

IGAA token'ı 60 günde bir yenilenmeli. `.github/workflows/refresh-token.yml`
her Pazartesi çalışır, token'ı yeniler ve `IG_ACCESS_TOKEN` secret'ını günceller.

**Ön koşul:** `GH_PAT` secret'ı (secrets:write izinli PAT) — varsayılan `GITHUB_TOKEN`
secret güncelleyemez. Yerelde elle yenilemek için:

```bash
IG_ACCESS_TOKEN=… python scripts/refresh_token.py   # yeni token'ı yazdırır
```

---

## Özelleştirme

- **Filigran:** `config/style.yaml` → `post.watermark.text` (şu an `KRONØS`). Kapatmak için `enabled: false`.
- **Renk/atmosfer:** `config/style.yaml` → `style_suffix` ve `palette`.
- **Sütunlar:** `config/pillars.yaml` → `yon`/`ornek` alanlarını düzenle, sırayı `rotation` belirler.
- **Ritim & hashtag havuzları:** `config/settings.yaml`.
- **Sağlayıcı:** `PROVIDER` env veya `settings.yaml` → `provider_chain`.

---

## Test

```bash
pip install pytest
pytest                 # API çağrıları mock'lu; ağ gerekmez
```

## Sağlayıcı notları

| Sağlayıcı | Anahtar | Not |
|-----------|---------|-----|
| `pollinations` | yok | Ücretsiz, varsayılan. FLUX. |
| `cloudflare` | evet | Workers AI FLUX-1-schnell, cömert ücretsiz kota |
| `together` | evet | FLUX.1-schnell-Free katmanı |
| `fal` | evet | Ücretli, en yüksek kalite (opsiyonel) |

Zincirdeki bir sağlayıcı hata verirse otomatik olarak sıradakine düşülür.
