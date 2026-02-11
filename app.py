import streamlit as st
import pandas as pd
import io
from logic_helpers import clean_po_data, parse_barcode

st.set_page_config(page_title="Lotus Preparation", layout="wide")

# --- تهيئة المخزن المؤقت (Session State) ---
if 'po_df' not in st.session_state:
    st.session_state.po_df = None
if 'scanned_data' not in st.session_state:
    st.session_state.scanned_data = {} # {material_id: {total: 0, expiries: {}}}

# --- الواجهة ---
st.title("📦 نظام لجنة التحضير")

# 1. رفع ملف الـ PO
uploaded_file = st.sidebar.file_uploader("ارفع ملف الـ PO (Excel)", type=['xlsx'])

if uploaded_file and st.session_state.po_df is None:
    raw_df = pd.read_excel(uploaded_file)
    st.session_state.po_df = clean_po_data(raw_df)
    st.sidebar.success("تم تحميل البيانات!")

if st.session_state.po_df is not None:
    # 2. خانة السكانر (التركيز الأساسي للهاند هيلد)
    barcode_input = st.text_input("👇 اسحب الباركود هنا (Scanner)", key="barcode_field")

    if barcode_input:
        mat_id, exp_date = parse_barcode(barcode_input)
        
        # التأكد أن الصنف موجود في الملف المرفوع
        if str(mat_id) in st.session_state.po_df['Material'].astype(str).values:
            # تحديث الكميات
            if mat_id not in st.session_state.scanned_data:
                st.session_state.scanned_data[mat_id] = {"total": 0, "expiries": {}}
            
            st.session_state.scanned_data[mat_id]["total"] += 1
            st.session_state.scanned_data[mat_id]["expiries"][exp_date] = \
                st.session_state.scanned_data[mat_id]["expiries"].get(exp_date, 0) + 1
            
            st.toast(f"✅ تم مسح: {mat_id}", icon="🔥")
        else:
            st.error(f"❌ الصنف {mat_id} غير موجود في أمر التحضير!")

    # 3. عرض الجدول الحي
    st.subheader("📊 حالة التحضير الحالية")
    
    display_df = st.session_state.po_df.copy()
    display_df['Scanned'] = display_df['Material'].astype(str).apply(
        lambda x: st.session_state.scanned_data.get(x, {}).get('total', 0)
    )
    display_df['Difference'] = display_df['Required'] - display_df['Scanned']
    
    # تلوين الصفوف (اختياري)
    st.dataframe(display_df, use_container_width=True)

    # 4. التصدير (Export)
    st.divider()
    if st.button("💾 استخراج تقرير التحضير النهائي"):
        output = io.BytesIO()
        with pd.ExcelWriter(output, engine='openpyxl') as writer:
            display_df.to_excel(writer, index=False, sheet_name='Summary')
            # إضافة تفاصيل التواريخ في شيت منفصل
            exp_list = []
            for m, data in st.session_state.scanned_data.items():
                for d, q in data['expiries'].items():
                    exp_list.append({"Material": m, "Expiry": d, "Qty": q})
            pd.DataFrame(exp_list).to_excel(writer, index=False, sheet_name='Expiry_Details')
        
        st.download_button(
            label="اضغط هنا لتحميل ملف Excel",
            data=output.getvalue(),
            file_name=f"Prep_Report_{uploaded_file.name}",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        )

    if st.sidebar.button("🗑 مسح البيانات والبدء من جديد"):
        st.session_state.po_df = None
        st.session_state.scanned_data = {}
        st.rerun()