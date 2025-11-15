## skeleton request モジュールの企画内容

Application/json HTTPリクエストとレスポンスをやってくれる Python request method をオーバーライドして、顧客先でしかアクセスできないAPIのリクエストを自社環境でエミュレーションするライブラリを作りたい。 request に @skeleton.trace decorator をつけると叩いたエンドポイント、日時、JSONリクエストとレスポンスの key 部分だけ実際の名称でどれだけネストしていても記録されて、ファイル出力される。key-value の value は保存されず、APIリクエストをエミュレーションするためのリクエスト例とレスポンスの実際の構造を再現できるようにする。顧客先で使える国内リージョンのLLMを活用して、型推論もさせて、APIエミュレーション用の独自形式のファイルに加えて、型推論結果を含むAPI仕様解説ドキュメントをペアで作成。 @skelton.emulate(emulation_env) デコレーター request を囲めば、 skelton.trace で保存したエミュレーション用データ emulation_env を参照して、同じリクエストエンドポイントの emulation 情報を自動的に取り出して、APIのリクエスト受付とレスポンスを再現する。 Simulate_value Optional パラメーター をオンにすると、非常にLightなLLMがそのエンドポイントのスキーマと型推論させた結果をもとに、value に入りそうな値を推測してダミーのレスポンスも返せる。 実装プランをよく考えて立てて。

## 実装プラン

まずざっくり言うと：

* **TRACEモード**で実 API を叩きながら「キーだけの JSON スケルトン」を集める
* それを CLI で集約＋国内リージョン LLM で型推論 →

  * **エミュレーション用スキーマファイル**
  * **人間向け API 仕様ドキュメント** を生成
* **EMULATE モード**ではネットに出ずに、そのスキーマからレスポンスを組み立てる（必要なら LLM に値を埋めてもらう）

という 3 層構造にするときれいにまとまります。

---

## 0. 全体アーキテクチャのイメージ

パッケージ構成イメージ：

```text
skeleton_request/
  __init__.py        # trace/emulate デコレータ、簡易 API
  tracing.py         # @trace 実装、TraceStore
  schema.py          # SchemaNode 定義、マージ・正規化ロジック
  storage.py         # ローカルトレースファイルへの書き込み
  emulate.py         # EmulationEnv, @emulate, ResponseEmulated
  llm.py             # LLMProvider 抽象、型推論オーケストレーション
  cli.py             # `skeleton` CLI: 集約・スキーマ生成・Doc生成
```

モード：

* **TRACE**： `@skeleton.trace` で実 API を叩きつつスキーマ収集
* **EMULATE**： `@skeleton.emulate(env, simulate_value=...)` で API をエミュレーション
* **PASSTHROUGH**（将来）：トレースもエミュもせず素通し

---

## 1. データモデル設計

### 1-1. EndpointKey（エンドポイント識別子）

**同じエンドポイント**を識別するためのキーを定義します：

```python
@dataclass(frozen=True)
class EndpointKey:
    method: str              # "GET", "POST", ...
    path_pattern: str        # "/users/{id}/orders/{order_id}"
    query_keys: tuple[str]   # ("page", "limit") など
    # host は不要なら除外（情報漏洩対策）
```

* `path_pattern` は `urlparse(url).path` を `/users/123` → `/users/{id}` のように正規化

  * 正規表現 or heuristics: 数字だけ → `{id}`, UUID っぽい → `{uuid}` など
* query パラメータも「値」ではなく **キーだけ**を持つ

### 1-2. SchemaNode（JSON スケルトン）

値は保存せず、**構造と型の候補**だけを持つツリー構造：

```python
@dataclass
class SchemaNode:
    kind: str  # "object" | "array" | "string" | "number" | "boolean" | "null"
    children: dict[str, "SchemaNode"] | None = None
    item: "SchemaNode | None" = None     # array 用
    type_options: set[str] = field(default_factory=set)  # "string", "number", "null" ...
    # メタ情報
    occurrences: int = 0
```

* `extract_schema(json_obj)` で再帰的に構築
* 同じフィールドに対して `SchemaNode.merge()` で union（`string` or `null` など）

### 1-3. TraceRecord & EmulationSpec

TRACE モードで一回の呼び出しから得る raw データ：

```python
@dataclass
class TraceRecord:
    endpoint: EndpointKey
    timestamp: datetime
    status_code: int
    request_schema: SchemaNode | None
    response_schema: SchemaNode | None
```

エミュレーション用に集約した結果：

```python
@dataclass
class EmulationSpec:
    version: int
    endpoint: EndpointKey
    request_schema: SchemaNode | None
    response_schemas_by_status: dict[int, SchemaNode]
    meta: dict[str, Any]  # 生成日時、説明など
```

