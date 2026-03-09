import base64
import io
import json
from datetime import date, timedelta
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()  # Must happen before any langchain imports for LangSmith tracing

import pandas as pd
import streamlit as st

from agents.receipt_analyzer.manager import ReceiptManager
from agents.receipt_analyzer.schemas import DEFAULT_CATEGORIES
from agents.receipt_analyzer.storage import get_categories
from shared.config.settings import settings

UPLOAD_DIR = Path("./data/uploads")
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)

mgr = ReceiptManager()
mgr.init()

if settings.start_watcher_in_ui:
    from agents.receipt_analyzer.watcher import start_watcher
    start_watcher()

st.set_page_config(page_title="Personal Agent", layout="wide")
st.title("Personal Agent")

# Count pending for tab label (exclude receipt shown on Upload tab)
pending = mgr.get_pending()
upload_sid = st.session_state.get("last_staging_id")
pending_count = sum(1 for s in pending if s["staging_id"] != upload_sid) if upload_sid else len(pending)
pending_label = f"Pending Review ({pending_count})" if pending_count else "Pending Review"

tab_upload, tab_pending, tab_expenses, tab_summary = st.tabs(
    ["Upload Receipt", pending_label, "Expenses", "Summary"]
)


def _show_image(image_path: str):
    """Display image, converting HEIC if needed."""
    if image_path.lower().endswith((".heic", ".heif")):
        from PIL import Image
        from pillow_heif import register_heif_opener

        register_heif_opener()
        img = Image.open(image_path)
        buf = io.BytesIO()
        img.save(buf, format="JPEG")
        st.image(buf.getvalue(), width="stretch")
    else:
        st.image(image_path, width="stretch")


def _copy_json_button(data: dict, key: str):
    """Render a copy-to-clipboard button for JSON data."""
    receipt_json = json.dumps(data, indent=2)
    b64 = base64.b64encode(receipt_json.encode()).decode()
    st.components.v1.html(
        """<button id="copybtn_"""
        + key
        + """" onclick="
            var text = atob('"""
        + b64
        + """');
            navigator.clipboard.writeText(text).then(function() {
                var btn = document.getElementById('copybtn_"""
        + key
        + """');
                btn.textContent = 'Copied!';
                setTimeout(function() { btn.textContent = 'Copy JSON'; }, 2000);
            });
        " style="
            padding: 0.4rem 1rem;
            border: 1px solid #ccc;
            border-radius: 0.5rem;
            background: white;
            cursor: pointer;
            font-size: 0.9rem;
        ">Copy JSON</button>""",
        height=45,
    )


@st.dialog("Receipt Detail", width="large")
def _show_receipt_detail(r):
    """Modal dialog showing full receipt detail + image."""
    r_date = date.fromisoformat(str(r.date)).strftime("%m/%d/%Y") if r.date else "?"
    col_img, col_detail = st.columns([1, 2])
    with col_img:
        if r.file_path and Path(r.file_path).exists():
            _show_image(r.file_path)
        else:
            st.caption("Image not available")
    with col_detail:
        st.markdown(f"**Merchant:** {r.merchant_name}")
        st.markdown(f"**Address:** {r.merchant_address or '—'}")
        st.markdown(f"**Date:** {r_date}")
        st.markdown(f"**Category:** {r.category}")
        st.markdown(f"**Payment:** {r.payment_method or '—'}")
        st.markdown(f"**Currency:** {r.currency}")
        items = r.items or []
        if items:
            st.markdown("**Items**")
            items_df = pd.DataFrame([i.model_dump() for i in items])
            items_df.columns = [c.replace("_", " ").title() for c in items_df.columns]
            st.dataframe(items_df, hide_index=True, width="stretch")
        c1, c2, c3, c4 = st.columns(4)
        c1.metric("Subtotal", f"${r.subtotal or 0:.2f}")
        c2.metric("Tax", f"${r.tax or 0:.2f}")
        c3.metric("Tip", f"${r.tip or 0:.2f}")
        c4.metric("Total", f"${r.total:.2f}")

    # Delete with confirmation
    st.divider()
    if st.session_state.get("_confirm_delete") == r.id:
        st.warning("This will permanently delete the receipt record and its archived image.")
        c1, c2 = st.columns(2)
        with c1:
            if st.button("Confirm Delete", type="primary", use_container_width=True):
                mgr.delete(r.id)
                st.session_state.pop("_confirm_delete", None)
                st.rerun()
        with c2:
            if st.button("Cancel", use_container_width=True):
                st.session_state.pop("_confirm_delete", None)
                st.rerun()
    else:
        if st.button("Delete Receipt", key=f"del_{r.id}", help="Permanently deletes the receipt from the database and removes the archived image"):
            st.session_state["_confirm_delete"] = r.id
            st.rerun()


