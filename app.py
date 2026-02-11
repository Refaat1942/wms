import streamlit as st
import pandas as pd
import io
from datetime import datetime, timedelta

# ======================================================
# 1. إعدادات المشرف (Admin Config)
# ======================================================
ADMIN_PASSWORD = "123" 

st.set_page_config(page_title="WMS - لجنة التحضير الذكية", layout="wide")

# ======================================================
# 2. تحسين المظهر (CSS Styling)
# ======================================================
st.markdown("""
    <style>
    /* تكبير خانة السكانر */
    .stTextInput > div > div > input {
        font-size: 22px !important;
        height: 55px !important;
        border: 2px solid #4CAF50 !important;
        text-align: center;
    }
    /* تنسيق الجدول */
    .stDataFrame { direction: rtl; }
    /* محاولة إخفاء القيم المزعجة بصرياً */
    [data-testid="stDataFrame"] td { font-family: 'Arial'; }
    </style>
    """, unsafe_allow_html=True)

# ======================================================
# 3. دوال المعالجة (Logic Helpers)
# ======================================================
def clean_po_data(df):
    """تنظيف البيانات وإزالة القيم الفارغة NaN"""
    # تنظيف أسماء الأعمدة
    df.columns = [str(c).strip() for c in df.columns]
    
    # خريطة الأعمدة
    rename_map = {
        'Material': 'Code', 
        'Short Text': 'Name', 
        'Order Quantity': 'Required'
    }
    
    # التأكد من وجود الأعمدة
    for col in rename_map.keys():
        if col not in df.columns:
            st.error(f"❌ العمود '{col}' ناقص في الملف!")
            return None

    # اختيار وتسمية الأعمدة
    df = df[list(rename_map.keys())].rename(columns=rename_map)
    
    # معالجة القيم الفارغة (NaN Removal)
    df['Code'] = df['Code'].astype(str).str.split('.').str[0].str.strip()
    df['Name'] = df['Name'].fillna("").astype(str)
    # تحويل الكميات لأرقام
    df['Required'] = pd.to_numeric(df['Required'], errors='coerce').fillna(0).astype(int)
    
    return df

def parse_barcode_sap(text):
    """معادلة التواريخ (SAP Logic: 01.01.2000 + days)"""
    text = str(text).strip()
    
    # المعادلة: الكود.عدد الأيام
    if '.' in text:
        try:
            parts = text.split('.')
            mat_code = parts[0].strip()
            days_diff = int(parts[1])
            
            # معادلة ساب: 01.01.2000 + عدد الأيام
            base_date = datetime(2000, 1, 1)
            # تم استخدام days_diff - 1 لضبط الحساب كما في الكود القديم
            expiry_date = (base_date + timedelta(days=days_diff - 1)).strftime("%d/%m/%Y")
            
            return mat_code, expiry_date
        except:
            # في حالة الفشل نرجع الكود فقط وبدون تاريخ
            return text.split('.')[0], ""
    
    return text, ""

# ======================================================
# 4. إدارة الحالة (Session State)
# ======================================================
if 'po_df' not in st.session_state:
    st.session_state.po_df = None
if 'scanned_data' not in st.session_state:
    st.session_state.scanned_data = {} # {Code: Quantity}
if 'expiry_map' not in st.session_state:
    st.session_state.expiry_map = {} # {Code: Last_Expiry_Date}
if 'expiry_log' not in st.session_state:
    st.session_state.expiry_log = []
if 'auth_required' not in st.session_state:
    st.session_state.auth_required = False
if 'pending_scan' not in st.session_state:
    st.session_state.pending_scan = None

# ======================================================
# 5. الواجهة والتشغيل
# ======================================================
st.title("📦 نظام التحضير الآمن")

# --- القائمة الجانبية ---
with st.sidebar:
    st.header("⚙️ التحكم")
    uploaded_file = st.file_uploader("رفع ملف PO", type=['xlsx'])
    
    if uploaded_file and st.session_state.po_df is None:
        try:
            df_raw = pd.read_excel(uploaded_file, engine='openpyxl')
            st.session_state.po_df = clean_po_data(df_raw)
            st.success("✅ تم التحميل بنجاح")
        except Exception as e:
            st.error(f"خطأ في الملف: {e}")

    if st.button("🔴 إنهاء ومسح الكل"):
        st.session_state.clear()
        st.rerun()

