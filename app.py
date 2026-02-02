import streamlit as st
import pandas as pd
import qrcode
from PIL import Image, ImageDraw, ImageFont
import io
import uuid
import os
import zipfile
from datetime import datetime
import base64
import re

# ตั้งค่าหน้าแอป
st.set_page_config(page_title="TicketStudio", layout="wide")

def sanitize_filename(name):
    """
    Sanitize string to be safe for use as a filename.
    Prevents path traversal and removes illegal characters.
    """
    # Remove leading/trailing directory indicators and null bytes
    name = os.path.basename(name).strip()
    # Allow Thai characters (\u0E00-\u0E7F), alphanumeric, spaces, dashes, underscores
    # Remove everything else
    safe_name = re.sub(r'[^\w\s\-\u0E00-\u0E7F]', '', name)
    return safe_name if safe_name else "untitled"

def format_phone_number(phone):
    if pd.isna(phone) or not str(phone).strip():
        return ""
    
    # แปลงเป็น string และจัดการกรณี float จาก Excel (เช่น 810000001.0)
    s = str(phone).strip()
    if s.endswith('.0'):
        s = s[:-2]
        
    # ลบอักขระที่ไม่ใช่ตัวเลขออกทั้งหมด
    digits = re.sub(r'\D', '', s)
    
    # ถ้ามี 9 หลัก ให้เติม 0 ข้างหน้า (กรณี Excel ตัดเลข 0)
    if len(digits) == 9:
        digits = "0" + digits
        
    if len(digits) == 10:
        return f"{digits[:3]}-{digits[3:6]}-{digits[6:]}"
    return str(phone)

def get_base64_font(font_path):
    if os.path.exists(font_path):
        with open(font_path, "rb") as f:
            return base64.b64encode(f.read()).decode()
    return None

font_reg_data = get_base64_font(os.path.join("assets", "fonts", "NotoSansThai-Regular.ttf"))
font_bold_data = get_base64_font(os.path.join("assets", "fonts", "NotoSansThai-Bold.ttf"))

if font_reg_data and font_bold_data:
    st.markdown(f"""
        <style>
        @font-face {{
            font-family: 'Noto Sans Thai';
            src: url(data:font/ttf;base64,{font_reg_data}) format('truetype');
            font-weight: 400;
            font-style: normal;
        }}
        @font-face {{
            font-family: 'Noto Sans Thai';
            src: url(data:font/ttf;base64,{font_bold_data}) format('truetype');
            font-weight: 700;
            font-style: normal;
        }}
        * {{
            font-family: 'Noto Sans Thai', sans-serif !important;
        }}
        /* บังคับให้หัวข้อหรือตัวหนาใช้ Weight 700 */
        b, strong, h1, h2, h3 {{ font-weight: 700 !important; }}
        
        /* Brighten Dark Mode (~25%) */
        .stApp {{
            background-color: #707070 !important;
        }}
        [data-testid="stSidebar"] {{
            background-color: #30303022 !important;
        }}
        [data-testid="stHeader"] {{
            background-color: rgba(84, 84, 84, 0.7) !important;
        }}

        .block-container {{
            padding: 40px !important;
        }}
        </style>
        """, unsafe_allow_html=True)
else:
    st.markdown("""
        <style>
        @import url('https://fonts.googleapis.com/css2?family=Noto+Sans+Thai:wght@100..900&display=swap');
        * {
            font-family: 'Noto Sans Thai', sans-serif !important;
        }
        /* Brighten Dark Mode (~25%) */
        .stApp {
            background-color: #A3A3A3 !important;
        }
        [data-testid="stSidebar"] {
            background-color: #A3A3A3 !important;
        }
        [data-testid="stHeader"] {
            background-color: rgba(37, 41, 49, 0.7) !important;
        }

        .block-container {
            padding: 40px !important;
        }
        </style>
        """, unsafe_allow_html=True)

