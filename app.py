import streamlit as st
import pandas as pd
import io
from datetime import datetime, timedelta

# ======================================================
# إعدادات الصفحة
# ======================================================
st.set_page_config(page_title="لوتس - لجنة التحضير", layout="wide")

# استايل خاص للهاند هيلد عشان الكلام يبقى واضح
st.markdown("""
    <style>
    .stTextInput > div > div > input { font-size: 25px !important; height: 60px !important; }
    [data-testid="stMetricValue"] { font-size: 30px; }
    </style>
    """, unsafe_allow_html=True)

# ======================================================
# دوال المنطق (Logic)
# ======================================================
def clean_po_data(df):
    """تنظيف الأعمدة وتوحيد الأسماء"""
    df.columns = [str(c).strip() for c in df.columns]
    rename_map = {}
    for col in df.columns:
        c_low = col.lower()
        if 'material' in c_low and 'desc' not in c_low: rename_map[col] = 'Material'
        if 'desc' in c_low or 'short text' in c_low: rename_map[col] = 'Description'
        if 'qty' in c_low or 'quantity' in c_low: rename_map[col] = 'Required'
    
    df.rename(columns=rename_map, inplace=True)
    
    # تحويل كود الصنف لنص (String) وتوحيد شكله
    if 'Material' in df.columns:
        df['Material'] = df['Material'].astype(str).str.split('.').str[0].str.strip()
    
    # التأكد من أن عمود المطلوب أرقام
    if 'Required' in df.columns:
        df['Required'] = pd.to_numeric(df['Required'], errors='coerce').fillna(0).astype(int)
        
    return df

def parse_barcode(text):
    """فك الباركود بنظام النقطة"""
    text = str(text).strip()
    if '.' not in text:
        return text, "No Date"
    parts = text.split('.')
    try:
        days_diff = int(parts[1])
        date = (datetime(2000, 1, 1) + timedelta(days=days_diff - 1)).strftime("%d/%m/%Y")
        return parts[0].strip(), date
    except:
        return parts[0].strip(), "Invalid"

# ======================================================
# إدارة الجلسة (Session State)
# ======================================================
if 'po_df' not in st.session_state:
    st.session_state.po_df = None
if 'scanned_data' not in st.session_state:
    st.session_state.scanned_data = {} # {mat_id: count}
if 'expiry_log' not in st.session_state:
    st.session_state.expiry_log = []

# ======================================================
# الواجهة (UI)
# ======================================================
st.title("📦 محضر لجنة التحضير الذكي")

# القائمة الجانبية
with st.sidebar:
    st.header("📂 إدارة الملفات")
    uploaded_file = st.file_uploader("ارفع ملف الـ PO", type=['xlsx', 'xls', 'csv'])
    
    if uploaded_file and st.session_state.po_df is None:
        try:
            if uploaded_file.name.endswith('.csv'):
                df_raw = pd.read_csv(uploaded_file)
            else:
                df_raw = pd.read_excel(uploaded_file, engine='openpyxl')
            
            st.session_state.po_df = clean_po_data(df_raw)
            st.success("✅ تم تحميل البيانات!")
        except Exception as e:
            st.error(f"خطأ في قراءة الملف: {e}")

    if st.button("🗑 مسح كل البيانات والبدء مجدداً"):
        for key in ['po_df', 'scanned_data', 'expiry_log']:
            st.session_state[key] = None if key == 'po_df' else ({} if key == 'scanned_data' else [])
        st.rerun()

# منطقة العمل الرئيسية
if st.session_state.po_df is not None:
    # إحصائيات سريعة
    total_items = len(st.session_state.po_df)
    scanned_count = len(st.session_state.scanned_data)
    
    c1, c2 = st.columns(2)
    c1.metric("إجمالي الأصناف", total_items)
    c2.metric("أصناف تم مسحها", scanned_count)

    # خانة السكانر
    barcode = st.text_input("👇 وجه الليزر هنا وابدأ المسح", key="scanner_input")

    if barcode:
        mat_id, exp_date = parse_barcode(barcode)
        
        # التأكد من وجود الصنف في الملف (البحث في النص الموحد)
        if mat_id in st.session_state.po_df['Material'].values:
            # زيادة العدد
            st.session_state.scanned_data[mat_id] = st.session_state.scanned_data.get(mat_id, 0) + 1
            # إضافة سجل التاريخ
            st.session_state.expiry_log.append({
                "Material": mat_id,
                "Expiry": exp_date,
                "Time": datetime.now().strftime("%H:%M:%S")
            })
            st.toast(f"✅ تم تسجيل صنف: {mat_id}", icon="🚀")
        else:
            st.error(f"❌ الصنف {mat_id} مش موجود في الملف ده!")

    # عرض الجدول ومعالجة الفروقات
    st.divider()
    
    # بناء جدول العرض بأمان لتجنب خطأ الـ apply
    display_df = st.session_state.po_df.copy()
    
    # دالة جلب الكمية بأمان
    def get_count(m_id):
        return st.session_state.scanned_data.get(str(m_id), 0)

    display_df['Scanned'] = display_df['Material'].apply(get_count)
    display_df['Difference'] = display_df['Required'] - display_df['Scanned']

    st.subheader("📋 كشف المتابعة")
    st.dataframe(display_df, use_container_width=True, hide_index=True)

    # التصدير
    if st.button("💾 تحميل تقرير الفروقات (Excel)"):
        output = io.BytesIO()
        with pd.ExcelWriter(output, engine='openpyxl') as writer:
            display_df.to_excel(writer, index=False, sheet_name='Summary')
            pd.DataFrame(st.session_state.expiry_log).to_excel(writer, index=False, sheet_name='Log')
        
        st.download_button(
            label="اضغط هنا لتحميل الملف",
            data=output.getvalue(),
            file_name=f"Prep_Report_{datetime.now().strftime('%m%d_%H%M')}.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        )
else:
    st.info("قم برفع ملف الـ PO من القائمة الجانبية للبدء.")