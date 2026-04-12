import os
from dotenv import load_dotenv
import streamlit as st
from streamlit_option_menu import option_menu
from st_chat_message import message
from langchain_groq import ChatGroq
from langchain_community.utilities import SQLDatabase
from langchain_core.prompts import ChatPromptTemplate
from sqlalchemy import create_engine, MetaData, Table, func
from sqlalchemy.orm import sessionmaker
import plotly.express as px
import pandas as pd
from prophet import Prophet
import serpapi


# ===============================
# Load environment
# ===============================
load_dotenv(override=True)
api_key = os.getenv("GROQ_API_KEY")
if not api_key:
    st.error("❌ GROQ_API_KEY tidak ditemukan di .env")
    st.stop()

serp_api_key = os.getenv("SERP_API_KEY")
if not serp_api_key:
    st.error("❌ SERP_API_KEY tidak ditemukan di .env")
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
    temperature=0
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

# Prompt klasifikasi intent
intent_classifier_prompt = ChatPromptTemplate.from_template("""
Kamu adalah router cerdas untuk sistem chatbot perusahaan PT Dahana.

Database perusahaan berisi tabel-tabel berikut:
{table_info}

Tugasmu: Tentukan apakah pertanyaan user BISA dijawab dari database perusahaan di atas,
atau harus dicari dari internet.

ATURAN PENTING - Gunakan DATABASE jika:
- Pertanyaan menyebut nama orang (bisa jadi nama karyawan perusahaan)
- Pertanyaan tentang karyawan, jabatan, departemen, divisi, unit
- Pertanyaan tentang absensi, kehadiran, status karyawan
- Pertanyaan tentang produksi, rencana, realisasi
- Pertanyaan tentang data internal perusahaan apapun
- Pertanyaan yang MUNGKIN bisa dijawab dari database (jika ragu pilih DATABASE)

Gunakan WEB hanya jika pertanyaan JELAS tidak mungkin ada di database perusahaan:
- Definisi atau penjelasan konsep umum (contoh: "apa itu inflasi?", "apa itu bahan peledak?")
- Sejarah atau profil umum perusahaan (contoh: "kapan PT Dahana didirikan?", "pt dahana adalah")
- Berita, kejadian eksternal, atau pengetahuan publik umum
- Pertanyaan yang sama sekali tidak berhubungan dengan data karyawan/produksi/absensi

Contoh:
- "siapakah abdul latip?" -> DATABASE  (bisa jadi nama karyawan)
- "info karyawan budi santoso" -> DATABASE
- "siapa saja karyawan departemen tambang?" -> DATABASE
- "berapa total produksi bulan ini?" -> DATABASE
- "bagaimana kehadiran budi santoso?" -> DATABASE
- "pt dahana adalah" -> WEB
- "apa itu bahan peledak?" -> WEB
- "kapan dahana didirikan?" -> WEB
- "siapa presiden indonesia?" -> WEB

Jika ragu, pilih DATABASE.

Pertanyaan user: {question}

Jawaban (DATABASE/WEB):
""")

# Prompt fallback dari SerpAPI (Google)
web_search_prompt = ChatPromptTemplate.from_template("""
Kamu adalah asisten AI yang membantu menjawab pertanyaan berdasarkan informasi dari internet.

Pertanyaan user:
{question}

Informasi yang ditemukan dari web:
{web_results}

Instruksi:
- Jawab pertanyaan user secara jelas dan informatif berdasarkan informasi yang ditemukan di web.
- Jangan menyebut bahwa kamu mencari di internet, cukup jawab pertanyaannya.
- Awali jawaban dengan "Jawaban Web:"
- Selalu sertakan sumber URL di akhir dengan format "Sumber: [url1, url2, ...]"
- Jika informasi tidak cukup untuk menjawab, katakan bahwa informasi tidak tersedia.

Jawaban:
""")


