# MeClaw Araç Paketi — Uygulama Planı

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Dosya araçlarını düzeltip arama/düzenleme, belge, web, tarih/hesap ve hafıza araçları eklemek; silme ve üzerine yazmadan önce sohbet içinde onay almak.

**Architecture:** Araçlar `meclaw/tools/` altında modüllere bölünür; her araç `ToolSpec` (şema + handler + onay kuralı) olarak tanımlanır ve `build_registry(ToolContext)` açık grupları kayda alır. Agent araçları async çalıştırır ve onay gereken çağrılarda bir `confirm` kancasını bekler; sunucu bu kancayı SSE `confirm` olayı + `POST /api/chat/confirm` ile gerçekler. Hafıza SQLite'ta tutulur ve sistem istemine eklenir.

**Tech Stack:** Python 3.12, FastAPI, httpx, pypdf 6.x, openpyxl 3.1.x, ddgs 9.x, sqlite3, sade JS.

**Spec:** `docs/superpowers/specs/2026-10-25-tools-pack-design.md`

## Global Constraints

- Araç adlarında `_tool` son eki yok: `create_file, delete_file, copy_file, read_file, write_file, rename_file, write_word_file, read_word_file, create_folder, remove_folder, list_items, move_item, rename_folder, copy_folder, zip_folder, extract_archive, search_files, edit_file, file_info, read_pdf, read_spreadsheet, write_spreadsheet, fetch_url, web_search, get_datetime, calculate, remember, forget`.
- Araç sonuçları modele İngilizce metin; kullanıcıya görünen onay açıklamaları Türkçe.
- `ToolRegistry.run` asla exception fırlatmaz: `Unknown tool: <ad>`, `Invalid arguments for <ad>: …`, `Tool <ad> failed: …`; sonuç 20000 karakterde `\n…(truncated)` ile kesilir.
- Klasör dışı yol: `Path is outside the workspace.` (mevcut `Explorer` davranışı).
- Onay zaman aşımı 300 sn; red/zaman aşımı/kancasız durumda araç sonucu `Denied by the user: <açıklama>`.
- `fetch_url`: yalnızca http/https; loopback/özel/link-local/ayrılmış/multicast adresler reddedilir (her yönlendirmede de); en fazla 5 yönlendirme; 10 sn; gövde ≤ 2 MB (2_000_000 bayt).
- `web_search`: `ddgs.DDGS().text(query, region="tr-tr", max_results=n)`, n ≤ 10, varsayılan 5.
- `calculate`: ifade ≤ 200 karakter, üs ≤ 1000, yalnızca spec'teki izinli düğümler/fonksiyonlar.
- Hafıza notu ≤ 500 karakter; sistem istemine en yeni 100 not.
- Ayarlar: `MECLAW_INTERNET`, `MECLAW_MEMORY`; `"0","false","off","no"` (büyük/küçük harf duyarsız) kapalı, diğer/boş açık; açık değer `.env`'den silinir, kapalı `0` yazılır.
- Yazma yapan yeni uç noktalar (`/api/chat/confirm`, `/api/memories` POST/PUT/DELETE) mevcut `require_local` korumasını kullanır.
- Bağımlılıklar: `pypdf>=6,<7`, `openpyxl>=3.1,<4`, `ddgs>=9,<10`.
- Testler ağa çıkmaz; `tmp_path`; async testler `asyncio.run` ile (eklenti yok).

## Review Focus

1. Model aynı turda iki onaylı işlem ister (iki silme) → iki kart sırayla çıkar, her biri ayrı karar alır; birinin reddi diğerini etkilemez. (Task 6: `test_two_confirmations_in_one_turn`)
2. Kullanıcı karar düğmesine akış bittikten/zaman aşımından sonra basar → 404, arayüz kartı "Süresi doldu" gösterir, hiçbir işlem yapılmaz. (Task 6: `test_confirm_after_resolution_404`; Task 8 arayüz davranışı)
3. Çok dosyalı workspace'te `list_items(recursive)` ve `search_files` → çıktı sınırlı kalır, yanıt makul sürede gelir. (Task 1: `test_list_items_recursive_limit`; Task 2: `test_search_files_result_limit`)
4. Adı hem genel hem özel IP'ye çözülen bir alan adı → reddedilir. (Task 5: `test_fetch_rejects_mixed_resolution`)
5. İnternet ayarı sohbet ortasında kapatılır; geçmişte `web_search` çağrıları var, model yine de çağırır → `Unknown tool: web_search` döner, sohbet bozulmaz. (Task 7: `test_disabled_internet_tool_unknown`)

---

### Task 1: Araç çekirdeği ve dosya araçlarının taşınması

**Files:**
- Create: `meclaw/tools/base.py`, `meclaw/tools/files.py`
- Modify: `meclaw/tools/__init__.py` (`build_registry`), `meclaw/agent.py` (async `run`), `server.py` (yeni kayıt, `make_registry(settings)`), `tests/fakes.py` (`make_registry` yardımcısı), mevcut testlerde araç adları ve kayıt kurulumu (`test_agent.py`, `test_server.py`, `test_settings_api.py`, `test_files_api.py`, `test_registry.py` → `test_tools_base.py` olarak yeniden yazılır), `tests/test_ollama_provider.py` adlar
- Delete: `meclaw/tools/registry.py`, `tools/finder/tool_definitions.json`
- Test: `tests/test_tools_base.py`, `tests/test_tools_files.py`

**Interfaces:**
- Produces (`meclaw/tools/base.py`):
  - `Confirmation(description: str, preview: str = "")` dataclass
  - `ToolContext(explorer: Explorer, storage: Storage | None = None, internet: bool = True, memory: bool = True)` dataclass
  - `ToolSpec(name: str, description: str, parameters: dict, handler: Callable, confirm: Callable[[ToolContext, dict], Confirmation | None] | None = None)` — handler çağrısı `handler(ctx, **args)`, `str` ya da `Awaitable[str]` döner
  - `ToolRegistry(ctx: ToolContext, specs: list[ToolSpec])`: `explorer` (property), `definitions() -> list[dict]` (`{"type":"function","function":{"name","description","parameters"}}`), `names() -> set[str]`, `needs_confirmation(name: str, arguments: dict | None) -> Confirmation | None`, `async run(name: str, arguments: dict | None) -> str`
  - `MAX_RESULT_CHARS = 20000`