@st.dialog("Duplicate Receipt Detected")
def _confirm_duplicate_approve(staging_id: str, edited_data: dict):
    """Modal dialog to confirm saving a duplicate receipt."""
    st.warning("This receipt appears to be a duplicate. Are you sure you want to save it?")
    c1, c2 = st.columns(2)
    with c1:
        if st.button("Confirm Approve", type="primary", use_container_width=True):
            mgr.update_staged(staging_id, edited_data)
            receipt_id = mgr.approve(staging_id)
            st.session_state["_dup_approved_msg"] = f"Saved as receipt #{receipt_id}"
            st.rerun()
    with c2:
        if st.button("Cancel", use_container_width=True):
            st.rerun()


def _render_review_form(staged: dict, key_prefix: str):
    """Render editable review form for a staged receipt."""
    data = staged["extracted_data"]
    image_path = staged["image_path"]
    staging_id = staged["staging_id"]

    dup_receipt = None
    col_img, col_data = st.columns([1, 2])

    with col_img:
        if Path(image_path).exists():
            _show_image(image_path)

    with col_data:
        # Editable fields
        merchant = st.text_input("Merchant", value=data.get("merchant_name", ""), key=f"{key_prefix}_merchant")
        address = st.text_input("Address", value=data.get("merchant_address") or "", key=f"{key_prefix}_address")

        c1, c2 = st.columns(2)
        with c1:
            receipt_date = st.date_input(
                "Date",
                value=date.fromisoformat(data["date"]) if data.get("date") else date.today(),
                key=f"{key_prefix}_date",
                format="MM/DD/YYYY",
            )
        with c2:
            db_cats = get_categories()
            default_cats = DEFAULT_CATEGORIES
            categories = sorted(set(default_cats + db_cats))
            current_cat = data.get("category", "other")
            # If LLM returned a new category not in the list, include it
            if current_cat and current_cat not in categories:
                categories.append(current_cat)
            cat_idx = categories.index(current_cat) if current_cat in categories else categories.index("other")
            category = st.selectbox("Category", categories, index=cat_idx, key=f"{key_prefix}_cat")

        c1, c2, c3 = st.columns(3)
        with c1:
            payment = st.text_input("Payment", value=data.get("payment_method") or "", key=f"{key_prefix}_payment")
        with c2:
            currency = st.text_input("Currency", value=data.get("currency", "USD"), key=f"{key_prefix}_currency")

        # Line items (read-only table for now)
        items = data.get("items") or []
        if items:
            st.markdown("**Items**")
            items_df = pd.DataFrame(items)
            items_df.columns = [c.replace("_", " ").title() for c in items_df.columns]
            st.dataframe(items_df, hide_index=True, width="stretch")

        # Editable totals
        c1, c2, c3, c4 = st.columns(4)
        with c1:
            subtotal = st.number_input("Subtotal", value=float(data.get("subtotal") or 0), format="%.2f", key=f"{key_prefix}_subtotal")
        with c2:
            tax = st.number_input("Tax", value=float(data.get("tax") or 0), format="%.2f", key=f"{key_prefix}_tax")
        with c3:
            tip = st.number_input("Tip", value=float(data.get("tip") or 0), format="%.2f", key=f"{key_prefix}_tip")
        with c4:
            total = st.number_input("Total", value=float(data.get("total") or 0), format="%.2f", key=f"{key_prefix}_total")

        # Build edited data
        edited_data = {
            "merchant_name": merchant,
            "merchant_address": address or None,
            "date": str(receipt_date),
            "items": data.get("items", []),
            "subtotal": subtotal,
            "tax": tax,
            "tip": tip,
            "total": total,
            "payment_method": payment or None,
            "category": category,
            "currency": currency,
        }

        # Check for duplicate using edited (user-corrected) data
        dup_receipt = mgr.check_duplicate(edited_data)

        # Duplicate warning with side-by-side comparison
        if dup_receipt:
            dup_date = dup_receipt.date
            try:
                dup_date = date.fromisoformat(str(dup_date)).strftime("%m/%d/%Y")
            except (ValueError, TypeError):
                dup_date = dup_date or "?"
            st.warning(f"Possible duplicate: {dup_receipt.merchant_name} — ${dup_receipt.total:.2f} — {dup_date}")
            col_new, col_existing = st.columns(2)
            with col_new:
                st.markdown("**New (this receipt)**")
                st.dataframe(
                    pd.DataFrame([
                        {"Field": "Merchant", "Value": edited_data.get("merchant_name", "")},
                        {"Field": "Date", "Value": edited_data.get("date", "")},
                        {"Field": "Total", "Value": f"${edited_data.get('total', 0):.2f}"},
                        {"Field": "Tax", "Value": f"${edited_data.get('tax', 0):.2f}"},
                        {"Field": "Payment", "Value": edited_data.get("payment_method") or "—"},
                        {"Field": "Category", "Value": edited_data.get("category", "")},
                    ]),
                    hide_index=True, width="stretch",
                )
            with col_existing:
                st.markdown("**Existing receipt**")
                existing_date = dup_receipt.date
                if existing_date:
                    try:
                        existing_date = date.fromisoformat(str(existing_date)).strftime("%m/%d/%Y")
                    except (ValueError, TypeError):
                        pass
                st.dataframe(
                    pd.DataFrame([
                        {"Field": "Merchant", "Value": dup_receipt.merchant_name},
                        {"Field": "Date", "Value": existing_date or "—"},
                        {"Field": "Total", "Value": f"${dup_receipt.total:.2f}"},
                        {"Field": "Tax", "Value": f"${dup_receipt.tax or 0:.2f}"},
                        {"Field": "Payment", "Value": dup_receipt.payment_method or "—"},
                        {"Field": "Category", "Value": dup_receipt.category},
                    ]),
                    hide_index=True, width="stretch",
                )
                if dup_receipt.file_path and Path(dup_receipt.file_path).exists():
                    _show_image(dup_receipt.file_path)

        # Show success message from dialog approval
        if st.session_state.pop("_dup_approved_msg", None):
            pass  # rerun after dialog will clear the staged receipt

        # Check if this is a valid receipt (LLM flag + minimum required data)
        is_valid = data.get("is_valid_receipt", False)
        has_valid_data = is_valid or bool(merchant and total)

        if not has_valid_data:
            st.error("This does not appear to be a receipt. You can reject it or re-analyze.")

        # Action buttons (ordered: Copy JSON, Reject, Re-analyze, Approve & Save)
        if has_valid_data:
            c_copy, c_reject, c_reanalyze, c_approve = st.columns([1, 1, 1, 1])
        else:
            c_copy, c_reject, c_reanalyze = st.columns([1, 1, 1])
        with c_copy:
            _copy_json_button(edited_data, key_prefix)
        with c_reject:
            if st.button("Reject", key=f"{key_prefix}_reject"):
                mgr.reject(staging_id)
                st.info("Receipt rejected")
                st.rerun()
        with c_reanalyze:
            if st.button("Re-analyze", key=f"{key_prefix}_reanalyze"):
                with st.spinner("Re-analyzing..."):
                    result = mgr.reanalyze(staging_id)
                if result.get("error"):
                    st.error(result["error"])
                else:
                    if key_prefix == "upload":
                        st.session_state["last_staging_id"] = result.get("staging_id")
                        st.session_state["last_result"] = result
                    st.success("Re-analysis complete")
                    st.rerun()
        if has_valid_data:
            with c_approve:
                if st.button("Approve & Save", key=f"{key_prefix}_approve", type="primary"):
                    if dup_receipt:
                        _confirm_duplicate_approve(staging_id, edited_data)
                    else:
                        mgr.update_staged(staging_id, edited_data)
                        receipt_id = mgr.approve(staging_id)
                    st.success(f"Saved as receipt #{receipt_id}")
                    st.rerun()



