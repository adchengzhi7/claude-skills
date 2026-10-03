# 做一個外觀包

外觀包＝一個資料夾，裡面兩個檔：

```
~/.config/session-office/themes/<名字>/
  theme.css   顏色、字、框、排法、動畫
  theme.js    小人怎麼畫、每個房間叫什麼、泡泡裡的用語
```

`<名字>` 只能用小寫英數字和 `-`（例：`aquarium`、`space-station`）。也可以放圖片或字型檔（png、svg、jpg、webp、gif、woff2），檔名只能用英數字、`_`、`-`。
檔案必須真的放在這個資料夾裡（指到別處的捷徑不會被讀）。SVG 檔只能當圖片用（`<img>`、CSS 背景）；裡面寫程式不會跑。

最快的做法：複製內建的 `themes/cat-cafe/`（結構最單純）或 `themes/pixel-office/`，改名後開始改。
不要直接改內建的那兩個，也不要改 `web/` 底下的檔——那些在辦公室更新時會被換掉。

## 邊改邊看

```
python3 run.py --demo --port 8766
```

打開 `http://127.0.0.1:8766/?theme=<名字>`。示範資料裡每一種狀態各有一張卡（等你回答、等你授權、球在你這裡、在跑、等幫手、做完、待命、卡住、已過期、已關閉），不會讀到任何真實對話。
存檔後頁面會自己重新載入。急診室、冰庫、已關閉預設是收起的，記得點開看。

## 三條規則

1. **只管長相和用語。** 誰進哪個房間、什麼時候算過期，都在共用的 `web/logic.js`。不要在外觀包裡重算，也不要自己去抓資料。
2. **不連外部網址。** 頁面只准載入本機的東西，外部字型、圖片、腳本都會被擋。要用字型就把 woff2 放進外觀包資料夾，用 `url('/themes/<名字>/xxx.woff2')`。
3. **不要動收合與可不可以點。** 那些規則在 `web/base.css`，外觀包的 CSS 不要蓋掉它們。具體就是下面這張表：不要用表裡那種選擇器去寫 `display`。其他都可以自己排——`.floor`、`.room`、一般的 `.desks { display: grid; }`（內建兩個外觀包都這樣寫）、`.desk` 和它裡面的東西。

| 共用規則管的事 | 元素 | 外觀包不要做 |
|---|---|---|
| 急診室收起／展開 | `.room.er .desks`（收起 `none`，`.open` 時 `grid`） | 不要寫 `.room.er .desks { display: … }` 這種指名急診室的規則；欄數用 `grid-template-columns` 調 |
| 冰庫收起／展開 | `.freezer .fz-body`（收起 `none`，`.open` 時 `block`） | 不要對 `.fz-body` 寫 `display` |
| 已關閉收起／展開 | `.clock .sleepers`（收起 `none`，`.open` 時 `flex`） | 不要對 `.sleepers` 寫 `display` |
| 警示條有沒有出現 | `.urgent`（`.on` 才顯示） | 不要對它寫 `display` |
| 切視窗提示有沒有出現 | `.jumpfx`（`.on` 才顯示，固定蓋滿整頁） | 不要對它寫 `display`、`position` |
| 提示小框 | `.toast`（固定在畫面下方，`.show` 才看得到） | 不要對它寫 `position`、`opacity` |
| 過期時不能點 | `.floor.dim`（`pointer-events: none`） | 不要把 `pointer-events` 開回來；變灰、變淡由外觀包自己寫 |
| 游標 | `.desk`（手指）、`.desk.noclick`（一般） | — |

一般房間、急診室、冰庫裡的 `.desks` 和 `.desk` 是同一種結構，可以共用同一份 CSS。

## theme.js

設定一個全域物件。每一項都可以省略，省略的會用預設值補上。

```js
window.SESSION_OFFICE_THEME = {
  name: '貓咪咖啡廳',
  labels: {
    title: '貓咪咖啡廳',                       // 頁面標題
    er:     { title: '獸醫室：不太對勁', calm: '大家都好好的', open: '點這裡收起', closed: '點開看是誰' },
    wait:   { title: '櫃檯：在叫你', hint: '先理牠', empty: '沒有貓在叫你' },
    run:    { title: '遊戲區：正在忙', hint: '讓牠玩', empty: '沒有貓在忙' },
    done:   { title: '窗台：做完在睡', hint: '有空再看', empty: '窗台空空的' },
    frozen: { title: '冬眠區：已過期', open: '點這裡收起', closed: '點開看是誰' },
    ended:  { title: '回家了：過去 12 小時內關掉的 session' },
    running: '敲鍵盤中',                        // 在跑的卡片泡泡：後面會自動接「已 6 分」
    helpers: (n) => '等 ' + n + ' 條小魚乾回來',  // 等幫手的卡片泡泡
    helperWord: '小魚乾',                       // 說明區提到幫手時用的詞
  },
  sprites: {
    person: (kind) => '<svg class="me" …>…</svg>',   // kind：'wait'｜'run'｜'done'｜'er'｜'ice'
    helper: (px) => '<svg width="…" …>…</svg>',      // 派出去的 agent，px 是建議寬度（第一個最大）
    mark: () => '<svg …>…</svg>',                     // 特別標記的小圖示
    jump: () => '<svg …>…</svg>',                     // 切視窗時全螢幕提示裡的圖（可省略）
  },
};
```

