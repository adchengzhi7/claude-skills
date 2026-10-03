// 貓咪咖啡廳：同一份資料、同一套判斷，換一組長相和用語。拿來當「做自己的外觀包」的範本——
// 複製這個資料夾、改名字，然後改這裡的圖和字、改 theme.css 的顏色與排法就好。
(function () {
  // 用文字畫貓：每個字元一格，F＝毛色、W＝白、P＝粉紅，其他＝透明
  const CAT = [
    '',
    '.....F........F',
    '....FPF......FPF',
    '....FFFFFFFFFFFF',
    '...FFFFFFFFFFFFFF',
    '...FFFFFFFFFFFFFF',
    '...FFFFFFFFFFFFFF',
    '...FFFFFWPPWFFFFF',
    '....FFFFWWWWFFFF',
    '.....FFFFFFFFFF',
    '....FFFFFFFFFFFF....F',
    '...FFFFWWWWWWFFFF..FF',
    '...FFFFWWWWWWFFFF.FF',
    '...FFFFWWWWWWFFFFFF',
    '...FFWWFFFFFFWWFF',
  ];
  const FUR = { wait: '#f08c3a', run: '#8d99ae', done: '#e9c9a0', er: '#5c5f66', ice: '#bcd9ec' };
  const r = (x, y, w, h, fill, extra) => '<rect x="' + x + '" y="' + y + '" width="' + w + '" height="' + h + '" fill="' + fill + '"' + (extra || '') + '/>';
  const openEyes = r(6, 4.6, 1.3, 2, '#2b2118') + r(12.7, 4.6, 1.3, 2, '#2b2118');
  const shutEyes = r(5.6, 5.8, 2.2, .6, '#2b2118') + r(12.2, 5.8, 2.2, .6, '#2b2118');
  const crossEyes = '<path d="M5.8 4.8l1.8 1.8M7.6 4.8L5.8 6.6M12.4 4.8l1.8 1.8M14.2 4.8l-1.8 1.8" stroke="#fff" stroke-width=".6"/>';

  // kind：wait＝舉手叫你、run＝敲筆電、done＝睡著、er＝暈了、ice＝結冰
  function person(kind) {
    const fur = FUR[kind] || FUR.done;
    let s = OfficeKit.rects(CAT, { F: fur, W: '#fff8ee', P: '#f4a6b7' });
    if (kind === 'wait') {
      s += openEyes + '<g class="hand">' + r(17, 4, 2, 5, fur) + r(17, 3, 2, 1.4, '#fff8ee') + '</g>';
      s += '<g class="bang">' + r(21, 1, 1.5, 4, '#f08c3a') + r(21, 6, 1.5, 1.5, '#f08c3a') + '</g>';
    } else if (kind === 'run') {
      s += openEyes + r(6, 11, 8, 4, '#4a4e69') + r(9.4, 12.5, 1.2, 1, '#c9d6ff', ' class="glow"');
      s += '<g class="arm">' + r(4.6, 12, 2, 1.2, '#fff8ee') + r(13.4, 12, 2, 1.2, '#fff8ee') + '</g>';
    } else if (kind === 'done') {
      s += shutEyes + '<text class="zz" x="18" y="5" font-size="4" font-weight="700" fill="#9a8468">z</text>';
    } else if (kind === 'er') {
      s += crossEyes + r(8, .2, 4, 1.2, '#e06666') + r(9.4, -1.2, 1.2, 4, '#e06666');
    } else {
      s += shutEyes + r(1.5, .5, 17, 15, '#bfe8ff', ' opacity=".4"') + r(1.5, .5, 17, .6, '#fff', ' opacity=".9"') + r(1.5, .5, .6, 15, '#fff', ' opacity=".9"');
      s += '<g class="snow">' + r(20.5, 2, 1, 3, '#8fc4e8') + r(19.5, 3, 3, 1, '#8fc4e8') + r(21.5, 9, 1, 1, '#8fc4e8') + '</g>';
    }
    return '<svg class="me" viewBox="0 -1.5 24 17.5" xmlns="http://www.w3.org/2000/svg" aria-hidden="true">' + s + '</svg>';
  }

  // 派出去的 agent＝出門的小魚乾
  const FISH = OfficeKit.rects(['..BBBB..B', '.BBBBBB.BB', 'BBKBBBBBBB', '.BBBBBB.BB', '..BBBB..B'], { B: '#74c0fc', K: '#1c3d5a' });
  const helper = (px) => '<svg viewBox="0 0 10 5" width="' + px + '" height="' + Math.round(px / 2) + '" xmlns="http://www.w3.org/2000/svg" aria-hidden="true">' + FISH + '</svg>';

  // 特別標記＝貓掌印
  const PAW = OfficeKit.rects(['.P.P.P', '.P.P.P', '', '..PPP', '.PPPPP', '..PPP'], { P: '#f06595' });
  const mark = () => OfficeKit.svg(7, 6, PAW);

  window.SESSION_OFFICE_THEME = {
    name: '貓咪咖啡廳',
    labels: {
      title: '貓咪咖啡廳',
      er: { title: '獸醫室：不太對勁', calm: '大家都好好的', closed: '有貓卡住或暈倒了；點開看是誰' },
      wait: { title: '櫃檯：在叫你', hint: '先理牠', empty: '沒有貓在叫你' },
      run: { title: '遊戲區：正在忙', hint: '讓牠玩', empty: '沒有貓在忙' },
      done: { title: '窗台：做完在睡', hint: '有空再看', empty: '窗台空空的' },
      frozen: { title: '冬眠區：已過期', closed: '點開看是誰（回去摸一下就醒）' },
      ended: { title: '回家了：過去 12 小時內關掉的 session' },
      running: '敲鍵盤中',
      helpers: (n) => '等 ' + n + ' 條小魚乾回來',
      helperWord: '小魚乾',
    },
    // 沒寫 jump＝切視窗提示不放圖，只有字（示範：外觀包可以只寫想改的部分）
    sprites: { person, helper, mark },
  };
})();
