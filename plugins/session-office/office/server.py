"""只聽本機（127.0.0.1）的小網站：出頁面、給資料、幫忙把 tmux 切到某個視窗。

資料裡有對話片段、切視窗會動到你的畫面，所以：
- 只綁 127.0.0.1，別台機器連不到（要從手機／平板看，請自己在前面加一層登入，這裡不開對外）
- 每個請求都檢查 Host 是不是本機（擋「惡意網頁把自己的網域指到 127.0.0.1」那一招）
- 切視窗另外要帶自訂標頭＋同源 Origin（一般網頁沒辦法偷偷替你按）
- 每個回應都帶 CSP：只准載入本機的東西、不准嵌框架。外觀包裡的 SVG 另外加 sandbox——
  SVG 被當成「一份文件」打開時裡面的程式會跑，而且跟辦公室同一個來源，不擋的話一張「圖」就能把資料送出去
- 外觀包的檔案不跟著捷徑（symlink）走：不然一個指到 ~/.ssh 的捷徑就能把別的檔讀出來
"""
import json
import math
import os
import re
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlsplit

from . import collect, config, demo, tmuxio

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
WEB_DIR = os.path.join(ROOT, "web")
BUILTIN_THEMES = os.path.join(ROOT, "themes")
REFRESH_SECONDS = 5
JUMP_MAX_AGE_S = 60   # 資料超過這麼久沒更新就不切：舊資料記的位置可能已經不對
TYPES = {"html": "text/html; charset=utf-8", "js": "text/javascript; charset=utf-8", "css": "text/css; charset=utf-8",
         "png": "image/png", "svg": "image/svg+xml", "jpg": "image/jpeg", "jpeg": "image/jpeg", "webp": "image/webp",
         "gif": "image/gif", "woff2": "font/woff2"}
WEB_FILES = ("logic.js", "app.js", "base.css")
THEME_FILE = re.compile(r"[A-Za-z0-9][A-Za-z0-9_-]{0,60}\.(css|js|png|svg|jpg|jpeg|webp|gif|woff2)")
CSP = ("default-src 'self'; img-src 'self' data:; style-src 'self' 'unsafe-inline'; object-src 'none'; frame-src 'none'; "
       "worker-src 'none'; base-uri 'none'; form-action 'none'; frame-ancestors 'none'")


def _read_json(path):
    try:
        with open(path, encoding="utf-8") as fh:
            return json.load(fh)
    except (OSError, ValueError):
        return None


def _write_private(path, data):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = path + ".tmp"
    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)  # 裡面有對話片段，只給自己讀
    with os.fdopen(fd, "w", encoding="utf-8") as fh:
        json.dump(data, fh)  # 不用 ensure_ascii=False：對話裡偶爾有落單的半個字元，直接寫 UTF-8 會整個失敗
    os.replace(tmp, path)