# แสดงโลโก้จากไฟล์ SVG
logo_path = "assets/logo_tick.svg"
if os.path.exists(logo_path):
    with open(logo_path, "rb") as f:
        logo_svg = base64.b64encode(f.read()).decode()
        st.markdown(
            f'<img src="data:image/svg+xml;base64,{logo_svg}" width="200" height="83" style="margin-bottom: 10px; margin-top: 5px; padding: 9px -5px; filter: drop-shadow(0px 0px 6px rgba(252, 190, 76, 1));">',
            unsafe_allow_html=True
        )
else:
    st.markdown('<h1><span style="color: gray;">Ticket</span><span style="color: #FFBF00; font-weight: 400;">Studio</span></h1>', unsafe_allow_html=True)

# -----------------------------
# 0) Helper Functions & Persistence
# -----------------------------
STORAGE_DIR = "project_data"
if not os.path.exists(STORAGE_DIR):
    os.makedirs(STORAGE_DIR)

def save_project_data(name, df):
    file_path = os.path.join(STORAGE_DIR, f"{name}.csv")
    df.to_csv(file_path, index=False, encoding='utf-8-sig')

def load_project_data(name):
    file_path = os.path.join(STORAGE_DIR, f"{name}.csv")
    if os.path.exists(file_path):
        return pd.read_csv(file_path, encoding='utf-8-sig')
    return None

@st.cache_resource
def get_font(font_path, size, fallback=True):
    try:
        return ImageFont.truetype(font_path, size)
    except:
        if not fallback:
            return None
        # พยายามหาฟอนต์สำรองในระบบถ้าไม่พบไฟล์ที่ระบุ
        fallbacks = ["arial.ttf", "Tahoma.ttf", "Helvetica.ttf"]
        for f in fallbacks:
            try:
                return ImageFont.truetype(f, size)
            except:
                continue
        return None # คืนค่า None เพื่อให้ฟังก์ชันวาดรู้ว่าต้องจัดการแบบไม่มีฟอนต์

# -----------------------------
# 1) เตรียม Session State
# -----------------------------
if "projects" not in st.session_state:
    # โหลดโปรเจกต์ที่มีอยู่ใน Local Storage ขึ้นมาอัตโนมัติ
    existing_projects = [f.replace(".csv", "") for f in os.listdir(STORAGE_DIR) if f.endswith(".csv")]
    st.session_state.projects = {p: load_project_data(p) for p in existing_projects}

if "current_project" not in st.session_state:
    st.session_state.current_project = None

if "templates" not in st.session_state:
    st.session_state.templates = {}

# -----------------------------
# 2) ส่วนเลือก/สร้างโปรเจ็กต์ (สูงสุด 5)
# -----------------------------
st.sidebar.header("จัดการโปรเจ็กต์")

project_names = list(st.session_state.projects.keys())
selected = st.sidebar.selectbox(
    "เลือกโปรเจ็กต์", ["(สร้างโปรเจ็กต์ใหม่)"] + project_names
)

if selected == "(สร้างโปรเจ็กต์ใหม่)":
    new_name = st.sidebar.text_input("ชื่อโปรเจ็กต์ใหม่")
    if st.sidebar.button("สร้างโปรเจ็กต์"):
        if not new_name:
            st.sidebar.warning("กรุณากรอกชื่อโปรเจ็กต์")
        else:
            # Sanitize the input name
            safe_name = sanitize_filename(new_name)
            if not safe_name or safe_name != new_name:
                st.sidebar.warning(f"ชื่อโปรเจ็กต์ไม่ถูกต้อง หรือมีอักขระต้องห้าม แนะนำ: {safe_name}")
            elif safe_name in st.session_state.projects:
                st.sidebar.error("มีชื่อโปรเจ็กต์นี้อยู่แล้ว")
            elif len(st.session_state.projects) >= 10:
                st.sidebar.error("สร้างได้สูงสุด 10 โปรเจ็กต์")
            else:
                # สร้าง DataFrame เปล่า พร้อมคอลัมน์ตามที่คุณใช้
                df_empty = pd.DataFrame(
                    columns=["ชื่อ", "นามสกุล", "เบอร์โทร", "ประเภท", "สถานะ", "รหัสบัตร"]
                )
                st.session_state.projects[safe_name] = df_empty
                st.session_state.current_project = safe_name
                save_project_data(safe_name, df_empty)
            st.rerun()
