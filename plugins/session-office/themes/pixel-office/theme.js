// 像素辦公室的小人與用語。小人用 SVG 一格一格畫（48×36 的格子）。
// 外觀包只負責「長相和用語」：這裡沒有任何判斷邏輯，也不要在這裡讀資料或連網路。
(function () {
  const r = (x, y, w, h, fill, extra) => '<rect x="' + x + '" y="' + y + '" width="' + w + '" height="' + h + '" fill="' + fill + '"' + (extra || '') + '/>';
  const SKIN = '#f2c9a0', DARK = '#1c1b28';
  const DESK = r(2, 24, 44, 3, '#8a5a36') + r(4, 27, 3, 9, '#6b4428') + r(41, 27, 3, 9, '#6b4428');

  // 坐在桌前的人。kind：wait＝舉手等你、run＝打字中、done＝做完往後靠、er＝出狀況、ice＝被冰塊包住
  function person(kind) {
    if (kind === 'ice') return frozen();
    const shirt = { wait: '#e8590c', run: '#2f6fed', done: '#2b9348', er: '#c92a2a' }[kind] || '#2b9348';
    const screen = { wait: '#ffb07a', run: '#9cc2ff', done: '#8ee6a9', er: '#ff8787' }[kind] || '#8ee6a9';
    let s = r(30, 10, 14, 10, DARK) + r(31, 11, 12, 8, screen, kind === 'run' ? ' class="glow"' : '') + r(36, 20, 2, 4, DARK);
    if (kind === 'er') s += r(36, 12, 2, 4, '#8a1c1c') + r(36, 17, 2, 1, '#8a1c1c');
    if (kind === 'done') s += r(34, 15, 2, 2, '#1c6b36') + r(36, 16, 2, 2, '#1c6b36') + r(38, 14, 2, 2, '#1c6b36') + r(40, 12, 2, 2, '#1c6b36');
    s += DESK;
    s += '<g transform="translate(' + (kind === 'done' ? -2 : 0) + ',0)">' + r(13, 6, 8, 8, SKIN) + r(13, 5, 8, 3, '#3a2a1a') + r(15, 9, 1, 1, '#222') + r(18, 9, 1, 1, '#222') + r(11, 14, 12, 10, shirt) + '</g>';
    if (kind === 'run') s += '<g class="arm">' + r(22, 18, 8, 3, shirt) + r(29, 18, 2, 3, SKIN) + '</g>';
    else if (kind === 'wait') s += '<g class="hand">' + r(22, 6, 3, 10, shirt) + r(22, 3, 3, 3, SKIN) + '</g><g class="bang">' + r(3, 1, 3, 7, '#ffd84d') + r(3, 10, 3, 3, '#ffd84d') + '</g>';
    else s += r(7, 12, 6, 3, shirt) + r(21, 12, 6, 3, shirt);
    s += r(11, 24, 12, 3, '#2a2938');
    return OfficeKit.svg(48, 36, s, 'me');
  }

  function frozen() {
    const ice = ' opacity=".9"';
    let s = r(30, 10, 14, 10, DARK) + r(31, 11, 12, 8, '#2a3444') + r(36, 20, 2, 4, DARK);
    s += r(2, 24, 44, 3, '#6f7f8f') + r(4, 27, 3, 9, '#56636f') + r(41, 27, 3, 9, '#56636f');
    s += r(13, 6, 8, 8, '#cfe3f0') + r(13, 5, 8, 3, '#5c6b78') + r(15, 9, 1, 1, '#3b5a73') + r(18, 9, 1, 1, '#3b5a73');
    s += r(11, 14, 12, 10, '#7fa8c9') + r(7, 12, 6, 3, '#7fa8c9') + r(21, 12, 6, 3, '#7fa8c9') + r(11, 24, 12, 3, '#3d4a57');
    s += r(8, 2, 20, 26, '#bfe8ff', ' opacity=".42"') + r(8, 2, 20, 1, '#eaf8ff', ice) + r(8, 2, 1, 26, '#eaf8ff', ice) + r(11, 4, 2, 1, '#fff', ice) + r(11, 5, 1, 2, '#fff', ice);
    s += '<g class="snow">' + r(3, 3, 1, 3, '#fff') + r(2, 4, 3, 1, '#fff') + r(41, 4, 1, 3, '#fff') + r(40, 5, 3, 1, '#fff') + r(44, 1, 1, 1, '#fff') + r(34, 2, 1, 1, '#fff') + '</g>';
    return OfficeKit.svg(48, 36, s, 'me');
  }

  // 派出去的 agent 畫成馬爾濟斯：第一隻最大、後面依序變小（大小由 px 決定）
  const MALTESE = ['.....PP..PP.....', '......PPPP......', '.....GWPPWG.....', '...GWWWWWWWWG...', '..GCWWWWWWWWCG..', '..CCWKWWWWKWCC..', '..CCWWWWWWWWCC..',
    '..CCWWWNNWWWCC..', '...CGWWTTWWGC.GG', '....GWWWWWWWWGWG', '....WWWWWWWWWWWG', '....GWWWWWWWWWG.', '....WW.WW..WW.WW'];
  const DOG = OfficeKit.rects(MALTESE, { W: '#ffffff', G: '#d6d4e0', C: '#efe3c8', K: '#1d1d1b', N: '#1d1d1b', P: '#ff6b9a', T: '#ff8fab' });
  const helper = (px) => '<svg class="dog" viewBox="0 0 16 13" width="' + px + '" height="' + Math.round(px * 13 / 16) + '" xmlns="http://www.w3.org/2000/svg" aria-hidden="true">' + DOG + '</svg>';

  // 特別標記：愛心
  const mark = () => '<svg viewBox="0 0 7 6" xmlns="http://www.w3.org/2000/svg" aria-hidden="true"><path fill="#e64980" d="M1 0h2v1h1V0h2v1h1v2H6v1H5v1H4v1H3V5H2V4H1V3H0V1h1z"/><rect x="1" y="1" width="1" height="1" fill="#ffc9de"/></svg>';

  // 切視窗時的全螢幕提示：小人跑向門
  function jump() {
    const x = [[48, 14], [50, 16], [52, 18], [54, 20], [54, 14], [52, 16], [50, 18], [48, 20]].map(([a, b]) => r(a, b, 2, 2, '#ff6b6b')).join('');
    let s = r(0, 42, 64, 2, '#3a3950') + r(44, 8, 16, 34, '#0f0e16');
    s += '<g class="jf-shut">' + r(46, 10, 12, 32, '#6b4428') + r(55, 25, 2, 2, '#ffd43b') + '</g>';
    s += '<g class="jf-open">' + r(46, 10, 12, 32, '#8ee6a9') + r(46, 10, 3, 32, '#6b4428') + '</g><g class="jf-x">' + x + '</g>';
    s += '<g class="jf-runner">' + r(12, 16, 8, 8, SKIN) + r(12, 15, 8, 3, '#3a2a1a') + r(17, 19, 1, 1, '#222') + r(11, 24, 10, 10, '#4c8dff') + r(21, 25, 5, 3, '#4c8dff') + r(6, 27, 5, 3, '#4c8dff');
    s += '<g class="jf-leg-a">' + r(12, 34, 3, 8, '#2a2938') + r(18, 34, 3, 5, '#2a2938') + r(20, 38, 3, 3, '#2a2938') + '</g>';
    s += '<g class="jf-leg-b">' + r(17, 34, 3, 8, '#2a2938') + r(12, 34, 3, 5, '#2a2938') + r(9, 38, 3, 3, '#2a2938') + '</g>';
    s += r(2, 20, 4, 1, '#8e8ba6') + r(0, 24, 5, 1, '#8e8ba6') + r(2, 28, 3, 1, '#8e8ba6') + '</g>';
    return OfficeKit.svg(64, 48, s);
  }

  window.SESSION_OFFICE_THEME = {
    name: '像素辦公室',
    labels: {
      title: 'Session 辦公室',
      helpers: (n) => '等 ' + n + ' 隻狗狗回來',
      helperWord: '小狗',
    },
    sprites: { person, helper, mark, jump },
  };
})();
