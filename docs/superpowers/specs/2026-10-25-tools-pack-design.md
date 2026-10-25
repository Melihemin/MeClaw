# MeClaw Araç Paketi — Tasarım

Tarih: 2026-10-25
Durum: Onay bekliyor

## Amaç

Asistanın dosyalarla ve dış dünyayla daha yetkin çalışması: mevcut dosya araçlarındaki eksikleri gidermek; arama, düzenleme, belge (PDF/Excel), web, tarih/hesap ve hafıza araçları eklemek; dosya silme ve üzerine yazma işlemlerinden önce kullanıcıdan onay almak.

### Başarı ölçütleri

- "notlar klasöründe ne var", "içinde fatura geçen dosyaları bul", "şu PDF'i özetle", "bu tabloyu Excel'e yaz", "şu linki özetle", "X'i internette ara", "yarın hangi gün", "1234*5678 kaç" gibi istekler tek sohbette araçlarla doğru yanıtlanır.
- Silme ya da var olan bir dosyanın değişmesi onay kartı çıkmadan gerçekleşmez; "Reddet" ya da 5 dakika sessizlik işlemi iptal eder ve model bunu bilir.
- Asistan kalıcı kişisel bilgileri kendiliğinden hafızaya alır, bunu sohbette görünür kılar; kullanıcı Ayarlar'dan notları görür, düzenler, siler, hafızayı kapatır.
- İnternet erişimi Ayarlar'dan kapatılınca web araçları modele hiç sunulmaz.
- `fetch_url` yerel ağ/loopback adreslerine istek atamaz.
- Testler ağa çıkmadan geçer.

### Kapsam dışı

- Komut/kod çalıştırma araçları, e-posta, takvim.
- Onay bekleyen işlemin sayfa yenilemesinden sonra sürdürülmesi (B yaklaşımı). Sayfa kapanırsa işlem reddedilir.
- Web aramada resmi/anahtarlı API'ler (Tavily, Brave).
- Hafıza için anlamsal arama/embedding; tüm notlar sistem istemine eklenir.

## Kararlar

| Konu | Karar |
|---|---|
| Onay gerektiren işlemler | Silme + var olan dosya/klasörün içeriğinin değişmesi veya üzerine yazılması |
| Onay mekanizması | A: SSE akışı içinde bekleme, `POST /api/chat/confirm` ile karar, 300 sn zaman aşımı = red |
| Web arama | DuckDuckGo, `ddgs` kütüphanesi (anahtarsız, resmi olmayan) |
| İnternet araçları | Varsayılan açık, Ayarlar'dan kapatılabilir (`MECLAW_INTERNET`) |
| Hafıza | Asistan kendisi karar verir; Ayarlar'da yönetilir; kapatılabilir (`MECLAW_MEMORY`) |
| Araç adları | `_tool` son eki kaldırılır (`create_file_tool` → `create_file`) |
| Araç tanımları | `tool_definitions.json` kaldırılır; şemalar Python modüllerinde araçla birlikte durur |

## Mimari

```
meclaw/tools/
  base.py        ToolSpec, ToolContext, ToolRegistry (kayıt, şema, onay sorgusu, async çalıştırma)
  files.py       dosya/klasör araçları (Explorer üstüne) + search_files, edit_file, file_info
  documents.py   read_pdf, read_spreadsheet, write_spreadsheet
  web.py         fetch_url, web_search (+ güvenli URL denetimi, HTML→metin)
  utils.py       get_datetime, calculate
  memory.py      remember, forget
  __init__.py    build_registry(ctx) — açık olan araç gruplarıyla kayıt kurar
meclaw/memory.py hafıza bölümünü sistem istemine ekleyen build_system_prompt
meclaw/agent.py  onay kancası + async araç çalıştırma
meclaw/storage.py memories tablosu ve CRUD
server.py        /api/chat/confirm, /api/memories*, yeni ayarlar, kayıt yeniden kurulumu
static/          onay kartı, Ayarlar → Araçlar ve Hafıza bölümleri
```

