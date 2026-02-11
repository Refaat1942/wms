import streamlit as st
import pandas as pd
import io
from datetime import datetime, timedelta

# ======================================================
# 1. إعدادات وتنسيق الصفحة
# ======================================================
ADMIN_PASSWORD = "123" 
st.set_page_config(page_title="WMS - Smart PO Loader", layout="wide")

st.markdown("""
    <style>
    /* تكبير خانة السكانر */
    .stTextInput > div > div > input {
        font-size: 20px !important;
        height: 60px !important;
        border: 2px solid #4CAF50 !important;
        text-align: center;
        border-radius: 10px;
    }
    .stDataFrame { direction: rtl; }
    #MainMenu {visibility: hidden;}
    footer {visibility: hidden;}
    </style>
    """, unsafe_allow_html=True)

# ======================================================
# 2. دوال مساعدة (Helpers)
# ======================================================
def clean_po_data(df):
    """تجهيز ملف الـ PO واستخراج رقمه"""
    # تنظيف أسماء الأعمدة من المسافات الزائدة
    df.columns = [str(c).strip() for c in df.columns]
    
    # 1. محاولة استخراج رقم الـ PO من عمود Purchasing Document
    po_number = None
    # احتمالات لاسم العمود (الأكثر شيوعاً في SAP)
    target_cols = ['Purchasing Document', 'Purch.Doc.', 'PO Number']
    
    for col in target_cols:
        if col in df.columns:
            # نأخذ القيمة من أول صف ونحولها لنص
            val = df[col].iloc[0]
            if pd.notna(val):
                po_number = str(val).strip()
            break
    
    # 2. التأكد من باقي الأعمدة الأساسية
    rename_map = {'Material': 'Code', 'Short Text': 'Name', 'Order Quantity': 'Required'}
    
    for col in rename_map.keys():
        if col not in df.columns:
            return None, None, f"العمود {col} ناقص في الملف!"

    # 3. تنظيف الداتا
    df_clean = df[list(rename_map.keys())].rename(columns=rename_map)
    df_clean['Code'] = df_clean['Code'].astype(str).str.split('.').str[0].str.strip()
    df_clean['Name'] = df_clean['Name'].fillna("").astype(str)
    df_clean['Required'] = pd.to_numeric(df_clean['Required'], errors='coerce').fillna(0).astype(int)
    
    return df_clean, po_number, None

def parse_barcode_sap(text):
    """تحليل الباركود وتاريخ الصلاحية"""
    text = str(text).strip()
    if '.' in text:
        try:
            parts = text.split('.')
            mat_code = parts[0].strip()
            days_diff = int(parts[1])
            base_date = datetime(2000, 1, 1)
            expiry_date = (base_date + timedelta(days=days_diff - 1)).strftime("%d/%m/%Y")
            return mat_code, expiry_date
        except:
            return text.split('.')[0], ""
    return text, ""

# ======================================================
# 3. إدارة الحالة (Session State Database)
# ======================================================
if 'pos_db' not in st.session_state:
    st.session_state.pos_db = {} 

if 'active_po' not in st.session_state:
    st.session_state.active_po = None 

if 'auth_required' not in st.session_state:
    st.session_state.auth_required = False
if 'pending_scan' not in st.session_state:
    st.session_state.pending_scan = None

# رسائل التنبيه
if 'msg_success' not in st.session_state:
    st.session_state.msg_success = None
if 'msg_error' not in st.session_state:
    st.session_state.msg_error = None

# ======================================================
# 4. دالة السكانر (Callback)
# ======================================================
def process_scan():
    """معالجة الباركود للملف النشط حالياً"""
    barcode = st.session_state.scanner_input
    active_po_name = st.session_state.active_po

    if not barcode or not active_po_name:
        return

    current_db = st.session_state.pos_db[active_po_name]
    mat_id, exp_date = parse_barcode_sap(barcode)

    # هل الصنف موجود؟
    if mat_id in current_db['df']['Code'].values:
        required_qty = current_db['df'].loc[current_db['df']['Code'] == mat_id, 'Required'].values[0]
        current_qty = current_db['scanned'].get(mat_id, 0)

        if current_qty < required_qty:
            current_db['scanned'][mat_id] = current_qty + 1
            if exp_date:
                current_db['expiry'][mat_id] = exp_date
            
            current_db['log'].append({
                "Code": mat_id, "Expiry": exp_date, "Time": datetime.now().strftime("%H:%M:%S"), "Note": "Normal"
            })
            st.session_state.msg_success = f"✅ {mat_id}"
        else:
            st.session_state.auth_required = True
            st.session_state.pending_scan = {'mat': mat_id, 'exp': exp_date, 'po': active_po_name}
    else:
        st.session_state.msg_error = f"❌ غير موجود في {active_po_name}"

    st.session_state.scanner_input = ""

# ======================================================
# 5. الواجهة والقوائم الجانبية
# ======================================================
st.title("📦 نظام إدارة الـ PO الذكي")

# عرض الرسائل
if st.session_state.msg_success:
    st.toast(st.session_state.msg_success, icon="📦")
    st.session_state.msg_success = None
if st.session_state.msg_error:
    st.error(st.session_state.msg_error)
    st.session_state.msg_error = None

