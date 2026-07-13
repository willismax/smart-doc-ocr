"""智慧文件辨識系統 — Streamlit UI（文書人員介面）。

啟動：streamlit run app.py    （或直接雙擊 start.bat）
"""
from __future__ import annotations

import logging
import tempfile
from pathlib import Path

import streamlit as st

from smartdoc.batch import BatchProcessor, Status
from smartdoc.comparator import DocumentComparator
from smartdoc.config import SETTINGS
from smartdoc.errors import SmartDocError
from smartdoc.pipeline import DocumentPipeline
from smartdoc.recognizer import OcrEngine
from smartdoc.structurer import extract_fields

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    handlers=[logging.FileHandler(
        Path(SETTINGS["paths"]["logs"]) / "app.log", encoding="utf-8")],
)

st.set_page_config(page_title="智慧文件辨識系統", page_icon="📄", layout="wide")

UPLOAD_TYPES = ["pdf", "docx", "xlsx", "xlsm", "pptx", "doc", "xls",
                "jpg", "jpeg", "png", "tiff", "tif", "bmp",
                "eml", "msg", "txt", "md", "csv"]


# ── 共用資源（快取，避免重複載入模型） ──────────────────────────
@st.cache_resource
def get_comparator() -> DocumentComparator:
    return DocumentComparator()


def make_pipeline(mask_pii: bool, operator: str) -> DocumentPipeline:
    return DocumentPipeline(mask_pii=mask_pii, pii_operator=operator)


def save_upload(uploaded) -> Path:
    """上傳檔存到暫存目錄（保留原始副檔名供降級讀取器判斷）。"""
    suffix = Path(uploaded.name).suffix or ".bin"
    with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp:
        tmp.write(uploaded.getbuffer())
        return Path(tmp.name)


def run_pipeline_safely(pipeline: DocumentPipeline, path: Path,
                        display_name: str) -> dict | None:
    try:
        result = pipeline.process(path)
        result["file_name"] = display_name
        return result
    except SmartDocError as e:
        st.error(f"⚠️ {display_name}：{e.user_message}")
    except Exception:
        logging.getLogger("app").exception("處理 %s 失敗", display_name)
        st.error(f"⚠️ {display_name}：發生未預期錯誤，"
                 "技術細節已寫入 logs/app.log，請聯絡資訊人員。")
    return None


# ── 側欄 ──────────────────────────────────────────────────────
with st.sidebar:
    st.title("⚙️ 設定")
    mode = st.radio("功能", ["📄 單檔辨識", "🔍 文件比對", "📚 批量處理"])
    st.divider()
    mask_pii = st.toggle(
        "自動遮蔽個資", value=True,
        help="預設開啟。關閉後畫面會顯示身分證、電話等原始個資，"
             "關閉動作會寫入稽核日誌。")
    if not mask_pii:
        st.warning("已關閉個資遮蔽，畫面將顯示原始個資。")
    operator = st.selectbox(
        "遮蔽方式", ["replace", "hash", "redact"],
        format_func={"replace": "標籤取代（推薦）",
                     "hash": "雜湊代碼（可核對）",
                     "redact": "完全刪除"}.get,
        disabled=not mask_pii)
    st.divider()
    engine = OcrEngine.get()
    if engine.available:
        st.success("OCR 引擎：已就緒")
    else:
        st.warning("OCR 引擎未就緒：掃描 PDF 與圖片暫時無法辨識，"
                   "數位 PDF 與 Office 文件不受影響。")
        with st.expander("技術訊息"):
            st.code(engine.load_error or "未知")
    st.caption("🔒 所有運算皆在本機執行，文件不會離開這台電腦。")