def _finite(obj):
    """把不是有限數的值（NaN、無限大）換成 None。Python 會照樣寫成 NaN／Infinity，但瀏覽器解不開，整份資料就看不到了。"""
    if isinstance(obj, float) and not math.isfinite(obj):
        return None
    if isinstance(obj, dict):
        return {k: _finite(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_finite(v) for v in obj]
    return obj


class Office:
    def __init__(self, paths, config_path, state_path, user_themes, demo_mode=False, clock=time.time,
                 alive=collect.pid_alive, tmux_bin=None):
        self.paths, self.config_path, self.state_path = paths, config_path, state_path
        self.theme_dirs = [user_themes, BUILTIN_THEMES]  # 使用者自己的排前面；內建的更新時不會蓋到它
        self.demo_mode, self.clock, self.alive, self.tmux_bin = demo_mode, clock, alive, tmux_bin
        self.lock = threading.Lock()
        self.state = None if demo_mode else _read_json(state_path)
        self.started = clock()
        self.snapshot = {"ok": False, "error": "剛啟動，還沒整理好第一份資料"}

    def refresh(self):
        """整理一輪。不丟例外：失敗就把原因放進 snapshot，讓畫面講出來（不能安靜地停在舊資料）。"""
        now = self.clock()
        try:
            if self.demo_mode:
                snap = {"ok": True, "data": {**demo.payload(now, self.started), "config": demo.DEMO_CONFIG}}
            else:
                cfg = config.load(self.config_path)
                data, state = self._collect(now, cfg)
                self.state = state
                try:
                    _write_private(self.state_path, state)
                except OSError as e:  # 記憶存不了不該讓整頁看不到：照樣給資料，在最上面講一聲
                    data = {**data, "warnings": data["warnings"] + ["辦公室的記憶檔寫不進去（" + str(e) + "），重開後會忘記最近關掉的 session"]}
                snap = {"ok": True, "data": {**_finite(data), "config": config.public_part(cfg)}}
        except config.ConfigError as e:
            snap = {"ok": False, "error": "設定檔有錯：" + str(e)}
        except collect.CollectError as e:
            snap = {"ok": False, "error": str(e)}
        except Exception as e:  # 沒想到的錯也要讓畫面看得到
            snap = {"ok": False, "error": "整理資料時出錯：" + type(e).__name__ + "：" + str(e)}
        with self.lock:
            self.snapshot = snap
        return snap

    def _collect(self, now, cfg):
        args = dict(alive=self.alive, list_panes=lambda: tmuxio.list_panes(self.tmux_bin))
        try:
            return collect.collect(now, cfg, self.paths, self.state, **args)
        except collect.CollectError:
            raise
        except Exception as e:
            # 沒料到的錯，而且手上有上一輪留下的記憶：多半是記憶檔裡有怪東西（每一輪都會在同一個地方跌倒）。
            # 丟掉記憶重來一次；還是不行才讓畫面顯示錯誤
            if self.state is None:
                raise
            data, state = collect.collect(now, cfg, self.paths, None, **args)
            why = type(e).__name__
            # 畫面上那句提醒只出現一輪，所以另外印一行（會進 server.log），事後才查得到發生過什麼
            try:
                print("記憶有問題，已丟掉重來：" + why + "：" + str(e)[:200], file=sys.stderr, flush=True)
            except Exception:  # 留紀錄是順手的事，寫不出去（輸出端已經不在）不能反過來讓整頁看不到
                pass
            return {**data, "warnings": data["warnings"] + ["辦公室的記憶有問題（" + why + "），已經丟掉重來（「已關閉」清單會從頭記起）"]}, state

    def loop(self):
        while True:
            self.refresh()
            time.sleep(REFRESH_SECONDS)

    def current(self):
        with self.lock:
            return self.snapshot

    def themes(self):
        found = set()
        for d in self.theme_dirs:
            try:
                names = os.listdir(d)
            except OSError:
                continue
            found.update(n for n in names if config.THEME_ID.fullmatch(n) and os.path.isfile(os.path.join(d, n, "theme.js")))
        return sorted(found)

    def default_theme(self):
        try:
            return config.load(self.config_path)["theme"]
        except config.ConfigError:
            return config.DEFAULTS["theme"]

    def theme_file(self, theme_id, name):
        if not config.THEME_ID.fullmatch(theme_id or "") or not THEME_FILE.fullmatch(name or ""):
            return None
        for d in self.theme_dirs:
            base = os.path.realpath(os.path.join(d, theme_id))
            path = os.path.join(base, name)
            # 外觀包資料夾本身可以是捷徑（方便開發時指到別處），但裡面的檔案必須是真的檔案、而且真的在那個資料夾裡
            if os.path.isfile(path) and not os.path.islink(path) and os.path.realpath(path) == path:
                return path
        return None

    def ui_version(self, theme_id):
        """頁面與外觀包檔案的最後修改時間。開著的分頁靠它發現「檔案改了」自動重新載入（做外觀包時不用一直手動重整）。"""
        files = [os.path.join(WEB_DIR, n) for n in ("index.html",) + WEB_FILES]
        files += [p for p in (self.theme_file(theme_id, n) for n in ("theme.css", "theme.js")) if p]
        latest = 0
        for f in files:
            try:
                latest = max(latest, os.path.getmtime(f))
            except OSError:
                pass
        return str(int(latest * 1000))

    def jump(self, pane):
        if self.demo_mode:
            return 409, {"error": "示範模式不會真的切視窗"}
        snap = self.current()
        if not snap["ok"]:
            return 503, {"error": snap["error"]}
        age = self.clock() - float(snap["data"]["generatedAt"])
        if not -120 <= age <= JUMP_MAX_AGE_S:
            return 503, {"error": "資料太舊，視窗位置可能已經不對，先不切"}
        ok_target = isinstance(pane, str) and tmuxio.PANE_RE.fullmatch(pane) and any(
            s.get("pane") == pane and s.get("state") != "ended" for s in snap["data"]["sessions"])
        if not ok_target:
            return 400, {"error": "這個 tmux 位置不在目前開著的 session 裡"}
        ok, err = tmuxio.select_window(self.tmux_bin, pane)
        return (200, {"ok": True, "pane": pane}) if ok else (409, {"error": "tmux 切換失敗：" + (err or "視窗可能已關閉")})


def make_handler(office, port):
    hosts = {"127.0.0.1:%d" % port, "localhost:%d" % port}
    origins = {"http://" + h for h in hosts}

    class Handler(BaseHTTPRequestHandler):
        server_version = "SessionOffice"

        def log_message(self, *_args):
            pass

        def _send(self, code, body, ctype, csp=CSP):
            raw = body if isinstance(body, bytes) else body.encode("utf-8")
            self.send_response(code)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(raw)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            # 每個回應都帶，不只頁面：CSP 是跟著「那一個回應」走的，漏掉哪一種檔案，哪一種就是洞
            self.send_header("Content-Security-Policy", csp)
            self.send_header("X-Frame-Options", "DENY")
            self.send_header("Cross-Origin-Resource-Policy", "same-origin")
            self.send_header("Referrer-Policy", "no-referrer")
            self.end_headers()
            self.wfile.write(raw)

        def _json(self, code, obj):
            self._send(code, json.dumps(obj), "application/json; charset=utf-8")

        def _file(self, path):
            try:
                with open(path, "rb") as fh:
                    body = fh.read()
            except OSError:
                return self._json(404, {"error": "找不到"})
            ext = path.rsplit(".", 1)[-1].lower()
            # SVG 當圖片用不受影響；被直接打開或嵌進別的東西時，sandbox 讓它裡面的程式跑不起來
            self._send(200, body, TYPES.get(ext, "application/octet-stream"), CSP + "; sandbox" if ext == "svg" else CSP)

        def _local(self):
            if self.headers.get("Host") in hosts:
                return True
            self._json(403, {"error": "只接受從這台電腦自己連（127.0.0.1）"})
            return False

        def do_GET(self):
            if not self._local():
                return
            url = urlsplit(self.path)
            path, query = url.path, parse_qs(url.query)
            if path in ("/", "/index.html"):
                return self._file(os.path.join(WEB_DIR, "index.html"))
            if path.startswith("/web/") and path[5:] in WEB_FILES:
                return self._file(os.path.join(WEB_DIR, path[5:]))
            m = re.match(r"^/themes/([^/]+)/([^/]+)$", path)
            if m:
                found = office.theme_file(m.group(1), m.group(2))
                return self._file(found) if found else self._json(404, {"error": "找不到這個外觀包的檔案"})
            if path == "/favicon.ico":
                return self._send(204, b"", "image/x-icon")
            if path == "/api/themes":
                return self._json(200, {"themes": office.themes(), "default": office.default_theme()})
            if path == "/api/agents":
                snap = office.current()
                if not snap["ok"]:
                    return self._json(503, {"error": snap["error"]})
                return self._json(200, {**snap["data"], "ui": office.ui_version((query.get("theme") or [""])[0])})
            self._json(404, {"error": "找不到"})

        def do_POST(self):
            if not self._local():
                return
            if urlsplit(self.path).path != "/api/jump":
                return self._json(404, {"error": "找不到"})
            origin = self.headers.get("Origin")
            if self.headers.get("X-Session-Office") != "1" or (origin is not None and origin not in origins):
                return self._json(403, {"error": "這個動作只接受辦公室頁面自己送出"})
            try:
                length = int(self.headers.get("Content-Length") or 0)
            except ValueError:
                length = -1
            if not 0 < length <= 1024:
                return self._json(400, {"error": "內容格式不對"})
            try:
                body = json.loads(self.rfile.read(length).decode("utf-8"))
            except (ValueError, UnicodeDecodeError):
                return self._json(400, {"error": "內容格式不對"})
            code, out = office.jump(body.get("pane") if isinstance(body, dict) else None)
            self._json(code, out)

    return Handler


def make_server(office, port):
    """port 給 0＝讓系統挑一個空的（測試用）；Host 檢查要用實際綁到的那個 port。"""
    httpd = ThreadingHTTPServer(("127.0.0.1", port), BaseHTTPRequestHandler)
    httpd.RequestHandlerClass = make_handler(office, httpd.server_address[1])
    return httpd
