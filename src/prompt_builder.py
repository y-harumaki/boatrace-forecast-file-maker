from __future__ import annotations


def build_chatgpt_prompt(jcd: str, start_hd: str, prev_hd: str, final_hd: str) -> str:
    jcd = str(jcd).zfill(2)
    return f"""以下の4ファイルをもとに、最終日の各レースを予想してください。

対象:
- 場コード: jcd={jcd}
- 初日: {start_hd}
- 前日: {prev_hd}
- 最終日: {final_hd}

添付ファイル:
1. racelist_detail_jcd{jcd}_{final_hd}.csv
2. racer_course_style_summary_jcd{jcd}_{start_hd}_{prev_hd}.csv
3. README.md
4. 展開.txt

重要:
- 予想はREADME.mdの方針に従ってください。
- 展開予想は必ず展開.txtの型に当てはまるかどうかで判定してください。
- 展開.txtに明確に当てはまらないレースは、無理に買い候補にしないでください。
- 1号艇のイン信頼が崩れていない場合は、まず1号艇中心の展開を優先してください。
- 4号艇・5号艇・6号艇頭は、README.mdに記載された条件が揃う場合のみ採用してください。
- 最終日の結果・払戻・オッズ・直前情報は使わない前提で判断してください。
- 各レース最大6点まで、3連単で本線・押さえを出してください。
- C評価は原則見送りにしてください。
- コース別集計のentriesが3未満の傾向は、強い根拠ではなく参考扱いにしてください。
- 今節集計が存在しない選手は、出走表の全国勝率・当地勝率・平均ST・モーター情報を優先して判断してください。

出力:
1. 各レースの展開型判定
2. 自信度 A/B/C
3. 買い/見送り
4. 本線買い目
5. 押さえ買い目
6. 根拠
7. 不安要素
8. 最後に買い候補一覧表
"""