# ── Tab 1: Upload ──
with tab_upload:
    if "uploader_key" not in st.session_state:
        st.session_state["uploader_key"] = 0
    uploaded_file = st.file_uploader(
        "Upload a receipt (image or PDF)",
        type=["png", "jpg", "jpeg", "heic", "heif", "pdf"],
        key=f"uploader_{st.session_state['uploader_key']}",
    )
    if uploaded_file and st.button("Analyze Receipt"):
        save_path = UPLOAD_DIR / uploaded_file.name
        save_path.write_bytes(uploaded_file.getbuffer())

        with st.spinner("Analyzing receipt..."):
            result = mgr.analyze(str(save_path))

        if result.get("error"):
            st.error(result["error"])
        else:
            st.session_state["last_staging_id"] = result["staging_id"]
            st.session_state["last_result"] = result

    # Show review form for just-uploaded receipt
    if st.session_state.get("last_staging_id"):
        staging_id = st.session_state["last_staging_id"]
        staged = mgr.get_staged(staging_id)
        if staged:
            result = st.session_state.get("last_result", {})
            orig = result.get("original_size_bytes", 0)
            sent = result.get("sent_size_bytes", 0)
            if orig:
                orig_mb = orig / 1_000_000
                sent_mb = sent / 1_000_000
                if orig != sent:
                    st.caption(f"Original: {orig_mb:.1f} MB → Sent: {sent_mb:.1f} MB")
                else:
                    st.caption(f"Size: {orig_mb:.1f} MB (no resize needed)")

            st.info("Review the extracted data below. Edit if needed, then approve or reject.")
            _render_review_form(staged, "upload")
        else:
            # Already approved/rejected — clear state and reset uploader
            st.session_state.pop("last_staging_id", None)
            st.session_state.pop("last_result", None)
            st.session_state["uploader_key"] += 1
            st.rerun()

