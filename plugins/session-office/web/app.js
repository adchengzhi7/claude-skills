// Session 辦公室的畫面組裝：讀資料 → 用 logic.js 分房間 → 照外觀包給的小人和用語畫出來 → 點卡片請本機切 tmux 視窗。
// 外觀包（themes/<名字>/theme.js）只提供「長相和用語」，判斷邏輯都在 logic.js，換外觀不會換掉判斷。
(function () {
  'use strict';
  const L = window.OfficeLogic;
  const nowS = () => Date.now() / 1000;

  // 給外觀包用的小工具：用一排排文字畫像素圖。rows 每個字元是一格，palette 把字元對到顏色，沒對到的字元＝透明
  const rects = (rows, palette, x0 = 0, y0 = 0) => rows.map((row, y) => [...row].map((ch, x) => palette[ch]
    ? '<rect x="' + (x + x0) + '" y="' + (y + y0) + '" width="1.02" height="1.02" fill="' + palette[ch] + '"/>' : '').join('')).join('');
  const svg = (w, h, inner, cls) => '<svg' + (cls ? ' class="' + cls + '"' : '') + ' viewBox="0 0 ' + w + ' ' + h
    + '" xmlns="http://www.w3.org/2000/svg" aria-hidden="true">' + inner + '</svg>';
  window.OfficeKit = { rects, svg };

  // 外觀包沒給的項目用這份補上，所以外觀包可以只寫它想改的部分
  const DEFAULT_THEME = {
    name: '預設',
    labels: {
      title: 'Session 辦公室',
      er: { title: '急診室：出狀況了', calm: '目前沒有卡住或當掉的', open: '點這裡收起', closed: '卡住、當掉或停在錯誤訊息；點開看是誰' },
      wait: { title: '會議室：舉手等你', hint: '先處理這裡', empty: '沒有人在等你' },
      run: { title: '工作區：正在跑（含等幫手）', hint: '不用管它', empty: '空的' },
      done: { title: '茶水間：做完了', hint: '有空再看回報', empty: '空的' },
      frozen: { title: '冰庫：已過期', open: '點這裡收起', closed: '點開看是誰（回去用就會解凍）' },
      ended: { title: '已關閉：過去 12 小時內關掉的 session' },
      running: '努力中⋯⋯',
      helpers: (n) => '等 ' + n + ' 個幫手回來',
      helperWord: '幫手',
    },
    sprites: {
      person: (kind) => svg(48, 36, '<circle cx="24" cy="18" r="10" fill="' + ({ wait: '#e8590c', run: '#2f6fed', done: '#2b9348', er: '#c92a2a', ice: '#7fa8c9' }[kind] || '#888') + '"/>', 'me'),
      helper: (px) => '<svg viewBox="0 0 8 8" width="' + px + '" height="' + px + '" aria-hidden="true"><circle cx="4" cy="4" r="3" fill="#d0bfff"/></svg>',
      mark: () => '<svg viewBox="0 0 8 8" aria-hidden="true"><circle cx="4" cy="4" r="3" fill="#e64980"/></svg>',
      jump: () => '',
    },
  };
  let T = DEFAULT_THEME, themeId = '';
  function applyTheme(custom) {
    const c = custom && typeof custom === 'object' ? custom : {};
    const isObj = (v) => !!v && typeof v === 'object' && !Array.isArray(v);
    const textOrFn = (v) => typeof v === 'string' || typeof v === 'function';
    // 外觀包給的每一項都要型別對才收，不對就留預設值：不然一個寫錯的欄位會讓頁面停在「讀取中」而且沒有任何訊息
    const labels = {};
    Object.entries(DEFAULT_THEME.labels).forEach(([k, def]) => {
      const v = isObj(c.labels) ? c.labels[k] : undefined;
      if (isObj(def)) {
        labels[k] = { ...def };
        if (isObj(v)) Object.keys(def).forEach((f) => { if (typeof v[f] === 'string' && v[f]) labels[k][f] = v[f]; });
      } else labels[k] = textOrFn(v) ? v : def;
    });
    const sprites = { ...DEFAULT_THEME.sprites };
    if (isObj(c.sprites)) Object.keys(sprites).forEach((k) => { if (typeof c.sprites[k] === 'function') sprites[k] = c.sprites[k]; });
    T = { name: typeof c.name === 'string' && c.name ? c.name : DEFAULT_THEME.name, labels, sprites };
  }
  // 外觀包的函式壞了不能讓整頁白掉：退回預設的那一個
  const sprite = (name, ...args) => { try { return String(T.sprites[name](...args)); } catch (e) { return String(DEFAULT_THEME.sprites[name](...args)); } };
  const label = (v, ...args) => { try { return typeof v === 'function' ? String(v(...args)) : String(v); } catch (e) { return ''; } };

  const $ = (id) => document.getElementById(id);
  function el(tag, cls, text) { const e = document.createElement(tag); if (cls) e.className = cls; if (text != null) e.textContent = text; return e; }
  let toastTimer;
  function toast(msg) { const t = $('toast'); t.textContent = msg; t.classList.add('show'); clearTimeout(toastTimer); toastTimer = setTimeout(() => t.classList.remove('show'), 2500); }

  // ===== 切視窗：全螢幕提示。切換中擋住重複點擊；成功 2 秒自己收，失敗要點一下才收 =====
  let jumping = false, jumpTimer = null;
  function jumpFx(mode, t1, t2) {
    const fx = $('jumpfx');
    fx.className = 'jumpfx on ' + mode;
    const art = fx.querySelector('.jf-art');
    if (!art.dataset.drawn) { art.innerHTML = sprite('jump'); art.dataset.drawn = '1'; }
    fx.querySelector('.jf-t1').textContent = t1;
    fx.querySelector('.jf-t2').textContent = t2 || '';
    clearTimeout(jumpTimer);
    if (mode === 'ok') jumpTimer = setTimeout(closeJumpFx, 2200);
  }
  function closeJumpFx() {
    const fx = $('jumpfx');
    if (fx.classList.contains('go')) return; // 切換中不給關，避免以為沒反應又按一次
    fx.className = 'jumpfx'; jumping = false;
  }
  async function jump(s) {
    if (!s.pane) return toast('「' + L.displayName(s) + '」不在 tmux 裡（或視窗已經關了），沒辦法幫你切過去');
    if (jumping) return;
    jumping = true;
    jumpFx('go', '切換中⋯', '正在切到「' + L.displayName(s) + '」');
    const started = Date.now();
    try {
      const r = await fetch('/api/jump', { method: 'POST', headers: { 'Content-Type': 'application/json', 'X-Session-Office': '1' }, body: JSON.stringify({ pane: s.pane }) });
      const j = await r.json().catch(() => ({}));
      if (!r.ok) throw new Error(j.error || r.status);
      await new Promise((ok) => setTimeout(ok, Math.max(0, 600 - (Date.now() - started)))); // 至少讓人看到在切
      jumpFx('ok', '已切到「' + L.displayName(s) + '」', '回到終端機就會看到');
    } catch (e) { jumpFx('bad', '切換失敗', e.message + '。點一下關掉'); }
  }

  // ===== 快取快過期：最上面的警示條，每秒倒數；3 分內變紅。點一下切過去（回去說一句就不用整段重讀）=====
  let urgentList = [];
  function renderUrgent(list) {
    urgentList = list;
    const box = $('urgent');
    box.replaceChildren();
    box.classList.toggle('on', list.length > 0);
    if (!list.length) return;
    box.append(el('div', 'u-title', '快取快過期（' + list.length + '）：趁現在回去說一句，就不用整段重讀'));
    list.forEach((s) => {
      const r = el('button', 'u-row'); r.type = 'button'; r.dataset.id = s.id;
      r.append(el('span', 'u-time', L.mmss(L.cacheLeftS(s, nowS()))), el('span', 'u-name', L.displayName(s)), el('span', 'u-cost', '過期要重讀 ' + L.tokensText(s.ctxTokens) + ' token'));
      r.onclick = () => jump(s);
      box.append(r);
    });
    tickUrgent();
  }
  function tickUrgent() {
    const box = $('urgent');
    if (!box.classList.contains('on')) return;
    let alive = 0;
    box.querySelectorAll('.u-row').forEach((r) => {
      const s = urgentList.find((x) => x.id === r.dataset.id);
      const left = s ? L.cacheLeftS(s, nowS()) : 0;
      if (!(left > 0)) { r.remove(); return; }
      alive++;
      r.querySelector('.u-time').textContent = L.mmss(left);
      r.classList.toggle('crit', left < L.CRIT_S);
    });
    if (!alive) box.classList.remove('on');
  }

  // ===== 一張卡 =====
  function cacheBadge(s) {
    const kind = L.cacheKind(s, nowS()); // 要不要催由 logic.js 決定（沒有人坐在前面的 session 不催）
    if (!kind) return null; // 單位錯或資料怪：寧可不顯示，不顯示一個離譜的數字
    const tok = L.tokensText(s.ctxTokens);
    if (kind === 'gone') return el('div', 'cache gone', '快取已過期・續用要重讀 ' + tok + ' token');
    const m = Math.ceil(L.cacheLeftS(s, nowS()) / 60);
    return el('div', 'cache ' + kind, (kind === 'soon' ? '快取剩 ' + m + ' 分，要用趁現在' : '快取剩 ' + m + ' 分') + '・' + tok + ' token');
  }
  // context 提醒：剩 50% 以下黃字、15% 以下紅字（快到自動壓縮，前面細節會被摘要掉）
  function ctxWarn(s) {
    if (s.context == null || s.context > 50) return null;
    const pct = (s.contextEstimated ? '約 ' : '') + s.context + '%';
    return s.context <= 15 ? el('div', 'ctxwarn bad', 'context 快滿：剩 ' + pct + '，建議先交接再清空') : el('div', 'ctxwarn', 'context 剩 ' + pct + '，找個段落交接');
  }
  function bubbleText(s, kind) {
    const now = nowS();
    if (kind === 'er') return L.erText(s) + (s.trouble && s.trouble.since ? '（' + L.ago(s.trouble.since, now) + '）' : '');
    if (kind === 'ice') return L.frozenLabel(s, now) + '・下一句要重讀 ' + L.tokensText(s.ctxTokens) + ' token';
    if (s.state === 'helpers') return label(T.labels.helpers, L.helpersOf(s));
    if (kind === 'run') { const a = L.ago(s.since, now); return label(T.labels.running) + (a === '剛剛' ? ' 剛開始' : ' 已 ' + a.replace('前', '')); }
    return L.say(s, CC) || L.stateWord(s);
  }
  // kind：wait／run／done／er／ice（決定畫哪一種小人和泡泡）
  function buildDesk(s, kind) {
    const g = L.groupOf(s, CC), marked = L.isMarked(s, CC), now = nowS();
    const d = el('div', 'desk' + (kind === 'er' ? ' er' : '') + (kind === 'run' ? ' typing' : '') + (kind === 'wait' ? ' waving' : '') + (kind === 'ice' ? ' frozen' : '')
      + (marked ? ' marked' : '') + (L.isExpiring(s, now) ? ' expiring' : '') + (s.pane ? '' : ' noclick'));
    d.innerHTML = sprite('person', kind);
    d.prepend(el('div', 'bubble' + (kind === 'wait' ? ' wait' : '') + (kind === 'er' ? ' er' : ''), bubbleText(s, kind)));
    const nh = L.helpersOf(s);
    if (nh) {
      const crew = el('div', 'crew'), sizes = [34, 24, 17];
      crew.innerHTML = sizes.slice(0, nh).map((px) => sprite('helper', px)).join('') + (nh > sizes.length ? '<b>+' + (nh - sizes.length) + '</b>' : '');
      crew.title = '還有 ' + nh + ' 個派出去的 agent 沒回來';
      d.append(crew);
    }
    if (marked) { const m = el('div', 'marks'); m.innerHTML = sprite('mark') + sprite('mark') + sprite('mark'); d.append(m); }
    if (s.context != null) { const ctx = el('div', 'ctx'); const f = el('i', s.context <= 50 ? 'low' : ''); f.style.setProperty('--pct', Math.max(0, Math.min(100, s.context)) + '%'); ctx.append(f); d.append(ctx); }
    const plate = el('div', 'plate'); plate.style.setProperty('--c', g.color);
    plate.append(document.createTextNode(L.displayName(s))); d.append(plate);
    if (s.windowName && s.windowName !== s.name) d.append(el('span', 'nick', 'tmux：' + s.windowName));
    const cb = cacheBadge(s); if (cb) d.append(cb);
    const cw = ctxWarn(s); if (cw) d.append(cw);
    if (s.tmux) d.append(el('span', 'winno', '#' + s.tmux.split(':')[1]));
    d.title = g.name + '｜' + (kind === 'er' ? L.erText(s) + '｜' : '') + L.stateWord(s) + '｜' + L.ago(s.since, now)
      + (s.context != null ? '｜context 剩' + (s.contextEstimated ? '約 ' : ' ') + s.context + '%' : '') + (nh ? '｜' + nh + ' 個 agent 在外面' : '')
      + (s.headless ? '｜沒有人坐在前面的 session（agent 或腳本開的）' : '')
      + '\n' + (s.path || '') + '\n' + (s.pane ? '點一下切到這個 tmux 視窗' : '不在 tmux 裡，點不過去');
    d.onclick = () => jump(s);
    asButton(d);
    return d;
  }
  // 卡片是 div，要讓鍵盤也按得到（Tab 走得到、Enter／空白鍵等於點一下）
  function asButton(node) {
    node.tabIndex = 0; node.setAttribute('role', 'button');
    node.addEventListener('keydown', (e) => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); node.click(); } });
  }

  // ===== 整層樓 =====
  const filterOn = new Set();
  let erOpen = false; // 急診室預設收起；展開狀態跨重畫保留
  let CC = L.compileConfig(null);
  function renderChips(m) {
    const chips = $('chips'); chips.replaceChildren();
    const add = (key, text, color, icon) => {
      const ch = el('button', 'chip' + (filterOn.has(key) ? ' on' : '')); ch.type = 'button'; ch.style.setProperty('--c', color);
      if (icon) ch.insertAdjacentHTML('beforeend', icon); else ch.append(el('i'));
      ch.append(document.createTextNode(text));
      ch.onclick = () => { if (filterOn.has(key)) filterOn.delete(key); else filterOn.add(key); render(last); };
      chips.append(ch);
    };
    if (m.marked && CC.mark) add('*mark', CC.mark.label + ' ' + m.marked, '#e64980', sprite('mark'));
    m.groups.forEach((g) => add(g.name, g.name + ' ' + g.n, g.color));
  }
  function foldable(cls, lab, count, open, onToggle) {
    const box = el('div', cls + (open ? ' open' : ''));
    const door = el('button', cls === 'freezer' ? 'fz-door' : 'door'); door.type = 'button';
    const hint = el('small', null, open ? lab.open : lab.closed);
    door.append(el('span', null, lab.title + ' ' + count), hint);
    door.onclick = () => { const now = !box.classList.contains('open'); box.classList.toggle('open', now); hint.textContent = now ? lab.open : lab.closed; onToggle(now); };
    box.append(door);
    return box;
  }
  function renderFloor(m, data) {
    const floor = $('floor');
    const endedOpen = !!floor.querySelector('.clock.open'), freezerOpen = !!floor.querySelector('.freezer.open');
    floor.replaceChildren();
    const lab = T.labels;
    if (m.er.length) {
      const room = foldable('room er', lab.er, m.er.length, erOpen, (o) => { erOpen = o; });
      const g = el('div', 'desks'); m.er.forEach((s) => g.append(buildDesk(s, 'er'))); room.append(g); floor.append(room);
    } else {
      const room = el('div', 'room er calm'), door = el('div', 'door');
      door.append(el('span', null, lab.er.title + ' 0'), el('small', null, lab.er.calm)); room.append(door); floor.append(room);
    }
    [['meet', 'wait'], ['work', 'run'], ['rest', 'done']].forEach(([cls, t]) => {
      const room = el('div', 'room ' + cls), door = el('div', 'door');
      door.append(el('span', null, lab[t].title + ' ' + m[t].length), el('small', null, lab[t].hint)); room.append(door);
      if (!m[t].length) room.append(el('div', 'empty', lab[t].empty));
      else { const g = el('div', 'desks'); m[t].forEach((s) => g.append(buildDesk(s, t))); room.append(g); }
      floor.append(room);
    });
    if (m.frozen.length) {
      const fz = foldable('freezer', lab.frozen, m.frozen.length + ' 個', freezerOpen, () => {});
      const body = el('div', 'fz-body'), g = el('div', 'desks');
      m.frozen.forEach((s) => g.append(buildDesk(s, 'ice'))); body.append(g); fz.append(body); floor.append(fz);
    }
    const clock = el('div', 'clock' + (endedOpen ? ' open' : ''));
    clock.append(el('div', null, lab.ended.title + ' ' + m.ended.length + ' 個（點開看是哪些）'));
    const sl = el('div', 'sleepers');
    m.ended.forEach((s) => { const b = el('span', 'sleeper', L.displayName(s) + '・' + L.ago(s.since, nowS())); b.style.setProperty('--c', L.groupOf(s, CC).color); sl.append(b); });
    clock.append(sl); clock.onclick = () => clock.classList.toggle('open'); asButton(clock);
    floor.append(clock);

    floor.classList.toggle('dim', m.stale);
    const meta = $('meta'), src = data.sources || {};
    const skipped = Number(data.skipped) || 0;
    meta.textContent = !(m.age >= -120) ? '資料時間看不懂，無法判斷是不是最新的'
      : m.age > 60 ? '資料已經 ' + Math.floor(m.age / 60) + ' 分鐘沒更新，辦公室的背景程式可能停了'
      : (skipped ? (!m.total ? '全部 ' + skipped + ' 個 session 都讀不到，可能是 Claude Code 改版了・' : '有 ' + skipped + ' 個 session 的資料讀不到，先跳過（其他照常更新）・') : '')
        + (data.demo ? '示範資料・' : '') + '每 5 秒自動更新'
        + (src.tmux ? '・點卡片切到那個 tmux 視窗' : '・沒偵測到 tmux，卡片點不過去')
        + (src.moshi ? '・context 用 Moshi 的數字' : '・context 是估計值')
        + (m.hidden ? '・篩選中，另有 ' + m.hidden + ' 個沒顯示' : '');
    // 上游出問題（讀不到對話紀錄、格式看不懂、設定寫錯）一律排在最前面講，不能淹在後面
    const warns = [...(Array.isArray(data.warnings) ? data.warnings : []), ...CC.warnings];
    if (warns.length && m.age >= -120 && m.age <= 60) meta.textContent = warns.join('・') + '・' + meta.textContent;
    meta.classList.toggle('stale', m.stale || skipped > 0 || warns.length > 0);
  }
  function renderHelp() {
    const lab = T.labels, body = $('helpBody');
    body.replaceChildren();
    const mini = el('div', 'rooms-mini');
    [[lab.er.title, '卡住、當掉、停在錯誤訊息的；預設收起', 'm'], [lab.wait.title, '在等你回答或授權，先處理', 'm'], [lab.run.title, '正在跑或等' + lab.helperWord + '回來，不用管', ''],
      [lab.done.title, '做完了、只是回報，有空再看', ''], [lab.frozen.title, '快取過期的，預設收起；回去用就解凍', 'o']].forEach(([t, d, cls]) => {
      const box = el('div', cls); box.append(el('b', null, t.split('：')[0]), document.createTextNode(d)); mini.append(box);
    });
    const list = el('ul', 'legend-list');
    [['對話泡泡', '它最後說的話；在等你時寫它問你什麼。'], ['#數字', 'tmux 視窗編號。點整張卡片會切到那個視窗（不在 tmux 裡的點不過去）。'],
      ['直條', 'context 還剩多少。變色＝剩不到一半。'], [lab.helperWord, '派出去還沒回來的 agent，一個代表一個。'],
      ['名牌', '這個 session 的名字（你自己取的，或 Claude Code 看對話取的）；色塊是分組顏色。'],
      ['快取倒數', '對話會暫存一段時間，期間接著聊很便宜；快過期會提醒，過期後下一句要整段重讀（寫多少 token）。'],
      ['context 警示', '剩 50% 以下提醒找個段落交接；15% 以下建議先交接再清空。']].forEach(([k, v]) => {
      const li = el('li'); li.append(el('b', null, k), document.createTextNode('：' + v)); list.append(li);
    });
    body.append(mini, list);
  }

  // ===== 讀資料 =====
  let last = null, loadError = null, uiVer = null;
  function render(data) {
    last = data;
    CC = L.compileConfig(data.config);
    const still = L.pruneFilter(filterOn, data, CC); // 已經沒有人的組別不能留在篩選裡
    [...filterOn].forEach((k) => { if (!still.has(k)) filterOn.delete(k); });
    const m = L.buildModel(data, nowS(), CC, filterOn);
    renderUrgent(m.urgent);
    renderChips(m);
    renderFloor(m, data);
    if (loadError) showLoadError(); // 重畫上一份資料時，不可把「讀不到」蓋掉
  }
  function showLoadError() {
    const meta = $('meta');
    meta.textContent = '讀不到資料（' + loadError + '）' + (last ? '，下面是上一次的畫面、先不能點' : '');
    meta.classList.add('stale');
    $('floor').classList.add('dim');
  }
  async function load() {
    try {
      const r = await fetch('/api/agents?theme=' + encodeURIComponent(themeId), { cache: 'no-store' });
      const j = await r.json().catch(() => ({}));
      if (!r.ok) throw new Error(j.error || r.status);
      if (!Array.isArray(j.sessions)) throw new Error('資料格式不對'); // 格式不對不能畫成「0 個 session」
      if (j.ui && uiVer && uiVer !== j.ui) return location.reload(); // 頁面或外觀包的檔案改了 → 自動重新載入
      uiVer = j.ui || uiVer;
      loadError = null;
      render(j);
    } catch (e) {
      loadError = e.message;
      showLoadError();
    }
  }

  // ===== 開機：先決定用哪個外觀包（網址 ?theme= ＞ 這台瀏覽器上次選的 ＞ 設定檔），載完它再開始畫 =====
  const loadScript = (src) => new Promise((ok) => { const s = document.createElement('script'); s.src = src; s.onload = () => ok(true); s.onerror = () => ok(false); document.head.append(s); });
  async function boot() {
    let themes = [], fallback = 'pixel-office';
    try { const j = await (await fetch('/api/themes', { cache: 'no-store' })).json(); themes = j.themes || []; fallback = j.default || fallback; } catch (e) { /* 列不出來就用預設長相，資料照樣顯示 */ }
    const asked = new URLSearchParams(location.search).get('theme');
    let saved = null; try { saved = localStorage.getItem('sessionOfficeTheme'); } catch (e) { /* 無痕模式 */ }
    themeId = [asked, saved, fallback, themes[0]].find((t) => t && themes.includes(t)) || '';
    const sel = $('themeSel');
    themes.forEach((t) => { const o = el('option', null, t); o.value = t; o.selected = t === themeId; sel.append(o); });
    sel.onchange = () => { try { localStorage.setItem('sessionOfficeTheme', sel.value); } catch (e) { /* 無痕模式 */ } location.href = location.pathname + '?theme=' + encodeURIComponent(sel.value); };
    let themeOk = true;
    if (themeId) {
      $('themeCss').href = '/themes/' + themeId + '/theme.css';
      themeOk = await loadScript('/themes/' + themeId + '/theme.js');
    }
    applyTheme(window.SESSION_OFFICE_THEME);
    document.documentElement.dataset.officeTheme = themeId;
    document.title = label(T.labels.title); $('title').textContent = label(T.labels.title);
    renderHelp();
    $('jumpfx').addEventListener('click', closeJumpFx);
    setInterval(tickUrgent, 1000);
    await load();
    if (!themeId || !themeOk) toast(themeId ? '外觀包「' + themeId + '」載入失敗，先用預設長相' : '找不到任何外觀包，先用預設長相');
    setInterval(load, 5000);
    document.addEventListener('visibilitychange', () => { if (document.visibilityState === 'visible') load(); });
  }
  boot();
})();