# ══ 模式一：單檔辨識 ══════════════════════════════════════════
if mode == "📄 單檔辨識":
    st.title("📄 單檔辨識")
    st.caption("支援 PDF（數位/掃描）、Word、Excel、PPT、圖片、Email、純文字")
    uploaded = st.file_uploader("拖放文件至此", type=UPLOAD_TYPES)

    if uploaded and st.button("🚀 開始辨識", type="primary"):
        pipeline = make_pipeline(mask_pii, operator)
        tmp_path = save_upload(uploaded)
        try:
            with st.spinner("辨識中，掃描文件可能需要數十秒…"):
                result = run_pipeline_safely(pipeline, tmp_path, uploaded.name)
        finally:
            tmp_path.unlink(missing_ok=True)

        if result:
            pii = result["pii_report"]
            c1, c2, c3, c4 = st.columns(4)
            c1.metric("文件類型", result["doc_type"])
            c2.metric("頁數", result["pages"])
            c3.metric("偵測到個資", pii["pii_count"])
            c4.metric("使用 OCR", "是" if result["used_ocr"] else "否")
            if pii["pii_labels"]:
                st.info("個資類型：" + "、".join(pii["pii_labels"]))
            st.subheader("辨識結果" + ("（已遮蔽個資）" if mask_pii else ""))
            st.markdown(result["display_text"] or "*（未辨識出文字）*")
            st.download_button(
                "⬇️ 下載 Markdown",
                data=result["display_text"],
                file_name=f"{Path(uploaded.name).stem}.md",
                mime="text/markdown")

# ══ 模式二：文件比對 ══════════════════════════════════════════
elif mode == "🔍 文件比對":
    st.title("🔍 文件比對")
    col1, col2 = st.columns(2)
    with col1:
        file_a = st.file_uploader("文件 A（基準版）", type=UPLOAD_TYPES, key="a")
    with col2:
        file_b = st.file_uploader("文件 B（比對版）", type=UPLOAD_TYPES, key="b")

    compare_mode = st.radio(
        "比對方式", ["逐行文字差異", "語意相似度", "欄位比對"], horizontal=True)

    field_labels = []
    if compare_mode == "欄位比對":
        field_input = st.text_input(
            "要比對的欄位（用逗號分隔）", value="姓名, 金額, 日期, 地址",
            help="系統會在兩份文件中尋找「欄位名：值」並逐項比對")
        field_labels = [x.strip() for x in field_input.replace("，", ",").split(",")
                        if x.strip()]

    if file_a and file_b and st.button("🔍 開始比對", type="primary"):
        pipeline = make_pipeline(mask_pii, operator)
        pa, pb = save_upload(file_a), save_upload(file_b)
        try:
            with st.spinner("辨識兩份文件中…"):
                ra = run_pipeline_safely(pipeline, pa, file_a.name)
                rb = run_pipeline_safely(pipeline, pb, file_b.name)
        finally:
            pa.unlink(missing_ok=True)
            pb.unlink(missing_ok=True)

        if ra and rb:
            # 比對一律用「遮蔽後」文字，避免個資出現在差異畫面
            ta = ra["display_text"]
            tb = rb["display_text"]
            comparator = get_comparator()

            if compare_mode == "逐行文字差異":
                d = comparator.diff_text(ta, tb)
                c1, c2, c3 = st.columns(3)
                c1.metric("相似度", d["similarity_pct"])
                c2.metric("新增行", d["added"])
                c3.metric("刪除行", d["removed"])
                if d["diff_lines"]:
                    shown = d["diff_lines"][:300]
                    st.code("\n".join(shown), language="diff")
                    if len(d["diff_lines"]) > 300:
                        st.caption(f"（僅顯示前 300 行，完整 "
                                   f"{len(d['diff_lines'])} 行請下載報告）")
                    st.download_button(
                        "⬇️ 下載完整差異報告",
                        data="\n".join(d["diff_lines"]),
                        file_name="diff_report.txt")
                else:
                    st.success("兩份文件內容完全相同。")

            elif compare_mode == "語意相似度":
                r = comparator.semantic_similarity(ta, tb)
                score = r["score"]
                st.metric("語意相似度", f"{score * 100:.1f}%")
                st.progress(min(max(score, 0.0), 1.0))
                st.caption(f"演算法：{r['method']}")
                if score >= 0.9:
                    st.success("兩份文件意思幾乎相同。")
                elif score >= 0.7:
                    st.info("兩份文件大致相似，部分內容有出入。")
                else:
                    st.warning("兩份文件內容差異明顯。")

            else:  # 欄位比對
                fa = extract_fields(ra["structured_text"], field_labels)
                fb = extract_fields(rb["structured_text"], field_labels)
                field_map = {k: {"type": "fuzzy", "threshold": 0.85}
                             for k in field_labels}
                rows = comparator.field_compare(fa, fb, field_map)
                # 遮蔽欄位值中的個資再顯示
                if mask_pii:
                    protector = pipeline.pii
                    for row in rows:
                        row["value_a"] = protector.mask(row["value_a"])
                        row["value_b"] = protector.mask(row["value_b"])
                match_n = sum(1 for r in rows if r["match"])
                st.metric("相符欄位", f"{match_n} / {len(rows)}")
                st.dataframe(
                    [{"欄位": r["field"], "文件A": r["value_a"],
                      "文件B": r["value_b"],
                      "結果": "✅ 相符" if r["match"] else "❌ 不符",
                      "分數": r["score"]} for r in rows],
                    use_container_width=True)

