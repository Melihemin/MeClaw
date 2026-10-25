# MeClaw Web Arayüzü — Tasarım

Tarih: 2026-10-25
Durum: Onay bekliyor

## Amaç

MeClaw'u Telegram botundan, yalnızca bu bilgisayarda çalışan kişisel bir web arayüzüne taşımak. Kullanıcı arayüzden LLM sağlayıcısını (Ollama veya OpenAI/ChatGPT) ve o sağlayıcının modelini seçebilmeli; mevcut dosya/klasör araçları (tools) her iki sağlayıcıyla da çalışmalı.

### Başarı ölçütleri

- `start.bat` çalıştırılınca sunucu `http://127.0.0.1:8000` adresinde açılır ve tarayıcı otomatik açılır.
- Arayüzde sağlayıcı ve model seçilip sohbet edilebilir; yanıt akış (streaming) halinde gelir.
- "notes.txt adında bir dosya oluştur" gibi bir istek, seçilen sağlayıcı hangisi olursa olsun aracı çalıştırır ve model sonucu doğal dille açıklar.
- Sohbetler SQLite'ta saklanır; sayfa yenilense veya sunucu yeniden başlasa da geri gelir.
- Ollama kapalıysa veya `OPENAI_API_KEY` tanımlı değilse ilgili sağlayıcı arayüzde pasif görünür, sunucu çökmez.
- Araçlar çalışma klasörünün (`tools/finder/testdir`) dışına erişemez.

### Kapsam dışı

- Telegram desteği (tamamen kaldırılır).
- Çok kullanıcılı kullanım, kimlik doğrulama, ağdan erişim.
- Dosya yükleme/indirme arayüzü, görsel/çok modlu girdiler.
- Ollama ve OpenAI dışındaki sağlayıcılar (mimari eklemeye açık, ama bu işte yapılmaz).

## Kararlar

| Konu | Karar |
|---|---|
| Telegram | Tamamen kaldırılır |
| Backend | FastAPI + uvicorn |
| Frontend | Sade HTML/CSS/JS, build adımı yok, FastAPI'den statik servis |
| Erişim | Yalnızca `127.0.0.1`, parola yok |
| Geçmiş | SQLite, çoklu sohbet |
| Streaming | Server-Sent Events (SSE), `POST /api/chat` yanıtı olarak |

## Mevcut durumdaki sorunlar (bu işte düzeltilecek)

1. `server.py` Telegram komutlarını, araç sarmalayıcılarını ve LLM döngüsünü tek dosyada topluyor.
2. Model `Qwen3:8b` olarak sabit kodlanmış.
3. LLM döngüsü bir araç çağrısında araç sonucunu doğrudan kullanıcıya döndürüyor; sonuç modele geri verilmediği için model açıklama yapamıyor ve çok adımlı araç kullanımı mümkün değil.
4. `Explorer._build_path` yolu `base_dir` içinde tutmuyor; `../` ile çalışma klasörü dışına çıkılabiliyor.
5. `tools/finder/explorer.py` kullanılmayan eski prosedürel sürüm ve Telegram'a bağımlı.
6. README, repoda olmayan `desktop_app.py` ve `tests/` dosyalarından bahsediyor.

## Mimari

```
meclaw/
  __init__.py
  config.py            .env okuma: OLLAMA_HOST, OPENAI_API_KEY, MECLAW_DB_PATH
  llm/
    __init__.py        get_provider(name) ve provider kaydı
    base.py            Provider protokolü ve ortak veri tipleri
    ollama.py          OllamaProvider
    openai.py          OpenAIProvider
  tools/
    __init__.py
    registry.py        araç adı → fonksiyon eşlemesi + JSON şemaları
  agent.py             araç döngüsü (provider'dan bağımsız)
  storage.py           SQLite erişimi
server.py              FastAPI uygulaması (giriş noktası)
static/
  index.html
  app.js
  style.css
tools/finder/          mevcut Explorer ve tool_definitions.json (yerinde kalır)
tests/
```

### Birimler

**`meclaw/llm/base.py`** — Ortak tipler:

```python
@dataclass
class ToolCall:
    id: str            # OpenAI'nin verdiği id; Ollama için üretilir
    name: str
    arguments: dict

@dataclass
class ChatEvent:
    type: Literal["text", "tool_calls", "done"]
    text: str = ""
    tool_calls: list[ToolCall] = field(default_factory=list)

class Provider(Protocol):
    name: str
    async def status(self) -> tuple[bool, str]      # (hazır mı, değilse nedeni)
    async def list_models(self) -> list[str]
    def chat(self, model: str, messages: list[dict], tools: list[dict]) -> AsyncIterator[ChatEvent]
```

Mesajlar provider'a ortak (OpenAI benzeri) bir biçimde verilir: `{"role": "system"|"user"|"assistant"|"tool", "content": str, "tool_calls"?: [...], "tool_call_id"?: str, "name"?: str}`. Her provider bu biçimi kendi API'sine çevirir.

