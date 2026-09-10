# -*- coding: utf-8 -*-
"""載入訓練好的 BERT 模型，對新句子做姓/名切分預測。

除了逐句預測，也提供篇章級後處理（參考 CN105868184A 專利的
「全局擴散」+「局部擴散」演算法）：
  - 全局擴散：這篇文章裡別的句子已經完整辨識出某個人名，
    就把同一篇文章裡其他地方漏抓（整段沒標到）的相同字串召回。
  - 局部擴散：修補「有姓無名」或「有名無姓」的殘缺辨識，
    用篇章內已確認的完整人名去把缺的那一半補上。
兩者都是模型輸出之後的後處理，不需要重新訓練。
"""
import re
import sys
import torch
from transformers import AutoTokenizer, AutoModelForTokenClassification

from surnames import match_surname

_SENT_SPLIT_RE = re.compile(r"([。！？；])")


def split_sentences_keep_punct(text, min_len=5, max_len=150):
    """把一段文字切成句子，保留句尾標點（不像 fetch_real_corpus.py 那樣砍掉）。

    重要教訓：砍掉句尾標點餵給模型會明顯降低辨識率，因為 BERT 的預訓練語料
    幾乎都是語法完整、有標點的正常中文文本，殘缺的句子會讓模型對句子後段
    的實體判斷失去信心（尤其是句子裡排在後面的人名，或多人並列列表）。
    務必用這個函式切句子，不要自己用 re.split + strip 重造一次。"""
    sents = []
    for line in text.split("\n"):
        buf = ""
        for part in _SENT_SPLIT_RE.split(line):
            buf += part
            if part in "。！？；":
                s = buf.strip()
                if min_len <= len(s) <= max_len:
                    sents.append(s)
                buf = ""
        s = buf.strip()
        if s and min_len <= len(s) <= max_len:
            sents.append(s)
    return sents


def load_model(path="model_bert", device=None):
    tokenizer = AutoTokenizer.from_pretrained(path)
    model = AutoModelForTokenClassification.from_pretrained(path)
    model.eval()
    if device is not None:
        model.to(device)
    return model, tokenizer


def predict(text, model, tokenizer):
    chars = list(text)
    enc = tokenizer(chars, is_split_into_words=True, return_tensors="pt")
    device = next(model.parameters()).device
    enc = enc.to(device)  # BatchEncoding.to() moves tensors but keeps word_ids() etc. working
    with torch.no_grad():
        logits = model(**enc).logits
    pred_ids = logits.argmax(-1)[0].tolist()
    word_ids = enc.word_ids()
    tags = ["O"] * len(chars)
    seen = set()
    for pid, w_idx in zip(pred_ids, word_ids):
        if w_idx is None or w_idx in seen:
            continue
        seen.add(w_idx)
        tags[w_idx] = model.config.id2label[pid]
    return list(zip(chars, tags))


def extract_names(tagged):
    results = []
    sur, giv = "", ""
    state = None
    for ch, tag in tagged:
        if tag == "B-SUR":
            if sur or giv:
                results.append((sur, giv))
            sur, giv = ch, ""
            state = "SUR"
        elif tag == "I-SUR" and state in ("SUR",):
            sur += ch
        elif tag == "B-GIV":
            giv = ch
            state = "GIV"
        elif tag == "I-GIV" and state in ("GIV",):
            giv += ch
        else:
            if sur or giv:
                results.append((sur, giv))
            sur, giv = "", ""
            state = None
    if sur or giv:
        results.append((sur, giv))
    return results