# ===============================
# Fungsi SerpAPI Fallback
# ===============================
def search_serp_and_extract(question: str) -> tuple[str, list[str]]:
    """
    Cari via SerpAPI dan ekstrak snippet dari ai_overview.text_blocks (paragraf).
    Jika ai_overview tidak ada, fallback ke organic_results snippets.
    """
    client = serpapi.Client(api_key=serp_api_key)
    results = client.search({
        "engine": "google",
        "q": question,
        "hl": "id",
        "gl": "id",
        "num": 5,
    })

    snippets: list[str] = []
    urls: list[str] = []

    # ── Prioritas 1: AI Overview paragraphs ──────────────────────────────
    ai_overview = results.get("ai_overview", {})
    text_blocks = ai_overview.get("text_blocks", [])
    for block in text_blocks:
        if block.get("type") == "paragraph":
            snippet = block.get("snippet", "").strip()
            if snippet:
                snippets.append(snippet)

    # ── Prioritas 2: Organic results (jika tidak ada AI Overview) ─────────
    if not snippets:
        for item in results.get("organic_results", [])[:5]:
            snippet = item.get("snippet", "").strip()
            link   = item.get("link", "")
            if snippet:
                snippets.append(f"[{link}]\n{snippet}" if link else snippet)
            if link:
                urls.append(link)

    combined = "\n\n".join(snippets) if snippets else "Tidak ada informasi yang ditemukan."
    return combined, urls


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
        }
    )