- Produces (`meclaw/tools/files.py`): `FILE_TOOLS: list[ToolSpec]` (16 araç; bu görevde `confirm=None`, Task 2 ekler)
- Produces (`meclaw/tools/__init__.py`): `build_registry(ctx: ToolContext) -> ToolRegistry` (bu görevde yalnızca `FILE_TOOLS`; sonraki görevler kendi listelerini ekler)
- Produces (`tests/fakes.py`): `make_registry(path, **ctx_kwargs) -> ToolRegistry` → `build_registry(ToolContext(Explorer(path), **ctx_kwargs))`
- Produces (`server.py`): `create_app(..., make_registry: Callable[[Settings], ToolRegistry] | None = None, ...)`; `build_registry_for(settings: Settings) -> ToolRegistry` (eski `build_registry(workspace)` yerine); `make_registry` workspace değişince çağrılır (Task 7 internet/hafıza bayraklarını ekler).
- Agent: `registry.run` artık `await` edilir; başka davranış değişmez.

- [ ] **Step 1: Başarısız testleri yaz**

`tests/test_tools_base.py`:

```python
def test_definitions_shape_and_names(tmp_path):
    reg = make_registry(tmp_path)
    names = {d["function"]["name"] for d in reg.definitions()}
    assert names == reg.names() and {"create_file", "list_items", "read_file"} <= names
    assert all(not n.endswith("_tool") for n in names)
    assert all(d["type"] == "function" and d["function"]["parameters"]["type"] == "object" for d in reg.definitions())

def test_unknown_and_bad_args(tmp_path):
    reg = make_registry(tmp_path)
    assert asyncio.run(reg.run("nope", {})) == "Unknown tool: nope"
    assert asyncio.run(reg.run("create_file", {"wrong": 1})).startswith("Invalid arguments for create_file")

def test_sync_and_async_handlers_and_failure(tmp_path):
    async def ahandler(ctx, x): return f"async {x}"
    def boom(ctx): raise RuntimeError("kaboom")
    reg = ToolRegistry(ToolContext(Explorer(tmp_path)), [
        ToolSpec("a", "", {"type": "object", "properties": {}}, ahandler),
        ToolSpec("b", "", {"type": "object", "properties": {}}, boom),
    ])
    assert asyncio.run(reg.run("a", {"x": 1})) == "async 1"
    assert asyncio.run(reg.run("b", None)) == "Tool b failed: kaboom"

def test_result_truncated(tmp_path):
    reg = ToolRegistry(ToolContext(Explorer(tmp_path)), [ToolSpec("big", "", {"type": "object", "properties": {}}, lambda ctx: "x" * 20001)])
    assert asyncio.run(reg.run("big", {})) == "x" * 20000 + "\n…(truncated)"

def test_needs_confirmation_swallows_errors(tmp_path):
    def bad(ctx, args): raise ValueError("x")
    reg = ToolRegistry(ToolContext(Explorer(tmp_path)), [ToolSpec("t", "", {"type": "object", "properties": {}}, lambda ctx: "ok", confirm=bad)])
    assert reg.needs_confirmation("t", {}) is None and reg.needs_confirmation("nope", {}) is None
```

`tests/test_tools_files.py` (bu görevdeki kısım; `run = lambda name, **a: asyncio.run(reg.run(name, a))`):

```python
def test_list_items_path_and_root(tmp_path): ...
    # kökte "a.txt" ve "sub/"; sub içinde "b.txt"
    assert run("list_items").startswith("Workspace contents:") and "📁 sub" in run("list_items")
    assert "📄 b.txt" in run("list_items", path="sub") and "a.txt" not in run("list_items", path="sub")
    assert run("list_items", path="..") == "Path is outside the workspace."

def test_list_items_recursive(tmp_path):
    out = run("list_items", recursive=True)
    assert "📁 sub" in out and "  📄 b.txt" in out   # alt öğeler iki boşluk girintili

def test_list_items_recursive_limit(tmp_path):
    # 600 dosya
    out = run("list_items", recursive=True)
    assert out.count("📄") == 500 and out.rstrip().endswith("… (100 more)")

def test_read_file_range(tmp_path):
    # "l1\nl2\nl3\nl4\n"
    assert run("read_file", filename="f.txt", start_line=2, end_line=3) == "Lines 2-3 of 4:\nl2\nl3"
    assert run("read_file", filename="f.txt") == "l1\nl2\nl3\nl4\n"
    assert run("read_file", filename="f.txt", start_line=3) == "Lines 3-4 of 4:\nl3\nl4"

def test_ported_tools_behave_as_before(tmp_path):
    assert run("create_file", filename="x.txt") == "File 'x.txt' created successfully."
    assert run("write_file", filename="x.txt", content="hi") .startswith("File 'x.txt'")
    assert run("delete_file", filename="x.txt") == "File 'x.txt' deleted successfully."
```

- [ ] **Step 2: Testlerin başarısız olduğunu gör**

Run: `python -m pytest tests/test_tools_base.py tests/test_tools_files.py -q`
Expected: FAIL (ImportError `meclaw.tools.base`).

- [ ] **Step 3: Uygula**

