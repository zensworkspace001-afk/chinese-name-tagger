# -*- coding: utf-8 -*-
"""授權碼的離線驗證邏輯——只驗證，不簽發（簽發是 mac/keygen.py 的事，
私鑰不會、也不能出現在這個檔案或這支 App 裡）。

授權碼格式：`CNT1-` 開頭，後面是 base32( license_id(9 bytes) +
Ed25519 簽章(64 bytes) )，每 5 個字元用「-」分段方便對照/複製貼上。
license_id 是隨機產生、不帶任何個資，賣家自己的訂單/email 對應關係記在
mac/issued_licenses.csv（只存在賣家自己電腦上），不編碼進金鑰本身。

刻意選擇完全離線驗證（不打任何 API、不需要網路）：App 不需要網路就能用，
使用者也不用擔心哪天授權伺服器關掉、軟體就跟著沒辦法用。這個選擇的代價
是沒辦法「事後撤銷」已經發出去的授權碼——離線驗證的 App 本來就沒有管道
收到撤銷通知，這是天生的取捨，不是這裡實作疏漏，未來如果要做撤銷，得
整套改成需要連網驗證才行。
"""
import base64
import re

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey

# 對應 mac/keygen.py 的私鑰。第一次執行
# `python3 keygen.py generate-keypair` 之後，把印出來的公鑰貼過來這裡
# 替換掉——公鑰外流沒有安全疑慮（只能拿來驗證，不能拿來簽發新的合法
# 授權碼），但沒換過（還是這組全 0 的佔位值）的話，所有授權碼一律驗證
# 失敗。
PUBLIC_KEY_HEX = "a5394655f0bf761df1660ee78eadc4f7ddd3144e25eacf9ffffb5513b7290bdf"

SIGNATURE_LEN = 64
KEY_PREFIX = "CNT1-"


def _b32_decode_loose(s):
    s = s.upper()
    padding = "=" * ((8 - len(s) % 8) % 8)
    return base64.b32decode(s + padding)


def normalize_license_key(raw):
    """把使用者貼進來的授權碼整理成純 base32 字元——去掉字首、破折號、
    空白、大小寫差異，這樣使用者複製貼上時多夾帶的換行/空格也不會導致
    驗證失敗。"""
    if not raw:
        return ""
    s = raw.strip()
    if s.upper().startswith(KEY_PREFIX):
        s = s[len(KEY_PREFIX):]
    return re.sub(r"[^A-Za-z2-7]", "", s)


def verify_license_key(raw_key):
    """純離線檢查，不打任何網路請求。回傳 True/False。"""
    cleaned = normalize_license_key(raw_key)
    if not cleaned:
        return False
    try:
        blob = _b32_decode_loose(cleaned)
    except Exception:
        return False
    if len(blob) <= SIGNATURE_LEN:
        return False
    payload, signature = blob[:-SIGNATURE_LEN], blob[-SIGNATURE_LEN:]
    try:
        public_key = Ed25519PublicKey.from_public_bytes(bytes.fromhex(PUBLIC_KEY_HEX))
        public_key.verify(signature, payload)
        return True
    except Exception:
        return False
