import os
import streamlit as st
import pdfplumber
import google.generativeai as genai
from dotenv import load_dotenv
import pandas as pd
from streamlit_lottie import st_lottie
import json
from google.cloud import translate_v2 as translate  # Use the Google Cloud Translation API
from dateutil import parser as dateparser

# Load environment variables
load_dotenv()
GEMINI_API_KEY = os.getenv("GOOGLE_API_KEY")
GOOGLE_CLOUD_API_KEY = os.getenv("GOOGLE_CLOUD_API_KEY")  # Ensure this is set in your .env file
genai.configure(api_key=GEMINI_API_KEY)

# Initialize Google Cloud Translate client
translate_client = translate.Client(credentials=GOOGLE_CLOUD_API_KEY)

# Load Lottie animation
def load_lottie_file(filepath: str):
    with open(filepath, "r") as f:
        return json.load(f)

# Inject custom CSS
def inject_custom_css():
    with open("dark_theme.css", "r") as css_file:
        st.markdown(f"<style>{css_file.read()}</style>", unsafe_allow_html=True)

# Extract PDF text
def extract_text_from_pdf(file_path):
    extracted_text = ""
    with pdfplumber.open(file_path) as pdf:
        for page in pdf.pages:
            text = page.extract_text()
            if text:
                extracted_text += text + "\n"
    return extracted_text.strip()

# Analyze with Gemini
def analyze_invoice_data(invoice_text, custom_prompt):
    model = genai.GenerativeModel("models/gemini-1.5-pro-latest")
    prompt = f"{custom_prompt}\n\nInvoice Data:\n{invoice_text}"
    response = model.generate_content(prompt)
    return response.text.strip() if response else "⚠️ AI did not return any response."

# Parse time-series expenses
def parse_time_series_expenses(analysis_text):
    import re
    from dateutil.parser import parse as date_parse

    data = []

    for line in analysis_text.splitlines():
        line = line.strip()
        if not line:
            continue

        try:
            # Split by 2+ spaces or tabs (assuming columns)
            parts = re.split(r'\s{2,}|\t', line)

            # Look for date and amount among parts
            for i, part in enumerate(parts):
                try:
                    date = date_parse(part, fuzzy=False)
                    amount_str = parts[i + 1].replace('$', '').replace(',', '').strip()
                    amount = float(re.findall(r'\d+(?:\.\d+)?', amount_str)[0])
                    data.append({"Date": date, "Amount": amount})
                    break
                except (ValueError, IndexError):
                    continue
        except Exception as e:
            continue

    df = pd.DataFrame(data)
    if not df.empty:
        df["Month"] = df["Date"].dt.to_period("M").astype(str)
        df = df.groupby("Month")["Amount"].sum().reset_index()

    return df


# Show expense trend analysis (increase or decrease)
def show_expense_trend_analysis(df):
    st.subheader("📅 Expense Trend Analysis")
    
    if len(df) < 2:
        st.warning("Not enough data to determine trends.")
        return
    
    trend_analysis = []
    
    # Loop through the DataFrame and compare current month with previous month
    for i in range(1, len(df)):
        previous_month = df.iloc[i-1]
        current_month = df.iloc[i]
        
        change = current_month['Amount'] - previous_month['Amount']
        percentage_change = (change / previous_month['Amount']) * 100 if previous_month['Amount'] != 0 else 0
        
        # Determine whether it is an increase or decrease
        if change > 0:
            trend_analysis.append(f"📈 {current_month['Month']}: Increase of ₹{change:.2f} ({percentage_change:.2f}%) compared to {previous_month['Month']}")
        elif change < 0:
            trend_analysis.append(f"📉 {current_month['Month']}: Decrease of ₹{-change:.2f} ({-percentage_change:.2f}%) compared to {previous_month['Month']}")
        else:
            trend_analysis.append(f"➡️ {current_month['Month']}: No change compared to {previous_month['Month']}")

    # Display the trend analysis
    for analysis in trend_analysis:
        st.markdown(f"- {analysis}")

# Translate text using Google Cloud Translation API
def translate_text(text, target_language):
    result = translate_client.translate(text, target_lang=target_language)
    return result['translatedText']

# Streamlit page config
st.set_page_config(page_title="🧾 Invoice Analyzer", page_icon="📈", layout="wide")
inject_custom_css()

# Load Lottie animation
lottie_json = load_lottie_file("asset/budget.json")
lottie_json_how = load_lottie_file("asset/how.json")

# Language options dictionary
language_options = {
    "en": "English",
    "es": "Spanish",
    "fr": "French",
    "de": "German",
    "it": "Italian",
    "hi": "Hindi",
    "ml": "Malayalam",
    "ta": "Tamil",
    "te": "Telugu",
}

st.markdown("""...""", unsafe_allow_html=True)

# Streamlit layout
left_column, right_column = st.columns([1, 2])

with left_column:
    st_lottie(lottie_json_how, height=250, key="how_animation")
    st.markdown("### 🛠️ How It Works")
    st.markdown("""...""")

with right_column:
    language_option = st.selectbox("Select output language", list(language_options.values()))
    selected_language_code = [code for code, name in language_options.items() if name == language_option][0]
    uploaded_file = st.file_uploader("📂 Upload your invoice (PDF only)", type=["pdf"])
    user_prompt = st.text_area("📝 Enter your custom prompt", placeholder="e.g. Analyze my expenses...")

if uploaded_file and st.button("🌟 Get Smart Budget Insights"):
    if uploaded_file:
        st.success("✅ Invoice uploaded successfully.")
        temp_path = f"temp_{uploaded_file.name}"
        with open(temp_path, "wb") as f:
            f.write(uploaded_file.read())

        with st.spinner("🔍 Extracting text from invoice..."):
            invoice_text = extract_text_from_pdf(temp_path)

        if not invoice_text:
            st.error("⚠ No text could be extracted. Try a different PDF.")
        elif not user_prompt.strip():
            st.warning("⚠ Please enter a prompt to analyze the invoice.")
        else:
            with st.spinner("🤖 Analyzing with Gemini AI..."):
                analysis = analyze_invoice_data(invoice_text, user_prompt)

            # Translate the analysis output to the selected language
            translated_analysis = translate_text(analysis, selected_language_code)

            st.markdown(f"<div class='result-item'>{translated_analysis}</div>", unsafe_allow_html=True)
            st.balloons()

            df_time_expenses = parse_time_series_expenses(analysis)

            if not df_time_expenses.empty and df_time_expenses["Amount"].sum() > 0:
                st.markdown("📆 Monthly Expenses")
                st.dataframe(df_time_expenses, use_container_width=True)

                if any(keyword in user_prompt.lower() for keyword in ["trend", "increase", "decrease", "change", "monthly"]):
                    st.success("📈 Analyzing expense trend...")
                    show_expense_trend_analysis(df_time_expenses)

        os.remove(temp_path)

# Footer
st.markdown("---")
st.caption("📘 Created with ❤️ | © 2025 Invoice Analyzer Pro")