- `base.py`: `run` senkron handler'ı `asyncio.to_thread` ile çalıştırır; sonucu `str()` yapıp keser. Şema `parameters` olduğu gibi kullanılır.
- `files.py`: her araç için şema (açıklamalar İngilizce, kısa) + `Explorer` metodunu çağıran handler. `list_items` ve `read_file` yeni parametrelerle; `list_items` çıktısı `Workspace contents:` başlığı, boş klasörde `No items found.`, recursive'de girinti iki boşluk/seviye, en fazla 500 öğe satırı. `read_file` aralığı satırları `splitlines()` ile alır, `end_line` dosya sonunu aşarsa kırpılır, `start_line` < 1 ya da > satır sayısı → `Invalid line range.`.
- Eski kayıt ve JSON silinir; `server.py`, agent ve testler yeni kayda geçer (araç adları `_tool`'suz).

- [ ] **Step 4: Tüm testlerin geçtiğini gör**

Run: `python -m pytest -q`
Expected: tümü PASS.

- [ ] **Step 5: Commit**

```bash
git add -A meclaw tests server.py tools/finder
git commit -m "refactor: tool specs registry with async tools; extend list_items and read_file"
```

---

### Task 2: Yeni dosya araçları ve onay kuralları

**Files:**
- Modify: `meclaw/tools/files.py`
- Test: `tests/test_tools_files.py`

**Interfaces:**
- Consumes: `ToolSpec`, `Confirmation`, `ToolContext` (Task 1)
- Produces: `search_files`, `edit_file`, `file_info` araçları `FILE_TOOLS` içinde; spec'teki "Onay kuralları" tablosunun tamamı ilgili araçların `confirm` alanında.

- [ ] **Step 1: Başarısız testleri yaz**

```python
def test_search_by_name_and_content(tmp_path):
    # notlar/fatura.md içeriği "Ekim faturası ğüş\nikinci satır"; a.txt "FATURA no 5"; resim.bin ikili
    assert "notlar/fatura.md" in run("search_files", name_pattern="*.MD")
    out = run("search_files", query="fatura")
    assert "notlar/fatura.md:1: Ekim faturası ğüş" in out and "a.txt:1: FATURA no 5" in out and "resim.bin" not in out
    assert "a.txt" not in run("search_files", query="fatura", name_pattern="*.md")
    assert run("search_files") == "Provide query or name_pattern."

def test_search_files_result_limit(tmp_path):
    # 60 dosya, her biri "eşleşme"
    out = run("search_files", query="eşleşme")
    assert out.count("\n") + 1 == 51 and out.endswith("(results limited to 50)")

def test_search_skips_large_files(tmp_path):
    # 1_000_001 baytlık metin dosyası "iğne" içeriyor
    assert "No matches." == run("search_files", query="iğne")

def test_edit_file_replace(tmp_path):
    # f.txt "a\nb\nc\n"
    assert run("edit_file", filename="f.txt", old_text="b", new_text="B") == "Edited 'f.txt'."
    assert (ws / "f.txt").read_text() == "a\nB\nc\n"
    assert run("edit_file", filename="f.txt", old_text="zzz", new_text="x") == "Text not found in 'f.txt'."
    # "x x" içeren dosyada old_text="x"
    assert run("edit_file", filename="g.txt", old_text="x", new_text="y") == "Text occurs 2 times in 'g.txt'; give a longer, unique snippet."
    assert run("edit_file", filename="yok.txt", old_text="a", new_text="b") == "File 'yok.txt' not found."

def test_edit_file_append(tmp_path):
    # f.txt "son" (satır sonu yok)
    run("edit_file", filename="f.txt", new_text="yeni", mode="append")
    assert (ws / "f.txt").read_text() == "son\nyeni"

def test_file_info(tmp_path):
    out = run("file_info", path="f.txt")
    assert "Type: file" in out and "Size: " in out and "Lines: 3" in out and "Modified: " in out
    assert "Type: folder" in run("file_info", path="sub") and "Items: " in run("file_info", path="sub")

@pytest.mark.parametrize("name,args,setup,expected", [
    ("delete_file", {"filename": "a.txt"}, "a.txt", "‘a.txt’ silinecek."),
    ("delete_file", {"filename": "yok.txt"}, None, None),
    ("remove_folder", {"folder_name": "sub"}, "sub/", "‘sub’ klasörü silinecek."),
    ("edit_file", {"filename": "a.txt", "old_text": "x", "new_text": "y"}, "a.txt", "‘a.txt’ düzenlenecek."),
    ("write_file", {"filename": "a.txt", "content": "z"}, "a.txt", "‘a.txt’ üzerine yazılacak."),
    ("write_file", {"filename": "yeni.txt", "content": "z"}, None, None),
    ("write_word_file", {"filename": "r.docx", "content": "z"}, "r.docx", "‘r.docx’ üzerine yazılacak."),
    ("copy_file", {"source_filename": "a.txt", "destination_filename": "b.txt"}, "a.txt,b.txt", "‘b.txt’ üzerine yazılacak (‘a.txt’ kopyalanıyor)."),
    ("copy_file", {"source_filename": "a.txt", "destination_filename": "c.txt"}, "a.txt", None),
    ("move_item", {"source_path": "a.txt", "destination_path": "b.txt"}, "a.txt,b.txt", "‘b.txt’ üzerine yazılacak (‘a.txt’ taşınıyor)."),
    ("rename_file", {"old_filename": "a.txt", "new_filename": "b.txt"}, "a.txt,b.txt", "‘b.txt’ üzerine yazılacak (‘a.txt’ yeniden adlandırılıyor)."),
    ("rename_folder", {"old_folder_name": "sub", "new_folder_name": "sub2"}, "sub/,sub2/", "‘sub2’ üzerine yazılacak (‘sub’ yeniden adlandırılıyor)."),
    ("copy_folder", {"source_folder_name": "sub", "destination_folder_name": "sub2"}, "sub/,sub2/", "‘sub2’ üzerine yazılacak (‘sub’ kopyalanıyor)."),
    ("zip_folder", {"folder_name": "sub"}, "sub/,sub.zip", "‘sub.zip’ üzerine yazılacak."),
    ("extract_archive", {"archive_name": "a.zip", "destination_folder": "out"}, "a.zip,out/x.txt", "‘out’ klasörüne açılacak; aynı adlı dosyalar değişebilir."),
    ("extract_archive", {"archive_name": "a.zip", "destination_folder": "bos"}, "a.zip,bos/", None),
    ("create_file", {"filename": "a.txt"}, "a.txt", None),
])
def test_confirmation_rules(tmp_path, name, args, setup, expected):
    # setup: virgülle ayrılmış yollar; "/" ile biten klasör oluşturur
    c = reg.needs_confirmation(name, args)
    assert (c.description if c else None) == expected

def test_edit_confirmation_preview(tmp_path):
    c = reg.needs_confirmation("edit_file", {"filename": "a.txt", "old_text": "eski", "new_text": "yeni"})
    assert c.preview == "- eski\n+ yeni"
    c2 = reg.needs_confirmation("write_file", {"filename": "a.txt", "content": "y" * 1000})
    assert len(c2.preview) <= 600
```

- [ ] **Step 2: Başarısız olduğunu gör** — `python -m pytest tests/test_tools_files.py -q` → yeni testler FAIL.

- [ ] **Step 3: Uygula**

- `search_files(query="", name_pattern="", path="")`: `Explorer.resolve(path)` altında `rglob("*")`, yalnızca dosyalar, göreli POSIX yol sırasıyla. Ad eşleşmesi `fnmatch` (her ikisi `casefold()`), içerik eşleşmesi satır bazında `casefold()` alt dize; ≤ 1_000_000 bayt ve UTF-8 çözülebilen dosyalar. Hem `query` hem `name_pattern` varsa ikisi birden sağlanmalı (adı uyan dosyalarda içerik araması). 50 sonuçtan sonra durur ve son satır `(results limited to 50)`; hiç yoksa `No matches.`
- `edit_file` metinleri `newline=""` ile okur/yazar (satır sonları korunur).
- Onay önizlemesi: `edit_file` replace → `- <old>\n+ <new>` (her biri 280 karakterde kesilir); append → `+ <new>`; yazma araçları → yeni içeriğin ilk 600 karakteri; diğerleri boş.

- [ ] **Step 4: Geçtiğini gör** — `python -m pytest -q` → PASS.

- [ ] **Step 5: Commit** — `git commit -m "feat: search_files, edit_file, file_info and confirmation rules"`

---

### Task 3: Belge araçları

**Files:**
- Create: `meclaw/tools/documents.py`
- Modify: `meclaw/tools/__init__.py` (`DOCUMENT_TOOLS` her zaman), `requirements.txt` (`pypdf>=6,<7`, `openpyxl>=3.1,<4`)
- Test: `tests/test_tools_documents.py`

**Interfaces:**
- Consumes: Task 1/2 çekirdeği, `Confirmation`
- Produces: `DOCUMENT_TOOLS: list[ToolSpec]` → `read_pdf`, `read_spreadsheet`, `write_spreadsheet` (sonuncusu hedef varsa `‘<ad>’ üzerine yazılacak.` onayı ve ilk satırların önizlemesi)

- [ ] **Step 1: Bağımlılıkları kur** — `python -m pip install -r requirements.txt`; `python -c "import pypdf, openpyxl"` çalışır.

- [ ] **Step 2: Başarısız testleri yaz**

Test yardımcısı `make_pdf(path, pages: list[str])`: her sayfa için `BT /F1 12 Tf 72 720 Td (<metin>) Tj ET` içerik akışlı, Helvetica fontlu, doğru `xref` tablosuyla ham PDF yazar (ASCII metin).

```python
def test_read_pdf_pages(tmp_path):
    make_pdf(ws / "r.pdf", ["Birinci sayfa", "Second page", "Third"])
    out = run("read_pdf", filename="r.pdf")
    assert out.startswith("Pages 1-3 of 3:") and "Second page" in out
    assert run("read_pdf", filename="r.pdf", start_page=2, end_page=2) == "Pages 2-2 of 3:\n\nSecond page"
    assert run("read_pdf", filename="r.pdf", start_page=5) == "Invalid page range."

def test_read_pdf_page_cap(tmp_path):
    make_pdf(ws / "big.pdf", [f"p{i}" for i in range(40)])
    assert run("read_pdf", filename="big.pdf").startswith("Pages 1-30 of 40:")

def test_spreadsheet_roundtrip_xlsx(tmp_path):
    assert run("write_spreadsheet", filename="t.xlsx", rows=[["Ad", "Tutar"], ["Çay", 12.5], ["Şeker", None]]) == "Wrote 3 rows to 't.xlsx'."
    out = run("read_spreadsheet", filename="t.xlsx")
    assert "Sheets: Sayfa1" in out and "Sayfa1: 3 rows x 2 columns" in out
    assert "| Ad | Tutar |" in out and "| Çay | 12.5 |" in out and "| Şeker |  |" in out

def test_read_csv_semicolon_and_bom(tmp_path):
    (ws / "d.csv").write_text("﻿ad;yaş\nAli;30\n", encoding="utf-8")
    assert "| ad | yaş |" in run("read_spreadsheet", filename="d.csv")

def test_read_spreadsheet_max_rows_and_sheet(tmp_path):
    # 300 satırlık xlsx, iki sayfa "A" ve "B"
    out = run("read_spreadsheet", filename="m.xlsx", sheet="B", max_rows=500)
    assert "B: 300 rows" in out and out.count("\n| ") <= 201
    assert run("read_spreadsheet", filename="m.xlsx", sheet="Z") == "Sheet 'Z' not found. Sheets: A, B"

def test_write_spreadsheet_bad_extension(tmp_path):
    assert run("write_spreadsheet", filename="t.ods", rows=[["a"]]) == "Use a .xlsx or .csv file name."

def test_write_spreadsheet_confirmation(tmp_path):
    run("write_spreadsheet", filename="t.csv", rows=[["a"]])
    c = reg.needs_confirmation("write_spreadsheet", {"filename": "t.csv", "rows": [["b"]]})
    assert c.description == "‘t.csv’ üzerine yazılacak."
```

- [ ] **Step 3: Başarısız olduğunu gör** — `python -m pytest tests/test_tools_documents.py -q` → FAIL.

- [ ] **Step 4: Uygula** — Markdown tablosunda `|` karakteri `\|` olarak kaçışlanır, `None` boş hücre; ilk satır başlık kabul edilip ardından `|---|` satırı. CSV yazımı `utf-8-sig`, `,` ayraç. xlsx okumada `wb.close()` (Windows dosya kilidi).

- [ ] **Step 5: Geçtiğini gör** — `python -m pytest -q` → PASS.

- [ ] **Step 6: Commit** — `git commit -m "feat: PDF and spreadsheet tools"`

---

### Task 4: Tarih ve hesap araçları

**Files:**
- Create: `meclaw/tools/utils.py`
- Modify: `meclaw/tools/__init__.py` (`UTIL_TOOLS` her zaman)
- Test: `tests/test_tools_utils.py`

**Interfaces:**
- Produces: `UTIL_TOOLS` → `get_datetime`, `calculate`; modül düzeyinde `format_datetime(dt: datetime) -> str` ve `safe_eval(expression: str) -> int | float` (ValueError fırlatır)

- [ ] **Step 1: Başarısız testleri yaz**

```python
def test_format_datetime():
    dt = datetime(2026, 10, 25, 21, 40, tzinfo=timezone(timedelta(hours=3)))
    assert format_datetime(dt) == "2026-10-25 21:40, Pazar (25 Ekim 2026), UTC+03:00"

@pytest.mark.parametrize("expr,value", [
    ("1234*5678", 7006652), ("2**10", 1024), ("(1+2)*3/4", 2.25), ("sqrt(16)+pi", 4 + math.pi),
    ("max(3, 7, 2)", 7), ("round(2.567, 2)", 2.57), ("-5 % 3", 1), ("7 // 2", 3),
])
def test_calculate_ok(expr, value):
    assert safe_eval(expr) == pytest.approx(value)

@pytest.mark.parametrize("expr", [
    "__import__('os')", "().__class__", "open('x')", "a", "2**10001", "x" * 201, "lambda: 1", "[1, 2]", "1 if 1 else 2",
])
def test_calculate_rejects(expr):
    assert run("calculate", expression=expr).startswith("Unsupported expression") or "too long" in run("calculate", expression=expr)

def test_calculate_tool_output():
    assert run("calculate", expression="1234*5678") == "1234*5678 = 7006652"
    assert run("calculate", expression="1/0") == "Error: division by zero"
```

- [ ] **Step 2: Başarısız olduğunu gör** → FAIL.

- [ ] **Step 3: Uygula** — Gün/ay adları sabit Türkçe listeler; `get_datetime` `datetime.now().astimezone()`. `safe_eval` `ast.parse(mode="eval")` + izinli düğüm beyaz listesi (`Expression, BinOp, UnaryOp, Constant(int/float), Call(Name), Name(pi/e)`, operatörler spec'teki), `**` sağ operandı > 1000 → ValueError; ifade > 200 karakter → `Expression too long (max 200 characters).`; diğer → `Unsupported expression`. `calculate` sonucu: tam sayıya eşit float'lar int gösterilir.

- [ ] **Step 4: Geçtiğini gör** → PASS. **Step 5: Commit** — `git commit -m "feat: get_datetime and safe calculate tools"`

---

### Task 5: Web araçları

**Files:**
- Create: `meclaw/tools/web.py`
- Modify: `meclaw/tools/__init__.py` (`WEB_TOOLS` yalnızca `ctx.internet`), `requirements.txt` (`ddgs>=9,<10`)
- Test: `tests/test_tools_web.py`

**Interfaces:**
- Produces: `WEB_TOOLS` → `fetch_url`, `web_search`; modül düzeyinde `html_to_text(html: str) -> tuple[str, str]` (başlık, metin), `check_public_host(host: str) -> None` (ValueError `Blocked address: <host>`), `async fetch(url: str, transport: httpx.AsyncBaseTransport | None = None) -> str` (testler sahte transport geçer), `_resolve` (`socket.getaddrinfo` sarmalayıcı, testte monkeypatch'lenir), `_ddgs_text(query, max_results) -> list[dict]` (testte monkeypatch'lenir).

- [ ] **Step 1: Kur** — `python -m pip install -r requirements.txt`; `python -c "from ddgs import DDGS"`.

- [ ] **Step 2: Başarısız testleri yaz**

```python
def test_html_to_text():
    title, text = html_to_text("<html><head><title>Başlık</title><style>x{}</style></head><body><nav>menü</nav><h1>Selam</h1><p>bir  <b>iki</b></p><script>kötü()</script><footer>alt</footer></body></html>")
    assert title == "Başlık" and "Selam" in text and "bir iki" in text
    assert "menü" not in text and "kötü" not in text and "alt" not in text and "x{}" not in text

@pytest.mark.parametrize("ip", ["127.0.0.1", "10.0.0.5", "192.168.1.10", "172.16.0.1", "169.254.1.1", "::1", "0.0.0.0", "224.0.0.1"])
def test_blocked_ips(monkeypatch, ip):
    monkeypatch.setattr(web, "_resolve", lambda host: [ip])
    with pytest.raises(ValueError, match="Blocked address"):
        check_public_host("ornek.com")

def test_fetch_rejects_mixed_resolution(monkeypatch):
    monkeypatch.setattr(web, "_resolve", lambda host: ["93.184.216.34", "10.0.0.1"])
    assert asyncio.run(fetch("https://ornek.com")) == "Blocked address: ornek.com"

def test_fetch_html(monkeypatch):
    public(monkeypatch)  # _resolve → ["93.184.216.34"]
    t = httpx.MockTransport(lambda r: httpx.Response(200, headers={"content-type": "text/html; charset=utf-8"}, text="<title>T</title><p>içerik</p>"))
    out = asyncio.run(fetch("https://ornek.com/a", transport=t))
    assert out.startswith("Title: T\nURL: https://ornek.com/a\n") and "içerik" in out

def test_fetch_redirect_to_private_blocked(monkeypatch):
    # ornek.com public, ic.local → 192.168.1.2; ilk yanıt 302 Location: http://ic.local/
    assert asyncio.run(fetch("https://ornek.com", transport=t)) == "Blocked address: ic.local"

def test_fetch_too_many_redirects(monkeypatch):
    # her yanıt 302 kendine
    assert asyncio.run(fetch("https://ornek.com", transport=t)) == "Too many redirects."

def test_fetch_scheme_and_type(monkeypatch):
    assert asyncio.run(fetch("file:///etc/passwd")) == "Only http and https URLs are supported."
    # application/pdf yanıtı
    assert asyncio.run(fetch("https://ornek.com/x.pdf", transport=t)) == "Unsupported content type: application/pdf"

def test_fetch_size_cap(monkeypatch):
    # 3_000_000 baytlık text/plain
    out = asyncio.run(fetch("https://ornek.com/b", transport=t))
    assert out.endswith("[content truncated at 2 MB]")

def test_web_search(monkeypatch):
    monkeypatch.setattr(web, "_ddgs_text", lambda q, n: [{"title": "Başlık", "href": "https://a.com", "body": "özet"}])
    assert run("web_search", query="x") == "1. Başlık\n   https://a.com\n   özet"
    monkeypatch.setattr(web, "_ddgs_text", lambda q, n: (_ for _ in ()).throw(RuntimeError("ratelimit")))
    assert run("web_search", query="x") == "Web search failed: ratelimit"

def test_web_tools_only_when_internet(tmp_path):
    assert "fetch_url" in make_registry(tmp_path).names()
    assert not {"fetch_url", "web_search"} & make_registry(tmp_path, internet=False).names()
```

- [ ] **Step 3: Başarısız olduğunu gör** → FAIL.

- [ ] **Step 4: Uygula** — `fetch`: `httpx.AsyncClient(follow_redirects=False, timeout=10, transport=transport, headers={"User-Agent": "MeClaw/1.0"})`; her adımda şema + `check_public_host`; `client.stream("GET", …)` ile en fazla 2_000_000 bayt okunur; içerik türü `text/html` → `html_to_text`, `text/plain` ve `application/json` → metin olarak. Hata metinleri: `Request timed out.`, `Could not resolve host: <host>`, `HTTP <kod>` (4xx/5xx). `html_to_text` stdlib `HTMLParser`, atlanan etiketler spec'te; blok etiketler (`p, div, br, li, h1-h6, tr, section, article`) satır sonu ekler; boş satırlar tekleştirilir. `web_search` `asyncio.to_thread(_ddgs_text, query, min(max_results, 10))`.

- [ ] **Step 5: Geçtiğini gör** → PASS. **Step 6: Commit** — `git commit -m "feat: fetch_url with private address guard and DuckDuckGo web_search"`

---

### Task 6: Onay akışı (agent + sunucu)

**Files:**
- Modify: `meclaw/agent.py`, `server.py`
- Test: `tests/test_agent.py`, `tests/test_confirm_api.py` (yeni)

**Interfaces:**
- Consumes: `ToolRegistry.needs_confirmation`, `Confirmation` (Task 1/2)
- Produces (`meclaw/agent.py`):
  - `ConfirmRequest(id: str, name: str, arguments: dict, description: str, preview: str)` dataclass
  - `AgentEvent.type` ∈ `"text" | "tool" | "confirm" | "confirm_result"`; yeni alanlar `id: str = ""`, `description: str = ""`, `preview: str = ""`, `approved: bool = False`
  - `run_agent(..., system_prompt=SYSTEM_PROMPT, confirm: Callable[[ConfirmRequest], Awaitable[bool]] | None = None)`
  - `DENIED_PREFIX = "Denied by the user: "`
- Produces (`server.py`): `CONFIRM_TIMEOUT = 300` (modül düzeyi, testte monkeypatch'lenir); `POST /api/chat/confirm` gövde `ConfirmDecision(confirm_id: str, approved: bool)` → 204 / 404 / 403; SSE `confirm {"id","name","description","preview"}` ve `confirm_result {"id","approved"}`.

- [ ] **Step 1: Başarısız testleri yaz**

`tests/test_agent.py` ekleri (registry `make_registry(tmp_path)`, `a.txt` mevcut):

```python
def test_confirmed_tool_runs(tmp_path):
    p = FakeProvider(turns=[[ChatEvent("tool_calls", tool_calls=[ToolCall("c1", "delete_file", {"filename": "a.txt"})])], [ChatEvent("text", "tamam")]])
    seen = []
    async def yes(req): seen.append(req); return True
    events = collect(run_agent(p, "m", [{"role": "user", "content": "sil"}], reg, [], confirm=yes))
    assert [e.type for e in events] == ["confirm", "confirm_result", "tool", "text"]
    assert seen[0].description == "‘a.txt’ silinecek." and events[1].approved is True and not (tmp_path / "a.txt").exists()

def test_denied_tool_not_run(tmp_path):
    async def no(req): return False
    new = []
    events = collect(run_agent(p, ..., new, confirm=no))
    assert (tmp_path / "a.txt").exists()
    assert new[1]["content"] == "Denied by the user: ‘a.txt’ silinecek."

def test_no_confirm_hook_denies(tmp_path): ...   # confirm=None → dosya duruyor, Denied by the user

def test_two_confirmations_in_one_turn(tmp_path):
    # aynı turda delete a.txt ve delete b.txt; kanca ilkine True, ikincisine False
    assert not (tmp_path / "a.txt").exists() and (tmp_path / "b.txt").exists()
    assert [e.type for e in events if e.type.startswith("confirm")] == ["confirm", "confirm_result", "confirm", "confirm_result"]

def test_unconfirmed_tools_skip_hook(tmp_path):
    async def boom(req): raise AssertionError("should not be called")
    collect(run_agent(FakeProvider(turns=[[tool_calls create_file x.txt], [text]]), ..., confirm=boom))   # hata yok
```

`tests/test_confirm_api.py` (`make_client`, `parse_sse` `test_server.py`'den paylaşılan yardımcılar `tests/helpers.py`'ye taşınır):

```python
def test_confirm_flow_approve(tmp_path):
    # provider: delete_file a.txt, sonra "bitti"
    # Akışı ayrı bir thread'de okuyup "confirm" olayı gelince POST /api/chat/confirm {approved: True}
    assert names == ["confirm", "confirm_result", "tool", "text", "done"] and not a.exists()

def test_confirm_flow_deny(tmp_path): ...   # approved False → dosya duruyor; tool olayı result "Denied by the user: ‘a.txt’ silinecek."

def test_confirm_timeout(tmp_path, monkeypatch):
    monkeypatch.setattr("server.CONFIRM_TIMEOUT", 0.2)
    # karar gönderilmez → confirm_result approved False, dosya duruyor

def test_confirm_after_resolution_404(tmp_path):
    # onaylanmış id ile ikinci POST → 404; hiç olmayan id → 404

def test_confirm_requires_local(tmp_path):
    assert client.post("/api/chat/confirm", json={"confirm_id": "x", "approved": True}).status_code == 403

def test_pending_cleared_on_disconnect(tmp_path):
    # akış confirm olayında kapatılır (response.close()); ardından aynı id ile POST → 404
```

- [ ] **Step 2: Başarısız olduğunu gör** — `python -m pytest tests/test_agent.py tests/test_confirm_api.py -q` → FAIL.

- [ ] **Step 3: Uygula**

- Agent: araç döngüsünde her çağrı için `registry.needs_confirmation(c.name, c.arguments)`; varsa `ConfirmRequest(uuid4().hex, …)`, `yield AgentEvent("confirm", …)`, karar = `await confirm(req)` (kanca yoksa ya da exception fırlatırsa `False`), `yield AgentEvent("confirm_result", id=…, approved=…)`; red → sonuç `DENIED_PREFIX + description`, araç çalışmaz. Tool mesajı ve `tool` olayı her durumda üretilir (mevcut sıra: mesaj eklenir, sonra olay yayılır).
- Sunucu: `state.pending: dict[str, asyncio.Future]` ve sohbet akışı başına kendi id kümesi. `confirm` kancası future oluşturur, kaydeder, `asyncio.wait_for(future, CONFIRM_TIMEOUT)`; `TimeoutError` → `False`; her durumda `finally` içinde id silinir. `gen()` `finally` bloğu bu akışın bekleyen future'larını iptal eder ve siler. SSE'de `confirm`/`confirm_result` olayları yayılır. `POST /api/chat/confirm`: `require_local`; id yoksa ya da future bitmişse 404; `future.set_result(approved)` → 204.

- [ ] **Step 4: Geçtiğini gör** — `python -m pytest -q` → PASS.

- [ ] **Step 5: Commit** — `git commit -m "feat: in-stream confirmation for destructive tool calls"`

---

### Task 7: Hafıza ve araç ayarları

**Files:**
- Create: `meclaw/tools/memory.py`, `meclaw/memory.py`
- Modify: `meclaw/storage.py`, `meclaw/config.py`, `meclaw/tools/__init__.py`, `server.py`
- Test: `tests/test_memory.py`, `tests/test_settings_api.py`, `tests/test_settings_store.py`

**Interfaces:**
- Produces (`storage.py`): `list_memories() -> list[dict]` (`{"id","content","created_at","updated_at"}`, `id` artan), `add_memory(content: str) -> dict`, `update_memory(memory_id: int, content: str) -> bool`, `delete_memory(memory_id: int) -> bool`, `clear_memories() -> int`
- Produces (`config.py`): `Settings.internet_enabled: bool = True`, `Settings.memory_enabled: bool = True`; `parse_flag(value: str | None) -> bool`
- Produces (`meclaw/memory.py`): `MEMORY_RULES: str` (spec'teki kural bloğu, İngilizce), `MAX_MEMORY_CHARS = 500`, `MAX_PROMPT_MEMORIES = 100`, `build_system_prompt(base: str, memories: list[dict], memory_enabled: bool) -> str`
- Produces (`meclaw/tools/memory.py`): `MEMORY_TOOLS` → `remember(content)`, `forget(memory_id: int)`; `build_registry` bunları `ctx.memory and ctx.storage is not None` ise ekler
- Produces (`server.py`): `SettingsUpdate.internet_enabled: bool | None`, `SettingsUpdate.memory_enabled: bool | None`; ayar yükünde aynı iki alan; workspace, internet veya hafıza değişince `state.registry = make_registry(state.settings)`; chat sistem istemi `build_system_prompt(base, storage.list_memories(), settings.memory_enabled)`; `/api/memories` uç noktaları (spec'teki tablo). `build_registry_for(settings, storage)` artık `ToolContext(Explorer(settings.workspace_dir), storage, settings.internet_enabled, settings.memory_enabled)` kurar; `build_default_app` `make_registry=lambda s: build_registry_for(s, storage)` geçer.

- [ ] **Step 1: Başarısız testleri yaz**

```python
def test_memory_crud(tmp_path):
    s = Storage(tmp_path / "m.db")
    a = s.add_memory("Adım Melih"); b = s.add_memory("Python seviyorum")
    assert [m["content"] for m in s.list_memories()] == ["Adım Melih", "Python seviyorum"]
    assert s.update_memory(a["id"], "Adım Melih Emin") and not s.update_memory(999, "x")
    assert s.delete_memory(b["id"]) and not s.delete_memory(b["id"])
    assert s.clear_memories() == 1 and s.list_memories() == []

def test_build_system_prompt():
    mems = [{"id": 1, "content": "Adım Melih"}, {"id": 2, "content": "Kahve sever"}]
    out = build_system_prompt("BASE", mems, True)
    assert out.startswith("BASE\n\n") and MEMORY_RULES in out and out.endswith("Known facts about the user:\n[1] Adım Melih\n[2] Kahve sever")
    assert build_system_prompt("BASE", mems, False) == "BASE"
    assert build_system_prompt("BASE", [], True).endswith("Known facts about the user:\n(none yet)")

def test_prompt_keeps_newest_100():
    mems = [{"id": i, "content": f"n{i}"} for i in range(1, 151)]
    out = build_system_prompt("B", mems, True)
    assert "[51] n51" in out and "[50] n50" not in out

def test_remember_forget_tools(tmp_path):
    reg = make_registry(tmp_path / "ws", storage=Storage(tmp_path / "m.db"))
    assert run(reg, "remember", content="Adı Melih") == "Saved memory #1."
    assert run(reg, "remember", content="x" * 501) == "Memory is too long (max 500 characters)."
    assert run(reg, "forget", memory_id=1) == "Forgot memory #1." and run(reg, "forget", memory_id=1) == "No memory #1."
    assert not {"remember", "forget"} & make_registry(tmp_path / "ws", storage=Storage(tmp_path / "m.db"), memory=False).names()

def test_memories_api(client):
    r = client.post("/api/memories", json={"content": "Adım Melih"}, headers=LOCAL); mid = r.json()["id"]
    assert client.get("/api/memories").json()[0]["content"] == "Adım Melih"
    assert client.put(f"/api/memories/{mid}", json={"content": "Melih Emin"}, headers=LOCAL).status_code == 200
    assert client.put("/api/memories/999", json={"content": "x"}, headers=LOCAL).status_code == 404
    assert client.post("/api/memories", json={"content": " "}, headers=LOCAL).status_code == 400
    assert client.post("/api/memories", json={"content": "x"}).status_code == 403
    assert client.delete(f"/api/memories/{mid}", headers=LOCAL).status_code == 204
    client.post("/api/memories", json={"content": "a"}, headers=LOCAL)
    assert client.delete("/api/memories", headers=LOCAL).json() == {"deleted": 1}

def test_memories_reach_system_prompt(...):   # not ekle → chat → provider.calls[0][0]["content"] içinde "[1] Adım Melih"

@pytest.mark.parametrize("value,expected", [(None, True), ("", True), ("1", True), ("0", False), ("FALSE", False), ("off", False), ("no", False), ("yes", True)])
def test_parse_flag(value, expected): assert parse_flag(value) is expected

def test_flags_saved_and_rebuild(client, h, built):
    client.put("/api/settings", json={"internet_enabled": False})
    assert h.calls[-1] == {"MECLAW_INTERNET": "0"} and len(built) == 1
    client.put("/api/settings", json={"internet_enabled": True})
    assert h.calls[-1] == {"MECLAW_INTERNET": None}
    assert client.get("/api/settings").json()["memory_enabled"] is True

def test_disabled_internet_tool_unknown(...):
    # internet kapalıyken provider web_search çağırır → tool olayı result "Unknown tool: web_search", akış "done" ile biter
```

- [ ] **Step 2: Başarısız olduğunu gör** → FAIL.

- [ ] **Step 3: Uygula** — `memories` tablosu `CREATE TABLE IF NOT EXISTS` ile mevcut şemaya eklenir (geçiş gerekmez). `build_system_prompt` biçimi: `base + "\n\n" + MEMORY_RULES + "\n\nKnown facts about the user:\n" + satırlar` (`(none yet)` boşken); en yeni 100 = en büyük 100 id, artan sırada yazılır. Test harness'i (`test_settings_api.py`) yeni ortam anahtarlarını `internet_enabled`/`memory_enabled` alanlarına `parse_flag` ile eşler; `make_registry` fixture'ı artık `Settings` alır.

- [ ] **Step 4: Geçtiğini gör** → PASS. **Step 5: Commit** — `git commit -m "feat: assistant memory and internet/memory settings"`

---

### Task 8: Arayüz — onay kartı, araç etiketleri, ayarlar

**Files:**
- Modify: `static/index.html`, `static/app.js`, `static/style.css`

**Interfaces:**
- Consumes: SSE `confirm`/`confirm_result`, `POST /api/chat/confirm` (`X-MeClaw: 1` başlığı), `/api/memories*`, ayar alanları `internet_enabled`/`memory_enabled` (Task 6/7)

Davranış:
- `confirm` olayı → mesaj akışına kart: başlık "🛡 Onay gerekiyor", `description` (`textContent`), `preview` doluysa `pre` (`textContent`), [İzin ver] [Reddet]. Tıklanınca iki düğme kilitlenir, istek gider; yanıt 404 ise kart "⌛ Süresi doldu" olur; `confirm_result` gelince "✓ İzin verildi" / "✗ Reddedildi". Bekleyen kart varken gönder düğmesi kilitli kalır (mevcut `busy`).
- Araç etiketleri: `remember` → "📝 Hafıza güncellendi", `forget` → "📝 Hafızadan silindi", `fetch_url`/`web_search` → "🌐 " + ad, sonuç `Denied by the user:` ile başlıyorsa "🚫 " + ad, diğerleri "🛠 " + ad. Geçmiş yüklenirken de aynı etiketler.
- Ayarlar → "Araçlar" bölümü: iki onay kutusu "İnternet erişimi (web arama ve sayfa okuma)" ve "Hafıza (asistan sizinle ilgili notlar tutar)"; kaydette `internet_enabled`/`memory_enabled` gönderilir.
- Ayarlar → "Hafıza" bölümü: liste (her satır: metin, ✎ düzenle — satır içi input + Kaydet/İptal, 🗑 sil), "Not ekle" input + Ekle düğmesi, "Tümünü sil" (`confirm()` ile). Hafıza kapalıyken liste üstünde "Hafıza kapalı; asistan bu notları kullanmıyor." notu. Hafıza işlemleri anında API'ye gider (Kaydet düğmesini beklemez); hata `settings-status`'ta.

- [ ] **Step 1: Uygula** (üç dosya)
- [ ] **Step 2:** `node --check static/app.js` → hata yok; `python -m pytest -q` → PASS.
- [ ] **Step 3: Commit** — `git commit -m "feat(ui): confirmation cards, tool labels, tools and memory settings"`

Tarayıcı doğrulaması controller tarafından sahte sağlayıcıyla yapılır (onay izin/ret/süresi doldu, hafıza ekle/düzenle/sil, ayar anahtarları).

---

### Task 9: Belgeler

**Files:**
- Modify: `README.md`

- [ ] **Step 1:** Features bölümüne: onaylı silme/üzerine yazma, arama/düzenleme, PDF/Excel, web (DuckDuckGo, ayarlardan kapatılabilir, yerel ağ adresleri engelli), tarih/hesap, hafıza. Installation'a `MECLAW_INTERNET`, `MECLAW_MEMORY`. Project Structure'da `meclaw/tools/` modülleri ve `meclaw/memory.py`; `tool_definitions.json` ve `tools/registry.py` satırları kaldırılır.
- [ ] **Step 2:** `git grep -n "tool_definitions\|_tool\b" -- ':!docs'` → çıktı yok; `python -m pytest -q` → PASS.
- [ ] **Step 3: Commit** — `git commit -m "docs: document the tools pack"`