`meclaw/tools/registry.py` ve `tools/finder/tool_definitions.json` kaldırılır. `tools/finder/explorer_class.py` dosya işlemlerinin alt katmanı olarak kalır.

### Araç çekirdeği (`meclaw/tools/base.py`)

```python
@dataclass
class ToolContext:
    explorer: Explorer
    storage: Storage | None        # hafıza araçları için
    internet: bool                 # web araçları kayda girsin mi
    memory: bool                   # hafıza araçları kayda girsin mi

@dataclass
class ToolSpec:
    name: str
    description: str
    parameters: dict                                   # JSON Schema (object)
    handler: Callable[..., str | Awaitable[str]]       # handler(ctx, **args)
    confirm: Callable[[ToolContext, dict], Confirmation | None] | None = None

@dataclass
class Confirmation:
    description: str      # Türkçe, ör. "‘notlar.txt’ silinecek."
    preview: str = ""     # en fazla 600 karakter; düzenlemede eski→yeni özeti

class ToolRegistry:
    def __init__(self, ctx: ToolContext, specs: list[ToolSpec]): ...
    explorer: Explorer                         # Files paneli için (property)
    def definitions(self) -> list[dict]        # OpenAI/Ollama "function" şemaları
    def names(self) -> set[str]
    def needs_confirmation(self, name, arguments) -> Confirmation | None
    async def run(self, name, arguments) -> str   # asla exception fırlatmaz
```

- `run`: bilinmeyen araç → `Unknown tool: <ad>`; `TypeError` → `Invalid arguments for <ad>: …`; diğer hatalar → `Tool <ad> failed: …` (loglanır). Sonuç 20.000 karakterde kesilir (`\n…(truncated)`), mevcut davranış korunur. Senkron handler'lar `asyncio.to_thread` ile çalışır.
- `needs_confirmation` exception fırlatırsa (ör. geçersiz yol) `None` döner; asıl hata `run` sırasında metin olarak modele gider.
- `build_registry(ctx)`: dosya + belge + yardımcı araçlar her zaman; web araçları `ctx.internet` ise; hafıza araçları `ctx.memory and ctx.storage` ise.

### Araçlar

Yollar her zaman çalışma klasörüne göreli; `Explorer` sınırı (`Path is outside the workspace.`) tüm araçlarda geçerli. Mesajlar mevcut araçlarla tutarlı olarak İngilizce kalır (model için), kullanıcıya görünen onay metinleri Türkçe.

**Dosya araçları (`files.py`)** — mevcut 16 araç adları kısaltılarak taşınır: `create_file, delete_file, copy_file, read_file, write_file, rename_file, write_word_file, read_word_file, create_folder, remove_folder, list_items, move_item, rename_folder, copy_folder, zip_folder, extract_archive`. Değişenler:

- `list_items(path="", recursive=false)`: `path` klasörünü listeler. `recursive` ise alt klasörler girintili ağaç olarak, en fazla 500 satır (aşılırsa `… (N more)`).
- `read_file(filename, start_line=null, end_line=null)`: 1 tabanlı, iki uç dahil. Aralık verilirse başa `Lines a-b of N:` eklenir.

Yeni:

- `search_files(query="", name_pattern="", path="")`: `name_pattern` fnmatch (büyük/küçük harf duyarsız, ör. `*.md`); `query` içerikte büyük/küçük harf duyarsız alt dize. En az biri zorunlu. İçerik araması yalnızca ≤1 MB ve UTF-8 çözülebilen dosyalarda. En fazla 50 sonuç; içerik eşleşmesi `yol:satır: metin` (metin 200 karakterde kesilir), ad eşleşmesi `yol`.
- `edit_file(filename, new_text, old_text="", mode="replace")`: `replace` modunda `old_text` dosyada tam bir kez geçmeli (0 → `Text not found in <dosya>.`, >1 → `Text occurs N times in <dosya>; give a longer, unique snippet.`). `append` modunda `new_text` sona eklenir (dosya satır sonuyla bitmiyorsa önce `\n`). Dosya yoksa hata.
- `file_info(path)`: tür (file/dir), boyut, değişiklik zamanı (yerel saat), metin dosyalarında satır sayısı, klasörlerde öğe sayısı.

