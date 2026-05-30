import os

import pandas as pd
import plotly.express as px
import streamlit as st
from dotenv import load_dotenv
from langchain_community.utilities import SQLDatabase
from langchain_core.prompts import ChatPromptTemplate
from langchain_groq import ChatGroq
from prophet import Prophet
from sqlalchemy import MetaData, Table, create_engine, func
from sqlalchemy.orm import sessionmaker
from st_chat_message import message
from streamlit_option_menu import option_menu

from chatbot_core import ask as chatbot_ask

# ===============================
# Load environment
# ===============================
load_dotenv(override=True)
api_key = os.getenv("GROQ_API_KEY")
if not api_key:
    st.error("❌ GROQ_API_KEY tidak ditemukan di .env")
    st.stop()

db_url = os.getenv("database_url")
if not db_url:
    st.error("❌ database_url tidak ditemukan di .env")
    st.stop()

# Jika menggunakan psycopg2, pastikan format URL diawali 'postgresql+psycopg2://'
if db_url.startswith("postgresql://"):
    db_url_psycopg2 = db_url.replace("postgresql://", "postgresql+psycopg2://", 1)
else:
    db_url_psycopg2 = db_url

# ===============================
# Init LLM
# ===============================
llm = ChatGroq(
    groq_api_key=api_key,
    model="llama-3.1-8b-instant",  # Model terbaru Groq yang direkomendasikan
    temperature=0,
)

# Init database
db = SQLDatabase.from_uri(db_url_psycopg2)
table_info = db.get_table_info()

# Koneksi ke database
engine = create_engine(db_url)

# Membuat koneksi sesi
Session = sessionmaker(bind=engine)
session = Session()

# ===============================
# Prompt SQL
# ===============================
sql_prompt = ChatPromptTemplate.from_template("""
Kamu adalah seorang **Data Analyst senior** sekaligus **Database Administrator berpengalaman**.
Kamu sangat memahami struktur, relasi, serta isi database.

Tugasmu:
- Hasilkan query PostgreSQL yang valid, efisien, dan optimal untuk menjawab pertanyaan user.
- Jangan gunakan format kode atau pembungkus Markdown dalam jawaban. Berikan hanya query SQL dalam bentuk teks biasa, tanpa tanda ``` sql atau format lain.
- Gunakan best practice SQL (contoh: JOIN dengan ON yang tepat, WHERE untuk filter, GROUP BY & agregasi bila relevan). BATASI dengan klausa LIMIT (maksimal limit 50) agar data tidak terlalu besar.
- Jika user meminta data spesifik (bisa jadi user typo), sehingga gunakan LIKE, ILIKE, atau SOUNDEX, dll.
- Hindari redundansi, subquery yang tidak perlu, dan sintaks yang usang.
- Jangan berikan jawaban naratif, hanya query PostgreSQL murni.
- Jika butuh menggabungkan tabel, gunakan relasi yang logis sesuai struktur database.
- Pastikan query bisa langsung dieksekusi tanpa perlu modifikasi tambahan.

Informasi database:
{table_info}

Pertanyaan user:
{question}

SQLQuery:
""")

# Prompt analisis
analysis_prompt = ChatPromptTemplate.from_template("""
Kamu adalah **Data Analyst Profesional** yang sangat berpengalaman dalam analisis data. Tugasmu adalah memberikan analisis mendalam terhadap data yang telah diambil menggunakan query SQL. Jika pertanyaan ini meminta **analisis** atau **penyebab** dalam data, maka kamu harus memberikan analisis yang komprehensif dan interpretatif dengan menggunakan data yang ada.

Berikut adalah informasi yang ada:
- Pertanyaan: {question}
- SQL Query yang digunakan: {sql_query}
- Hasil query dari database: {result}

Instruksi:
- Jika pertanyaan hanya meminta data atau informasi tertentu (seperti "tanggal dengan suhu terendah"), jawab dengan hasil query secara langsung tanpa analisis. Jawaban tidak perlu mencakup analisis tren, pola, atau korelasi.
- Jika pertanyaan meminta untuk analisis (seperti "apa yang menyebabkan suhu rendah pada tanggal tersebut"), maka lakukan analisis tren, pola, atau insight yang dapat diambil dari data tersebut TANPA MEMBUAT KORELASI atau KAUSALITAS. Korelasi atau kausalitas hanya boleh dibuat jika didukung oleh data yang ada, dan user memintanya secara eksplisit.
- Jika pertanyaan tidak meminta analisis seperti hanya meminta isi data, maka berikan jawaban singkat berdasarkan hasil query.
- Awali setiap jawaban dengan "Jawaban Analisis:" atau "Jawaban Non-Analisis:" sesuai konteks pertanyaan.
- Berikan jawaban yang informatif, jelas, mudah dipahami, dan tanpa bertele-tele.
- Jika data hasil perhitungan/query kamu lebih bagus untuk disajikan dalam bentuk tabel, maka sajikan dalam bentuk tabel.
- Selalu sertakan sumber data di akhir dengan "Sumber: (data apa saja yang digunakan)".

Jawaban:
""")


# ===============================
# UI Streamlit
# ===============================
st.set_page_config(page_title="Dahanalyzer", layout="wide")

# Sidebar menu
with st.sidebar:
    selected = option_menu(
        "📌 Menu Utama",
        ["Dashboard", "Chatbot SuperBrain"],
        icons=["bar-chart", "robot"],
        menu_icon="list",
        default_index=0,
        styles={
            "icon": {"color": "#009684", "font-size": "20px"},
            "nav-link-selected": {"background-color": "#CFE8E6", "color": "black"},
        },
    )

