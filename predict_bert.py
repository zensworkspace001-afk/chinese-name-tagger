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


def collect_confirmed_names(doc_tagged):
    """doc_tagged: 每句話的 (sentence, tagged) list。
    回傳這篇文章裡「姓+名都有」的完整人名字串集合。"""
    confirmed = set()
    for sentence, tagged in doc_tagged:
        for sur, giv in extract_names(tagged):
            if sur and giv:
                confirmed.add(sur + giv)
    return confirmed


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


def predict_document(sentences, model, tokenizer, rounds=1):
    """對一整篇文章（多句話）做逐句預測 + 篇章級全局/局部擴散後處理。
    回傳 [(sentence, tagged, names), ...]。"""
    doc_tagged = [(s, predict(s, model, tokenizer)) for s in sentences]
    for _ in range(rounds):
        confirmed = collect_confirmed_names(doc_tagged)
        doc_tagged = global_diffusion(doc_tagged, confirmed)
        confirmed = collect_confirmed_names(doc_tagged)
        doc_tagged = local_diffusion(doc_tagged, confirmed)
    return [(s, tagged, extract_names(tagged)) for s, tagged in doc_tagged]


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