**Belge araçları (`documents.py`)**

- `read_pdf(filename, start_page=1, end_page=null)`: pypdf ile metin; tek çağrıda en fazla 30 sayfa; başa `Pages a-b of N:`. Metin çıkmayan sayfa için `[page k: no extractable text]`.
- `read_spreadsheet(filename, sheet="", max_rows=50)`: `.xlsx` (openpyxl, `read_only=True, data_only=True`) veya `.csv` (`utf-8-sig`, `csv.Sniffer` ile ayraç). `max_rows` en fazla 200. Çıktı: sayfa adları, seçili sayfanın satır×sütun sayısı, ilk satırlar Markdown tablosu olarak.
- `write_spreadsheet(filename, rows, sheet="Sayfa1")`: `rows` = dizi dizisi (string/sayı/null). Uzantıya göre `.xlsx` ya da `.csv`; başka uzantı hata.

**Web araçları (`web.py`)** — yalnızca `ctx.internet` açıkken kayıtlı.

- `fetch_url(url)`:
  - Sadece `http`/`https`. Ana makine adı çözülür; çözülen adreslerden biri loopback/özel/link-local/ayrılmış/multicast ise reddedilir (`ipaddress`).
  - `httpx.AsyncClient(follow_redirects=False)`; yönlendirmeler elle, en fazla 5 adım, her adımda aynı denetim.
  - 10 sn zaman aşımı, gövde en fazla 2 MB (akışla okunur, aşılırsa kesilir ve not düşülür).
  - `text/html` → stdlib `HTMLParser` ile okunur metin: `script, style, noscript, svg, head, nav, footer` atlanır; blok öğeler satır sonu; boşluklar sadeleşir; başa `Title: …` ve `URL: …`. `text/plain`, `application/json` olduğu gibi. Diğer türler → `Unsupported content type: …`.
  - User-Agent `MeClaw/1.0`.
- `web_search(query, max_results=5)`: `ddgs.DDGS().text(query, region="tr-tr", max_results=n)` (`asyncio.to_thread`), `n` en fazla 10. Çıktı numaralı liste: başlık, adres, özet. Hata → `Web search failed: …`.

**Yardımcılar (`utils.py`)**

- `get_datetime()`: yerel saat diliminde `2026-10-25 21:40, Pazar (25 Ekim 2026), UTC+03:00` biçiminde. Türkçe gün/ay adları sabit tablodan (sistem yerel ayarına bağlı değil).
- `calculate(expression)`: `ast` ile güvenli değerlendirme. İzinli: sayılar, `+ - * / // % **`, tekli `+ -`, parantez, `math` sabitleri `pi, e`, fonksiyonlar `sqrt, abs, round, floor, ceil, log, log10, sin, cos, tan, min, max`. Üs ≤ 1000, ifade ≤ 200 karakter. Diğer her şey → `Unsupported expression`. `,` ondalık ayırıcıysa (`3,5`) `.` olarak kabul edilmez; model doğru biçimi kullanır.

**Hafıza araçları (`memory.py`)** — yalnızca hafıza açıkken kayıtlı.

- `remember(content)`: ≤500 karakter, boş değil; `Saved memory #id.`
- `forget(memory_id)`: `Forgot memory #id.` ya da `No memory #id.`

### Onay kuralları

`confirm` fonksiyonu yalnızca aşağıdaki durumlarda `Confirmation` döner:

| Araç | Onay koşulu | Açıklama örneği |
|---|---|---|
| `delete_file` | dosya varsa | ‘notlar.txt’ silinecek. |
| `remove_folder` | klasör varsa | ‘eski’ klasörü silinecek. |
| `edit_file` | her zaman (dosya varsa) | ‘notlar.txt’ düzenlenecek. (önizleme: `- eski` / `+ yeni` kesitleri) |
| `write_file`, `write_word_file`, `write_spreadsheet` | hedef varsa | ‘rapor.docx’ üzerine yazılacak. (önizleme: yeni içeriğin başı) |
| `copy_file`, `copy_folder`, `move_item`, `rename_file`, `rename_folder` | hedef varsa | ‘b.txt’ üzerine yazılacak (‘a.txt’ kopyalanıyor). |
| `zip_folder` | `<klasör>.zip` varsa | ‘proje.zip’ üzerine yazılacak. |
| `extract_archive` | hedef klasör var ve boş değilse | ‘arsiv’ klasörüne açılacak; aynı adlı dosyalar değişebilir. |

