// 判斷邏輯的測試：誰進哪個房間。跑法：node --test tests/logic.test.mjs
import test from 'node:test';
import assert from 'node:assert/strict';
import { createRequire } from 'node:module';

const L = createRequire(import.meta.url)('../web/logic.js');
const NOW = 1_800_000_000;
const s = (id, state, extra = {}) => ({ id, state, since: NOW - 60, project: 'shop', path: '~/Projects/shop', name: id, helpers: 0, ...extra });
const CC0 = L.compileConfig(null);
const ids = (list) => list.map((x) => x.id);
const model = (sessions, cc = CC0, filter = new Set(), generatedAt = NOW) => L.buildModel({ generatedAt, sessions }, NOW, cc, filter);

test('每種狀態進對的房間', () => {
  const m = model([s('q', 'waiting_question'), s('p', 'waiting_permission'), s('b', 'ball'), s('r', 'running'), s('h', 'helpers', { helpers: 2 }),
    s('d', 'reported'), s('i', 'idle'), s('e', 'ended')]);
  assert.deepEqual(ids(m.wait).sort(), ['b', 'p', 'q']);
  assert.deepEqual(ids(m.run).sort(), ['h', 'r']);
  assert.deepEqual(ids(m.done).sort(), ['d', 'i']);
  assert.deepEqual(ids(m.ended), ['e']);
  assert.deepEqual(m.er, []);
  assert.equal(m.total, 8);
});

test('認不得的狀態進急診室，不會安靜地出現在別的房間', () => {
  const m = model([s('x', 'unknown:hibernating'), s('ok', 'reported')]);
  assert.deepEqual(ids(m.er), ['x']);
  assert.deepEqual(ids(m.done), ['ok']); // 對照組：正常的還在
  for (const room of ['wait', 'run', 'done', 'frozen', 'ended']) assert.ok(!ids(m[room]).includes('x'), room);
  assert.match(L.erText(m.er[0]), /認不得的狀態/);
});

test('有 trouble 的進急診室、不重複出現在原房間與警示條', () => {
  const stuck = s('stuck', 'running', { trouble: { kind: 'stuck', text: '顯示在跑，但已 75 分鐘沒有任何動靜', since: NOW - 4500 }, cacheExpiresAt: NOW + 100 });
  const m = model([stuck, s('r', 'running')]);
  assert.deepEqual(ids(m.er), ['stuck']);
  assert.deepEqual(ids(m.run), ['r']);
  assert.deepEqual(m.urgent, []);
});

test('快取：剩不到 10 分＝快過期排最前；做完又過期＝冰庫；在等你的過期仍留會議室', () => {
  const soon = s('soon', 'reported', { cacheExpiresAt: NOW + 300, since: NOW - 999 });
  const later = s('later', 'reported', { cacheExpiresAt: NOW + 3000 });
  const gone = s('gone', 'reported', { cacheExpiresAt: NOW - 10 });
  const waitGone = s('waitGone', 'waiting_question', { cacheExpiresAt: NOW - 10 });
  const m = model([later, soon, gone, waitGone]);
  assert.deepEqual(ids(m.done), ['soon', 'later']);
  assert.deepEqual(ids(m.frozen), ['gone']);
  assert.deepEqual(ids(m.wait), ['waitGone']);
  assert.deepEqual(ids(m.urgent), ['soon']);
  assert.equal(L.isExpiring(later, NOW), false);
  assert.equal(L.isExpiring(s('e', 'ended', { cacheExpiresAt: NOW + 300 }), NOW), false);
});

test('沒有快取資料（新開的 session）不算過期也不進冰庫', () => {
  for (const v of [undefined, null, 0, 'abc']) {
    const x = s('n', 'idle', { cacheExpiresAt: v });
    assert.equal(L.cacheLeftS(x, NOW), null);
    assert.equal(L.isFrozen(x, NOW), false);
    assert.equal(L.isExpiring(x, NOW), false);
  }
});

test('資料新舊：沒時間戳、毫秒單位、太舊都算過期', () => {
  assert.equal(model([], CC0, new Set(), NOW - 5).stale, false); // 對照組：剛更新的不算
  assert.equal(model([], CC0, new Set(), NOW - 61).stale, true);
  assert.equal(model([], CC0, new Set(), NOW * 1000).stale, true);
  assert.equal(L.buildModel({ sessions: [] }, NOW, CC0, new Set()).stale, true);
  assert.equal(L.buildModel(null, NOW, CC0, new Set()).stale, true);
});