# --- Halaman Dashboard ---
if selected == "Dashboard":
    st.title("📊 Dahanalyzer - Dashboard")
    metadata = MetaData() 

    # VISUALISASI ABSENSI KARYAWAN
    st.subheader("Kehadiran Karyawan")
    attendance_table = Table('karyawan_attendance', metadata, autoload_with=engine)

    # Query mengelompokkan jumlah karyawan berdasarkan tanggal dan status
    attendance_query = session.query(
        attendance_table.c.date,
        attendance_table.c.status,
        func.count(attendance_table.c.nip).label('count')
    ).group_by(
        attendance_table.c.date, 
        attendance_table.c.status
    ).order_by(
        attendance_table.c.date
    )
    
    attendance_data = pd.read_sql(attendance_query.statement, engine)
    
    if not attendance_data.empty:
        attendance_fig = px.bar(attendance_data, 
                            x='date', 
                            y='count', 
                            title='Status Kehadiran Karyawan Harian',
                            color='status',
                            barmode='stack'
                            )
        st.plotly_chart(attendance_fig, use_container_width=True)
    else:
        st.info("Data attendance tidak tersedia.")

    # VISUALISASI PRODUKSI
    st.subheader("Prediksi & Realisasi Produksi")
    production_table = Table('dm_produksi', metadata, autoload_with=engine)
    
    # Karena ada kolom Pabrik/Produk, kita agregatkan dulu per Tanggal agar Prophet bisa membaca time-series dengan baik
    production_query = session.query(
        production_table.c.Tanggal.label('date'),
        func.sum(production_table.c.Rencana).label('target_output'),
        func.sum(production_table.c.Realisasi).label('actual_output')
    ).group_by(production_table.c.Tanggal).order_by(production_table.c.Tanggal)
    
    production_data = pd.read_sql(production_query.statement, engine)

    if not production_data.empty:
        # Persiapkan data untuk Prophet
        df_forecast = production_data[['date', 'actual_output']].rename(columns={'date': 'ds', 'actual_output': 'y'})

        # Bersihkan: hapus NaN di kolom ds atau y, konversi ds ke datetime
        df_forecast['ds'] = pd.to_datetime(df_forecast['ds'], errors='coerce')
        df_forecast = df_forecast.dropna(subset=['ds', 'y'])
        df_forecast = df_forecast[df_forecast['y'] > 0]  # buang baris tanpa produksi

        if df_forecast.empty or len(df_forecast) < 2:
            st.info("Data produksi tidak cukup untuk forecast.")
        else:
            # Inisialisasi model Prophet
            model = Prophet()
            model.fit(df_forecast)

            # Buat dataframe untuk prediksi 40 hari ke depan
            future = model.make_future_dataframe(periods=40)
            forecast = model.predict(future)

            # Gabungkan hasil forecast ke data historis
            forecast_data = forecast[['ds', 'yhat', 'yhat_lower', 'yhat_upper']]
            forecast_data.columns = ['date', 'forecast_output', 'lower_bound', 'upper_bound']

            # Gabungkan data aktual dengan prediksi
            # Pastikan kolom tanggal dalam format datetime
            production_data['date'] = pd.to_datetime(production_data['date'])
            forecast_data['date'] = pd.to_datetime(forecast_data['date'])

            # Ambil hanya forecast 40 hari ke depan (setelah data terakhir di database)
            last_actual_date = production_data['date'].max()
            future_forecast = forecast_data[forecast_data['date'] > last_actual_date]

            # Gabungkan data historis dengan forecast masa depan
            merged = pd.concat([production_data, future_forecast], ignore_index=True)

            # Visualisasi menggunakan Plotly
            production_fig = px.line(
                merged,
                x='date',
                y=['target_output', 'actual_output', 'forecast_output'],
                title='Total Volume Produksi Harian (dengan Forecast 40 Hari)',
                labels={'value': 'Output Produksi', 'date': 'Tanggal'},
            )

            # Warna garis
            production_fig.update_traces(line=dict(color='green'), selector=dict(name='target_output'))
            production_fig.update_traces(line=dict(color='orange'), selector=dict(name='actual_output'))
            production_fig.update_traces(line=dict(color='blue', dash='dot'), selector=dict(name='forecast_output'))

            # Tambahkan shading area untuk batas bawah dan atas forecast
            production_fig.add_traces(px.scatter(
                forecast_data, x='date', y='upper_bound', opacity=0.1
            ).data)
            production_fig.add_traces(px.scatter(
                forecast_data, x='date', y='lower_bound', opacity=0.1
            ).data)

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
        message(pertanyaan, is_user=True, key=f"user_{len(st.session_state['messages'])}")

        with st.spinner("🤖 Sedang proses Dahanalyzing..."):
            use_web_fallback = False
            response = ""

            # ── Klasifikasi intent terlebih dahulu ───────────────────────
            try:
                intent_input = {"table_info": table_info, "question": pertanyaan}
                intent_raw = llm.invoke(intent_classifier_prompt.format(**intent_input))
                intent = intent_raw.content.strip().upper()
                if "WEB" in intent:
                    use_web_fallback = True
            except Exception:
                use_web_fallback = False  # default coba DB dulu jika classifier error

            # ── Path: Database (SQL) ─────────────────────────────────────
            if not use_web_fallback:
                try:
                    # Generate SQL
                    sql_input = {"table_info": table_info, "question": pertanyaan}
                    raw_output = llm.invoke(sql_prompt.format(**sql_input))
                    sql_query = raw_output.content.split("SQLQuery:")[-1].strip()

                    # Jalankan query
                    result = str(db.run(sql_query))

                    # Jika hasil query kosong, gunakan web fallback
                    if not result or result.strip() in ("", "[]", "None"):
                        use_web_fallback = True
                    else:
                        # Memotong (truncate) ekstra agresif ke 3000 karakter
                        if len(result) > 3000:
                            result = result[:3000] + "... [Hasil terlalu panjang, dipotong untuk API LLM!]"

                        # Analisis jawaban
                        analysis_input = {
                            "question": pertanyaan,
                            "sql_query": sql_query,
                            "result": result
                        }
                        jawaban = llm.invoke(analysis_prompt.format(**analysis_input))
                        response = jawaban.content

                except Exception:
                    # SQL gagal → fallback ke web
                    use_web_fallback = True

            # ── SerpAPI Fallback ──────────────────────────────────────────
            if use_web_fallback:
                try:
                    web_results, urls = search_serp_and_extract(pertanyaan)
                    web_input = {
                        "question": pertanyaan,
                        "web_results": web_results
                    }
                    jawaban_web = llm.invoke(web_search_prompt.format(**web_input))
                    response = jawaban_web.content
                except Exception as e_web:
                    response = f"❌ Tidak dapat menemukan jawaban dari database maupun web.\n\nError: {e_web}"

        # Simpan jawaban bot
        st.session_state["messages"].append({"role": "assistant", "content": response})
        message(response, is_user=False, key=f"bot_{len(st.session_state['messages'])}")