def extract_entities(tagged):
    """統一格式版本，同時處理中文人名（切姓/名）、外語音譯人名（B-FOR/
    I-FOR，整段一個實體不切邊界）、日文人名（B-JPN/I-JPN，同樣整段一個
    實體）。回傳 dict 清單：
    - {"type": "CN", "sur": ..., "giv": ..., "text": sur+giv}
    - {"type": "FOR", "text": ...}
    - {"type": "JPN", "text": ...}
    刻意不修改 extract_names()（只認 SUR/GIV，行為維持不變）——app.py
    以外的呼叫端（colab notebook、streamlit_app 等）目前都是靠
    extract_names() 的 (sur, giv) tuple 格式運作，改了會連帶要求它們
    都跟著改，這裡新增一個函式取代，不動舊的。"""
    results = []
    sur, giv = "", ""
    cn_state = None
    buf, buf_type = "", None

    def flush_cn():
        nonlocal sur, giv, cn_state
        if sur or giv:
            results.append({"type": "CN", "sur": sur, "giv": giv, "text": sur + giv})
        sur, giv, cn_state = "", "", None

    def flush_buf():
        nonlocal buf, buf_type
        if buf:
            results.append({"type": buf_type, "text": buf})
        buf, buf_type = "", None

    for ch, tag in tagged:
        if tag == "B-SUR":
            flush_buf()
            flush_cn()
            sur, giv = ch, ""
            cn_state = "SUR"
        elif tag == "I-SUR" and cn_state == "SUR":
            sur += ch
        elif tag == "B-GIV":
            flush_buf()
            giv = ch
            cn_state = "GIV"
        elif tag == "I-GIV" and cn_state == "GIV":
            giv += ch
        elif tag == "B-FOR":
            flush_cn()
            flush_buf()
            buf, buf_type = ch, "FOR"
        elif tag == "I-FOR" and buf_type == "FOR":
            buf += ch
        elif tag == "B-JPN":
            flush_cn()
            flush_buf()
            buf, buf_type = ch, "JPN"
        elif tag == "I-JPN" and buf_type == "JPN":
            buf += ch
        else:
            flush_cn()
            flush_buf()
    flush_cn()
    flush_buf()
    return results


def collect_confirmed_names(doc_tagged):
    """doc_tagged: 每句話的 (sentence, tagged) list。
    回傳這篇文章裡「姓+名都有」的完整人名字串集合。"""
    confirmed = set()
    for sentence, tagged in doc_tagged:
        for sur, giv in extract_names(tagged):
            if sur and giv:
                confirmed.add(sur + giv)
    return confirmed


def collect_confirmed_entities(doc_tagged):
    """跟 collect_confirmed_names() 一樣的概念，但同時收集 CN/FOR/JPN
    三種類型，回傳 {"CN": {...}, "FOR": {...}, "JPN": {...}} 三個集合。"""
    confirmed = {"CN": set(), "FOR": set(), "JPN": set()}
    for sentence, tagged in doc_tagged:
        for ent in extract_entities(tagged):
            if ent["type"] == "CN":
                if ent["sur"] and ent["giv"]:
                    confirmed["CN"].add(ent["text"])
            else:
                confirmed[ent["type"]].add(ent["text"])
    return confirmed