房間標題請維持「名字：說明」的寫法（用全形冒號），說明區會取冒號前面那段當房間名。

`labels` 的鍵對到畫面上的哪一塊，以及沒寫時的預設值：

| 鍵 | 畫面上的元素 | 沒寫時用 |
|---|---|---|
| `er.title`／`er.calm` | `.room.er` 的標題／沒人時右邊的字 | 急診室：出狀況了／目前沒有卡住或當掉的 |
| `er.closed`／`er.open` | 急診室收起／展開時右邊的提示 | 卡住、當掉或停在錯誤訊息；點開看是誰／點這裡收起 |
| `wait.title`／`.hint`／`.empty` | `.room.meet` 的標題／右邊提示／沒人時的字 | 會議室：舉手等你／先處理這裡／沒有人在等你 |
| `run.title`／`.hint`／`.empty` | `.room.work` | 工作區：正在跑（含等幫手）／不用管它／空的 |
| `done.title`／`.hint`／`.empty` | `.room.rest` | 茶水間：做完了／有空再看回報／空的 |
| `frozen.title`／`.closed`／`.open` | `.freezer` | 冰庫：已過期／點開看是誰（回去用就會解凍）／點這裡收起 |
| `ended.title` | `.clock` | 已關閉：過去 12 小時內關掉的 session |
| `running` | 在跑的卡片泡泡開頭 | 努力中⋯⋯ |
| `helpers(n)` | 等幫手的卡片泡泡 | 等 n 個幫手回來 |
| `helperWord` | 說明區提到幫手的詞 | 幫手 |

`open`、`closed` 這類提示多半用預設值就好（內建的貓咪咖啡廳就只改了 `closed`）。

`person` 的五種 `kind`：

| kind | 什麼時候 | 卡片上同時會有的 class |
|---|---|---|
| `wait` | 等你回答、等你授權、球在你這裡 | `.desk.waving` |
| `run` | 正在跑、等幫手回來 | `.desk.typing` |
| `done` | 做完了、待命 | — |
| `er` | 出狀況（急診室） | `.desk.er` |
| `ice` | 做完而且快取過期（冰庫） | `.desk.frozen` |

函式壞掉（丟錯）時那一項會退回預設長相；`labels` 或 `sprites` 裡型別寫錯的項目（例如該是 `{ title: … }` 的地方寫成一個字串）會被忽略、用預設值。兩種情況都不會讓整頁白掉，但也不會有錯誤訊息——所以請自己在示範模式把五種小人、每個房間的名字都看過。

### 用文字畫像素圖

頁面提供兩個小工具，在 theme.js 裡可以直接用：

```js
// 每個字元一格；palette 把字元對到顏色，沒對到的字元＝透明
const FISH = OfficeKit.rects(['..BBBB..B', '.BBBBBB.BB', 'BBKBBBBBBB', '.BBBBBB.BB', '..BBBB..B'], { B: '#74c0fc', K: '#1c3d5a' });
// OfficeKit.rects(rows, palette, x0 = 0, y0 = 0) 回一串 <rect>；OfficeKit.svg(寬, 高, 內容, class) 把它包成 <svg>
const helper = (px) => OfficeKit.svg(10, 5, FISH);
```

- `rows` 每一列長度可以不一樣（短的那列右邊就是透明）；空字串 `''` 代表一整列透明。
- `OfficeKit.svg(寬, 高, 內容, class)` 包出來的 `viewBox` 是 `0 0 寬 高`。要用別的 `viewBox`（例如讓圖往上多留一點空間放驚嘆號）就自己寫 `<svg viewBox="…">`，裡面放 `OfficeKit.rects(…)` 回的那串。
- 小人的 `viewBox` 用多大都可以，頁面不會限制 `svg.me` 的大小——它在卡片裡多寬多高由你的 theme.css 決定（記得給 `svg.me` 寫寬度，不然會撐到整張卡片寬）。

要讓某一部分會動，就把那部分包在 `<g class="arm">…</g>` 之類的群組裡，在 theme.css 寫動畫。記得加 `shape-rendering: crispEdges` 邊緣才不會糊。
要做放大、旋轉這類動畫時，在那個群組上加 `transform-box: fill-box; transform-origin: center;`，不然它會繞著整張圖的左上角轉。