**`meclaw/llm/ollama.py`** — `ollama.AsyncClient(host=OLLAMA_HOST)` kullanır. `status()` `client.list()` çağrısıyla erişilebilirliği test eder. `list_models()` yüklü modellerin adlarını döner. `chat()` `stream=True` ile çağırır; içerik parçalarını `text` olayı olarak, araç çağrılarını `tool_calls` olayı olarak yayar. Ollama tool call id vermediği için `uuid4` ile üretilir; `tool` mesajları Ollama'ya `tool_name` alanıyla iletilir.

**`meclaw/llm/openai.py`** — `openai.AsyncOpenAI(api_key=OPENAI_API_KEY)` kullanır. Anahtar yoksa `status()` `(False, "OPENAI_API_KEY tanımlı değil")` döner. `list_models()` `client.models.list()` sonucunu `gpt-` veya `o` ile başlayan sohbet modellerine süzer ve sıralar. `chat()` Chat Completions API'sini `stream=True, tools=...` ile çağırır; akıştaki `tool_calls` parçalarını index'e göre birleştirip akış bitince tek bir `tool_calls` olayı olarak yayar.

**`meclaw/tools/registry.py`** — `ToolRegistry(explorer: Explorer)` sınıfı; `tool_definitions.json`'u yükler (testlerde geçici klasörlü bir `Explorer` verilebilsin diye explorer dışarıdan alınır; uygulama varsayılan `Explorer()` ile tek bir örnek kurar). İçindeki `dict[str, Callable[..., str]]` eşlemesi `server.py`'deki `*_tool` sarmalayıcılarının yerini alır (`list_items_tool` okunabilir metin üretme mantığıyla birlikte taşınır). `run_tool(name, arguments) -> str`: bilinmeyen araçta `"Unknown tool: <ad>"`, hatalı argümanda (`TypeError`) `"Invalid arguments for <ad>: ..."` döner; hiçbir zaman exception fırlatmaz. `definitions() -> list[dict]` şemaları döner.

**`meclaw/agent.py`** — `run_agent(provider, model, history, registry, new_messages: list[dict]) -> AsyncIterator[AgentEvent]`. `AgentEvent` tipleri `text` ve `tool` (ad, argümanlar, sonuç) olur:

