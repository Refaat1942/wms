import sys
sys.coinit_flags = 0 

import customtkinter as ctk
from tkinter import filedialog, messagebox
import pandas as pd
import qrcode
import os
import json
import glob
from datetime import datetime, timedelta
import win32com.client
import subprocess
import time
import re # مكتبة للتعامل مع النصوص بذكاء

# ==========================================
# ⚙️ إعدادات الاتصال بالساب
# ==========================================
SAP_USERNAME = "area2"
SAP_PASSWORD = "Lotus@16310"
SAP_CONNECTION_NAME = "S4 Out"
# ==========================================

ctk.set_appearance_mode("Dark")
ctk.set_default_color_theme("dark-blue")

DB_FOLDER = "PO_Database"
if not os.path.exists(DB_FOLDER): os.makedirs(DB_FOLDER)

class SAPHandler:
    def __init__(self):
        self.session = None

    def connect_and_login(self):
        try:
            try:
                SapGuiAuto = win32com.client.GetObject("SAPGUI")
                application = SapGuiAuto.GetScriptingEngine
                if application.Children.Count > 0:
                    connection = application.Children(0)
                    if connection.Children.Count > 0:
                        self.session = connection.Children(0)
                        try:
                            _ = self.session.Info.ScreenNumber
                            return True, "Connected"
                        except: pass
            except: pass 

            print("Starting SAP Logon...")
            try:
                sap_path = r"C:\Program Files (x86)\SAP\FrontEnd\SAPgui\saplogon.exe"
                if not os.path.exists(sap_path):
                     sap_path = r"C:\Program Files\SAP\FrontEnd\SAPgui\saplogon.exe"
                subprocess.Popen(sap_path)
                time.sleep(5)
            except:
                return False, "Could not find saplogon.exe"

            try:
                SapGuiAuto = win32com.client.GetObject("SAPGUI")
                application = SapGuiAuto.GetScriptingEngine
                print(f"Connecting to {SAP_CONNECTION_NAME}...")
                connection = application.OpenConnection(SAP_CONNECTION_NAME, True)
                time.sleep(3)
                self.session = connection.Children(0)

                self.session.findById("wnd[0]/usr/txtRSYST-BNAME").text = SAP_USERNAME
                self.session.findById("wnd[0]/usr/pwdRSYST-BCODE").text = SAP_PASSWORD
                self.session.findById("wnd[0]").sendVKey(0)
                time.sleep(2)
                
                return True, "Logged in"
            except Exception as e:
                return False, f"Login Failed: {e}"

        except Exception as e:
            return False, f"Critical: {e}"

    def run_me2l_and_auto_export(self, po_number):
        try:
            self.session.findById("wnd[0]/tbar[0]/okcd").text = "/nME2L"
            self.session.findById("wnd[0]").sendVKey(0)
            time.sleep(1)

            found = False
            try:
                self.session.findById("wnd[0]/usr/ctxtS_EBELN-LOW").text = po_number
                found = True
            except:
                try: 
                    user_area = self.session.findById("wnd[0]/usr")
                    for i in range(user_area.Children.Count):
                        child = user_area.Children(i)
                        if "EBELN" in child.Id and "TextField" in child.Type:
                            child.text = po_number
                            found = True
                            break
                except: pass
            
            if not found:
                 try: self.session.findById("wnd[0]/usr/ctxtEBELN-LOW").text = po_number
                 except: pass

            try: self.session.findById("wnd[0]/usr/ctxtP_LSTUB").text = "ALV" 
            except: pass
            
            self.session.findById("wnd[0]/tbar[1]/btn[8]").press() 
            time.sleep(1.5)

            self.session.sendCommand("%PC") 
            time.sleep(1)

            try:
                self.session.findById("wnd[1]/usr/subSUBSCREEN_STEPLOOP:SAPLSPO5:0150/sub:SAPLSPO5:0150/radSPOPLI-SELFLAG[1,0]").select()
            except: pass
            
            self.session.findById("wnd[1]/tbar[0]/btn[0]").press() 
            time.sleep(1)

            export_path = os.getcwd()
            export_filename = "auto_sap_export.txt"
            full_path = os.path.join(export_path, export_filename)

            try:
                self.session.findById("wnd[1]/usr/ctxtDY_PATH").text = export_path
                self.session.findById("wnd[1]/usr/ctxtDY_FILENAME").text = export_filename
                self.session.findById("wnd[1]/tbar[0]/btn[11]").press() 
            except:
                try: self.session.findById("wnd[1]/tbar[0]/btn[0]").press()
                except: pass

            time.sleep(1) 
            return full_path

        except Exception as e: 
            print(f"Script Error: {e}")
            return None

