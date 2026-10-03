// Session 辦公室的判斷邏輯：誰進哪個房間、快取倒數、分組。所有外觀包共用這一份。
// 純函式、不碰畫面（時間用參數傳進來），所以瀏覽器和測試（node）讀的是同一個檔。
(function (root, factory) {
  const api = factory();
  if (typeof module === 'object' && module.exports) module.exports = api;
  else root.OfficeLogic = api;
})(typeof self !== 'undefined' ? self : this, function () {
  // 狀態 → 房間：wait＝會議室（等你）、run＝工作區、done＝茶水間、off＝已關閉
  const TONE = { waiting_question: 'wait', waiting_permission: 'wait', ball: 'wait', running: 'run', helpers: 'run', reported: 'done', idle: 'done', ended: 'off' };
  const WORD = { waiting_question: '等你回答', waiting_permission: '等你授權', ball: '球在你這裡', running: '執行中', helpers: '等幫手回來', reported: '已回報', idle: '待命', ended: '已結束' };
  const URGENT_S = 600, CRIT_S = 180;
  const PALETTE = ['#d9480f', '#7048e8', '#c2255c', '#1098ad', '#5c940d', '#e67700', '#1971c2', '#495057'];
  const OTHER = '其他';

  // 沒見過的狀態不准安靜收進「已關閉」或「做完了」：一律進急診室標「未知狀態」，讓人看到
  // 用 hasOwnProperty 查表：狀態字串是外面來的，直接用 TONE[x] 會被 'constructor' 這類字騙過去
  const known = (s) => Object.prototype.hasOwnProperty.call(TONE, s.state);
  const tone = (s) => (known(s) ? TONE[s.state] : 'wait');
  const stateWord = (s) => (known(s) ? WORD[s.state] : '未知狀態：' + s.state);
  const inER = (s) => !!(s.trouble && s.trouble.text) || !known(s);
  const erText = (s) => (s.trouble && s.trouble.text) || ('認不得的狀態：' + s.state + '（Claude Code 可能改版了，辦公室要更新）');
  const helpersOf = (s) => Math.max(0, Math.floor(Number(s.helpers) || 0));

  function ago(ts, now) {
    const sec = Math.max(0, now - (ts || 0));
    if (sec < 60) return '剛剛';
    if (sec < 3600) return Math.floor(sec / 60) + ' 分前';
    if (sec < 86400) return Math.floor(sec / 3600) + ' 小時前';
    return Math.floor(sec / 86400) + ' 天前';
  }
  const mmss = (sec) => { sec = Math.max(0, Math.floor(sec)); return String(Math.floor(sec / 60)).padStart(2, '0') + ':' + String(sec % 60).padStart(2, '0'); };
  function tokensText(n) {
    if (!n) return '0';
    return n >= 10000 ? (Math.round(n / 1000) / 10) + ' 萬' : Number(n).toLocaleString('en-US');
  }
  function displayName(s) {
    if (s.name) return s.name;
    const m = (s.path || '').match(/\/([^/]+)\/\.claude\/worktrees\//);
    if (m) return m[1] + '（分支）';
    if ((s.path || '') === '~') return '家目錄';
    return s.project || '？';
  }

  // 快取倒數：剩不到 10 分鐘＝快過期（最優先提醒）；已過期且已經做完＝進冰庫
  const cacheLeftS = (s, now) => (s.cacheExpiresAt && Number.isFinite(Number(s.cacheExpiresAt)) ? Number(s.cacheExpiresAt) - now : null);
  // 沒有人坐在前面的 session（腳本、agent 開的）不催：你沒辦法「回去說一句」讓它不過期
  const isExpiring = (s, now) => { const l = cacheLeftS(s, now); return s.state !== 'ended' && !s.headless && l != null && l > 0 && l < URGENT_S; };
  const isFrozen = (s, now) => { const l = cacheLeftS(s, now); return s.state !== 'ended' && tone(s) === 'done' && l != null && l <= 0; };
  // 卡片上的快取小框要用哪一種樣子：gone＝已過期、soon＝快過期要催、ok＝還久；null＝不顯示（沒資料或數字離譜）
  function cacheKind(s, now) {
    const l = cacheLeftS(s, now);
    if (l == null || !(l < 7200)) return null;
    if (l <= 0) return 'gone';
    return isExpiring(s, now) ? 'soon' : 'ok';
  }
  const frozenLabel = (s, now) => { const m = Math.round(-cacheLeftS(s, now) / 60); return m < 1 ? '剛凍住' : '凍住 ' + (m >= 60 ? Math.floor(m / 60) + ' 小時' : m + ' 分'); };

  // 設定檔裡的分組、標記、「球在你這裡」句型 → 編成可以直接用的樣子。寫錯的那一條跳過並回報，不讓整頁壞掉
  function compileConfig(cfg) {
    const out = { groups: [], mark: null, ballPhrases: [], warnings: [] };
    const c = cfg || {};
    const rx = (text, where) => {
      try { return new RegExp(text, 'i'); } catch (e) { out.warnings.push(where + ' 的 match 在瀏覽器裡不是合法的正規表示式'); return null; }
    };
    (Array.isArray(c.groups) ? c.groups : []).forEach((g, i) => {
      const re = g && typeof g.match === 'string' ? rx(g.match, '分組「' + g.name + '」') : null;
      if (re && g.name) out.groups.push({ name: String(g.name), color: String(g.color || PALETTE[i % PALETTE.length]), re });
    });
    if (c.mark && typeof c.mark.match === 'string') {
      const re = rx(c.mark.match, '標記');
      if (re) out.mark = { label: String(c.mark.label || '標記'), re };
    }
    out.ballPhrases = (Array.isArray(c.ballPhrases) ? c.ballPhrases : []).filter((p) => typeof p === 'string' && p);
    return out;
  }
  function hashColor(name) {
    let h = 0;
    for (const ch of String(name)) h = (h * 31 + ch.codePointAt(0)) >>> 0;
    return PALETTE[h % PALETTE.length];
  }
  // 分組：先看資料夾與名字，再看對話內容；都對不上就用資料夾名當組名（不用設定也有顏色可分）
  function groupOf(s, cc) {
    const where = [s.path, s.name, s.windowName, s.project].filter(Boolean).join(' ');
    for (const g of cc.groups) if (g.re.test(where)) return { name: g.name, color: g.color };
    const said = [s.lastUser, s.lastReport, s.question].filter(Boolean).join(' ');
    for (const g of cc.groups) if (g.re.test(said)) return { name: g.name, color: g.color };
    const name = s.project || OTHER;
    return { name, color: hashColor(name) };
  }
  const isMarked = (s, cc) => !!cc.mark && ['name', 'windowName', 'path', 'lastUser', 'lastReport', 'question'].some((k) => cc.mark.re.test(s[k] || ''));
  // 泡泡裡的話：在等你時是它問你的事，否則是最後一句回報；「球在你這裡」那類固定開頭拿掉，只留內容
  function say(s, cc) {
    let text = s.question || s.lastReport || '';
    for (const p of (cc ? cc.ballPhrases : [])) if (text.startsWith(p)) { text = text.slice(p.length).replace(/^[\s：:，,]+/, ''); break; }
    return text;
  }

  // 篩選鈕選的那一組如果已經沒有人了（分組會看最後一句話，講一句就可能換組），那顆鈕會從畫面消失、沒得取消，
  // 整間辦公室就變空——有人在等你也看不到。所以每次重畫先把已經不存在的篩選拿掉
  function pruneFilter(filter, data, cc) {
    const alive = new Set();
    for (const s of ((data && data.sessions) || [])) {
      alive.add(groupOf(s, cc).name);
      if (isMarked(s, cc)) alive.add('*mark');
    }
    return new Set([...(filter || [])].filter((k) => alive.has(k)));
  }

  const byNewest = (a, b) => (b.since || 0) - (a.since || 0);
  // 把一份資料分進各個房間。filter＝篩選鈕選到的組名（Set，空的＝全部）；'*mark'＝只看有標記的
  function buildModel(data, now, cc, filter) {
    const all = [...((data && data.sessions) || [])].sort(byNewest);
    const groups = {};
    all.forEach((s) => { const g = groupOf(s, cc); groups[g.name] = groups[g.name] || { name: g.name, color: g.color, n: 0 }; groups[g.name].n++; });
    const on = filter && filter.size ? filter : null;
    const shown = all.filter((s) => !on || on.has(groupOf(s, cc).name) || (on.has('*mark') && isMarked(s, cc)));
    const expiringFirst = (a, b) => (isExpiring(b, now) - isExpiring(a, now)) || (isExpiring(a, now) ? cacheLeftS(a, now) - cacheLeftS(b, now) : 0);
    const room = (t) => shown.filter((s) => !inER(s) && tone(s) === t && !isFrozen(s, now)).sort(expiringFirst);
    const age = now - (data && data.generatedAt != null ? Number(data.generatedAt) : NaN);
    return {
      er: shown.filter(inER).sort((a, b) => (Number(b.trouble && b.trouble.since) || 0) - (Number(a.trouble && a.trouble.since) || 0)),
      wait: room('wait'), run: room('run'), done: room('done'),
      frozen: shown.filter((s) => !inER(s) && isFrozen(s, now)).sort((a, b) => Number(b.cacheExpiresAt) - Number(a.cacheExpiresAt)),
      ended: shown.filter((s) => !inER(s) && tone(s) === 'off'),
      // 急診室的不在警示條重複出現
      urgent: all.filter((s) => !inER(s) && isExpiring(s, now)).sort((a, b) => cacheLeftS(a, now) - cacheLeftS(b, now)),
      groups: Object.values(groups).sort((a, b) => b.n - a.n),
      marked: all.filter((s) => isMarked(s, cc)).length,
      age,
      // 沒時間戳、單位錯（毫秒會變成很大的負數）、太舊，一律當過期：過期的畫面要變灰、不能點
      stale: !(age >= -120 && age <= 60),
      total: all.length,
      hidden: all.length - shown.length,
    };
  }

  return { TONE, WORD, URGENT_S, CRIT_S, PALETTE, tone, stateWord, inER, erText, helpersOf, ago, mmss, tokensText, displayName,
    cacheLeftS, isExpiring, isFrozen, cacheKind, frozenLabel, compileConfig, groupOf, isMarked, say, pruneFilter, buildModel };
});