## theme.css

畫面骨架是固定的，外觀包的 CSS 決定它長什麼樣、怎麼排。兩個內建外觀包用的是同一份骨架：
像素辦公室是「大房間裡排桌子、直式卡片」，貓咪咖啡廳是「三欄並排、橫式卡片」。

```
.wrap
  header
    h1#title                      頁面標題
    .meta(.stale)                 一行狀態文字；.stale＝資料有問題，要醒目
    .themepick > select           外觀切換
  .urgent(.on)                    快取快過期的警示條（沒有就不顯示）
    .u-title
    button.u-row(.crit)           一個 session 一列；.crit＝剩不到 3 分鐘
      .u-time  .u-name  .u-cost
  details.help                    「這頁怎麼看」
    .rooms-mini > div(.m|.o)      .legend-list > li
  .chips
    button.chip(.on)              篩選鈕；--c 是這一組的顏色；裡面是 <i>（色點）或標記的 <svg>
  .floor(.dim)                    .dim＝資料過期或讀不到，整層不能點
    .room.er(.calm)(.open)        急診室；.calm＝沒人；有人時 .door 是 <button>
    .room.meet                    會議室（等你）
    .room.work                    工作區（在跑）
    .room.rest                    茶水間（做完）
      .door > span, small         房間標題＋人數、右邊的提示
      .empty                      沒人時的字
      .desks > .desk …
    .freezer(.open)               冰庫
      button.fz-door > span, small
      .fz-body > .desks > .desk.frozen …
    .clock(.open)                 已關閉
      .sleepers > .sleeper        --c 是分組顏色
.toast(.show)
.jumpfx(.on)(.go|.ok|.bad)        切視窗的全螢幕提示
  .jf-box > .jf-art, .jf-t1, .jf-t2
```

一張卡（`.desk`）裡面的元素如下，表格由上到下就是它們在網頁裡的先後順序。要換視覺上的順序（例如把泡泡放到小人下面），用 CSS 的 grid 區域或 flex 的 `order`。

骨架本身不替卡片裡的任何元素定位。內建的兩個外觀包把 `.winno`、`.marks`（像素辦公室還有 `.bubble`、`.crew`、`.ctx`）設成 `position: absolute` 疊在卡片角落，那是它們自己的 CSS——複製範本之後記得看這幾條，換了排法它們可能會蓋到別的東西。

| 元素 | 內容 | 備註 |
|---|---|---|
| `.bubble`(`.wait`｜`.er`) | 它最後說的話，或在等你什麼 | 可能很長，請限制行數 |
| `svg.me` | `sprites.person(kind)` 回的那張圖 | |
| `.crew` | 幫手圖示，超過三個會多一個 `<b>+N</b>` | 沒有幫手就沒有這個元素 |
| `.marks` | 三個 `sprites.mark()` | 有特別標記才有；不想要三個就用 CSS 藏掉兩個 |
| `.ctx > i`(`.low`) | context 剩多少；`--pct` 是百分比（例 `62%`） | 直條就 `height: var(--pct)`，橫條就 `width: var(--pct)`；`.low`＝剩不到一半 |
| `.plate` | 名字；`--c` 是分組顏色 | |
| `.nick` | tmux 視窗名 | 跟名字不同才有 |
| `.cache`(`.ok`｜`.soon`｜`.gone`) | 快取倒數 | `.soon`＝剩不到 10 分；`.gone`＝已過期 |
| `.ctxwarn`(`.bad`) | context 警示 | 剩 50% 以下才有；`.bad`＝15% 以下 |
| `.winno` | `#` 加 tmux 視窗編號 | 在 tmux 裡才有 |

`.desk` 本身的狀態 class：`.waving`、`.typing`、`.er`、`.frozen`、`.marked`（有特別標記）、`.expiring`（快取快過期，要最顯眼）、`.noclick`（點不過去）。

## 交出去之前自己看一遍

- 示範模式裡十張卡都看過：五種小人、幫手、標記、快過期的卡、警示條。急診室、冰庫、已關閉都點開過
- 等你的（會議室）一眼最明顯；快過期的卡比其他卡更顯眼
- 名字或泡泡很長時不會撐破卡片
- 視窗拉窄到手機寬度還能看
- 系統開「減少動態效果」時不會一直閃（`web/base.css` 已經統一關掉動畫，不要用 `!important` 蓋回來）
- 沒有任何 `http://`、`https://` 開頭的網址
- 深色模式下字看得清楚（或明確只做淺色）

## 分享給別人

把整個資料夾給對方，放進對方的 `~/.config/session-office/themes/` 就能用。
請提醒對方：外觀包裡的 `theme.js` 是會執行的程式，裝之前讓自己的 Claude 讀一遍。