# ══ 模式三：批量處理 ══════════════════════════════════════════
else:
    st.title("📚 批量處理")
    st.caption("一次丟入多份文件，逐份獨立處理：一份失敗不影響其他。")
    uploaded_files = st.file_uploader(
        "選擇多份文件", type=UPLOAD_TYPES, accept_multiple_files=True)

    if uploaded_files:
        st.info(f"已選 {len(uploaded_files)} 份文件")
        if st.button(f"🚀 批量處理 {len(uploaded_files)} 份", type="primary"):
            pipeline = make_pipeline(mask_pii, operator)
            tmp_paths, name_map = [], {}
            for f in uploaded_files:
                p = save_upload(f)
                tmp_paths.append(p)
                name_map[str(p)] = f.name

            progress = st.progress(0.0)
            status_text = st.empty()

            def on_progress(done, total, result):
                name = name_map.get(result.file_path,
                                    Path(result.file_path).name)
                ok = "✅" if result.status == Status.SUCCESS else "❌"
                status_text.text(f"{ok} {name}（{done}/{total}）")
                progress.progress(done / total)

            processor = BatchProcessor(pipeline)
            try:
                results = processor.run(tmp_paths, on_progress=on_progress)
            finally:
                for p in tmp_paths:
                    p.unlink(missing_ok=True)

            # 報告內顯示原始檔名
            for r in results:
                if r.file_path in name_map:
                    r.file_path = name_map[r.file_path]

            s = processor.summary()
            c1, c2, c3, c4 = st.columns(4)
            c1.metric("總計", s["total"])
            c2.metric("成功", s["success"])
            c3.metric("失敗", s["failed"] + s["skipped"])
            c4.metric("平均耗時", f"{s['avg_sec']} 秒")

            report_md = processor.report_markdown()
            with st.expander("📋 完整報告", expanded=True):
                st.markdown(report_md)

            col1, col2 = st.columns(2)
            with col1:
                st.download_button("⬇️ 下載報告（Markdown）",
                                   data=report_md,
                                   file_name="batch_report.md")
            with col2:
                out = Path(SETTINGS["paths"]["output"]) / "batch_report.xlsx"
                xlsx = processor.report_xlsx(out)
                if xlsx:
                    st.download_button(
                        "⬇️ 下載報告（Excel）",
                        data=xlsx.read_bytes(),
                        file_name="batch_report.xlsx",
                        mime="application/vnd.openxmlformats-officedocument"
                             ".spreadsheetml.sheet")

            # 成功檔案的辨識結果打包下載
            ok_results = [r for r in results if r.status == Status.SUCCESS]
            if ok_results:
                import io
                import zipfile
                buf = io.BytesIO()
                with zipfile.ZipFile(buf, "w",
                                     zipfile.ZIP_DEFLATED) as zf:
                    for r in ok_results:
                        stem = Path(r.file_path).stem
                        zf.writestr(f"{stem}.md",
                                    r.output.get("display_text", ""))
                st.download_button(
                    "⬇️ 下載全部辨識結果（ZIP）",
                    data=buf.getvalue(),
                    file_name="results.zip", mime="application/zip")