def global_diffusion_multi(doc_tagged, confirmed):
    """global_diffusion() 的多類型版本：對每句話裡完全沒被標到（整段 O）、
    但字串跟篇章內已確認實體一致的地方，召回標成對應類型。CN 沿用
    match_surname() 切姓/名邊界；FOR/JPN 整段直接標同一個實體，不用切
    邊界（跟 fetch_foreign_corpus.py／fetch_japanese_corpus.py 的標記
    邏輯一致）。"""
    all_confirmed = []
    for name in confirmed.get("CN", ()):
        all_confirmed.append((name, "CN"))
    for name in confirmed.get("FOR", ()):
        all_confirmed.append((name, "FOR"))
    for name in confirmed.get("JPN", ()):
        all_confirmed.append((name, "JPN"))
    if not all_confirmed:
        return doc_tagged
    all_confirmed.sort(key=lambda x: len(x[0]), reverse=True)

    new_doc = []
    for sentence, tagged in doc_tagged:
        chars = [c for c, _ in tagged]
        tags = [t for _, t in tagged]
        i, n = 0, len(chars)
        while i < n:
            if tags[i] == "O":
                matched, matched_type = None, None
                for name, etype in all_confirmed:
                    if sentence.startswith(name, i):
                        matched, matched_type = name, etype
                        break
                if matched:
                    span_all_o = all(t == "O" for t in tags[i:i + len(matched)])
                    if span_all_o:
                        if matched_type == "CN":
                            ms = match_surname(sentence, i)
                            if ms and matched.startswith(ms[0]):
                                sur, slen = ms
                                giv = matched[slen:]
                                if giv:
                                    tags[i] = "B-SUR"
                                    for k in range(1, slen):
                                        tags[i + k] = "I-SUR"
                                    goff = i + slen
                                    tags[goff] = "B-GIV"
                                    for k in range(1, len(giv)):
                                        tags[goff + k] = "I-GIV"
                                    i += len(matched)
                                    continue
                        else:  # FOR / JPN：整段一個實體，不切邊界
                            tags[i] = f"B-{matched_type}"
                            for k in range(1, len(matched)):
                                tags[i + k] = f"I-{matched_type}"
                            i += len(matched)
                            continue
            i += 1
        new_doc.append((sentence, list(zip(chars, tags))))
    return new_doc


def global_diffusion(doc_tagged, confirmed_names):
    """對每句話裡完全沒被標到（整段 O）、但字串跟篇章內已確認人名
    一致的地方，召回標成人名。"""
    if not confirmed_names:
        return doc_tagged
    confirmed_by_len = sorted(confirmed_names, key=len, reverse=True)
    new_doc = []
    for sentence, tagged in doc_tagged:
        chars = [c for c, _ in tagged]
        tags = [t for _, t in tagged]
        i, n = 0, len(chars)
        while i < n:
            if tags[i] == "O":
                matched = None
                for name in confirmed_by_len:
                    if sentence.startswith(name, i):
                        matched = name
                        break
                if matched:
                    ms = match_surname(sentence, i)
                    if ms and matched.startswith(ms[0]):
                        sur, slen = ms
                        giv = matched[slen:]
                        span_all_o = all(t == "O" for t in tags[i:i + len(matched)])
                        if giv and span_all_o:
                            tags[i] = "B-SUR"
                            for k in range(1, slen):
                                tags[i + k] = "I-SUR"
                            goff = i + slen
                            tags[goff] = "B-GIV"
                            for k in range(1, len(giv)):
                                tags[goff + k] = "I-GIV"
                            i += len(matched)
                            continue
            i += 1
        new_doc.append((sentence, list(zip(chars, tags))))
    return new_doc


def local_diffusion(doc_tagged, confirmed_names):
    """修補「有姓無名」（姓後面沒接上名）或「有名無姓」（名前面沒接上姓）
    的殘缺辨識，用篇章內已確認的完整人名去補齊。"""
    if not confirmed_names:
        return doc_tagged
    confirmed_by_len = sorted(confirmed_names, key=len, reverse=True)
    new_doc = []
    for sentence, tagged in doc_tagged:
        chars = [c for c, _ in tagged]
        tags = [t for _, t in tagged]
        n = len(chars)

        # 有姓無名：B-SUR(+I-SUR) 後面沒接 B-GIV，往後找看看是不是某個
        # 已確認人名的姓氏開頭，字元對得上就把名的部分補上
        i = 0
        while i < n:
            if tags[i] == "B-SUR":
                j = i
                while j < n and tags[j] == "I-SUR":
                    j += 1
                sur_text = "".join(chars[i:j])
                has_giv_after = j < n and tags[j] == "B-GIV"
                if not has_giv_after:
                    for full in confirmed_by_len:
                        if full.startswith(sur_text) and len(full) > len(sur_text):
                            giv = full[len(sur_text):]
                            if "".join(chars[j:j + len(giv)]) == giv and \
                               all(tags[k] == "O" for k in range(j, min(j + len(giv), n))):
                                tags[j] = "B-GIV"
                                for k in range(1, len(giv)):
                                    tags[j + k] = "I-GIV"
                                break
                i = j if j > i else i + 1
            else:
                i += 1

        # 有名無姓：B-GIV 前面沒有 B-SUR/I-SUR，往前找看看是不是某個
        # 已確認人名的名字結尾，字元對得上就把姓的部分補上
        i = 0
        while i < n:
            if tags[i] == "B-GIV":
                j = i
                while j < n and tags[j] in ("B-GIV", "I-GIV"):
                    j += 1
                giv_text = "".join(chars[i:j])
                prev_is_sur = i > 0 and tags[i - 1] in ("B-SUR", "I-SUR")
                if not prev_is_sur:
                    for full in confirmed_by_len:
                        if full.endswith(giv_text) and len(full) > len(giv_text):
                            sur = full[:len(full) - len(giv_text)]
                            start = i - len(sur)
                            if start >= 0 and "".join(chars[start:i]) == sur and \
                               all(tags[k] == "O" for k in range(start, i)):
                                tags[start] = "B-SUR"
                                for k in range(start + 1, i):
                                    tags[k] = "I-SUR"
                                break
                i = j
            else:
                i += 1

        new_doc.append((sentence, list(zip(chars, tags))))
    return new_doc


