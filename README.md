# BOATRACE 最終日予想ファイル作成ツール

Streamlitで、ChatGPTブラウザに添付する4ファイルを作成するためのMVPです。
OpenAI APIは使いません。

## 作成する4ファイル

- `racelist_detail_jcdXX_YYYYMMDD.csv`
- `racer_course_style_summary_jcdXX_YYYYMMDD_YYYYMMDD.csv`
- `README.md`
- `展開.txt`

## 取得ルール

- 初日〜前日: `raceresult` を取得して選手別・コース別傾向を集計
- 最終日: `racelist` のみ取得
- 最終日の `raceresult` / `refund` / `odds` / `beforeinfo` は取得しない

## ローカル起動

```bash
python -m venv .venv
source .venv/bin/activate  # Windows: .venv\Scripts\activate
pip install -r requirements.txt
streamlit run app.py
```

## コマンド実行

```bash
python run_local.py --jcd 14 --start 20260429 --prev 20260503 --final 20260504
```

## Streamlit Community Cloudで使う場合

1. このフォルダをGitHubにpush
2. Streamlit Community Cloudでリポジトリを選択
3. Main file path に `app.py` を指定
4. Deploy

## 注意

BOATRACE公式サイトのHTML構造が変わるとparserが壊れる可能性があります。
その場合は、アプリで「デバッグ用に取得HTMLも保存する」をONにして、`outputs/.../debug_html/` のHTMLを確認してください。
