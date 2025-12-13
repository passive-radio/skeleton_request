# skeleton-request

顧客環境でしかアクセスできない API を、自社環境でオフライン再現する HTTP トレース & エミュレーションライブラリ

[![Python 3.13+](https://img.shields.io/badge/python-3.13+-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Development Status](https://img.shields.io/badge/status-alpha-orange.svg)]()

---

## 目次

- [概要](#概要)
- [動作の仕組み](#動作の仕組み)
- [クイックスタート](#クイックスタート)
- [インストール](#インストール)
- [基本的な使い方](#基本的な使い方)
- [CLI リファレンス](#cli-リファレンス)
- [設定](#設定)
- [高度な使い方](#高度な使い方)
- [実例](#実例)
- [トラブルシューティング](#トラブルシューティング)
- [プロジェクト構成](#プロジェクト構成)

---

## 概要

`skeleton-request` は、顧客環境でしかアクセスできない外部 API の構造を記録し、開発環境でオフライン再現するための Python ライブラリです。

**こんな課題を解決します:**
- 顧客環境の API にアクセスできない自社開発環境でのテスト
- API の仕様書が存在しない・古い場合の構造把握
- セキュリティ要件の厳しい環境での API 挙動の再現

**主な特徴:**
- **プライバシー保護設計** - JSON の構造（キー名）のみを記録し、実際の値は一切保存しない
- **LLM 活用型推論** - OpenAI 互換 API（Azure OpenAI、Google Gemini など国内リージョン LLM）で正確な型推論
- **デコレータベースの軽量 API** - 既存コードへの影響を最小化
- **包括的なドキュメント生成** - `.skel.json` エミュレーションファイルと Markdown API 仕様書をペアで出力

---

## 動作の仕組み

skeleton-request は 3 つのステップで動作します:

### 1. TRACE モード（顧客環境）

`@trace` デコレータで API 呼び出しを記録します。実際の値は一時的にのみ保持され、**構造（JSON キー）だけ**を NDJSON 形式で保存します。

```python
@trace
def api_request(method, url, **kwargs):
    return requests.request(method, url, **kwargs)
```

### 2. 集約 & 型推論（自社環境）

`skeleton build-env` コマンドで複数のトレースを集約し、LLM で型推論を実行。`.skel.json` ファイルと Markdown 形式の API 仕様書を生成します。

```bash
skeleton build-env --infer-types
```

### 3. EMULATE モード（開発環境）

`@emulate` デコレータで、**実際のネットワーク通信なし**に API レスポンスを再現します。

```python
@emulate(env)
def api_request(method, url, **kwargs):
    return requests.request(method, url, **kwargs)
```

### プライバシー設計

- **トレースファイル**（`.ndjson`）には実際の値も含まれますが、`build-env --infer-types` 実行後は破棄可能
- **最終的な `.skel.json`** にはスキーマと推論された型情報のみ
- **`--key-names-only`** オプションで LLM に値を一切送信しない運用も可能

---

## クイックスタート

### ステップ 1: インストール

```bash
# GitHub から直接インストール（推奨）
pip install git+https://github.com/YOUR_USERNAME/skeleton-request.git

# または uv を使用（Python 3.13+）
git clone https://github.com/YOUR_USERNAME/skeleton-request.git
cd skeleton-request
uv sync
```

### ステップ 2: API 呼び出しの記録（TRACE モード）

```python
import requests
from skeleton_request import trace

@trace
def api_request(method, url, **kwargs):
    return requests.request(method, url, **kwargs)

# 通常通り API を呼び出すだけで自動記録
response = api_request("GET", "https://jsonplaceholder.typicode.com/users/1")
print(response.json())
```

実行すると `./traces/` ディレクトリにトレースファイルが生成されます。

### ステップ 3: エミュレーション環境の構築

```bash
# 基本的な構築（スキーマのみ）
skeleton build-env --trace-dir ./traces --output-dir ./skel_env

# LLM で型推論（推奨）
export OPENAI_API_KEY=your-key
skeleton build-env --infer-types

# プライバシー重視モード（値を LLM に送信しない）
skeleton build-env --infer-types --key-names-only
```

`./skel_env/` に `.skel.json` ファイルが生成されます。

### ステップ 4: オフライン再現（EMULATE モード）

```python
from skeleton_request import emulate, EmulationEnv

env = EmulationEnv.load_from_dir("./skel_env")

@emulate(env)
def api_request(method, url, **kwargs):
    return requests.request(method, url, **kwargs)

# ネットワーク通信なしで動作！
response = api_request("GET", "https://jsonplaceholder.typicode.com/users/1")
print(response.json())  # スキーマに基づくモックデータ
```

完了！これでオフライン環境でも API レスポンスを再現できます。

---

## インストール

### 必須要件

- **Python 3.13 以上**
- `requests` ライブラリ
- OpenAI API 互換の LLM アクセス（型推論機能使用時のみ）

### GitHub から（推奨）

```bash
# 最新版
pip install git+https://github.com/YOUR_USERNAME/skeleton-request.git

# 特定バージョン
pip install git+https://github.com/YOUR_USERNAME/skeleton-request.git@v0.1.0
```

### ソースから

```bash
git clone https://github.com/YOUR_USERNAME/skeleton-request.git
cd skeleton-request

# uv を使用（Python 3.13+）
uv sync

# または pip
pip install -e .
```

### 開発用インストール

```bash
# 開発用依存関係を含む
uv sync --extra dev

# または pip
pip install -e ".[dev]"
```

---

## 基本的な使い方

### TRACE モード: API 呼び出しの記録

#### パターン 1: 関数ラッパー方式（推奨）

```python
import requests
from skeleton_request import trace

@trace
def my_request(method, url, **kwargs):
    """requests.request() のトレース版ラッパー"""
    return requests.request(method, url, **kwargs)

# 既存コードで my_request を使用
response = my_request("GET", "https://api.example.com/users/1")
response = my_request("POST", "https://api.example.com/posts",
                      json={"title": "test", "body": "content"})
```

#### パターン 2: 個別関数デコレート方式

```python
@trace
def fetch_user(user_id: int):
    """特定のユーザー情報を取得"""
    return requests.get(f"https://api.example.com/users/{user_id}")

@trace
def create_post(title: str, body: str):
    """投稿を作成"""
    return requests.post("https://api.example.com/posts",
                        json={"title": title, "body": body})

# 通常通り呼び出すだけで記録される
user = fetch_user(1)
post = create_post("Hello", "World")
```

#### トレースの保存

```python
from skeleton_request import TraceStore

# 明示的にフラッシュ（通常は自動）
TraceStore.current().flush()

# トレースファイルの場所を確認
trace_file = TraceStore.current().get_trace_file()
print(f"Saved to: {trace_file}")
```

### EMULATE モード: オフライン再現

#### 基本的なエミュレーション

```python
from skeleton_request import emulate, EmulationEnv

# エミュレーション環境をロード
env = EmulationEnv.load_from_dir("./skel_env")

@emulate(env)
def my_request(method, url, **kwargs):
    return requests.request(method, url, **kwargs)

# ネットワークアクセスなしで動作
response = my_request("GET", "https://api.example.com/users/1")
print(response.json())  # {"id": "", "name": "", "email": "", ...}
```

#### リアルな値を LLM で生成

```python
from skeleton_request import emulate, EmulationEnv, LLMProvider

env = EmulationEnv.load_from_dir("./skel_env")
llm = LLMProvider()

@emulate(env, simulate_value=True, llm_provider=llm)
def my_request(method, url, **kwargs):
    return requests.request(method, url, **kwargs)

# よりリアルなダミーデータが返る
response = my_request("GET", "https://api.example.com/users/1")
print(response.json())
# {"id": "550e8400-e29b-41d4-a716-446655440000",
#  "name": "John Doe",
#  "email": "john.doe@example.com", ...}
```

#### フォールバック設定

```python
@emulate(env, fallback_original=True)
def my_request(method, url, **kwargs):
    return requests.request(method, url, **kwargs)

# スキーマがない場合、実際の API にフォールバック
response = my_request("GET", "https://api.example.com/new-endpoint")
```

---

## CLI リファレンス

skeleton-request は 2 つの CLI コマンドを提供します。

### `skeleton build-env`

トレースファイルからエミュレーション環境を構築します。

**基本構文:**
```bash
skeleton build-env [OPTIONS]
```

**オプション:**

| オプション | 説明 | デフォルト |
|-----------|------|-----------|
| `--trace-dir PATH` | トレースファイルのディレクトリ | `./traces` |
| `--output-dir PATH` | 出力先ディレクトリ | `./skel_env` |
| `--infer-types` | LLM で型推論を実行 | false |
| `--key-names-only` | フィールド名のみから型推論（値を LLM に送信しない） | false |
| `--delete-traces` | 構築後にトレースファイルを削除 | false |

**使用例:**

```bash
# 基本的な使い方（スキーマのみ）
skeleton build-env --trace-dir ./traces --output-dir ./skel_env

# LLM で型推論（値も使用）
export OPENAI_API_KEY=your-key
skeleton build-env --infer-types

# プライバシー重視（キー名のみ）
skeleton build-env --infer-types --key-names-only

# トレース削除（機密情報対策）
skeleton build-env --infer-types --delete-traces
```

### `skeleton gen-docs`

`.skel.json` ファイルから Markdown 形式の API 仕様書を生成します。

**基本構文:**
```bash
skeleton gen-docs [OPTIONS]
```

**オプション:**

| オプション | 説明 | デフォルト |
|-----------|------|-----------|
| `--spec-dir PATH` | `.skel.json` ファイルのディレクトリ | `./skel_env` |
| `--output-dir PATH` | 出力先ディレクトリ | `./docs` |

**使用例:**

```bash
# 基本的な使い方
skeleton gen-docs --spec-dir ./skel_env --output-dir ./docs

# カスタムディレクトリ
skeleton gen-docs --spec-dir ./my_specs --output-dir ./api_docs
```

**生成されるドキュメント:**
- エンドポイント情報（メソッド、パスパターン、クエリパラメータ）
- リクエスト/レスポンススキーマのツリー表示
- 推論された型情報とフィールド説明

---

## 設定

### 環境変数

skeleton-request は環境変数で動作をカスタマイズできます。

| 変数名 | 説明 | デフォルト値 | 設定例 |
|-------|------|------------|--------|
| `SKELETON_MODE` | 動作モード: `trace` \| `emulate` \| `off` | `trace` | `export SKELETON_MODE=emulate` |
| `SKELETON_TRACE_DIR` | トレースファイルの保存先 | `./traces` | `export SKELETON_TRACE_DIR=/tmp/traces` |
| `SKELETON_ENV_DIR` | `.skel.json` ファイルのディレクトリ | `./skel_env` | `export SKELETON_ENV_DIR=./my_env` |
| `OPENAI_API_KEY` | OpenAI API キー | - | `export OPENAI_API_KEY=sk-...` |
| `OPENAI_BASE_URL` | カスタム API ベース URL | - | `export OPENAI_BASE_URL=https://...` |
| `SKELETON_LLM_PROVIDER` | LLM プロバイダー: `openai` \| `azure` \| `gemini` | `openai` | `export SKELETON_LLM_PROVIDER=azure` |
| `SKELETON_LLM_MODEL` | 使用するモデル名 | `gpt-4.1` | `export SKELETON_LLM_MODEL=gpt-4.1` |
| `SKELETON_LLM_TEMPERATURE` | LLM の温度パラメータ | `0.0` | `export SKELETON_LLM_TEMPERATURE=0.0` |
| `SKELETON_LLM_MAX_TOKENS` | 最大トークン数 | `2000` | `export SKELETON_LLM_MAX_TOKENS=2000` |

### モード切替

#### TRACE モード（デフォルト）

```bash
export SKELETON_MODE=trace
export SKELETON_TRACE_DIR=./traces
python your_app.py
```

#### EMULATE モード

```bash
export SKELETON_MODE=emulate
export SKELETON_ENV_DIR=./skel_env
python your_app.py  # ネットワーク通信なし
```

#### OFF モード（パススルー）

```bash
export SKELETON_MODE=off
python your_app.py  # 通常の requests 動作
```

### LLM プロバイダー設定

#### OpenAI

```bash
export SKELETON_LLM_PROVIDER=openai
export OPENAI_API_KEY=sk-...
export SKELETON_LLM_MODEL=gpt-4o-mini
```

#### Azure OpenAI（国内リージョン対応）

```bash
export SKELETON_LLM_PROVIDER=azure
export OPENAI_API_KEY=your-azure-key
export OPENAI_BASE_URL=https://your-resource.openai.azure.com/
export SKELETON_LLM_MODEL=gpt-4
```

#### Google Gemini

```bash
export SKELETON_LLM_PROVIDER=gemini
export OPENAI_API_KEY=your-gemini-key
export OPENAI_BASE_URL=https://generativelanguage.googleapis.com/v1beta/
export SKELETON_LLM_MODEL=gemini-pro
```

---

## 高度な使い方

### エンドポイント正規化

URL パスは自動的にパターン化されます:
- `/users/123` → `/users/{id}`
- `/orders/550e8400-e29b-41d4-a716-446655440000` → `/orders/{uuid}`
- `/items/abc123def` → `/items/{id}`
- クエリパラメータはキー名のみ記録

### マルチステータスコード対応

```python
# 異なるステータスコードを記録
response_200 = my_request("GET", "/api/users/1")  # 200 OK
response_404 = my_request("GET", "/api/users/999")  # 404 Not Found

# build-env 後、両方のレスポンススキーマが保存される
# EMULATE モードでは 200 を優先的に返す
```

### プライバシー保護の実践

#### レベル 1: 基本保護（値は一時保存）

```bash
# トレースに値が含まれるが、build-env 後に削除可能
skeleton build-env --delete-traces
```

#### レベル 2: LLM に値を送信しない

```bash
# キー名のみから型推論（精度は下がる）
skeleton build-env --infer-types --key-names-only
```

#### レベル 3: LLM を使用しない

```bash
# 型推論なし、構造のみ
skeleton build-env
```

### カスタム LLM プロバイダーの実装

```python
from skeleton_request.llm import LLMProvider, FieldTypeInfo

class MyCustomLLM(LLMProvider):
    def infer_types(
        self,
        endpoint_key,
        schema_node,
        sample_values=None,
    ) -> dict[str, FieldTypeInfo]:
        # カスタムロジック
        return {
            "user.email": FieldTypeInfo(
                path="user.email",
                json_type="string",
                domain_type="email",
                description="User email address",
                required=True
            ),
        }

# 使用
llm = MyCustomLLM()
env = EmulationEnv.load_from_dir("./skel_env")

@emulate(env, simulate_value=True, llm_provider=llm)
def my_request(method, url, **kwargs):
    return requests.request(method, url, **kwargs)
```

### スキーマの手動編集

`.skel.json` ファイルは手動編集可能です:

```json
{
  "version": 1,
  "endpoint": {
    "method": "GET",
    "path_pattern": "/users/{id}",
    "query_keys": []
  },
  "request_schema": null,
  "response_schemas_by_status": {
    "200": {
      "kind": "object",
      "children": {
        "id": {"kind": "string"},
        "name": {"kind": "string"},
        "email": {"kind": "string"}
      }
    }
  },
  "response_type_hints": {
    "200": [
      {
        "path": "id",
        "json_type": "string",
        "domain_type": "uuid",
        "description": "User ID",
        "required": true
      }
    ]
  }
}
```

---

## 実例

### 基本的な使用例

[examples/basic_usage.py](examples/basic_usage.py) - JSONPlaceholder API を使った基本的なトレース & エミュレーション

```bash
# TRACE モード
python examples/basic_usage.py trace

# EMULATE モード
python examples/basic_usage.py emulate
```

### 実際の API 例: The Cat API

[examples/test_cat_api.py](examples/test_cat_api.py) - The Cat API の 3 つのエンドポイントをトレース

```bash
# .env.local に CAT_API_KEY を設定後
uv run python examples/test_cat_api.py --both

# エミュレーション環境を構築
skeleton build-env --infer-types
skeleton gen-docs
```

詳細は [examples/README.md](examples/README.md) を参照してください。

### 主要コンポーネント

**SchemaNode** (`schema.py`)
- JSON 構造を値なしで表現する再帰的ツリー
- `extract_schema()` で JSON → SchemaNode
- `merge()` で複数トレースを統合

**TraceRecord** (`tracing.py`)
- 1 回の API 呼び出しのスナップショット
- EndpointKey（正規化されたエンドポイント識別子）
- リクエスト/レスポンススキーマ

**EmulationSpec** (`cli.py`)
- エンドポイントごとの集約されたスキーマ
- ステータスコード別のレスポンススキーマ
- 型ヒント情報

詳細は [CLAUDE.md](CLAUDE.md) を参照してください。

### アップデート予定

- GraphQL 対応
- gRPC 対応

---

## FAQ

### Q1: 実際の値は本当に保存されないのですか？

**A:** トレースファイル（`.ndjson`）には一時的に値が含まれますが、これは型推論の精度向上のためです。`skeleton build-env --infer-types` 実行後は、トレースファイルを `--delete-traces` オプションで削除できます。最終的な `.skel.json` には**スキーマと型情報のみ**が保存されます。

完全に値を保存したくない場合は `--key-names-only` オプションを使用してください。

### Q2: どの LLM プロバイダーが使えますか？

**A:** OpenAI API 互換のプロバイダーに対応しています:
- OpenAI（GPT-4、GPT-4o-mini など）
- Azure OpenAI（国内リージョン対応）
- Google Gemini（via OpenAI 互換 API）
- その他 OpenAI 互換エンドポイント

カスタム LLM プロバイダーも `LLMProvider` インターフェースを実装することで追加可能です。

### Q3: 既存のコードへの影響はどのくらいですか？

**A:** 最小限です。`@trace` または `@emulate` デコレータを追加するだけで動作します。`requests.request()` の署名や戻り値は変更しません。環境変数 `SKELETON_MODE=off` でいつでも無効化できます。

### Q4: エミュレートできないエンドポイントがある場合は？

**A:** `fallback_original=True` オプションを使用すると、スキーマがない場合に実際の API にフォールバックします:

```python
@emulate(env, fallback_original=True)
def my_request(method, url, **kwargs):
    return requests.request(method, url, **kwargs)
```

### Q5: requests 以外の HTTP クライアントに対応していますか？

**A:** 現在は `requests` ライブラリのみ対応しています。`httpx`、`aiohttp` などへの対応はロードマップに含まれています（v0.4.0 以降）。

### Q6: 認証情報はどう扱われますか？

**A:** ヘッダー情報（API キーなど）はデフォルトで記録されません。エンドポイントパターンと JSON 構造のみ記録されます。セキュリティ上の理由から、認証情報を含むヘッダーはトレース対象に含まれません。

### ライセンス

MIT License