test('分組：先看資料夾，再看對話；都沒有就用資料夾名', () => {
  const cc = L.compileConfig({ groups: [{ name: '甲', color: '#111111', match: 'client-a' }, { name: '乙', color: '#222222', match: '乙客戶' }] });
  assert.deepEqual(L.groupOf(s('1', 'idle', { path: '~/work/Client-A/site' }), cc), { name: '甲', color: '#111111' });
  assert.deepEqual(L.groupOf(s('2', 'idle', { lastUser: '幫乙客戶改首頁' }), cc), { name: '乙', color: '#222222' });
  const g = L.groupOf(s('3', 'idle'), cc);
  assert.equal(g.name, 'shop');
  assert.ok(L.PALETTE.includes(g.color));
  assert.deepEqual(L.groupOf(s('3', 'idle'), cc), g); // 同名永遠同色
});

test('篩選鈕：只留選到的組；*mark 只留有標記的', () => {
  const cc = L.compileConfig({ groups: [{ name: '甲', color: '#111111', match: 'client-a' }], mark: { label: '重要', match: '很急' } });
  const list = [s('a', 'running', { path: '~/client-a' }), s('b', 'running'), s('c', 'reported', { lastUser: '這個很急' })];
  assert.equal(model(list, cc).run.length, 2); // 對照組：沒篩選時兩個都在
  assert.deepEqual(ids(model(list, cc, new Set(['甲'])).run), ['a']);
  const marked = model(list, cc, new Set(['*mark']));
  assert.deepEqual([ids(marked.run), ids(marked.done)], [[], ['c']]);
  assert.equal(model(list, cc).marked, 1);
  assert.equal(model(list, cc).groups.find((g) => g.name === '甲').n, 1);
});

test('設定裡寫壞的正規表示式：跳過那一條並回報，其他照常', () => {
  const cc = L.compileConfig({ groups: [{ name: '壞', color: '#111111', match: '(' }, { name: '好', color: '#222222', match: 'shop' }] });
  assert.deepEqual(cc.groups.map((g) => g.name), ['好']);
  assert.equal(cc.warnings.length, 1);
  assert.equal(L.compileConfig({ groups: 'x', mark: 3, ballPhrases: [1, ''] }).warnings.length, 0);
});

test('泡泡文字：等你時用問題，拿掉「球在你這裡」那類固定開頭', () => {
  const cc = L.compileConfig({ ballPhrases: ['現在球在你這裡的是'] });
  assert.equal(L.say(s('a', 'ball', { lastReport: '現在球在你這裡的是：選 A 或 B' }), cc), '選 A 或 B');
  assert.equal(L.say(s('a', 'waiting_question', { question: '要哪個？', lastReport: '舊回報' }), cc), '要哪個？');
  assert.equal(L.say(s('a', 'reported', { lastReport: '現在球在你這裡的是：選 A 或 B' }), CC0), '現在球在你這裡的是：選 A 或 B');
});

test('小工具：名字、時間、數字', () => {
  assert.equal(L.displayName({ name: '', project: 'shop', path: '~/x' }), 'shop');
  assert.equal(L.displayName({ name: '', path: '~/repo/.claude/worktrees/fix-1' }), 'repo（分支）');
  assert.equal(L.displayName({ name: '', path: '~' }), '家目錄');
  assert.equal(L.displayName({}), '？');
  assert.equal(L.ago(NOW - 30, NOW), '剛剛');
  assert.equal(L.ago(NOW - 300, NOW), '5 分前');
  assert.equal(L.ago(NOW - 7300, NOW), '2 小時前');
  assert.equal(L.mmss(414), '06:54');
  assert.equal(L.tokensText(312000), '31.2 萬');
  assert.equal(L.tokensText(9500), '9,500');
  assert.equal(L.helpersOf({ helpers: '3' }), 3);
  assert.equal(L.helpersOf({ helpers: -2 }), 0);
  assert.equal(L.stateWord({ state: 'zzz' }), '未知狀態：zzz');
});