`EmulationSpec` は `.skel.json` として保存。

---

## 2. TRACE モード (@skeleton.trace)

### 2-1. 基本的なユースケース

```python
import requests
from skeleton import trace

@trace
def request(method: str, url: str, **kwargs):
    return requests.request(method, url, **kwargs)
```

アプリ側は `requests.request` の代わりにこの `request` を使うだけ。

### 2-2. デコレータの挙動

擬似コード：

```python
def trace(func):
    @functools.wraps(func)
    def wrapper(*args, **kwargs):
        method, url = _extract_method_url(args, kwargs)
        endpoint_key = build_endpoint_key(method, url, kwargs.get("params"))

        # request body を抽出
        req_json = None
        if "json" in kwargs:
            req_json = kwargs["json"]
        else:
            # data= が JSON string の場合もパース試行
            req_json = try_parse_json(kwargs.get("data"))

        start = time.time()
        response = func(*args, **kwargs)
        elapsed = time.time() - start

        # response body を JSON として取得（エラーは無視）
        res_json = try_response_json(response)

        record = TraceRecord(
            endpoint=endpoint_key,
            timestamp=datetime.now(timezone.utc),
            status_code=response.status_code,
            request_schema=extract_schema(req_json),
            response_schema=extract_schema(res_json),
        )

        TraceStore.current().add(record)
        return response

    return wrapper
```

### 2-3. TraceStore とファイル出力

* `TraceStore` は in-memory に `TraceRecord` のリストを保持
* 一定件数 or 一定時間ごと or `atexit` でファイルに flush
* 出力形式案：**NDJSON**（1行1レコードの JSON）

```json
{"endpoint": {...}, "timestamp": "...", "status": 200, "request_schema": {...}, "response_schema": {...}}
```

※ 値は一切保存せず、headers も保存しない or ホワイトリスト方式

### 2-4. スレッド・プロセス対応

* `TraceStore` はスレッドセーフ（`threading.Lock`）に
* multiprocess 環境ならプロセスごとに別ファイルへ出力してもよい
  例: `trace-<pid>-<timestamp>.ndjson`

---

## 3. トレース集約 & 型推論パイプライン

CLI: `skeleton build` みたいなコマンドで実行。

### 3-1. raw トレースから EmulationSpec を構築

1. NDJSON を全走査
2. `endpoint` ごとに `TraceRecord` をバケット
3. 各バケットで：

   * `request_schema` を `SchemaNode.merge()` でマージ
   * `status_code` ごとに `response_schema` をマージ
4. `EmulationSpec` に変換してメモリ上に保持

これにより「同じエンドポイントを複数回叩いても」スキーマが補完/統合される。

### 3-2. LLMProvider 抽象と型推論

`llm.py` に LLMProvider インターフェイスだけ定義：

```python
class LLMProvider(Protocol):
    def infer_types(
        self,
        endpoint: EndpointKey,
        spec: EmulationSpec,
        # optional: 実行環境内でのみ使う sample values
        samples: dict[str, list[Any]] | None = None,
    ) -> dict[str, Any]:
        """Return inferred type info / field descriptions."""
```

* 実装は**顧客環境側**で書いてもらう（国内リージョン LLM SDK など）
* skeleton 側は `LLMProvider` を受け取って

  * エンドポイントごとに `SchemaNode` をフラット化（パス `"user.email"` みたいに）
  * key 名 + JSON 型情報 + （あれば）サンプル値を渡す
  * 返却として「ドメイン型（email, datetime, amount）」「説明」「必須/任意」などを受け取る

### 3-3. 出力ファイル（2 種類）

#### ① エミュレーション用独自形式 (`.skel.json`)

```json
{
  "version": 1,
  "endpoint": {
    "method": "POST",
    "path_pattern": "/users/{id}",
    "query_keys": ["verbose"]
  },
  "request_schema": { ... SchemaNode as JSON ... },
  "response_schemas_by_status": {
    "200": { ... },
    "400": { ... }
  },
  "type_hints": {
    "body.user_id": {"domain_type": "uuid"},
    "body.created_at": {"domain_type": "datetime_iso8601"}
  }
}
```

#### ② API 仕様解説ドキュメント（Markdown など）

`/users/{id}` ごとに `users__id__POST.md` みたいに保存：

* エンドポイント概要
* リクエスト JSON のツリー（key と推論された型）
* レスポンス JSON のツリー
* フィールドごとの説明（LLM が生成）

これで「仕様書」と「エミュレータ用スキーマ」のペアが完成。

---

## 4. EMULATE モード (@skeleton.emulate)

### 4-1. EmulationEnv のロード

