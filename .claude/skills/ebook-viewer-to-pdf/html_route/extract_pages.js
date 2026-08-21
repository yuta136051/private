// ブラウザ側の抽出テンプレート。claude-in-chrome の javascript_tool で 1 ページごとに実行する。
// 使い方:
//   1) 最初に一度だけ localStorage['EXT'] にこの関数本体を入れる
//   2) 各ページで navigate → `await eval('(async()=>{'+localStorage.getItem('EXT')+'})()')`
//      （ページ遷移で JS のグローバルは消えるが localStorage は残る、が要点）
//   3) 全ページ終わったら dump_download.js で 1 ファイルだけダウンロードする
// CONTENT_SEL はサイトごとに実測して差し替える。

const PREFIX = 'bk_';                                  // ← localStorage のキー接頭辞
const CONTENT_SEL = '.premium-blog-article-content';   // ← 本文コンテナ
const DROP_SEL = '.article-inline-banner,.ad-data,script,ins,iframe,noscript'; // ← 広告等

const id = location.pathname.split('/').filter(Boolean).pop();
let c = null;
for (let i = 0; i < 40; i++) {                 // 本文がJSで後入れされる場合があるのでポーリング
  c = document.querySelector(CONTENT_SEL);
  if (c && c.innerText.trim().length > 300) break;
  await new Promise(r => setTimeout(r, 300));
}
let out;
if (!c) {
  out = { id, err: 'no content' };
} else {
  const cl = c.cloneNode(true);
  cl.querySelectorAll(DROP_SEL).forEach(e => e.remove());
  cl.querySelectorAll('img').forEach(im => {
    im.setAttribute('src', im.src);            // 相対→絶対(別ドメインCDNのこともある)
    im.removeAttribute('srcset');
    im.removeAttribute('loading');
    im.removeAttribute('class');
  });
  const pag = document.querySelector('.article-pagination');   // 記事内ページ送りの有無を確認
  const h1 = document.querySelector('h1');
  const rec = {
    id,
    title: h1 ? h1.innerText.replace(/\s+/g, ' ').trim() : '',
    html: cl.innerHTML,
    pagination: pag ? pag.innerText.replace(/\s+/g, ' ').trim() : ''
  };
  localStorage.setItem(PREFIX + id, JSON.stringify(rec));
  // 戻り値は検証用の1行だけ。本文をツール出力に載せない(コンテキスト浪費と情報漏れの両方を避ける)
  out = { id, title: rec.title.slice(0, 45), htmlLen: rec.html.length,
          textLen: cl.innerText.length, imgs: cl.querySelectorAll('img').length,
          pag: rec.pagination };
}
return JSON.stringify(out);
