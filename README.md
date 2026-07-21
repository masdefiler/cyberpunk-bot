# kulups.com — Otonom Instagram İçerik Botu

`@kulupsapps` hesabı için kendi kendine çalışan içerik üretim + paylaşım sistemi.
İçerik: **kulups.com özellik tanıtımı** (basketbol kulüpleri için dijital yönetim sistemi).

Her çalışmada: özellik seç → tanıtım metni yaz → arka plan görseli üret →
üzerine **gerçek metin kartı** bas → barındır → Instagram'a yayınla.
Zamanlama **GitHub Actions cron** ile. Maliyet: **$0/ay**.

---

## Nasıl çalışır

```
state → ideate → generate (+card) → host → caption → publish → SQLite
```

| Modül | İş |
|-------|----|
| `state.py` | SQLite: sütun rotasyonu, tekrar önleme (son 50 başlık), 24s kotası |
| `ideate.py` | Özellik tanıtımı üretir (başlık + fayda + görsel prompt + caption) |
| `generate.py` | Arka plan görseli (sağlayıcı zinciri + retry) + son-işleme |
| `card.py` | **Görselin üstüne gerçek metin basar** — logo, altın aksan, başlık, fayda, kulups.com |
| `host.py` | Public URL: GitHub raw (varsayılan) veya Cloudflare R2 |
| `caption.py` | Açıklama + her seferinde farklı 15–25 hashtag |
| `publish.py` | Instagram Graph API iki adımlı yayın + 24s limiti |
| `pipeline.py` | Orkestratör (`--dry-run`, `--count`, `--publish`) |

> **Neden ayrı kart katmanı?** AI görsel modelleri düzgün yazı basamaz. Bu yüzden
> arka planı model üretir, metni Pillow ile biz basarız → Türkçe karakterler dahil
> her zaman düzgün ve marka tutarlı.

### 5 içerik sütunu (sırayla döner)
`config/pillars.yaml` — **sadece gerçek ürün özellikleri**, uydurma özellik yok:

| | Sütun | Kapsam |
|---|---|---|
| A | Saha & Takım Yönetimi | Takım/sporcu kadrosu, yoklama, antrenman-maç takvimi |
| B | Sporcu Gelişimi | Bireysel program, ölçüm & gelişim, sakatlık takibi |
| C | Aidat & Tahsilat | Aidat takibi, iyzico online tahsilat, kulüp mağazası |
| D | Veli İletişimi & Evrak | Veli-sporcu portalı, bildirim/e-posta, evrak takibi |
| E | Ücretsiz Taktik Tahtası | Üyeliksiz, ücretsiz sürükle-bırak taktik tahtası (değer sunma) |

---

## Maliyet

| Kalem | Maliyet |
|-------|---------|
| Metin (Gemini ücretsiz katman / pollinations anahtarsız) | **0 USD** |
| Görsel (pollinations anahtarsız) | 0 USD |
| Barındırma (GitHub raw) + zamanlama (Actions) | 0 USD |

---

## Yerel kullanım

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

python -m src.pipeline --count 3      # dry-run → preview/ klasörüne yazar, YAYINLAMAZ
python -m src.pipeline --publish      # gerçek yayın
IDEATE_PROVIDER=template python -m src.pipeline   # ağsız/şablon test
```

Anahtarlar `.env`'den okunur (`.env.example`'a bak). Hiç anahtar olmasa bile
dry-run çalışır: fikir → pollinations, görsel → pollinations, en kötü ihtimalle şablon.

---

## GitHub Secrets

| Secret | Zorunlu | Ne |
|--------|---------|----|
| `IG_USER_ID` | evet | Instagram profesyonel hesap ID'si (@kulupsapps) |
| `IG_ACCESS_TOKEN` | evet | Uzun ömürlü IGAA token (60 gün) |
| `GEMINI_API_KEY` | önerilir | Metin kalitesi (ücretsiz katman); yoksa pollinations |
| `GH_PAT` | token yenileme | `secrets:write` izinli fine-grained PAT |

## Zamanlama

`.github/workflows/post.yml` — günde iki kez: **16:00** ve **02:00 UTC**.
Manuel: Actions → *Gönderi Yayınla* → Run workflow.

> Cron UTC'dir ve DST bilmez. Duraklatmak için `on:` altındaki `schedule` bloğunu
> yorum satırı yap.

`.github/workflows/refresh-token.yml` haftalık çalışıp IG token'ını yeniler
(60 günlük süre hiç dolmaz). `GH_PAT` gerektirir.

---

## Özelleştirme

- **Özellikler/sütunlar:** `config/pillars.yaml` (⚠️ gerçek özellik dışında ekleme)
- **Görsel kimlik & kart:** `config/style.yaml` — palet, degrade örtü, punto, logo, footer
- **Logo:** `assets/logo.png` (şeffaf kalkan)
- **Ritim & hashtag havuzları:** `config/settings.yaml`
- **Sağlayıcı:** `PROVIDER` env veya `provider_chain`

## Test

```bash
pytest        # 35 test, API'ler mock'lu, ağ gerekmez
```