test('篩選的那一組沒人了：自動拿掉，不會把整間辦公室變空', () => {
  const cc = L.compileConfig({ groups: [{ name: '甲', color: '#111111', match: 'client-a' }, { name: '乙', color: '#222222', match: 'client-b' }], mark: { label: '重要', match: '很急' } });
  const data = { generatedAt: NOW, sessions: [s('a', 'waiting_question', { path: '~/client-a' }), s('b', 'running', { path: '~/client-a' })] };
  const stale = new Set(['乙', '*mark']);
  assert.equal(L.buildModel(data, NOW, cc, stale).wait.length, 0); // 這就是出事的樣子：有人在等你卻看不到
  const pruned = L.pruneFilter(stale, data, cc);
  assert.deepEqual([...pruned], []);
  assert.deepEqual(ids(L.buildModel(data, NOW, cc, pruned).wait), ['a']);
  assert.deepEqual([...L.pruneFilter(new Set(['甲', '乙']), data, cc)], ['甲']); // 對照組：還有人的那一組留著
  const marked = { generatedAt: NOW, sessions: [s('c', 'reported', { lastUser: '這個很急' })] };
  assert.deepEqual([...L.pruneFilter(new Set(['*mark']), marked, cc)], ['*mark']);
  assert.deepEqual([...L.pruneFilter(new Set(['甲']), null, cc)], []);
});

test('篩選中會回報有幾個沒顯示', () => {
  const cc = L.compileConfig({ groups: [{ name: '甲', color: '#111111', match: 'client-a' }] });
  const list = [s('a', 'running', { path: '~/client-a' }), s('b', 'running'), s('c', 'reported')];
  assert.equal(model(list, cc).hidden, 0);
  assert.equal(model(list, cc, new Set(['甲'])).hidden, 2);
});

test('狀態字串剛好是物件內建的名字（constructor、toString）也算認不得', () => {
  for (const state of ['constructor', 'toString', '__proto__', 'hasOwnProperty']) {
    const x = s('x', state);
    assert.equal(L.inER(x), true, state);
    assert.equal(L.tone(x), 'wait', state);
    assert.match(L.stateWord(x), /未知狀態/);
  }
});

test('頁面只有五個地方會把字串當成 HTML 插進去，而且都只吃外觀包的圖', async () => {
  const { readFileSync } = await import('node:fs');
  const src = readFileSync(new URL('../web/app.js', import.meta.url), 'utf8');
  const lines = src.split('\n').filter((l) => /\binnerHTML\b|insertAdjacentHTML|outerHTML|document\.write/.test(l) && !l.trim().startsWith('//'));
  assert.equal(lines.length, 5, '多了或少了插入點：新增的要確認不會把對話內容、名字、設定值當成 HTML\n' + lines.join('\n'));
  // 對話內容、session 名字、tmux 視窗名、設定值都不可以出現在這幾行
  const untrusted = /\bs\.|data\.|displayName|L\.say|erText|bubbleText|label\(|\.name\b|question|lastReport|lastUser|windowName|\.path\b|CC\./;
  for (const l of lines) {
    assert.ok(!untrusted.test(l.replace(/sprite\('[a-z]+'(, [a-z]+)?\)/g, '')), '這一行可能把不可信的字串當成 HTML：' + l.trim());
  }
  // 篩選鈕的圖示是呼叫端傳進來的，確認呼叫端只傳外觀包的圖
  assert.match(src, /add\('\*mark', CC\.mark\.label \+ ' ' \+ m\.marked, '#e64980', sprite\('mark'\)\)/);
});

test('沒有人坐在前面的 session 快取快過期也不催（你沒辦法回去說一句）', () => {
  const script = s('h', 'reported', { cacheExpiresAt: NOW + 300, headless: true });
  const mine = s('m', 'reported', { cacheExpiresAt: NOW + 300 });
  const m = model([script, mine]);
  assert.deepEqual(ids(m.urgent), ['m']); // 對照組：你自己的照樣催
  assert.equal(L.isExpiring(script, NOW), false);
  assert.deepEqual(ids(m.done).sort(), ['h', 'm']); // 卡片還在，只是不催
});

test('卡片上的快取小框：沒有人坐在前面的不用「快過期」的樣子催', () => {
  assert.equal(L.cacheKind(s('m', 'reported', { cacheExpiresAt: NOW + 300 }), NOW), 'soon'); // 對照組：你自己的要催
  assert.equal(L.cacheKind(s('h', 'reported', { cacheExpiresAt: NOW + 300, headless: true }), NOW), 'ok');
  assert.equal(L.cacheKind(s('h', 'reported', { cacheExpiresAt: NOW + 3000 }), NOW), 'ok');
  assert.equal(L.cacheKind(s('g', 'reported', { cacheExpiresAt: NOW - 5 }), NOW), 'gone');
  assert.equal(L.cacheKind(s('n', 'idle'), NOW), null);
  assert.equal(L.cacheKind(s('x', 'idle', { cacheExpiresAt: NOW * 1000 }), NOW), null); // 單位錯（毫秒）不顯示離譜的數字
});