with st.sidebar:
    st.header("🗂️ إدارة الملفات")
    
    # 1. رفع ملف جديد
    uploaded_file = st.file_uploader("➕ إضافة PO جديد", type=['xlsx'], key="file_uploader")
    
    if uploaded_file:
        # قراءة الملف مرة واحدة فقط عند الرفع
        try:
            df_raw = pd.read_excel(uploaded_file, engine='openpyxl')
            df_clean, extracted_po_num, error_msg = clean_po_data(df_raw)
            
            if df_clean is not None:
                # تحديد الاسم النهائي: لو لقينا رقم PO نستخدمه، لو ملقيناش نستخدم اسم الملف
                final_name = extracted_po_num if extracted_po_num else uploaded_file.name
                
                if final_name in st.session_state.pos_db:
                    st.warning(f"⚠️ الـ PO رقم {final_name} موجود بالفعل!")
                else:
                    st.session_state.pos_db[final_name] = {
                        'df': df_clean,
                        'scanned': {},
                        'expiry': {},
                        'log': []
                    }
                    st.session_state.active_po = final_name
                    st.success(f"تم تحميل PO: {final_name}")
                    st.rerun()
            else:
                st.error(error_msg)
        except Exception as e:
            st.error(f"حدث خطأ في قراءة الملف: {e}")

    st.divider()

    # 2. القائمة المنسدلة (تظهر بأسماء الـ PO الآن)
    if st.session_state.pos_db:
        po_list = list(st.session_state.pos_db.keys())
        
        index = 0
        if st.session_state.active_po in po_list:
            index = po_list.index(st.session_state.active_po)
            
        selected_po = st.selectbox("📂 اختر أمر الشراء:", po_list, index=index)
        
        # تحديث الاختيار فقط لو اتغير
        if selected_po != st.session_state.active_po:
            st.session_state.active_po = selected_po
            st.rerun()
        
        # زر الحذف
        col_del, col_space = st.columns([1, 2])
        if col_del.button("🗑️ حذف"):
            del st.session_state.pos_db[selected_po]
            st.session_state.active_po = None
            st.rerun()
    else:
        st.info("لا توجد ملفات مفتوحة.")

# ======================================================
# 6. منطقة العمل الرئيسية
# ======================================================

if st.session_state.active_po and st.session_state.active_po in st.session_state.pos_db:
    current_po_data = st.session_state.pos_db[st.session_state.active_po]
    
    # --- أ. معالجة طلب الباسورد ---
    if st.session_state.auth_required:
        st.warning(f"⚠️ زيادة كمية في الملف: {st.session_state.pending_scan['po']}")
        c_pass, c_btn = st.columns([3, 1])
        pwd = c_pass.text_input("كلمة مرور المشرف", type="password", key="admin_pass")
        
        if c_btn.button("موافقة"):
            if pwd == ADMIN_PASSWORD:
                p_scan = st.session_state.pending_scan
                target_db = st.session_state.pos_db[p_scan['po']]
                
                target_db['scanned'][p_scan['mat']] = target_db['scanned'].get(p_scan['mat'], 0) + 1
                if p_scan['exp']:
                    target_db['expiry'][p_scan['mat']] = p_scan['exp']
                
                target_db['log'].append({
                    "Code": p_scan['mat'], "Expiry": p_scan['exp'], "Time": datetime.now().strftime("%H:%M:%S"), "Note": "Over-delivery (Authorized)"
                })
                
                st.session_state.auth_required = False
                st.session_state.pending_scan = None
                st.success("تم التصريح")
                st.rerun()
            else:
                st.error("كلمة المرور خطأ")
        
        if st.button("إلغاء"):
            st.session_state.auth_required = False
            st.session_state.pending_scan = None
            st.rerun()

    else:
        # --- ب. خانة السكانر ---
        st.subheader(f"رقم الملف: {st.session_state.active_po}")
        
        st.text_input(
            "👇 اسحب الباركود", 
            key="scanner_input", 
            on_change=process_scan
        )

        # --- ج. عرض الجدول ---
        df_display = current_po_data['df'].copy()
        
        df_display['Scanned'] = df_display['Code'].map(current_po_data['scanned']).fillna(0).astype(int)
        df_display['Expiry'] = df_display['Code'].map(current_po_data['expiry']).fillna("")
        df_display['Remaining'] = df_display['Required'] - df_display['Scanned']
        
        def get_status(row):
            if row['Scanned'] == 0: return "Pending"
            if row['Scanned'] < row['Required']: return "In Progress"
            if row['Scanned'] == row['Required']: return "Completed"
            return "Over Delivered"

        df_display['Status'] = df_display.apply(get_status, axis=1)

        # تنظيف العرض
        df_show = df_display.copy()
        df_show['Scanned'] = df_show['Scanned'].replace(0, "")
        df_show['Remaining'] = df_show['Remaining'].replace(0, "")

        def highlight_rows(row):
            color = ''
            if row['Status'] == 'Completed': color = 'background-color: #d4edda'
            elif row['Status'] == 'Over Delivered': color = 'background-color: #f8d7da'
            elif row['Status'] == 'In Progress': color = 'background-color: #fff3cd'
            return [color] * len(row)

        st.dataframe(
            df_show[['Code', 'Name', 'Expiry', 'Required', 'Scanned', 'Remaining', 'Status']].style.apply(highlight_rows, axis=1),
            use_container_width=True,
            height=450
        )

        # --- د. التصدير ---
        if st.button(f"💾 تحميل تقرير {st.session_state.active_po}"):
            output = io.BytesIO()
            with pd.ExcelWriter(output, engine='openpyxl') as writer:
                df_display.to_excel(writer, index=False, sheet_name='Summary')
                if current_po_data['log']:
                    pd.DataFrame(current_po_data['log']).to_excel(writer, index=False, sheet_name='Logs')
            
            st.download_button(
                label="📥 تنزيل الملف",
                data=output.getvalue(),
                file_name=f"Report_{st.session_state.active_po}.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
            )

else:
    st.info("👈 قم برفع ملف PO من القائمة الجانبية للبدء")