1. Mesajları sistem istemi + geçmiş olarak kurar (sistem istemi mevcut `server.py`'deki metinden alınır).
2. En fazla 5 tur: provider'dan akışı okur, `text` parçalarını dışarı yayar.
3. Tur `tool_calls` ile bittiyse: asistan mesajını (araç çağrılarıyla) geçmişe ekler, her aracı `run_tool` ile çalıştırır, `tool` olayını dışarı yayar ve `tool` mesajını geçmişe ekler; sonra yeni tura geçer.
4. Araç çağrısı yoksa döngü biter.
5. Tur limiti aşılırsa bir uyarı metni yayar.

Üretilen her asistan ve tool mesajı, üretildiği anda çağıranın verdiği `new_messages` listesine eklenir. Böylece provider hatasıyla akış yarıda kesilse bile `server.py` o ana kadarki mesajları kaydedebilir. Yarıda kalan bir turun kısmi metni de asistan mesajı olarak eklenir.

**`meclaw/storage.py`** — `sqlite3` (standart kütüphane), dosya varsayılan olarak `data/meclaw.db` (`.gitignore`'a eklenir).

```sql
conversations(id TEXT PK, title TEXT, provider TEXT, model TEXT, created_at TEXT, updated_at TEXT)
messages(id INTEGER PK AUTOINCREMENT, conversation_id TEXT FK ON DELETE CASCADE,
         role TEXT, content TEXT, tool_calls TEXT NULL, tool_call_id TEXT NULL,
         name TEXT NULL, created_at TEXT)
```

Fonksiyonlar: `create_conversation`, `list_conversations`, `get_conversation` (mesajlarla), `delete_conversation`, `add_messages`, `touch_conversation`. Sohbet başlığı ilk kullanıcı mesajının ilk 40 karakteridir. Sohbet son kullanılan sağlayıcı/modeli saklar, böylece açıldığında seçiciler ona göre ayarlanır.

**`server.py`** — FastAPI uygulaması; `uvicorn.run(app, host="127.0.0.1", port=8000)` ile başlar.

| Uç nokta | Açıklama |
|---|---|
| `GET /` | `static/index.html` |
| `GET /api/providers` | `[{"name": "ollama", "ready": true, "reason": ""}, ...]` |
| `GET /api/models?provider=` | `{"models": [...]}`; sağlayıcı hazır değilse 503 |
| `GET /api/conversations` | sohbet listesi (son güncellenen önce) |
| `POST /api/conversations` | boş sohbet oluşturur |
| `GET /api/conversations/{id}` | sohbet + mesajlar (`system` hariç) |
| `DELETE /api/conversations/{id}` | sohbeti siler |
| `POST /api/chat` | gövde `{conversation_id, provider, model, message}`; yanıt `text/event-stream` |

SSE olayları:

```
event: text    data: {"text": "..."}
event: tool    data: {"name": "create_file_tool", "arguments": {...}, "result": "..."}
event: error   data: {"message": "..."}
event: done    data: {"conversation_id": "..."}
```

Kullanıcı mesajı akış başlamadan kaydedilir; asistan ve tool mesajları akış bitince (hata olsa bile o ana kadar üretilenler) kaydedilir.

### Arayüz (`static/`)

- Sol kenar çubuğu: "Yeni sohbet" düğmesi, sohbet listesi (başlık, silme düğmesi).
- Üst çubuk: sağlayıcı seçici, model seçici. Pasif sağlayıcılar `disabled` ve nedeni `title` ile gösterilir. Son seçim `localStorage`'da tutulur (try/catch ile).
- Mesaj alanı: kullanıcı ve asistan baloncukları; asistan metni akarken eklenir. Araç çağrıları küçük katlanabilir etiketler olarak gösterilir (ad + sonuç).
- Giriş: çok satırlı metin kutusu, Enter gönderir, Shift+Enter yeni satır; yanıt sürerken gönder düğmesi devre dışı.
- Markdown: asistan metni için basit güvenli işleme (kod blokları, satır içi kod, kalın, listeler); HTML her zaman kaçışlanır. Harici kütüphane kullanılmaz.
- Açık/koyu tema `prefers-color-scheme` ile.
- `fetch` + `ReadableStream` ile SSE okunur (`EventSource` POST desteklemediği için).

## Güvenlik

- `Explorer._build_path`: `(self.base_dir / name).resolve()` sonucunun `base_dir` içinde olduğu `Path.is_relative_to` ile doğrulanır; değilse `ValueError` fırlatılır ve her metot bunu `"Path is outside the workspace."` mesajına çevirir.
- Sunucu yalnızca `127.0.0.1`'e bağlanır.
- `OPENAI_API_KEY` yalnızca `.env`'den okunur; arayüze veya loglara yazılmaz.

## Hata yönetimi

- Provider hataları (bağlantı, kimlik, model bulunamadı) `agent` içinde yakalanmaz, `server.py`'de yakalanır ve `error` SSE olayına çevrilir; akış `done` ile kapanır.
- Araç hataları `run_tool` içinde metne çevrilir ve modele geri verilir.
- `/api/providers` hiçbir zaman 500 dönmez; her sağlayıcının durumu ayrı ayrı denetlenir.

## Temizlik

- Silinecek: `tools/finder/explorer.py`, `server.py` içindeki tüm Telegram kodu ve `*_tool` sarmalayıcıları.
- `requirements.txt`: `python-telegram-bot` ve `requests` çıkar; `fastapi`, `uvicorn`, `openai`, `pytest`, `httpx` girer.
- `.env.example`: `TELEGRAM_API` çıkar; `OLLAMA_HOST=http://localhost:11434`, `OPENAI_API_KEY=` eklenir.
- `start.bat`: Ollama kontrolü uyarıya dönüşür (OpenAI ile Ollama olmadan da çalışılabilir), `python server.py` çalıştırılır ve tarayıcı `http://127.0.0.1:8000` adresinde açılır.
- `.gitignore`: `data/` eklenir.
- `README.md`: yeni kurulum, çalıştırma ve özellikler; olmayan dosyalara referanslar kaldırılır.

## Test

`pytest` ile, ağ erişimi olmadan:

- `tests/test_explorer_paths.py`: `../` ve mutlak yollarla klasör dışına çıkma reddedilir; normal alt klasör yolları çalışır.
- `tests/test_registry.py`: bilinen araç çalışır, bilinmeyen araç ve hatalı argüman metin döner.
- `tests/test_agent.py`: sahte bir provider ile — araç çağrısı sonrası sonucun `tool` mesajı olarak modele geri verildiği, ikinci turdaki metnin yayıldığı ve tur limitinin uygulandığı doğrulanır.
- `tests/test_storage.py`: geçici bir veritabanıyla sohbet oluşturma, mesaj ekleme, listeleme, silme (cascade).
- `tests/test_server.py`: `TestClient` ve sahte provider ile `/api/providers`, sohbet CRUD ve `/api/chat` SSE olay sırası.

Testlerde `Explorer` geçici bir klasörle (`tmp_path`) kurulur; `testdir` içeriği değiştirilmez.

Elle doğrulama: sunucuyu başlatıp tarayıcıda Ollama (yüklü bir modelle) ve — anahtar varsa — OpenAI ile bir sohbet ve bir dosya oluşturma isteği denenir.