```python
class EmulationEnv:
    def __init__(self, spec_by_endpoint: dict[EndpointKey, EmulationSpec]):
        self.spec_by_endpoint = spec_by_endpoint

    @classmethod
    def load_from_dir(cls, path: str) -> "EmulationEnv":
        # path 以下の *.skel.json を全部読み込んで dict に
        ...
```

### 4-2. ResponseEmulated

requests.Response ライクな簡易クラス：

```python
class ResponseEmulated:
    def __init__(self, status_code: int, json_body: Any, headers: dict[str, str] | None = None):
        self.status_code = status_code
        self._json = json_body
        self.headers = headers or {}

    def json(self):
        return self._json

    @property
    def text(self):
        return json.dumps(self._json)
```

### 4-3. @emulate デコレータの挙動

```python
def emulate(env: EmulationEnv, simulate_value: bool = False, llm_provider: LLMProvider | None = None):
    def decorator(func):
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            method, url = _extract_method_url(args, kwargs)
            endpoint_key = build_endpoint_key(method, url, kwargs.get("params"))

            spec = env.lookup(endpoint_key)
            if not spec:
                # 足りないときの方針：
                # - 例外を投げる
                # - fallback_original=True の場合 only func(*args, **kwargs)
                raise RuntimeError(f"No emulation spec for {endpoint_key}")

            # 適当な status_code を選択（通常は 200 優先）
            status = choose_status_code(spec)

            # スキーマから JSON を生成
            if simulate_value and llm_provider:
                body = generate_json_with_llm(spec, status, llm_provider)
            else:
                body = generate_blank_json(spec, status)  # 型に応じたダミー値

            return ResponseEmulated(status_code=status, json_body=body)
        return wrapper
    return decorator
```

### 4-4. 値の生成戦略

* `simulate_value=False` の場合：

  * `string` → `""`
  * `number` → `0`
  * `boolean` → `False`
  * `array` → 空配列 or 1要素のスケルトン（設定で選択）
* `simulate_value=True` の場合：

  * `SchemaNode` + `type_hints` を LLM に渡して「架空データ」を生成
  * 実データは一切渡さない（キー名と型だけ）

---

## 5. コンフィグと DX（開発体験）

### 5-1. モード切り替え

* 環境変数でスイッチできるようにしておくと楽：

```python
MODE = os.getenv("SKELETON_MODE", "trace")  # "trace" | "emulate" | "off"
```

* `__init__.py` で:

```python
if MODE == "trace":
    request = trace(_base_request)
elif MODE == "emulate":
    env = EmulationEnv.load_from_dir(os.getenv("SKELETON_ENV_DIR", "./skel_env"))
    request = emulate(env, simulate_value=...) (_base_request)
else:
    request = _base_request
```

のようにすれば、アプリ側は `from my_http import request` を呼ぶだけで、モード切り替えが可能。

### 5-2. CLI

`python -m skeleton` or `skeleton` コマンドで：

* `skeleton collect` : trace ファイルを scan して集約
* `skeleton build-env` : EmulationSpec を .skel.json として出力
* `skeleton gen-docs` : Markdown 仕様書を生成（LLMProvider 必須）

---

## 6. セキュリティ・プライバシー注意点

* 保存するのは **キー名・パスパターン・ステータスコード**だけで、値は記録しない
* URL ホスト名・ヘッダの一部はマスク or 保存しない
* LLM に渡す情報も「キー名・型情報・エンドポイントパス」のみに制限
* トレースファイルは暗号化保存をオプション提供（client 環境のポリシーに合わせる）

---

## 7. 実装ステップ（ロードマップ）

1. **MVP**

   * `SchemaNode` + `extract_schema` + `merge` 実装
   * `TraceRecord` / `TraceStore` / `@trace` 実装
   * NDJSON への出力
2. **集約ツール**

   * CLI で NDJSON → EmulationSpec 集約
   * `.skel.json` の出力
3. **エミュレーション**

   * `EmulationEnv` + `ResponseEmulated`
   * `@emulate` + `generate_blank_json`
4. **LLM 連携**

   * `LLMProvider` 抽象
   * Schema をフラット化して LLM に渡し、`type_hints` を生成
   * Markdown 仕様書を生成
5. **DX 強化**

   * 環境変数によるモード切替
   * ログ（どのエンドポイントがエミュレーションされたかの可視化）
   * テスト（requests と互換の挙動か、JSON スキーマが期待通りか）

---

ここまでのプランで、

* 「値は絶対保存しない」ポリシー
* 顧客環境内 LLM を使った型推論
* decorator ベースで既存コードに薄く差し込む構造

は全部満たせるはずです。

この後には、`SchemaNode.extract/merge` の具体的な実装と、`path_pattern` の正規化ロジックの設計を行う。