def _find_nonO_runs(doc_tagged):
    """把每句話切成「最大連續非 O 字元區段」（run），回傳 dict list：
    {sent_idx, start, end, text, tags, coherent, type}。
    coherent 的判斷：把這段 run 自己丟進 extract_entities()，如果剛好解析成
    「一個」實體、而且那個實體的文字長度跟整段 run 的長度一樣長，代表這段
    run 從頭到尾是同一個家族的標籤（純 JPN、純 FOR，或是合法的 SUR→GIV
    銜接），沒有中途斷裂或混雜家族；否則就是「破碎/雜訊」預測（例如
    B-JPN 後面接 I-SUR 這種同一段裡混了兩種家族標籤的情況），不當作
    多數決的有效票。"""
    runs = []
    for sent_idx, (sentence, tagged) in enumerate(doc_tagged):
        chars = [c for c, _ in tagged]
        tags = [t for _, t in tagged]
        n = len(tags)
        i = 0
        while i < n:
            if tags[i] != "O":
                j = i
                while j < n and tags[j] != "O":
                    j += 1
                run_chars, run_tags = chars[i:j], tags[i:j]
                text = "".join(run_chars)
                ents = extract_entities(list(zip(run_chars, run_tags)))
                coherent = len(ents) == 1 and len(ents[0]["text"]) == len(text)
                runs.append({
                    "sent_idx": sent_idx, "start": i, "end": j,
                    "text": text, "tags": run_tags,
                    "coherent": coherent,
                    "type": ents[0]["type"] if coherent else None,
                })
                i = j
            else:
                i += 1
    return runs