# ── Tab 2: Pending Review ──
with tab_pending:
    st.button("Refresh", key="pending_refresh")

    pending = mgr.get_pending()
    # Exclude the receipt currently shown on the Upload tab
    upload_sid = st.session_state.get("last_staging_id")
    if upload_sid:
        pending = [s for s in pending if s["staging_id"] != upload_sid]
    if not pending:
        st.info("No receipts pending review.")
    else:
        for i, staged in enumerate(pending):
            sid = staged["staging_id"]
            data = staged["extracted_data"]
            raw_date = data.get("date", "")
            try:
                display_date = date.fromisoformat(raw_date).strftime("%m/%d/%Y")
            except (ValueError, TypeError):
                display_date = raw_date or "?"
            total_val = data.get("total")
            total_str = f"${float(total_val):.2f}" if total_val is not None else "$?.??"
            label = f"{data.get('merchant_name', 'Unknown')} — {total_str} — {display_date}"
            with st.expander(label, expanded=(i == 0)):
                _render_review_form(staged, f"pending_{sid}")

# ── Tab 3: Expenses Table ──
with tab_expenses:
    with st.form("expense_filters"):
        col1, col2, col3, col4 = st.columns(4)
        with col1:
            start = st.date_input("From", value=date.today() - timedelta(days=30), key="exp_start", format="MM/DD/YYYY")
        with col2:
            end = st.date_input("To", value=date.today(), key="exp_end", format="MM/DD/YYYY")
        with col3:
            all_cats = sorted(set(DEFAULT_CATEGORIES + get_categories()))
            cat = st.selectbox("Category", ["All"] + all_cats, key="exp_cat")
        with col4:
            merchant = st.text_input("Merchant", key="exp_merchant")
        searched = st.form_submit_button("Search")

    if searched:
        st.session_state["_exp_has_results"] = True
    if st.session_state.get("_exp_has_results"):
        receipts = mgr.query(
            start_date=str(start) if start else None,
            end_date=str(end) if end else None,
            category=cat if cat != "All" else None,
            merchant=merchant or None,
        )

        if receipts:
            st.session_state["_exp_receipts"] = {r.id: r for r in receipts}
            df = pd.DataFrame(
                [
                    {
                        "ID": r.id,
                        "Date": (date.fromisoformat(str(r.date)).strftime("%m/%d/%Y") if r.date else "—"),
                        "Merchant": r.merchant_name,
                        "Category": r.category,
                        "Tax": r.tax,
                        "Total": r.total,
                        "Payment": r.payment_method,
                    }
                    for r in receipts
                ]
            )
            event = st.dataframe(
                df, width="stretch", hide_index=True,
                on_select="rerun", selection_mode="single-row",
            )

            # Show detail dialog when a row is selected
            if event.selection and event.selection.rows:
                selected_idx = event.selection.rows[0]
                r = receipts[selected_idx]
                _show_receipt_detail(r)
        else:
            st.session_state.pop("_exp_has_results", None)
            st.info("No receipts found.")

# ── Tab 4: Summary Stats ──
with tab_summary:
    col1, col2 = st.columns(2)
    with col1:
        s_start = st.date_input(
            "Summary from", value=date.today() - timedelta(days=30), key="s_start", format="MM/DD/YYYY"
        )
    with col2:
        s_end = st.date_input("Summary to", value=date.today(), key="s_end", format="MM/DD/YYYY")

    stats = mgr.get_summary(str(s_start), str(s_end))

    m1, m2, m3 = st.columns(3)
    m1.metric("Total Spent", f"${stats['total_spent']:.2f}")
    m2.metric("Total Tax", f"${stats['total_tax']:.2f}")
    m3.metric("Receipts", stats["receipt_count"])

    if stats["by_category"]:
        st.subheader("Spending by Category")
        cat_df = pd.DataFrame(
            [{"Category": k, "Amount": v} for k, v in stats["by_category"].items()]
        )
        st.bar_chart(cat_df.set_index("Category"))
