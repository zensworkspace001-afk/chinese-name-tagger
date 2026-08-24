# 中文人名標示工具

貼上一段中文文字，選一個模型，看模型把句子裡的人名切成「姓」（藍色）／
「名」（橘色）。這是一個中文姓名切分（token classification / NER）的
demo，底層是微調過的 `hfl/chinese-roberta-wwm-ext`（BERT）。

部署在 [Streamlit Community Cloud](https://streamlit.io/cloud)。

## 提供的兩個模型

- **`model_bert_v4`**：原始開發過程中第一個驗證有效的版本
- **`model_bert_colab_v5`**：目前驗證過表現最好的版本（真實文件測試、
  第一人物+子句+第二人物句型、罕見姓氏泛化能力都優於 v4）

完整的訓練過程、資料來源、每個版本的比較與失敗經驗，見專案的
`CHANGELOG.md`。

## 已知限制

- 只處理中文姓氏詞典裡有的姓氏，音譯外國人名／日本人名（例如「鈴木櫻子」）
  目前的架構完全沒有處理
- 訓練資料以繁體中文、台灣/中國時事語境為主

## 本機執行

```bash
pip install -r requirements.txt
streamlit run app.py
```
