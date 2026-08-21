// 全ページ抽出後に1回だけ実行。localStorage に溜めた全章を1つのJSONにしてダウンロードする。
// ツール出力経由で本文を往復させるとコンテキストを大量に食うので、必ずこのダウンロード経路を使う。
// ※ ダウンロードはユーザーの明示的な承認が必要な操作。実行前に一言伝えること。
const PREFIX = 'bk_';           // ← extract_pages.js と同じ接頭辞
const IDS = ['0000', '0101'];   // ← 実際のID一覧に差し替える
const recs = IDS.map(i => JSON.parse(localStorage.getItem(PREFIX + i)));
const missing = IDS.filter((i, k) => !recs[k]);
if (missing.length) throw new Error('missing: ' + missing.join(','));
const json = JSON.stringify({ book: '書名', source: location.origin, chapters: recs });
const b = new Blob([json], { type: 'application/json' });
const a = document.createElement('a');
a.href = URL.createObjectURL(b);
a.download = 'book.json';
document.body.appendChild(a);
a.click();
setTimeout(() => { URL.revokeObjectURL(a.href); a.remove(); }, 4000);
'download triggered, chars=' + json.length;   // UTF-8のバイト数は日本語ぶん約2.3倍になる