class WarehouseApp(ctk.CTk):
    def __init__(self):
        super().__init__()
        self.title(f"WMS - Smart Import & Auto Fetch")
        self.geometry("1400x850")
        
        self.sap = SAPHandler()
        self.current_po_data = None
        self.current_po_id = None
        self.scanned_details = {} 

        self.grid_columnconfigure(1, weight=1)
        self.grid_rowconfigure(0, weight=1)

        # === Sidebar ===
        self.sidebar = ctk.CTkFrame(self, width=280, corner_radius=0)
        self.sidebar.grid(row=0, column=0, sticky="nsew")
        ctk.CTkLabel(self.sidebar, text="📦 SAVED POs", font=("Arial", 20, "bold")).pack(pady=20)
        ctk.CTkButton(self.sidebar, text="🔄 Refresh List", command=self.load_saved_pos_list, fg_color="#555").pack(pady=5)
        self.po_list_frame = ctk.CTkScrollableFrame(self.sidebar)
        self.po_list_frame.pack(fill="both", expand=True, padx=10, pady=10)

        # === Main Area ===
        self.main_area = ctk.CTkFrame(self, fg_color="transparent")
        self.main_area.grid(row=0, column=1, sticky="nsew", padx=10, pady=10)
        self.main_area.grid_columnconfigure(0, weight=1)
        self.main_area.grid_rowconfigure(2, weight=1)

        # Top Stats
        self.top_frame = ctk.CTkFrame(self.main_area)
        self.top_frame.grid(row=0, column=0, sticky="ew", pady=5)
        self.lbl_status = ctk.CTkLabel(self.top_frame, text="READY", font=("Arial", 24, "bold"), text_color="gray")
        self.lbl_status.pack(pady=5)
        
        self.metrics_frame = ctk.CTkFrame(self.top_frame, fg_color="#2B2B2B")
        self.metrics_frame.pack(fill="x", padx=10, pady=5)
        self.metrics_frame.columnconfigure((0,1,2,3), weight=1)
        self.lbl_metrics = [self.create_metric(self.metrics_frame, t, "0", i) for i, t in enumerate(["Total", "Scanned", "Remain", "Progress"])]

        # Inputs
        self.input_frame = ctk.CTkFrame(self.main_area, fg_color="transparent")
        self.input_frame.grid(row=1, column=0, sticky="ew", pady=5)
        
        self.entry_scan = ctk.CTkEntry(self.input_frame, width=300, placeholder_text="Scan Item...", font=("Arial", 16))
        self.entry_scan.pack(side="left", padx=5)
        self.entry_scan.bind('<Return>', self.on_scan_enter)
        
        self.btn_sap = ctk.CTkButton(self.input_frame, text="🚀 Auto Fetch PO", command=self.sap_import_auto, fg_color="#E67E22", text_color="black", font=("Arial", 14, "bold"), width=160)
        self.btn_sap.pack(side="left", padx=5)

        # زر الرفع الذكي (يقرأ ساب أو إكسيل محفوظ)
        self.btn_upload = ctk.CTkButton(self.input_frame, text="📂 Import (SAP/Excel)", command=self.admin_upload_process, fg_color="#2C3E50", width=150)
        self.btn_upload.pack(side="right", padx=5)
        self.btn_export = ctk.CTkButton(self.input_frame, text="💾 Export", command=self.export_report, fg_color="green", state="disabled", width=80)
        self.btn_export.pack(side="right", padx=5)

        # === Table Area ===
        self.table_frame = ctk.CTkScrollableFrame(self.main_area)
        self.table_frame.grid(row=2, column=0, sticky="nsew", pady=5)
        
        self.load_saved_pos_list()

    def create_metric(self, parent, title, val, col):
        f = ctk.CTkFrame(parent, fg_color="transparent")
        f.grid(row=0, column=col, pady=5)
        ctk.CTkLabel(f, text=title, text_color="gray").pack()
        l = ctk.CTkLabel(f, text=val, font=("Arial", 18, "bold"))
        l.pack()
        return l

    def load_saved_pos_list(self):
        for w in self.po_list_frame.winfo_children(): w.destroy()
        files = sorted(glob.glob(f"{DB_FOLDER}/*.json"), key=os.path.getmtime, reverse=True)
        for f in files:
            try:
                d = json.load(open(f))
                po_id = d.get('po_id', 'Unknown')
                row_frame = ctk.CTkFrame(self.po_list_frame, fg_color="transparent")
                row_frame.pack(fill="x", pady=2)
                btn = ctk.CTkButton(row_frame, text=po_id, command=lambda p=f: self.load_po_session(p), 
                                  fg_color="#333", height=35, anchor="w")
                btn.pack(side="left", fill="x", expand=True, padx=(0, 5))
                del_btn = ctk.CTkButton(row_frame, text="❌", width=35, height=35, 
                                      fg_color="#C0392B", hover_color="#922B21",
                                      command=lambda p=f: self.delete_po(p))
                del_btn.pack(side="right")
            except: pass

    def delete_po(self, file_path):
        if messagebox.askyesno("Confirm Delete", "Are you sure you want to delete this PO?"):
            try:
                os.remove(file_path)
                qr_path = f"QR_{os.path.basename(file_path).replace('.json', '')}.png"
                if os.path.exists(qr_path): os.remove(qr_path)
                self.load_saved_pos_list()
                if self.current_po_id and self.current_po_id in file_path:
                    self.current_po_data = None
                    self.current_po_id = None
                    self.lbl_status.configure(text="READY", text_color="gray")
                    for w in self.table_frame.winfo_children(): w.destroy()
            except Exception as e:
                messagebox.showerror("Error", f"Failed to delete: {e}")

    # ==========================
    # 🔥 الاستيراد الذكي (Excel & SAP) 🔥
    # ==========================
    def admin_upload_process(self, default_po=None):
        file_path = filedialog.askopenfilename(filetypes=[("Excel/SAP/Text", "*.xlsx *.xls *.MHTML *.HTML *.csv *.txt")])
        if not file_path: return

        try:
            # محاولة قراءة الملف كـ Excel أولاً
            try:
                df = pd.read_excel(file_path)
            except:
                # لو فشل، نجرب CSV/Text (صيغة الساب)
                try:
                    df = pd.read_csv(file_path, sep='\t', encoding='utf-16', on_bad_lines='skip')
                except:
                    df = pd.read_csv(file_path, sep='\t', encoding='utf-8', on_bad_lines='skip')
            
            # تنظيف أسماء الأعمدة
            df.columns = df.columns.str.strip()

            # 🛑 فحص: هل هذا الملف هو "Report" تم تصديره من البرنامج؟ (يحتوي على بيانات مسح سابقة)
            # المميز هنا هو وجود عمود "Scanned Qty" أو "Scanned Expiry Details"
            is_restore_file = any(col in df.columns for col in ["Scanned Qty", "Scanned Expiry Details"])
            
            if is_restore_file:
                # ✅ استعادة جلسة عمل سابقة
                self.restore_po_from_excel_report(df, file_path)
            else:
                # ✅ استيراد جديد (SAP Raw Data)
                self.import_new_sap_file(df, file_path)

        except Exception as e:
            messagebox.showerror("Error", f"Failed to load file: {e}")

    def restore_po_from_excel_report(self, df, original_path):
        """ دالة ذكية لاستعادة البيانات من ملف الإكسيل المصدّر """
        try:
            po_id = os.path.basename(original_path).split('.')[0]
            # تنظيف الاسم من كلمة Report_ لو موجودة
            po_id = po_id.replace("Report_", "")
            
            restored_items = []
            
            for _, row in df.iterrows():
                # قراءة البيانات الأساسية
                mat = str(row.get('Material', '')).strip()
                desc = row.get('Description', 'No Desc')
                req_qty = int(row.get('Required Qty', 0))
                po_exp = row.get('PO Expiry', '-')
                scanned_qty = int(row.get('Scanned Qty', 0))
                
                # استعادة تفاصيل التواريخ من النص
                # النص المتوقع: "[12/12/2025: 5 pcs], [01/01/2026: 3 pcs]"
                exp_details_str = str(row.get('Scanned Expiry Details', ''))
                exp_dict = {}
                
                if exp_details_str and exp_details_str.lower() != 'nan':
                    # استخدام Regex لاستخراج التواريخ والكميات بدقة
                    matches = re.findall(r'\[(.*?):\s*(\d+)\s*pcs\]', exp_details_str)
                    for date_str, qty_str in matches:
                        exp_dict[date_str] = int(qty_str)

                # بناء هيكل البيانات
                restored_items.append({
                    'Material': mat,
                    'Material Description': desc,
                    'PO Quantity': req_qty,
                    'Expiry': po_exp,
                    'Scanned': scanned_qty, # قيمة استرشادية، سيتم حسابها من القاموس
                    'expiry_details': exp_dict
                })
            
            # حفظ كملف JSON جديد
            data = {"po_id": po_id, "items": restored_items}
            json_path = os.path.join(DB_FOLDER, f"{po_id}.json")
            with open(json_path, 'w') as f:
                json.dump(data, f, default=str)
            
            # إعادة توليد QR إذا لزم الأمر
            qr = qrcode.make(po_id)
            qr.save(f"QR_{po_id}.png")
            
            messagebox.showinfo("Restored", f"Successfully restored PO: {po_id}")
            self.load_saved_pos_list()
            self.load_po_session(json_path)
            
        except Exception as e:
            messagebox.showerror("Restore Error", f"Could not restore from Excel: {e}")

    def import_new_sap_file(self, df, file_path):
        """ معالجة ملف ساب عادي جديد """
        rename_map = {}
        for col in df.columns:
            c_lower = str(col).lower()
            if "material" in c_lower and "desc" not in c_lower: rename_map[col] = "Material"
            if "material" in c_lower and "desc" in c_lower: rename_map[col] = "Material Description"
            if "short text" in c_lower: rename_map[col] = "Material Description"
            if "quantity" in c_lower or "qty" in c_lower: rename_map[col] = "PO Quantity"
            if "expiry" in c_lower or "sled" in c_lower or "batch" in c_lower: rename_map[col] = "Expiry"

        df.rename(columns=rename_map, inplace=True)

        if 'Material' not in df.columns:
            messagebox.showerror("Error", "Invalid Columns. Could not find Material column.")
            return

        df['Material'] = df['Material'].astype(str).str.replace(r'\.0$', '', regex=True)
        df['PO Quantity'] = pd.to_numeric(df['PO Quantity'], errors='coerce').fillna(0).astype(int)
        if 'Material Description' not in df.columns: df['Material Description'] = "No Description"
        if 'Expiry' not in df.columns: df['Expiry'] = "-"

        df = df[df['PO Quantity'] > 0]
        
        # إنشاء اسم فريد
        filename = os.path.basename(file_path).split('.')[0]
        unique_id = f"{filename}__{datetime.now().strftime('%d-%m')}"
        
        data = {"po_id": unique_id, "items": df[['Material', 'Material Description', 'PO Quantity', 'Expiry']].to_dict('records')}
        
        json_path = os.path.join(DB_FOLDER, f"{unique_id}.json")
        with open(json_path, 'w') as f:
            json.dump(data, f, default=str)
        
        qr = qrcode.make(unique_id)
        qr.save(f"QR_{unique_id}.png")
        
        self.load_saved_pos_list()
        self.load_po_session(json_path)
        messagebox.showinfo("Success", "New PO Imported Successfully")

    # ==========================
    # بقية الوظائف الأساسية
    # ==========================
    def build_table(self):
        for w in self.table_frame.winfo_children(): w.destroy()
        cols = ["Material", "Description", "Req", "Scan", "Diff", "PO Expiry", "Scanned Expiry"]
        
        self.table_frame.grid_columnconfigure(0, weight=0, minsize=80)
        self.table_frame.grid_columnconfigure(1, weight=1, minsize=200)
        self.table_frame.grid_columnconfigure(2, weight=0, minsize=50)
        self.table_frame.grid_columnconfigure(3, weight=0, minsize=50)
        self.table_frame.grid_columnconfigure(4, weight=0, minsize=50)
        self.table_frame.grid_columnconfigure(5, weight=0, minsize=100)
        self.table_frame.grid_columnconfigure(6, weight=0, minsize=150)

        for i, c in enumerate(cols): 
            ctk.CTkLabel(self.table_frame, text=c, font=("Arial", 14, "bold"), text_color="#FFA500").grid(row=0, column=i, padx=5, pady=5, sticky="w")
        
        for idx, i in enumerate(self.current_po_data, 1):
            mat = str(i['Material'])
            desc = str(i.get('Material Description', 'No Desc'))
            req_qty = int(i['PO Quantity'])
            
            scan_data = self.scanned_details.get(mat, {'Total':0, 'Expiries':{}})
            scanned_qty = scan_data['Total']
            diff = req_qty - scanned_qty
            
            po_expiry_date = i.get('Expiry', '-') 
            scanned_exp_list = [f"{date} ({qty})" for date, qty in scan_data['Expiries'].items()]
            scanned_exp_str = " | ".join(scanned_exp_list) if scanned_exp_list else ""

            row_color = "white"
            if scanned_qty == req_qty: row_color = "#2ECC71"
            elif scanned_qty > req_qty: row_color = "#E74C3C"
            elif scanned_qty > 0: row_color = "#F1C40F"
            
            diff_color = "#E74C3C" if diff > 0 else "#2ECC71"

            ctk.CTkLabel(self.table_frame, text=mat, font=("Arial", 12)).grid(row=idx, column=0, padx=5, pady=2, sticky="w")
            ctk.CTkLabel(self.table_frame, text=desc[:40], font=("Arial", 12)).grid(row=idx, column=1, padx=5, pady=2, sticky="w")
            ctk.CTkLabel(self.table_frame, text=str(req_qty), font=("Arial", 12, "bold")).grid(row=idx, column=2, padx=5, pady=2)
            ctk.CTkLabel(self.table_frame, text=str(scanned_qty), font=("Arial", 12, "bold"), text_color=row_color).grid(row=idx, column=3, padx=5, pady=2)
            ctk.CTkLabel(self.table_frame, text=str(diff), font=("Arial", 12, "bold"), text_color=diff_color).grid(row=idx, column=4, padx=5, pady=2)
            ctk.CTkLabel(self.table_frame, text=po_expiry_date, text_color="gray").grid(row=idx, column=5, padx=5, pady=2, sticky="w")
            ctk.CTkLabel(self.table_frame, text=scanned_exp_str, text_color="#3498DB", font=("Arial", 11)).grid(row=idx, column=6, padx=5, pady=2, sticky="w")

    def sap_import_auto(self):
        dialog = ctk.CTkInputDialog(text="Enter SAP PO Number:", title="Auto Fetch")
        po_number = dialog.get_input()
        if not po_number: return
        success, msg = self.sap.connect_and_login()
        if not success:
             messagebox.showerror("Error", f"Connection Failed: {msg}")
             return
        file_path = self.sap.run_me2l_and_auto_export(po_number)
        if file_path and os.path.exists(file_path):
            try:
                df = pd.read_csv(file_path, sep='\t', encoding='utf-16', on_bad_lines='skip')
            except:
                df = pd.read_csv(file_path, sep='\t', encoding='utf-8', on_bad_lines='skip')
            self.import_new_sap_file(df, file_path)
            try: os.remove(file_path)
            except: pass
        else:
            messagebox.showerror("Error", "Automation failed.")

    def parse_barcode(self, raw_text):
        text = str(raw_text).strip()
        if '.' not in text: return text, "No Date"
        parts = text.split('.')
        try:
            days_diff = int(parts[1])
            date = (datetime(2000, 1, 1) + timedelta(days=days_diff - 1)).strftime("%d/%m/%Y")
            return parts[0], date
        except: return text, "Invalid"

    def on_scan_enter(self, event):
        t = self.entry_scan.get().strip()
        self.entry_scan.delete(0, 'end')
        if t: self.process_input(t)

    def process_input(self, text):
        path = os.path.join(DB_FOLDER, f"{text}.json")
        if os.path.exists(path): self.load_po_session(path)
        elif self.current_po_data:
            mat, date = self.parse_barcode(text)
            self.update_item(mat, date)
        else: messagebox.showwarning("Warning", "Load PO first")

    def load_po_session(self, path):
        try:
            self.current_file_path = path
            d = json.load(open(path))
            self.current_po_data = d['items']
            self.current_po_id = d['po_id']
            self.scanned_details = {}
            for i in self.current_po_data:
                mat = str(i['Material']).split('.')[0]
                exp = i.get('expiry_details', {})
                # لو البيانات جاية من استعادة إكسيل، نحسب المجموع
                total_scan = sum(exp.values()) if exp else int(i.get('Scanned', 0))
                self.scanned_details[mat] = {'Total': total_scan, 'Expiries': exp if exp else {}}
            
            self.lbl_status.configure(text=f"PO: {self.current_po_id}", text_color="#3498DB")
            self.btn_export.configure(state="normal")
            self.build_table()
            self.update_dashboard()
        except Exception as e: messagebox.showerror("Error", str(e))

    def update_item(self, mat, date):
        if mat in self.scanned_details:
            self.scanned_details[mat]['Total'] += 1
            self.scanned_details[mat]['Expiries'][date] = self.scanned_details[mat]['Expiries'].get(date, 0) + 1
            self.build_table()
            self.update_dashboard()
            self.save_progress()
        else: messagebox.showerror("Error", f"Material {mat} not in this PO")

    def update_dashboard(self):
        req = sum(int(i['PO Quantity']) for i in self.current_po_data)
        scan = sum(d['Total'] for d in self.scanned_details.values())
        self.lbl_metrics[0].configure(text=str(req))
        self.lbl_metrics[1].configure(text=str(scan))
        self.lbl_metrics[2].configure(text=str(req-scan))
        self.lbl_metrics[3].configure(text=f"{int(scan/req*100) if req else 0}%")

    def save_progress(self):
        for i in self.current_po_data:
            mat = str(i['Material'])
            if mat in self.scanned_details:
                i['Scanned'] = self.scanned_details[mat]['Total']
                i['expiry_details'] = self.scanned_details[mat]['Expiries']
        json.dump({"po_id": self.current_po_id, "items": self.current_po_data}, open(self.current_file_path, 'w'), default=str)

    def export_report(self):
        if not self.current_po_data: return
        save_path = filedialog.asksaveasfilename(defaultextension=".xlsx", initialfile=f"Report_{self.current_po_id}.xlsx")
        if not save_path: return
        export_data = []
        for mat, info in self.scanned_details.items():
            desc = "Unknown"
            req = 0
            po_exp = "-"
            for i in self.current_po_data:
                if str(i['Material']).split('.')[0] == mat:
                    desc = i['Material Description']
                    req = i['PO Quantity']
                    po_exp = i.get('Expiry', '-')
                    break
            
            exp_str = ", ".join([f"[{k}: {v} pcs]" for k, v in info['Expiries'].items()])
            
            export_data.append({
                "Material": mat, 
                "Description": desc, 
                "Required Qty": req,
                "Scanned Qty": info['Total'], 
                "Difference": req - info['Total'],
                "PO Expiry": po_exp,
                "Scanned Expiry Details": exp_str,
                "Status": "Complete" if info['Total'] >= req else "Pending"
            })
        pd.DataFrame(export_data).to_excel(save_path, index=False)
        messagebox.showinfo("Done", "Export Saved!")
        os.startfile(save_path)

if __name__ == "__main__":
    app = WarehouseApp()
    app.mainloop()