# --- Halaman Dashboard ---
if selected == "Dashboard":
    st.title("📊 Dahanalyzer - Dashboard")
    metadata = MetaData()

    # VISUALISASI ABSENSI KARYAWAN
    st.subheader("Kehadiran Karyawan")
    attendance_table = Table("karyawan_attendance", metadata, autoload_with=engine)

    # Query mengelompokkan jumlah karyawan berdasarkan tanggal dan status
    attendance_query = (
        session.query(
            attendance_table.c.date,
            attendance_table.c.status,
            func.count(attendance_table.c.nip).label("count"),
        )
        .group_by(attendance_table.c.date, attendance_table.c.status)
        .order_by(attendance_table.c.date)
    )

    attendance_data = pd.read_sql(attendance_query.statement, engine)

    if not attendance_data.empty:
        attendance_fig = px.bar(
            attendance_data,
            x="date",
            y="count",
            title="Status Kehadiran Karyawan Harian",
            color="status",
            barmode="stack",
        )
        st.plotly_chart(attendance_fig, use_container_width=True)
    else:
        st.info("Data attendance tidak tersedia.")

    # VISUALISASI PRODUKSI
    st.subheader("Prediksi & Realisasi Produksi")
    production_table = Table("dm_produksi", metadata, autoload_with=engine)

    # Karena ada kolom Pabrik/Produk, kita agregatkan dulu per Tanggal agar Prophet bisa membaca time-series dengan baik
    production_query = (
        session.query(
            production_table.c.Tanggal.label("date"),
            func.sum(production_table.c.Rencana).label("target_output"),
            func.sum(production_table.c.Realisasi).label("actual_output"),
        )
        .group_by(production_table.c.Tanggal)
        .order_by(production_table.c.Tanggal)
    )

    production_data = pd.read_sql(production_query.statement, engine)

    if not production_data.empty:
        # Persiapkan data untuk Prophet
        df_forecast = production_data[["date", "actual_output"]].rename(
            columns={"date": "ds", "actual_output": "y"}
        )
        df_forecast["ds"] = pd.to_datetime(df_forecast["ds"])
        df_forecast = df_forecast.dropna(subset=["ds", "y"])

        # Inisialisasi model Prophet
        model = Prophet()
        model.fit(df_forecast)

        # Buat dataframe untuk prediksi 40 hari ke depan
        future = model.make_future_dataframe(periods=40)
        forecast = model.predict(future)

        # Gabungkan hasil forecast ke data historis
        forecast_data = forecast[["ds", "yhat", "yhat_lower", "yhat_upper"]]
        forecast_data.columns = [
            "date",
            "forecast_output",
            "lower_bound",
            "upper_bound",
        ]

        # Gabungkan data aktual dengan prediksi
        # Pastikan kolom tanggal dalam format datetime
        production_data["date"] = pd.to_datetime(production_data["date"])
        forecast_data["date"] = pd.to_datetime(forecast_data["date"])

        # Ambil hanya forecast 40 hari ke depan (setelah data terakhir di database)
        last_actual_date = production_data["date"].max()
        future_forecast = forecast_data[forecast_data["date"] > last_actual_date]

        # Gabungkan data historis dengan forecast masa depan
        merged = pd.concat([production_data, future_forecast], ignore_index=True)

        # Visualisasi menggunakan Plotly
        production_fig = px.line(
            merged,
            x="date",
            y=["target_output", "actual_output", "forecast_output"],
            title="Total Volume Produksi Harian (dengan Forecast 40 Hari)",
            labels={"value": "Output Produksi", "date": "Tanggal"},
        )

        # Warna garis
        production_fig.update_traces(
            line=dict(color="green"), selector=dict(name="target_output")
        )
        production_fig.update_traces(
            line=dict(color="orange"), selector=dict(name="actual_output")
        )
        production_fig.update_traces(
            line=dict(color="blue", dash="dot"), selector=dict(name="forecast_output")
        )

        # Tambahkan shading area untuk batas bawah dan atas forecast
        production_fig.add_traces(
            px.scatter(forecast_data, x="date", y="upper_bound", opacity=0.1).data
        )
        production_fig.add_traces(
            px.scatter(forecast_data, x="date", y="lower_bound", opacity=0.1).data
        )

        # Tampilkan grafik
        st.plotly_chart(production_fig, use_container_width=True)
    else:
        st.info("Data produksi tidak tersedia.")

# --- Halaman Chatbot SuperBrain ---
elif selected == "Chatbot SuperBrain":
    st.title("🤖 DahanaChatbot - SuperBrain")

    # Inisialisasi chat history
    if "messages" not in st.session_state:
        st.session_state["messages"] = []

    # Tampilkan pesan yang sudah ada
    for i, msg in enumerate(st.session_state["messages"]):
        if msg["role"] == "user":
            message(msg["content"], is_user=True, key=f"user_{i}")
        else:
            message(msg["content"], is_user=False, key=f"bot_{i}")

    # Input chat pakai st.chat_input
    if pertanyaan := st.chat_input("Ketik pertanyaan di sini..."):
        # Tambahkan & langsung tampilkan pertanyaan user
        st.session_state["messages"].append({"role": "user", "content": pertanyaan})
        message(
            pertanyaan, is_user=True, key=f"user_{len(st.session_state['messages'])}"
        )

        with st.spinner("🤖 Sedang proses Dahanalyzing..."):
            try:
                result = chatbot_ask(pertanyaan)
                response = result["answer"]
            except Exception as e:
                response = f"❌ Error: {e}"

        # Simpan jawaban bot
        st.session_state["messages"].append({"role": "assistant", "content": response})
        message(response, is_user=False, key=f"bot_{len(st.session_state['messages'])}")
