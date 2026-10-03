"""設定檔：~/.config/session-office/config.json（沒有這個檔＝全部用預設值）。

設定寫錯一律丟 ConfigError、不退回預設值：退回預設會讓「我設的分組怎麼不見了」變成沒有任何訊息的怪事。
"""
import json
import os
import re

# 一律用 fullmatch 比對：$ 會放過結尾的換行
THEME_ID = re.compile(r"[a-z0-9][a-z0-9-]{0,40}")
COLOR = re.compile(r"#[0-9a-fA-F]{3,8}")

DEFAULTS = {
    "port": 8765,
    "theme": "pixel-office",
    # "auto"＝看 ~/.claude/settings.json 的 model 有沒有 [1m]；也可以直接寫數字（例 200000）
    "contextWindow": "auto",
    # 分組（篩選鈕＋名牌色塊）：[{"name": "客戶A", "color": "#d9480f", "match": "client-a|客戶A"}]，match 是不分大小寫的正規表示式
    "groups": [],
    # 特別標記（卡片上多一個小圖示）：{"label": "重要", "match": "urgent|很急"}
    "mark": None,
    # 最後一句回報用這些字開頭＝「球在你這裡」，放會議室。例：["現在球在你這裡"]
    "ballPhrases": [],
}


class ConfigError(Exception):
    pass


def config_dir(environ=os.environ):
    base = environ.get("XDG_CONFIG_HOME") or os.path.join(os.path.expanduser("~"), ".config")
    return os.path.join(base, "session-office")


def state_dir(environ=os.environ):
    base = environ.get("XDG_STATE_HOME") or os.path.join(os.path.expanduser("~"), ".local", "state")
    return os.path.join(base, "session-office")


def _check_regex(text, where):
    if not isinstance(text, str) or not text:
        raise ConfigError(where + " 的 match 要是一段文字")
    try:
        re.compile(text)
    except re.error as e:
        raise ConfigError(where + " 的 match 不是合法的正規表示式：" + str(e))


def validate(raw):
    if not isinstance(raw, dict):
        raise ConfigError("設定檔最外層要是 { }")
    unknown = sorted(set(raw) - set(DEFAULTS))
    if unknown:
        raise ConfigError("設定檔有不認得的欄位：" + "、".join(unknown))
    cfg = {**DEFAULTS, **raw}
    if not isinstance(cfg["port"], int) or isinstance(cfg["port"], bool) or not 1024 <= cfg["port"] <= 65535:
        raise ConfigError("port 要是 1024～65535 的整數")
    if not isinstance(cfg["theme"], str) or not THEME_ID.fullmatch(cfg["theme"]):
        raise ConfigError("theme 只能用小寫英數字和 -（外觀包的資料夾名）")
    cw = cfg["contextWindow"]
    if cw != "auto" and (not isinstance(cw, int) or isinstance(cw, bool) or cw < 10000):
        raise ConfigError('contextWindow 要寫 "auto" 或一個數字（例 200000）')
    if not isinstance(cfg["groups"], list):
        raise ConfigError("groups 要是清單 [ ]")
    for i, g in enumerate(cfg["groups"]):
        where = "groups 第 " + str(i + 1) + " 筆"
        if not isinstance(g, dict) or not isinstance(g.get("name"), str) or not g["name"].strip():
            raise ConfigError(where + " 要有 name")
        if not isinstance(g.get("color"), str) or not COLOR.fullmatch(g["color"]):
            raise ConfigError(where + " 的 color 要是 #RRGGBB")
        _check_regex(g.get("match"), where)
    m = cfg["mark"]
    if m is not None:
        if not isinstance(m, dict) or not isinstance(m.get("label"), str) or not m["label"].strip():
            raise ConfigError("mark 要有 label")
        _check_regex(m.get("match"), "mark")
    if not isinstance(cfg["ballPhrases"], list) or not all(isinstance(x, str) and x for x in cfg["ballPhrases"]):
        raise ConfigError("ballPhrases 要是文字清單")
    return cfg


def load(path):
    """沒有檔＝預設值；有檔但讀不懂＝ConfigError。"""
    try:
        with open(path, encoding="utf-8") as fh:
            raw = json.load(fh)
    except FileNotFoundError:
        return dict(DEFAULTS)
    except ValueError as e:
        raise ConfigError("設定檔不是合法的 JSON：" + str(e))
    except OSError as e:
        raise ConfigError("設定檔讀不了：" + str(e))
    return validate(raw)


def public_part(cfg):
    """給畫面用的部分（分組、標記、球在你這裡的句型）。"""
    return {"groups": cfg["groups"], "mark": cfg["mark"], "ballPhrases": cfg["ballPhrases"]}
