import os

import pandas as pd
import plotly.express as px
import streamlit as st
from dotenv import load_dotenv
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

if db_url.startswith("postgresql://"):
    db_url_psycopg2 = db_url.replace("postgresql://", "postgresql+psycopg2://", 1)
else:
    db_url_psycopg2 = db_url


# ===============================
# Cached resource init
# ===============================
@st.cache_resource
def get_llm():
    return ChatGroq(
        groq_api_key=api_key,
        model="llama-3.1-8b-instant",
        temperature=0,
    )


@st.cache_resource
def get_engine():
    return create_engine(db_url)


@st.cache_resource
def get_session(_engine):
    Session = sessionmaker(bind=_engine)
    return Session()


llm = get_llm()
engine = get_engine()
session = get_session(engine)


# ===============================
# Cached data queries
# ===============================
@st.cache_data(ttl=300)
def get_attendance_data():
    metadata = MetaData()
    attendance_table = Table("karyawan_attendance", metadata, autoload_with=engine)
    attendance_query = (
        session.query(
            attendance_table.c.date,
            attendance_table.c.status,
            func.count(attendance_table.c.nip).label("count"),
        )
        .group_by(attendance_table.c.date, attendance_table.c.status)
        .order_by(attendance_table.c.date)
    )
    return pd.read_sql(attendance_query.statement, engine)


@st.cache_data(ttl=300)
def get_production_data():
    metadata = MetaData()
    production_table = Table("dm_produksi", metadata, autoload_with=engine)
    production_query = (
        session.query(
            production_table.c.Tanggal.label("date"),
            func.sum(production_table.c.Rencana).label("target_output"),
            func.sum(production_table.c.Realisasi).label("actual_output"),
        )
        .group_by(production_table.c.Tanggal)
        .order_by(production_table.c.Tanggal)
    )
    return pd.read_sql(production_query.statement, engine)


@st.cache_data(ttl=3600)
def get_production_forecast(production_data_json: str):
    production_data = pd.read_json(production_data_json)
    df_forecast = production_data[["date", "actual_output"]].rename(
        columns={"date": "ds", "actual_output": "y"}
    )
    df_forecast["ds"] = pd.to_datetime(df_forecast["ds"])
    df_forecast = df_forecast.dropna(subset=["ds", "y"])

    model = Prophet()
    model.fit(df_forecast)

    future = model.make_future_dataframe(periods=40)
    forecast = model.predict(future)

    forecast_data = forecast[["ds", "yhat", "yhat_lower", "yhat_upper"]].copy()
    forecast_data.columns = ["date", "forecast_output", "lower_bound", "upper_bound"]
    return forecast_data



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

    # VISUALISASI ABSENSI KARYAWAN
    st.subheader("Kehadiran Karyawan")

    attendance_data = get_attendance_data()

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

    production_data = get_production_data()

    if not production_data.empty:
        production_data["date"] = pd.to_datetime(production_data["date"])

        forecast_data = get_production_forecast(production_data.to_json())
        forecast_data["date"] = pd.to_datetime(forecast_data["date"])

        last_actual_date = production_data["date"].max()
        future_forecast = forecast_data[forecast_data["date"] > last_actual_date]

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

                # Debug expander — tampil saat DATABASE atau AI_KNOWLEDGE
                if result.get("source") in ("DATABASE", "AI_KNOWLEDGE"):
                    with st.expander(
                        f"🔍 Debug SQL [{result['source']}]",
                        expanded=result.get("source") == "AI_KNOWLEDGE",
                    ):
                        sql = result.get("sql_query")
                        err = result.get("sql_error")
                        if sql:
                            st.code(sql, language="sql")
                        else:
                            st.warning(
                                "⚠️ SQL tidak berhasil di-generate (LLM kembalikan kosong)."
                            )
                        if err:
                            st.error(f"❌ SQL Error: {err}")
                        elif sql and result.get("source") == "AI_KNOWLEDGE":
                            st.info(
                                "ℹ️ Query berjalan tapi tidak ada data yang cocok di database."
                            )
                        elif (
                            not sql
                            and not err
                            and result.get("source") == "AI_KNOWLEDGE"
                        ):
                            st.warning(
                                "⚠️ SQL tidak di-generate dan tidak ada error — cek terminal untuk detail debug."
                            )
            except Exception as e:
                response = f"❌ Error: {e}"

        # Simpan jawaban bot
        st.session_state["messages"].append({"role": "assistant", "content": response})
        message(response, is_user=False, key=f"bot_{len(st.session_state['messages'])}")
