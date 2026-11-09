# scripts/models

- `ppocr_det_v3.onnx`：PaddleOCR の文字検出 PP-OCRv3（ch_PP-OCRv3_det_infer、DBNet）を ONNX にしたもの。RapidOCR（rapidocr_onnxruntime 1.2.3）が配っている同じファイル。
  - 出どころ：https://github.com/PaddlePaddle/PaddleOCR ・ https://github.com/RapidAI/RapidOCR
  - 決まり：Apache License 2.0
  - 使う所：`scripts/photo_bands.py` の `text_box`（写真の中の見出しくらいの大きさの字の範囲 → data-k。render の cropAt はこの範囲を欠かさない切り方しか許さない）