else:
    st.session_state.current_project = selected
    if st.sidebar.button("🗑️ ลบโปรเจ็กต์นี้"):
        if selected in st.session_state.projects:
            # Remove file
            file_path = os.path.join(STORAGE_DIR, f"{selected}.csv")
            if os.path.exists(file_path):
                os.remove(file_path)
            del st.session_state.projects[selected]
            st.session_state.current_project = None
            st.rerun()

current_project = st.session_state.current_project

if not current_project:
    st.info("โปรดสร้างหรือเลือกโปรเจ็กต์จากแถบด้านซ้าย")
    st.stop()

st.subheader(f"โปรเจ็กต์: {current_project}")

# ดึง DataFrame ของโปรเจ็กต์ปัจจุบัน
df = st.session_state.projects[current_project]

# ตรวจสอบและสร้างคอลัมน์ที่จำเป็น
required_cols = ["ชื่อ", "นามสกุล", "เบอร์โทร", "ประเภท", "สถานะ", "รหัสบัตร"]
for col in required_cols:
    if col not in df.columns:
        df[col] = ""

# เรียงลำดับคอลัมน์ให้เป็นลำดับที่ต้องการ
df = df[required_cols] if not df.empty else pd.DataFrame(columns=required_cols)

# -----------------------------
# 3) จัดการเทมเพลตบัตร
# -----------------------------
st.sidebar.markdown("---")
st.sidebar.subheader("ตั้งค่าเทมเพลต")
orientation = st.sidebar.radio("รูปแบบบัตร", ["แนวนอน (2300x800)", "แนวตั้ง (800x2300)"])

def generate_blank_template(mode):
    size = (2300, 800) if "แนวนอน" in mode else (800, 2300)
    img = Image.new('RGB', size, color=(240, 240, 240))
    d = ImageDraw.Draw(img)
    d.rectangle([10, 10, size[0]-10, size[1]-10], outline=(200, 200, 200), width=5)
    return img

if st.sidebar.button("ดาวน์โหลดเทมเพลตตัวอย่าง"):
    template_img = generate_blank_template(orientation)
    buf = io.BytesIO()
    template_img.save(buf, format="PNG")
    st.sidebar.download_button(
        label="Download PNG Template",
        data=buf.getvalue(),
        file_name=f"template_{orientation}.png",
        mime="image/png"
    )

uploaded_template = st.sidebar.file_uploader("อัปโหลดเทมเพลตจริง", type=["png", "jpg", "jpeg"])
if uploaded_template:
    temp_img = Image.open(uploaded_template)
    expected_size = (2300, 800) if "แนวนอน" in orientation else (800, 2300)
    if temp_img.size != expected_size:
        st.sidebar.warning(f"⚠️ ขนาดเทมเพลตไม่ตรงสเปก: พบ {temp_img.size[0]}x{temp_img.size[1]} (ควรเป็น {expected_size[0]}x{expected_size[1]})")
    
    st.session_state.templates[current_project] = temp_img

# -----------------------------
# -----------------------------
st.markdown("### โหลดรายชื่อผู้เข้าร่วม (CSV / Excel)")

uploaded = st.file_uploader(
    "อัปโหลดไฟล์รายชื่อ", type=["csv", "xlsx", "xls"], key="file_uploader"
)

