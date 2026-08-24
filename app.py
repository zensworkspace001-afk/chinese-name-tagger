# -*- coding: utf-8 -*-
"""中文人名標示工具 — Streamlit Community Cloud 版。

跟本機的 app.py（Flask）、hf_space/app.py（Gradio）功能一樣：貼文字、選模型、
看標示出來的姓（藍）/名（橘）。改用 Streamlit 是因為 Hugging Face Spaces
的 Gradio/Docker SDK 現在需要付費 PRO 方案，Streamlit Community Cloud
對這個規模的 demo（單一 CPU、一次只載入一個模型）還是免費的。
"""
import os

import streamlit as st

from predict_bert import (
    load_model,
    predict,
    extract_names,
    predict_document,
    split_sentences_keep_punct,
)

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
MODELS_DIR = os.path.join(BASE_DIR, "models")

MODEL_LABELS = {
    "model_bert_v4": "v4（原始推薦版本）",
    "model_bert_colab_v5": "colab_v5（目前最佳版本）",
}


@st.cache_resource(show_spinner="載入模型中...")
def get_model(name):
    """用 st.cache_resource 快取模型——一個 session 裡切換模型會各自載入一次，
    之後同一個模型再選到就直接吃快取，不用重新載入權重。"""
    return load_model(os.path.join(MODELS_DIR, name))


def tag_html(chars, tags):
    parts = []
    for c, t in zip(chars, tags):
        if t in ("B-SUR", "I-SUR"):
            parts.append(f'<span style="background:#cfe3ff;border-radius:3px;padding:1px 2px">{c}</span>')
        elif t in ("B-GIV", "I-GIV"):
            parts.append(f'<span style="background:#ffe1b3;border-radius:3px;padding:1px 2px">{c}</span>')
        else:
            parts.append(c)
    return "".join(parts)


st.set_page_config(page_title="中文人名標示工具", page_icon="🈶")

st.title("中文人名標示工具")
st.write("貼上一段中文文字、選一個模型，看模型標出來的姓（藍色）／名（橘色）。")
st.caption("訓練細節、資料來源、各版本比較，見 repo 裡的 `CHANGELOG.md`。")

model_name = st.selectbox(
    "模型",
    options=list(MODEL_LABELS.keys()),
    format_func=lambda name: MODEL_LABELS[name],
    index=list(MODEL_LABELS.keys()).index("model_bert_colab_v5"),
)
use_diffusion = st.checkbox(
    "篇章級擴散後處理（用同篇文章裡已確認的人名，召回/修補漏抓的部分）",
    value=True,
)
text = st.text_area("要分析的文字", height=200, placeholder="貼上一段中文文字...")

if st.button("標示人名", type="primary"):
    if not text.strip():
        st.warning("請貼入文字")
    else:
        model, tokenizer = get_model(model_name)
        sentences = split_sentences_keep_punct(text)
        if not sentences:
            sentences = [text]

        if use_diffusion:
            results = predict_document(sentences, model, tokenizer, rounds=2)
        else:
            results = [(s, predict(s, model, tokenizer)) for s in sentences]
            results = [(s, tagged, extract_names(tagged)) for s, tagged in results]

        html_parts, all_names = [], []
        for sentence, tagged, names in results:
            chars = [c for c, _ in tagged]
            tags = [t for _, t in tagged]
            html_parts.append(f"<p>{tag_html(chars, tags)}</p>")
            for sur, giv in names:
                if giv:
                    all_names.append(sur + giv)

        st.markdown("".join(html_parts), unsafe_allow_html=True)
        st.subheader("抽出的人名")
        st.write("、".join(dict.fromkeys(all_names)) if all_names else "（沒有偵測到人名）")