# --- الشاشة الرئيسية ---
if st.session_state.po_df is not None:

    # 1. منطق التخويل (Admin Auth Dialog)
    if st.session_state.auth_required:
        st.warning("⚠️ الكمية المطلوبة اكتملت! مطلوب إذن مشرف للزيادة.")
        col_pass, col_btn = st.columns([3, 1])
        password_input = col_pass.text_input("Admin Password", type="password", key="auth_pass")
        
        if col_btn.button("موافقة"):
            if password_input == ADMIN_PASSWORD:
                # تنفيذ العملية المعلقة
                mat_to_add = st.session_state.pending_scan['mat']
                exp_to_add = st.session_state.pending_scan['exp']
                
                # الزيادة الجبرية وتحديث التاريخ
                st.session_state.scanned_data[mat_to_add] = st.session_state.scanned_data.get(mat_to_add, 0) + 1
                if exp_to_add: # تحديث التاريخ فقط لو موجود
                    st.session_state.expiry_map[mat_to_add] = exp_to_add
                
                st.session_state.expiry_log.append({
                    "Code": mat_to_add, "Expiry": exp_to_add, "Time": datetime.now().strftime("%H:%M:%S"), "Note": "Over-delivery (Authorized)"
                })
                
                st.success(f"تمت الزيادة بتصريح مشرف للصنف {mat_to_add}")
                st.session_state.auth_required = False
                st.session_state.pending_scan = None
                st.rerun()
            else:
                st.error("❌ كلمة المرور غير صحيحة")
        
        if st.button("إلغاء"):
            st.session_state.auth_required = False
            st.session_state.pending_scan = None
            st.rerun()

    else:
        # 2. خانة السكانر
        barcode = st.text_input("👇 اسحب الباركود هنا", key="scanner_input", placeholder="Scan Barcode...")

        if barcode:
            mat_id, exp_date = parse_barcode_sap(barcode)
            
            # التحقق من وجود الصنف
            if mat_id in st.session_state.po_df['Code'].values:
                # التحقق من الكمية
                required_qty = st.session_state.po_df.loc[st.session_state.po_df['Code'] == mat_id, 'Required'].values[0]
                current_qty = st.session_state.scanned_data.get(mat_id, 0)
                
                if current_qty < required_qty:
                    # سماح بالمسح الطبيعي
                    st.session_state.scanned_data[mat_id] = current_qty + 1
                    # حفظ تاريخ الصلاحية في الجدول الرئيسي
                    if exp_date:
                        st.session_state.expiry_map[mat_id] = exp_date
                        
                    st.session_state.expiry_log.append({
                        "Code": mat_id, "Expiry": exp_date, "Time": datetime.now().strftime("%H:%M:%S"), "Note": "Normal"
                    })
                    st.toast(f"✅ تم: {mat_id}", icon="📦")
                else:
                    # طلب تفويض للإضافة الزائدة
                    st.session_state.auth_required = True
                    st.session_state.pending_scan = {'mat': mat_id, 'exp': exp_date}
                    st.rerun()
            else:
                st.error(f"❌ الصنف {mat_id} غير موجود في الـ PO")

    # 3. عرض الجدول المحسن
    st.divider()
    
    # تجهيز الداتا للعرض
    df_display = st.session_state.po_df.copy()
    
    # جلب الكميات المسحوبة
    df_display['Scanned'] = df_display['Code'].map(st.session_state.scanned_data).fillna(0).astype(int)
    
    # جلب تاريخ الصلاحية
    df_display['Expiry Date'] = df_display['Code'].map(st.session_state.expiry_map).fillna("")

    df_display['Remaining'] = df_display['Required'] - df_display['Scanned']
    
    # تحديد الحالة للتلوين
    def get_status(row):
        scanned = row['Scanned']
        required = row['Required']
        if scanned == 0: return "Pending"
        if scanned < required: return "In Progress"
        if scanned == required: return "Completed"
        return "Over Delivered"

    df_display['Status'] = df_display.apply(get_status, axis=1)

    # تنظيف الأصفار (تحويل الأصفار لنصوص فارغة للعرض فقط)
    # ملاحظة: هذا للعرض فقط حتى لا يؤثر على الحسابات
    df_show = df_display.copy()
    df_show['Scanned'] = df_show['Scanned'].replace(0, "")
    df_show['Remaining'] = df_show['Remaining'].replace(0, "")
    
    # دالة التلوين
    def highlight_rows(row):
        color = ''
        status = row['Status'] # نستخدم الحالة من البيانات الأصلية
        if status == 'Completed':
            color = 'background-color: #d4edda; color: #155724;' 
        elif status == 'Over Delivered':
            color = 'background-color: #f8d7da; color: #721c24;' 
        elif status == 'In Progress':
            color = 'background-color: #fff3cd; color: #856404;' 
        
        return [color] * len(row)

    st.subheader("📋 تقرير التحضير اللحظي")
    
    # ترتيب الأعمدة للعرض
    cols_to_show = ['Code', 'Name', 'Expiry Date', 'Required', 'Scanned', 'Remaining', 'Status']
    
    st.dataframe(
        df_show[cols_to_show].style.apply(highlight_rows, axis=1),
        use_container_width=True,
        height=500
    )

    # 4. التصدير (Excel)
    c1, c2 = st.columns(2)
    with c1:
        if st.button("💾 تحميل شيت الفروقات"):
            output = io.BytesIO()
            with pd.ExcelWriter(output, engine='openpyxl') as writer:
                # تصدير البيانات الأصلية (بالأرقام وليس الفراغات)
                df_display.to_excel(writer, index=False, sheet_name='Summary')
                if st.session_state.expiry_log:
                    pd.DataFrame(st.session_state.expiry_log).to_excel(writer, index=False, sheet_name='Details')
            
            st.download_button(
                label="📥 تنزيل Excel",
                data=output.getvalue(),
                file_name="WMS_Final_Report.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
            )

else:
    st.info("👈 يرجى رفع ملف الـ PO للبدء")