if uploaded is not None:
    # ป้องกันการประมวลผลไฟล์เดิมซ้ำเมื่อมีการ Rerun หน้าจอ
    file_id = f"{uploaded.name}_{uploaded.size}"
    if st.session_state.get("last_uploaded_file_id") != file_id:
        try:
            if uploaded.name.lower().endswith(".csv"):
                try:
                    # พยายามอ่านด้วย UTF-8-SIG ก่อน
                    new_df = pd.read_csv(uploaded, encoding='utf-8-sig')
                except UnicodeDecodeError:
                    # หากล้มเหลว ให้ลองอ่านด้วย TIS-620 (ภาษาไทยมาตรฐานเก่า)
                    uploaded.seek(0)
                    new_df = pd.read_csv(uploaded, encoding='tis-620')
            else:
                new_df = pd.read_excel(uploaded)

            # ลบช่องว่างส่วนเกินในชื่อคอลัมน์เพื่อให้ Mapping แม่นยำขึ้น
            new_df.columns = new_df.columns.str.strip()

            # ระบบ Mapping คอลัมน์อัตโนมัติ
            col_map = {
                "ชื่อ": "ชื่อ", "First Name": "ชื่อ", "F_Name": "ชื่อ",
                "นามสกุล": "นามสกุล", "Last Name": "นามสกุล", "L_Name": "นามสกุล",
                "ชื่อ-นามสกุล": "ชื่อ-นามสกุล", "ชื่อ–นามสกุล": "ชื่อ-นามสกุล", "Name": "ชื่อ-นามสกุล",
                "เบอร์": "เบอร์โทร", "เบอร์โทร": "เบอร์โทร", "เบอร์โทรศัพท์": "เบอร์โทร",
                "Phone": "เบอร์โทร"
            }
            new_df = new_df.rename(columns=col_map)

            # แยกชื่อ-นามสกุล หากมาเป็นคอลัมน์เดียว
            if "ชื่อ-นามสกุล" in new_df.columns and ("ชื่อ" not in new_df.columns or "นามสกุล" not in new_df.columns):
                split_data = new_df["ชื่อ-นามสกุล"].astype(str).str.split(" ", n=1, expand=True)
                new_df["ชื่อ"] = split_data[0]
                new_df["นามสกุล"] = split_data[1].fillna("")

            # คอลัมน์ที่คาดหวัง
            expected_cols = ["ชื่อ", "นามสกุล", "เบอร์โทร", "ประเภท", "สถานะ", "รหัสบัตร"]
            for col in expected_cols:
                if col not in new_df.columns:
                    new_df[col] = ""
            
            # เจนรหัสบัตรอัตโนมัติ (UUID 12 หลัก) หากไม่มีข้อมูล
            mask_empty_id = (new_df["รหัสบัตร"] == "") | (new_df["รหัสบัตร"].isna())
            if mask_empty_id.any():
                new_df.loc[mask_empty_id, "รหัสบัตร"] = [
                    str(uuid.uuid4()).upper()[-12:] for _ in range(mask_empty_id.sum())
                ]
            
            new_df["สถานะ"] = new_df["สถานะ"].fillna("PENDING")
            # จัดรูปแบบเบอร์โทรศัพท์
            if "เบอร์โทร" in new_df.columns:
                new_df["เบอร์โทร"] = new_df["เบอร์โทร"].apply(format_phone_number)

            # รวมกับข้อมูลเดิม และลบข้อมูลซ้ำทันที (อิงจาก ชื่อ-นามสกุล-เบอร์โทร)
            df = pd.concat([df, new_df[expected_cols]], ignore_index=True)
            df = df.drop_duplicates(subset=["ชื่อ", "นามสกุล", "เบอร์โทร"], keep='first')
            
            st.session_state.projects[current_project] = df
            save_project_data(current_project, df)
            st.session_state["last_uploaded_file_id"] = file_id
            st.success("โหลดรายชื่อเรียบร้อย (และลบรายการที่ซ้ำกันออกแล้ว)")
            st.rerun()
        except Exception as e:
            st.error(f"ไม่สามารถอ่านไฟล์ได้: {e}")