### Onay akışı (A)

- `run_agent(..., confirm: Callable[[ConfirmRequest], Awaitable[bool]] | None = None)`.
- Her araç çağrısından önce `registry.needs_confirmation`. Gerekiyorsa agent önce `AgentEvent("confirm", confirm_id, name, arguments, description, preview)` yayar, sonra `await confirm(req)`.
  - `True` → araç çalışır.
  - `False` ya da `confirm is None` → araç çalışmaz; sonuç `Denied by the user: <açıklama>` olur ve normal `tool` mesajı olarak modele verilir.
  - Ardından `AgentEvent("confirm_result", confirm_id, approved)`.
- `confirm_id` = `uuid4().hex`.
- Sunucu: sohbet başına bekleyen kararlar için `dict[confirm_id, asyncio.Future]`. `confirm` kancası future oluşturur, `asyncio.wait_for(future, 300)`; zaman aşımı → `False`. Akış biterken (normal, hata ya da istemci kopması) o sohbetin bekleyen future'ları iptal edilir ve sözlükten silinir.
- `POST /api/chat/confirm` gövde `{confirm_id: str, approved: bool}`; `require_local` korumalı (özel başlık + köken). Bilinmeyen ya da çözülmüş id → 404. Başarı → 204.
- SSE yeni olaylar: `confirm {"id","name","description","preview"}`, `confirm_result {"id","approved"}`.
- Reddedilen işlemler geçmişe normal `tool` mesajı olarak kaydedilir; onay kartı geçmiş yüklenirken ayrıca gösterilmez (araç etiketi yeterli).

### Hafıza

- `memories(id INTEGER PK AUTOINCREMENT, content TEXT, created_at TEXT, updated_at TEXT)`.
- `Storage`: `list_memories() -> list[dict]`, `add_memory(content) -> dict`, `update_memory(id, content) -> bool`, `delete_memory(id) -> bool`, `clear_memories() -> int`.
- `build_system_prompt(base: str, memories: list[dict], memory_enabled: bool) -> str`: hafıza açıksa `base` sonuna sabit Türkçe/İngilizce kural bloğu (kalıcı kişisel bilgileri — ad, tercihler, süren projeler, önemli ilişkiler — `remember` ile kaydet; geçici ayrıntıları, parola/anahtar/kimlik numarası gibi gizli bilgileri kaydetme; yanlış/eskimiş bilgiyi `forget` ile sil, gerekirse yenisini kaydet; kaydettiğini kısaca belirt) ve `Known facts about the user:` altında `[id] içerik` satırları (en yeni 100 not). Kapalıysa `base` aynen.
- API (hepsi JSON; yazanlar `require_local` korumalı):
  - `GET /api/memories` → liste
  - `POST /api/memories {content}` → yeni not
  - `PUT /api/memories/{id} {content}` → güncelle (404)
  - `DELETE /api/memories/{id}` → 204/404
  - `DELETE /api/memories` → hepsini sil, `{deleted: n}`
  - İçerik boş ya da >500 karakter → 400.

### Ayarlar

- `Settings`: `internet_enabled: bool = True` (`MECLAW_INTERNET`), `memory_enabled: bool = True` (`MECLAW_MEMORY`). `"0", "false", "off", "no"` (büyük/küçük harf duyarsız) → kapalı; diğer/boş → açık.
- `GET/PUT /api/settings` iki boolean alanla genişler: `internet_enabled`, `memory_enabled`. Varsayılan (açık) değer `.env`'den silinir, kapalı `0` yazılır.
- Workspace, internet veya hafıza ayarı değişince kayıt `make_registry(settings)` ile yeniden kurulur (mevcut `make_registry(path)` imzası `make_registry(settings)` olur).