def reconcile_type_conflicts(doc_tagged):
    """篇章級後處理第三步：同一個字串在文章裡不同地方出現，卻被標成不同
    類型（例如「小林誠」某處標對 B-JPN 整段，另一處卻標成中文姓/名切分甚至
    中途斷裂），global_diffusion/local_diffusion 都不處理這種「兩處都有
    標籤、但彼此衝突」的狀況（它們只處理「完全沒標到」或「中文半個名字」）。

    做法：同一字串的所有出現裡，只採計「乾淨」(coherent，見
    _find_nonO_runs()) 的那些當作投票，票數最高的類型當作這個字串在全文
    的正確樣板，其餘出現（不管是雜訊斷裂還是乾淨但少數的類型）全部覆寫成
    同一個標籤樣板。

    已知限制：如果模型對某個字串「乾淨但持續標錯」的次數比標對的次數還
    多（例如同一姓氏字元在訓練資料裡中文用法遠多於日文用法，模型該次
    多數表決反而會選到錯的那個多數），單純多數決無法救回來——這種情況
    要靠補訓練資料修正模型本身，不是這裡的後處理範圍。"""
    runs = _find_nonO_runs(doc_tagged)
    by_text = {}
    for r in runs:
        by_text.setdefault(r["text"], []).append(r)

    canonical = {}
    for text, rs in by_text.items():
        if len(rs) < 2:
            continue
        coherent_rs = [r for r in rs if r["coherent"]]
        if not coherent_rs:
            continue  # 沒有任何乾淨版本可以參考，無法安全判斷，維持原樣
        if len(coherent_rs) == len(rs) and len({r["type"] for r in coherent_rs}) == 1:
            continue  # 已經完全一致，不用動

        type_counts, first_seen = {}, {}
        for r in coherent_rs:
            type_counts[r["type"]] = type_counts.get(r["type"], 0) + 1
            first_seen.setdefault(r["type"], r)
        best = max(type_counts.values())
        tied = [t for t, c in type_counts.items() if c == best]
        majority_type = min(tied, key=lambda t: (first_seen[t]["sent_idx"], first_seen[t]["start"]))
        canonical[text] = first_seen[majority_type]["tags"]

    new_doc = [(s, list(tg)) for s, tg in doc_tagged]
    for text, rs in by_text.items():
        if text not in canonical:
            continue
        pattern = canonical[text]
        for r in rs:
            if r["tags"] != pattern:
                sentence, tagged = new_doc[r["sent_idx"]]
                chars = [c for c, _ in tagged]
                tags = [t for _, t in tagged]
                tags[r["start"]:r["end"]] = pattern
                new_doc[r["sent_idx"]] = (sentence, list(zip(chars, tags)))
    return new_doc


def predict_document(sentences, model, tokenizer, rounds=1):
    """對一整篇文章（多句話）做逐句預測 + 篇章級全局/局部擴散後處理。
    回傳 [(sentence, tagged, entities), ...]，entities 是 extract_entities()
    的統一格式（CN/FOR/JPN 都有）。

    global diffusion（跨句召回同一個已確認實體）用 global_diffusion_multi()，
    CN/FOR/JPN 三種都處理；local diffusion（修補「有姓無名」/「有名無姓」
    的殘缺 CN 姓名）維持只處理 CN——FOR/JPN 是整段不切邊界的單一實體，
    沒有「半個實體」這種殘缺狀態可以修補，套用 local diffusion 沒有意義。
    最後跑一次 reconcile_type_conflicts()，處理前兩者都不管的「同一字串、
    不同地方標成不同類型」的衝突（見該函式 docstring 的已知限制）。"""
    doc_tagged = [(s, predict(s, model, tokenizer)) for s in sentences]
    for _ in range(rounds):
        confirmed = collect_confirmed_entities(doc_tagged)
        doc_tagged = global_diffusion_multi(doc_tagged, confirmed)
        confirmed_cn = collect_confirmed_entities(doc_tagged)["CN"]
        doc_tagged = local_diffusion(doc_tagged, confirmed_cn)
    doc_tagged = reconcile_type_conflicts(doc_tagged)
    return [(s, tagged, extract_entities(tagged)) for s, tagged in doc_tagged]


if __name__ == "__main__":
    model_path = sys.argv[1] if len(sys.argv) > 1 else "model_bert"
    model, tokenizer = load_model(model_path)

    test_sentences = [
        "王小明昨天去看電影。",
        "歐陽鋒和洪七公在華山比武。",
        "老師陳美玲稱讚了學生林志豪的表現。",
        "諸葛亮向劉備獻上了妙計。",
        "這次記者會由張淑芬主持，來賓有李國瑞。",
    ]

    for s in test_sentences:
        tagged = predict(s, model, tokenizer)
        names = extract_names(tagged)
        print(f"句子：{s}")
        print(f"  逐字標籤：{tagged}")
        print(f"  抽出姓名：{names}\n")