# อัปเดต df หลังโหลด (เผื่อมีการเปลี่ยนแปลง)
df = st.session_state.projects[current_project]

# -----------------------------
# 4) ตัวกรองตามสถานะ GUEST / AGENT / PAID / PENDING
# -----------------------------
st.markdown("### จัดการรายชื่อและสถานะ")

status_options = ["PENDING", "PAID"]
type_options = ["Agent", "Guest"]

# ตรวจสอบและเตรียมข้อมูล
if not df.empty:
    # ถ้าไม่มีคอลัมน์สถานะ ให้สร้าง
    if "สถานะ" not in df.columns:
        df["สถานะ"] = "PENDING"
    else:
        df["สถานะ"] = df["สถานะ"].fillna("PENDING")
else:
    # สร้าง DataFrame เปล่า
    df = pd.DataFrame(columns=required_cols)

st.caption("แก้ไข / เพิ่ม / ลบแถวได้โดยตรงในตารางด้านล่าง")

# ตัวเลือกตัวกรอง (แยกจากการแก้ไข)
col1, col2, col3 = st.columns([2, 1, 1])
with col1:
    selected_status = st.multiselect(
        "กรองตามสถานะ", status_options, default=status_options
    )
with col2:
    if st.button("🔍 ตรวจสอบข้อมูลซ้ำ"):
        dupes = df[df.duplicated(subset=["ชื่อ", "นามสกุล", "เบอร์โทร"], keep=False)]
        if not dupes.empty:
            st.warning(f"พบข้อมูลซ้ำ {len(dupes)} รายการ")
        else:
            st.success("ข้อมูลไม่ซ้ำซ้อน")
    if st.button("🪄 ลบข้อมูลซ้ำทั้งหมด"):
        df = df.drop_duplicates(subset=["ชื่อ", "นามสกุล", "เบอร์โทร"], keep='first')
        st.session_state.projects[current_project] = df
        save_project_data(current_project, df)
        st.rerun()

with col3:
    st.write("") # เว้นระยะ
    if st.button("🗑️ ล้างรายชื่อทั้งหมด", help="ลบรายชื่อทั้งหมดในโปรเจกต์นี้"):
        df = pd.DataFrame(columns=required_cols)
        st.session_state.projects[current_project] = df
        save_project_data(current_project, df)
        st.rerun()

# กรองข้อมูล
if selected_status and not df.empty:
    display_df = df[df["สถานะ"].isin(selected_status)].reset_index(drop=True)
else:
    display_df = df.copy()

# เพิ่มข้อมูลตัวอย่าง ถ้าตารางว่างเปล่า
if display_df.empty and df.empty:
    display_df = pd.DataFrame({
        "ชื่อ": [""],
        "นามสกุล": [""],
        "เบอร์โทร": [""],
        "ประเภท": [""],
        "สถานะ": ["PENDING"],
        "รหัสบัตร": [str(uuid.uuid4()).upper()[-12:]]
    })

# ทำให้แน่ใจว่าลำดับคอลัมน์ถูกต้อง
display_df = display_df[required_cols]

