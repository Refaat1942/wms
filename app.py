import streamlit as st
import pandas as pd
import io
from datetime import datetime, timedelta

# ======================================================
# 1. إعدادات الصفحة
# ======================================================
st.set_page_config(page_title="WMS - لجنة التحضير", layout="wide")

# تكبير الخطوط والخانة عشان الهاند هيلد يشوف كويس
st.markdown("""
    <style>
    .stTextInput > div > div > input { font-size: 24px !important; height: 60px !important; }
    .stMetric { font-size: 20px !important; }
    div[data-testid="stDataFrameResizable"] { direction: rtl; }
    </style>
    """, unsafe_allow_html=True)

# ======================================================
# 2. دوال المنطق (Logic)
# ======================================================
def clean_po_data(df):
    """تنظيف البيانات بناءً على أعمدة الشيت بتاعك بالظبط"""
    
    # 1. تنظيف أسماء الأعمدة من المسافات الزايدة
    df.columns = [str(c).strip() for c in df.columns]
    
    # 2. اختيار الأعمدة المهمة فقط وإعادة تسميتها عشان الكود يفهمها
    # Material -> كود الصنف
    # Short Text -> اسم الصنف
    # Order Quantity -> الكمية المطلوبة
    
    required_cols = {
        'Material': 'Material', 
        'Short Text': 'Description', 
        'Order Quantity': 'Required'
    }
    
    # التأكد إن الأعمدة دي موجودة
    for col in required_cols.keys():
        if col not in df.columns:
            st.error(f"❌ العمود '{col}' مش موجود في الملف! تأكد من الشيت.")
            return None

    # فلترة الجدول واختيار الأعمدة دي بس
    df = df[list(required_cols.keys())].rename(columns=required_cols)
    
    # 3. تنظيف البيانات جوه الجدول
    # تحويل الكود لنص عشان ميبقاش فيه كسور (مثلاً 100.0 تبقى 100)
    df['Material'] = df['Material'].astype(str).str.split('.').str[0].str.strip()
    
    # تحويل الكمية لرقم صحيح
    df['Required'] = pd.to_numeric(df['Required'], errors='coerce').fillna(0).astype(int)
    
    return df

def parse_barcode(text):
    """فك الباركود (الكود + التاريخ)"""
    text = str(text).strip()
    # لو الباركود فيه نقطة (نظام ساب للتواريخ)
    if '.' in text:
        parts = text.split('.')
        try:
            # حساب التاريخ
            days = int(parts[1])
            date = (datetime(2000, 1, 1) + timedelta(days=days - 1)).strftime("%d/%m/%Y")
            return parts[0].strip(), date
        except:
            return parts[0].strip(), "Invalid Date"
    
    # لو باركود عادي مفيهوش تاريخ
    return text, "No Date"

# ======================================================
# 3. إدارة الجلسة (Session State)
# ======================================================
if 'po_df' not in st.session_state:
    st.session_state.po_df = None
if 'scanned_data' not in st.session_state:
    st.session_state.scanned_data = {} # {mat_id: count}
if 'expiry_log' not in st.session_state:
    st.session_state.expiry_log = []

# ======================================================
# 4. واجهة التطبيق
# ======================================================
st.title("📦 سيستم التحضير - Handheld")

# --- القائمة الجانبية (للرفع والمسح) ---
with st.sidebar:
    st.header("⚙️ العمليات")
    uploaded_file = st.file_uploader("📂 ارفع شيت الـ PO", type=['xlsx', 'xls'])
    
    if uploaded_file and st.session_state.po_df is None:
        try:
            # قراءة الملف
            df_raw = pd.read_excel(uploaded_file, engine='openpyxl')
            clean_df = clean_po_data(df_raw)
            
            if clean_df is not None:
                st.session_state.po_df = clean_df
                st.success("✅ تم التحميل!")
        except Exception as e:
            st.error(f"❌ الملف فيه مشكلة: {e}")

    if st.button("🗑️ تصفير العدادات (بدء جديد)", type="primary"):
        st.session_state.po_df = None
        st.session_state.scanned_data = {}
        st.session_state.expiry_log = []
        st.rerun()

# --- الشاشة الرئيسية ---
if st.session_state.po_df is not None:
    
    # 1. خانة السكانر (أهم حاجة)
    st.markdown("### 👇 اسحب الباركود هنا")
    barcode = st.text_input("Scanner Input", key="scanner_input", label_visibility="collapsed", placeholder="Focus here & Scan...")

    # منطق المسح
    if barcode:
        mat_id, exp_date = parse_barcode(barcode)
        
        # البحث عن الصنف في الجدول
        # بنحول العمود لـ list ونبحث فيه عشان نضمن الدقة
        available_mats = st.session_state.po_df['Material'].unique().tolist()
        
        if mat_id in available_mats:
            # زيادة العدد
            current_qty = st.session_state.scanned_data.get(mat_id, 0)
            st.session_state.scanned_data[mat_id] = current_qty + 1
            
            # تسجيل التاريخ
            st.session_state.expiry_log.append({
                "Material": mat_id,
                "Expiry": exp_date,
                "Time": datetime.now().strftime("%H:%M:%S")
            })
            
            st.toast(f"✅ تم سحب الصنف: {mat_id}", icon="📦")
        else:
            st.error(f"⚠️ الصنف {mat_id} مش موجود في الطلبية دي!")

    st.divider()

    # 2. جدول المتابعة (Live)
    # بنعمل نسخة للعرض عشان متبوظش الأصل
    display_df = st.session_state.po_df.copy()
    
    # دالة بسيطة تجيب العدد اللي اتسحب
    def get_scanned_qty(m):
        return st.session_state.scanned_data.get(str(m), 0)
    
    display_df['Scanned'] = display_df['Material'].apply(get_scanned_qty)
    display_df['Remaining'] = display_df['Required'] - display_df['Scanned']
    
    # ترتيب الأعمدة للعرض
    display_df = display_df[['Material', 'Description', 'Required', 'Scanned', 'Remaining']]
    
    # عرض الجدول (الأصناف اللي لسه مخلصتش تيجي في الأول)
    display_df = display_df.sort_values(by='Remaining', ascending=False)
    
    st.subheader("📊 حالة التحضير (المتبقي)")
    st.dataframe(
        display_df.style.apply(lambda x: ['background: #d4edda' if v == 0 else '' for v in x], subset=['Remaining']), 
        use_container_width=True, 
        height=400
    )

    # 3. زر التحميل (Export)
    st.markdown("### 💾 استخراج النتائج")
    if st.button("تحميل ملف الإكسيل النهائي"):
        output = io.BytesIO()
        with pd.ExcelWriter(output, engine='openpyxl') as writer:
            display_df.to_excel(writer, index=False, sheet_name='Final_Report')
            if st.session_state.expiry_log:
                pd.DataFrame(st.session_state.expiry_log).to_excel(writer, index=False, sheet_name='Expiry_Dates')
        
        st.download_button(
            label="📥 تنزيل الملف (Excel)",
            data=output.getvalue(),
            file_name=f"WMS_Report_{datetime.now().strftime('%H%M')}.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        )

else:
    st.info("👈 من فضلك ارفع ملف الـ PO من القائمة الجانبية.")