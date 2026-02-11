import pandas as pd
from datetime import datetime, timedelta

def clean_po_data(df):
    # تنظيف أسماء الأعمدة من المسافات
    df.columns = [str(c).strip() for c in df.columns]
    
    # خريطة لتوحيد المسميات (Material, Description, Qty)
    rename_map = {}
    for col in df.columns:
        c_low = col.lower()
        if 'material' in c_low and 'desc' not in c_low: rename_map[col] = 'Material'
        if 'desc' in c_low or 'text' in c_low: rename_map[col] = 'Description'
        if 'qty' in c_low or 'quantity' in c_low: rename_map[col] = 'Required'
    
    df.rename(columns=rename_map, inplace=True)
    
    # التأكد من وجود الأعمدة الأساسية
    for col in ['Material', 'Description', 'Required']:
        if col not in df.columns:
            df[col] = 0 if col == 'Required' else "N/A"
            
    return df

def parse_barcode(text):
    """يفك الباركود إذا كان يحتوي على تاريخ صلاحية (نظام النقطة)"""
    text = str(text).strip()
    if '.' not in text:
        return text, "No Date"
    parts = text.split('.')
    try:
        # تحويل الرقم بعد النقطة لتاريخ (نظام ساب)
        days_diff = int(parts[1])
        date = (datetime(2000, 1, 1) + timedelta(days=days_diff - 1)).strftime("%d/%m/%Y")
        return parts[0], date
    except:
        return parts[0], "Invalid"