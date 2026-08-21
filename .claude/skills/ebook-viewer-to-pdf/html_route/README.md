# HTMLテキスト版ルート（スクショ+OCRを使わない）

対象: **本文が画像ではなく本物のHTMLテキスト**で配信されている電子書籍
（会員向けWeb書籍、Web連載をまとめた書籍など）。

このルートなら本文は**元テキストそのまま**＝誤字ゼロで検索・コピーできる。
OCRは図表画像にだけ後から重ねる。スクショルートより速く、品質も上。

## 判定（最初の5分でやる）

対象ページで次を確認する。

```js
const c = document.querySelector('<本文コンテナのセレクタ>');
JSON.stringify({ textLen: c.innerText.length, imgs: c.querySelectorAll('img').length })
```

- `textLen` が数千あり、文章が読める → **このルート**
- 本文が `<img>` だけ / canvas / テキストが取れない → 親ディレクトリの `SKILL.md`（スクショルート）へ

## 手順

### 1. ページ一覧を取る
目次ページから本文ページのURLを列挙する（`a[href*="<本文のパス>"]` を重複排除）。
記事内ページ送り（`◀ 1 ▶` のような表示）が「1」だけであること＝1記事1ページを確認する。

### 2. 取得経路を実測する（ここを飛ばすと後で詰む）
会員コンテンツは**普通のページ遷移以外を弾く**ことが多い。次を順に試す。

| 経路 | 判定方法 |
|---|---|
| `curl`（未ログイン） | 本文の特徴的な語がHTMLに含まれるか |
| ページ内 `fetch(url, {credentials:'include'})` | 本文コンテナが取れるか |
| 同一オリジンのiframe | `contentDocument` が `null` でないか |
| **タブを実際に navigate** | 最終手段だが確実 |

実例では curl / fetch / iframe すべて弾かれ、**navigate だけが通った**
（サーバーが `Sec-Fetch-Mode: navigate` 以外を拒否している）。

**図表画像は別ドメインのCDNにあり、認証不要なことが多い。** `img.src` のホストを必ず確認する
（同一オリジンだと思い込むとcanvasが汚染されて `toDataURL` が落ちる＝そこで気づける）。
CDN直だとページ経由の `fetch` が404でも、`curl` では200で普通に取れる。

### 3. 本文を抽出（`extract_pages.js`）
navigate → 抽出 を `browser_batch` で1コールにまとめ、5ページずつ処理する。
抽出結果は **localStorage に貯める**（ページ遷移でグローバル変数は消えるがlocalStorageは残る）。
ツールの戻り値は検証用の1行だけにして、本文をコンテキストに載せない。

### 4. 1ファイルだけダウンロード（`dump_download.js`）
全章まとめて1つのJSONをBlobでダウンロードする。ダウンロードは事前にユーザーへ一言伝える。

### 5. 図表をCDNから取得
JSONから `img` のURLを列挙して `curl -O`。**URLリストをPythonで書き出すときは改行がCRLFになる**
（`io.open(...,'w')` のWindows既定）。`tr -d '\r'` を通さないと curl が全件 `000` で落ちる。
`xargs -P 8` で並列化すると速い。

### 6. 書籍HTMLを組む（`build_book.py`）
表紙 → 目次 → 各章。図表はローカル相対パス参照。

### 7. PDF化（Chromeヘッドレス）
```
"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe" --headless=new --disable-gpu \
  --no-pdf-header-footer --virtual-time-budget=120000 \
  --user-data-dir="<temp>\chromeprof" --print-to-pdf="<out>\book.pdf" "file:///<path>/book.html"
```
Chromeの印刷なので**テキスト層はそのまま残る**。`--user-data-dir` を別に切らないと
起動中のChromeとぶつかる。フォールバックは `msedge.exe`（同じエンジン）。

### 8. 図表OCRを重ねる（`ocr_overlay.py`）
`PYTHONUTF8=1 PYTHONIOENCODING=utf-8` 必須。100枚超は `run_in_background`。
画像とPDF内の配置は**埋め込み画像バイト列のMD5**で突き合わせる（1:1で一致するはず。要確認）。

### 9. しおり（`add_bookmarks.py`）
見出しをフォントサイズで検出する。**必ずOCR前のPDFを検出元に渡す**
（OCR層の文字を見出しと誤検出して、しおりにゴミが混ざる。実際に混ざった）。

### 10. 検証（`verify_html_route.py`）
- 元HTMLとPDFテキストを章ごとにスライス照合 → 欠けゼロ
- 使用文字の集合差 → ゼロ
- OCR前後のページ画像のピクセル差 → 0（OCR層が不可視である証明）
- 先頭・中間・終盤を実際に画像化して目視

## 落とし穴

- **pypdfのテキスト抽出は游ゴシックを誤読する。** グリフの逆引きで康熙部首（`目`→`⽬` U+2F6C など）や
  異体字（`黒`→`黑`）を返す。**PyMuPDFなら正しく取れる**ので、検証は必ずPyMuPDFで行う。
  「PDFが壊れている」と誤診しやすい。実PDFリーダーの検索は問題ない。
  互換性のために `fix_cmap.py` でToUnicode CMapを直しておくと、pypdf系のツールでも正しく読める。
- **OCR層と本文層はフォント名で見分けられる**（本文=`YuGothic-*` / OCR層=`MS-Gothic`）。
  検証時に混ぜると「本文が欠けている」ように見える。
- 図表だけのページは本文テキストが0文字になる。白紙ページと誤判定しない。
- 作業後は localStorage に置いたキーを消し、開いたタブを閉じる。

## 成果物の置き場所
Googleドライブの電子書籍PDFフォルダに `<書名>_searchable.pdf` として置く（正確なパスはメモリ参照）。
ローカルには重いファイルを残さない。中間ファイル（図表画像・中間PDF・プレビュー）も作業後に削除する。