# -----------------------------
# 5) ใช้ st.data_editor แก้ไข/เพิ่ม/ลบ
# -----------------------------
edited_df = st.data_editor(
    display_df,
    key=f"editor_{current_project}_{len(df)}", # บังคับรีเฟรชเมื่อข้อมูลเปลี่ยน
    num_rows="dynamic",  # อนุญาตเพิ่ม/ลบแถว
    use_container_width=True,
    column_config={
        "ชื่อ": st.column_config.TextColumn(
            "ชื่อ",
            help="กรอกชื่อ",
            width="medium",
        ),
        "นามสกุล": st.column_config.TextColumn(
            "นามสกุล",
            help="กรอกนามสกุล",
            width="medium",
        ),
        "เบอร์โทร": st.column_config.TextColumn(
            "เบอร์โทร",
            help="กรอกเบอร์โทรศัพท์",
            width="medium",
        ),
        "ประเภท": st.column_config.SelectboxColumn(
            "ประเภท",
            options=type_options,
            help="เลือกประเภท",
            width="medium",
        ),
        "สถานะ": st.column_config.SelectboxColumn(
            "สถานะ",
            options=status_options,
            help="เลือกสถานะของผู้เข้าร่วม",
            width="medium",
        ),
        "รหัสบัตร": st.column_config.TextColumn(
            "รหัสบัตร",
            help="รหัสสำหรับสร้าง QR Code",
            width="medium",
        ),
    },
    hide_index=True,
)

# อัปเดต session state ด้วยข้อมูลที่แก้ไข
if not edited_df.equals(display_df):
    # ลบแถวว่างเปล่า
    edited_df = edited_df.dropna(how='all')
    
    # จัดรูปแบบเบอร์โทรศัพท์อัตโนมัติ
    if "เบอร์โทร" in edited_df.columns:
        edited_df["เบอร์โทร"] = edited_df["เบอร์โทร"].apply(format_phone_number)
    
    # รวมแถวที่ถูกกรองออกกับข้อมูลใหม่
    if selected_status and not df.empty:
        # ส่วนที่ไม่ถูกกรอง
        unfiltered_df = df[~df["สถานะ"].isin(selected_status)].reset_index(drop=True)
        # รวมกลับ
        updated_df = pd.concat([edited_df, unfiltered_df], ignore_index=True)
    else:
        updated_df = edited_df
    
    st.session_state.projects[current_project] = updated_df
    save_project_data(current_project, updated_df)

# -----------------------------
# 6) ปุ่มดาวน์โหลดรายชื่อ (CSV)
# -----------------------------
st.markdown("### ดาวน์โหลดรายชื่อ (Excel / CSV)")

if not edited_df.empty:
    col_dl1, col_dl2 = st.columns(2)
    
    with col_dl1:
        # ส่งออกเป็น Excel (.xlsx) - แนะนำสำหรับภาษาไทย
        excel_buffer = io.BytesIO()
        with pd.ExcelWriter(excel_buffer, engine='openpyxl') as writer:
            edited_df.to_excel(writer, index=False, sheet_name='รายชื่อ')
        st.download_button(
            "ดาวน์โหลด Excel (.xlsx)",
            data=excel_buffer.getvalue(),
            file_name=f"{current_project}_tickets.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            key="download_excel"
        )

    with col_dl2:
        # ส่งออกเป็น CSV
        csv_bytes = edited_df.to_csv(index=False, encoding='utf-8-sig').encode("utf-8-sig")
        st.download_button(
            "ดาวน์โหลด CSV",
            data=csv_bytes,
            file_name=f"{current_project}_tickets.csv",
            mime="text/csv",
            key="download_csv",
        )
else:
    st.info("ยังไม่มีข้อมูลให้ดาวน์โหลด")

# -----------------------------
# 7) พื้นที่สำหรับพรีวิวบัตร / QR Code
# -----------------------------
st.markdown("## แสดงภาพบัตร QR Code")