### Arayüz

- Onay kartı (mesaj akışında): "🛡 Onay gerekiyor" başlığı, açıklama, varsa önizleme (`pre`, `textContent`), [İzin ver] [Reddet]. Tıklanınca düğmeler kilitlenir, `POST /api/chat/confirm`; `confirm_result` gelince kart "✓ İzin verildi" / "✗ Reddedildi" durumuna geçer. Zaman aşımında da `confirm_result` (false) gelir.
- Araç etiketleri: `remember` → "📝 Hafıza güncellendi", `forget` → "📝 Hafızadan silindi", web araçları → "🌐 …", diğerleri mevcut "🛠 ad".
- Ayarlar → yeni "Araçlar" bölümü: "İnternet erişimi (web arama ve sayfa okuma)" ve "Hafıza" anahtarları.
- Ayarlar → yeni "Hafıza" bölümü: not listesi (her satırda düzenle/sil), "Not ekle" alanı, "Tümünü sil" (onaylı). Hafıza kapalıyken liste görünür ama "Hafıza kapalı; asistan notları kullanmıyor" uyarısı çıkar.

## Hata yönetimi

- Araç hataları metin olarak modele döner (mevcut ilke); onay kancası hatası → işlem reddedilmiş sayılır.
- Web: DNS hatası, zaman aşımı, engellenen adres, büyük gövde, desteklenmeyen tür → açıklayıcı İngilizce metin.
- `ddgs` içe aktarılamazsa ya da hata verirse `web_search` metin hatası döner; diğer araçlar etkilenmez.

## Bağımlılıklar

`requirements.txt`: `pypdf>=5,<7`, `openpyxl>=3.1,<4`, `ddgs>=9,<10` (sürümler kurulumda doğrulanıp sabitlenir). `httpx` zaten mevcut.

## Test

Ağa çıkmadan, `tmp_path` ile:

- `test_tools_base.py`: kayıt, şema üretimi, bilinmeyen araç, hatalı argüman, async/sync handler, sonuç kesme, internet/hafıza kapalıyken araçların kayıtta olmaması.
- `test_tools_files.py`: `list_items` (path, recursive, sınır), `read_file` aralığı, `search_files` (ad, içerik, ikisi, sınır, ikili dosya atlama), `edit_file` (tek/çok/yok eşleşme, append), `file_info`, onay kuralları tablosunun her satırı (gerekli/gereksiz).
- `test_tools_documents.py`: metinli PDF, testteki küçük bir yardımcıyla elle yazılmış ham PDF baytlarından (Helvetica, tek satır metin içeren içerik akışı) üretilir; ek kütüphane gerekmez. Ayrıca xlsx/csv okuma-yazma, sayfa seçimi, max_rows sınırı.
- `test_tools_web.py`: `httpx.MockTransport` ile HTML→metin, yönlendirme zinciri, 2 MB sınırı, içerik türü; `getaddrinfo` sahtelenerek 127.0.0.1 / 10.x / 192.168.x / ::1 reddi ve yönlendirmeyle özel adrese kaçışın reddi; `web_search` sahte `DDGS` ile.
- `test_tools_utils.py`: `calculate` doğru sonuçlar ve kötü niyetli ifadeler (`__import__`, öznitelik erişimi, dev üs, uzun ifade); `get_datetime` biçimi (saat sabitlenerek).
- `test_memory.py`: storage CRUD, `build_system_prompt`, hafıza API'si ve korumaları, `remember`/`forget`.
- `test_agent.py` / `test_server.py`: onaylı araçta `confirm` olayı, izin → çalışır, red → `Denied by the user`, `confirm=None` → red, zaman aşımı (kısa süreyle), istemci kopunca bekleyen kararların temizlenmesi, `POST /api/chat/confirm` 404/403/204; yeni ayarların kaydı yeniden kurması.

Tarayıcı: onay kartı (izin/ret), hafıza bölümü, araç ayarları — sahte sağlayıcıyla.
