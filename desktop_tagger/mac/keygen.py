#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""賣家自己在本機執行的授權碼產生工具——這支檔案**不會**被打包進
ChineseNameTagger.app（ChineseNameTagger.spec 沒有把它列進去），純粹是
每賣一份就在自己電腦上跑一次的命令列小工具，跟一般使用者無關。

第一次使用（只做一次）：
    python3 keygen.py generate-keypair
產生一組 Ed25519 金鑰對：
  - 私鑰存到 license_signing_key.pem（跟這支檔案同一個資料夾）。這個
    檔案絕對不能外流、不能進 git（.gitignore 已經排除掉了）——外流的話
    等於任何人都可以自己簽發出合法的授權碼，等於這整套機制作廢。備份
    到你自己控制的地方（例如密碼管理器、加密的隨身碟），遺失的話代表
    再也沒辦法用同一把金鑰簽新的授權碼（已經發出去、使用者手上的授權
    碼不受影響，還是能正常驗證）。
  - 印出對應的「公鑰」，把印出來那行貼到
    backend/license_check.py 的 PUBLIC_KEY_HEX 常數裡（覆蓋掉那組全 0
    的佔位值）——公鑰外流沒有安全疑慮，本來就是要跟著 App 一起分發，
    只能拿來驗證授權碼，不能拿來簽發新的。

每賣出一份就執行一次：
    python3 keygen.py issue "備註（例如買家 email，純粹方便自己對帳用，
                              不會被編碼進金鑰本身、也驗證不出來）"
會印出一組授權碼字串（複製貼給買家），同時把（時間、license id、備註、
金鑰本身）記一筆到 issued_licenses.csv，方便日後對帳/查是哪一筆訂單發
出去的授權碼。

這支工具刻意沒有做「撤銷」功能——見 backend/license_check.py 開頭的
說明：App 是完全離線驗證，沒有管道接收撤銷通知，做了也沒用；真的要能
撤銷，得整套改成連網驗證才行。
"""
import base64
import csv
import datetime
import os
import secrets
import sys

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
PRIVATE_KEY_PATH = os.path.join(BASE_DIR, "license_signing_key.pem")
ISSUED_LOG_PATH = os.path.join(BASE_DIR, "issued_licenses.csv")

LICENSE_ID_LEN = 9
KEY_PREFIX = "CNT1-"


def _load_private_key():
    if not os.path.exists(PRIVATE_KEY_PATH):
        sys.exit(
            f"找不到 {PRIVATE_KEY_PATH}——先執行一次「python3 keygen.py generate-keypair」。"
        )
    with open(PRIVATE_KEY_PATH, "rb") as f:
        return serialization.load_pem_private_key(f.read(), password=None)


def _format_key(blob):
    encoded = base64.b32encode(blob).decode("ascii").rstrip("=")
    chunks = [encoded[i : i + 5] for i in range(0, len(encoded), 5)]
    return KEY_PREFIX + "-".join(chunks)


def cmd_generate_keypair():
    if os.path.exists(PRIVATE_KEY_PATH):
        sys.exit(
            f"{PRIVATE_KEY_PATH} 已經存在，不能覆蓋——換掉私鑰會讓所有已經\n"
            "發出去的授權碼全部失效（App 端的公鑰會對不上新的私鑰）。"
        )
    private_key = Ed25519PrivateKey.generate()
    pem = private_key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    )
    with open(PRIVATE_KEY_PATH, "wb") as f:
        f.write(pem)
    os.chmod(PRIVATE_KEY_PATH, 0o600)

    public_bytes = private_key.public_key().public_bytes(
        encoding=serialization.Encoding.Raw,
        format=serialization.PublicFormat.Raw,
    )
    print(f"私鑰已存到 {PRIVATE_KEY_PATH}——備份好、絕對不要進 git/外流。\n")
    print("把下面這一行貼到 backend/license_check.py 的 PUBLIC_KEY_HEX：")
    print(public_bytes.hex())


def cmd_issue(note):
    private_key = _load_private_key()
    license_id = secrets.token_bytes(LICENSE_ID_LEN)
    signature = private_key.sign(license_id)
    key_str = _format_key(license_id + signature)

    is_new_log = not os.path.exists(ISSUED_LOG_PATH)
    with open(ISSUED_LOG_PATH, "a", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        if is_new_log:
            writer.writerow(["issued_at", "license_id_hex", "note", "license_key"])
        writer.writerow(
            [
                datetime.datetime.now().isoformat(timespec="seconds"),
                license_id.hex(),
                note,
                key_str,
            ]
        )

    print(key_str)


def main():
    if len(sys.argv) < 2:
        sys.exit(__doc__)
    cmd = sys.argv[1]
    if cmd == "generate-keypair":
        cmd_generate_keypair()
    elif cmd == "issue":
        note = sys.argv[2] if len(sys.argv) > 2 else ""
        cmd_issue(note)
    else:
        sys.exit(f"不認識的指令：{cmd}\n\n{__doc__}")


if __name__ == "__main__":
    main()