def create_ticket_image(row, template_img, orientation_mode):
    # ใช้เทมเพลตที่อัปโหลด หรือสร้างพื้นหลังสีขาวถ้าไม่มี
    if template_img:
        img = template_img.copy()
    else:
        img = generate_blank_template(orientation_mode)
    
    draw = ImageDraw.Draw(img)
    
    # Font paths
    f_reg = os.path.join("assets", "fonts", "IBMPlexSansThai-Regular.ttf")
    f_bold = os.path.join("assets", "fonts", "IBMPlexSansThai-Bold.ttf") # Weight 700
    f_mono = os.path.join("assets", "fonts", "IBMPlexSansThai-Bold.ttf") # Fallback for mono font

    # --- ส่วนที่ 1: ขนาดฟอนต์ (Noto Sans Thai) ---
    font_first = get_font(f_bold, 115, fallback=False) or get_font(f_reg, 110) # ชื่อ (หนา 700)
    font_last = get_font(f_reg, 75)                                           # นามสกุล (ปกติ 400)
    font_tel = get_font(f_reg, 55)                                          # เบอร์โทร
    font_qr_mini = get_font(f_reg, 45)                                         # รหัสใต้ชื่อ
    font_qr_main = get_font(f_bold, 55)

    # ฟังก์ชันช่วยวาดข้อความแบบปลอดภัย (รองรับกรณีฟอนต์โหลดไม่ได้)
    def safe_draw_text(draw_obj, pos, text, font, fill, anchor):
        if font is not None:
            try:
                # ใช้ layout_engine="raqm" เพื่อจัดการสระและวรรณยุกต์ไทยให้ถูกต้อง
                draw_obj.text(pos, text, fill=fill, font=font, anchor=anchor, layout_engine="raqm")
            except:
                # Fallback กรณีที่เครื่องไม่ได้ติดตั้ง libraqm
                draw_obj.text(pos, text, fill=fill, font=font, anchor=anchor)
        else:
            draw_obj.text(pos, text, fill=fill) # Fallback แบบไม่มี anchor

    # Helper for tracking-widerest (letter spacing)
    def draw_spaced_text(draw_obj, pos, text, font, fill, anchor):
        spaced_text = " ".join(list(str(text)))
        safe_draw_text(draw_obj, pos, spaced_text, font, fill, anchor)

    # สร้าง QR Code
    qr_code_val = str(row["รหัสบัตร"])[-12:] if row["รหัสบัตร"] else "000000000000"
    qr = qrcode.QRCode(version=1, error_correction=qrcode.constants.ERROR_CORRECT_L, box_size=10, border=2)
    qr.add_data(qr_code_val)
    qr.make(fit=True)
    
    # --- ส่วนที่ 2: ขนาดของ QR Code (ปรับตัวเลข 400) ---
    qr_size = 430 
    qr_img = qr.make_image(fill_color="black", back_color="white").convert('RGB').resize((qr_size, qr_size), Image.Resampling.LANCZOS)
    
    first_name = str(row.get("ชื่อ", ""))
    last_name = str(row.get("นามสกุล", ""))
    # ตรวจสอบและจัดฟอร์เมตเบอร์โทรอีกครั้งก่อนพิมพ์ลงบัตร
    formatted_phone = format_phone_number(row.get("เบอร์โทร", ""))
    phone_text = f"โทร. {formatted_phone}" if formatted_phone else ""
    
    # --- ส่วนที่ 3: ตำแหน่ง สูง-ต่ำ (Y) และ ซ้าย-ขวา (X) ---
    x_text_pos = 970
    qr_x = 1953
    qr_y = 350  # ตำแหน่งความสูงของ QR Code

    if "แนวนอน" in orientation_mode:
        # วาง QR Code (กึ่งกลางตาม qr_x, qr_y)
        img.paste(qr_img, (qr_x - (qr_size // 2), qr_y - (qr_size // 2)))
        
        # วางรหัสใต้ QR Code (ปรับ 620 เพื่อเลื่อนขึ้นลง)
        safe_draw_text(draw, (qr_x, 620), qr_code_val, font_qr_main, "white", "mt")
        
        # วางชื่อ (Bold 700), นามสกุล (Regular 400) และเบอร์โทร (โทร. 080-000-0000)
        safe_draw_text(draw, (x_text_pos, 310), first_name, font_first, "black", "lt") # ปรับเลข 300 เพื่อเลื่อน ชื่อ ขึ้น-ลง
        safe_draw_text(draw, (x_text_pos, 450), last_name, font_last, "#4C4C4C", "lt") # ปรับเลข 440 เพื่อเลื่อน นามสกุล ขึ้น-ลง
        safe_draw_text(draw, (x_text_pos, 560), phone_text, font_tel, "#994B1A", "lt") # ปรับเลข 560 เพื่อเลื่อน เบอร์โทร ขึ้น-ลง
        draw_spaced_text(draw, (x_text_pos, 680), qr_code_val, font_qr_mini, "#A0765C", "lt")
    else:
        # Fallback for portrait mode using similar logic
        img.paste(qr_img, (400 - 200, 1950 - 200))
        safe_draw_text(draw, (400, 1950 + 250), qr_code_val, font_qr_main, "black", "mt")
        safe_draw_text(draw, (100, 400), first_name, font_first, "black", "lt")
        safe_draw_text(draw, (100, 500), last_name, font_last, "black", "lt")
        
    return img
  
if not edited_df.empty:
    selected_row_idx = st.selectbox("เลือกรายชื่อเพื่อพรีวิว", edited_df.index, 
        format_func=lambda x: f"{edited_df.iloc[x]['ชื่อ']} {edited_df.iloc[x]['นามสกุล']} ({edited_df.iloc[x]['สถานะ']})")

    if st.button("สร้างภาพพรีวิว"):
        row_data = edited_df.iloc[selected_row_idx]
        current_temp = st.session_state.templates.get(current_project)
        
        with st.spinner("กำลังสร้างบัตร..."):
            ticket_result = create_ticket_image(row_data, current_temp, orientation)
            st.image(ticket_result, caption=f"ตัวอย่างบัตร: {row_data['ชื่อ']} {row_data['นามสกุล']}", use_container_width=True)
            
            # ปุ่มดาวน์โหลดภาพ
            buf = io.BytesIO()
            ticket_result.save(buf, format="PNG")
            st.download_button(
                label="ดาวน์โหลดภาพบัตรนี้ (PNG)",
                data=buf.getvalue(),
                file_name=f"ticket_{row_data['ชื่อ']}_{row_data['นามสกุล']}.png",
                mime="image/png"
            )
else:
    st.info("กรุณาเพิ่มรายชื่อเพื่อพรีวิวบัตร")

# -----------------------------
# 8) Bulk Export (ZIP) สำหรับโรงพิมพ์
# -----------------------------
st.markdown("---")
st.markdown("### ส่งออกบัตรทั้งหมด (Bulk Export)")
if st.button("📦 สร้างไฟล์ ZIP สำหรับบัตรทั้งหมด"):
    if not edited_df.empty:
        zip_buffer = io.BytesIO()
        with zipfile.ZipFile(zip_buffer, "a", zipfile.ZIP_DEFLATED, False) as zip_file:
            current_temp = st.session_state.templates.get(current_project)
            progress_bar = st.progress(0)
            for i, (idx, row) in enumerate(edited_df.iterrows()):
                ticket_img = create_ticket_image(row, current_temp, orientation)
                img_byte_arr = io.BytesIO()
                ticket_img.save(img_byte_arr, format='PNG')
                
                # Sanitize components of the filename
                s_name = sanitize_filename(str(row['ชื่อ']))
                s_last = sanitize_filename(str(row['นามสกุล']))
                s_code = sanitize_filename(str(row['รหัสบัตร']))
                
                zip_file.writestr(f"ticket_{s_name}_{s_last}_{s_code}.png", img_byte_arr.getvalue())
                progress_bar.progress((i + 1) / len(edited_df))
        
        st.download_button(
            label="ดาวน์โหลด ZIP (บัตรทั้งหมด)",
            data=zip_buffer.getvalue(),
            file_name=f"tickets_{current_project}_{datetime.now().strftime('%Y%m%d_%H%M')}.zip",
            mime="application/zip"
        )