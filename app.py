import os
import streamlit as st
import pdfplumber
import google.generativeai as genai
from dotenv import load_dotenv
import pandas as pd
from streamlit_lottie import st_lottie
import json
from dateutil import parser as dateparser
from io import BytesIO
from reportlab.lib.pagesizes import letter
from reportlab.pdfgen import canvas

# Load environment variables
load_dotenv()
GEMINI_API_KEY = os.getenv("GOOGLE_API_KEY")
genai.configure(api_key=GEMINI_API_KEY)

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
    model = genai.GenerativeModel("models/gemini-2.0-flash")
    prompt = f"{custom_prompt}\n\nInvoice Data:\n{invoice_text}"
    response = model.generate_content(prompt)
    return response.text.strip() if response else "⚠️ AI did not return any response."

# Parse time-series expenses
def parse_time_series_expenses(analysis_text):
    import re
    from dateutil.parser import parse as date_parse

    data = []
    lines = analysis_text.splitlines()
    for line in lines:
        line = line.strip()
        if not line:
            continue
        match = re.match(r"(\d{4}-\d{2}-\d{2})\s+\$(\d+(?:\.\d{2})?)", line)
        if match:
            date_str, amount_str = match.groups()
            try:
                date = date_parse(date_str)
                amount = float(amount_str)
                data.append({"Date": date, "Amount": amount})
            except ValueError:
                continue

    df = pd.DataFrame(data)
    if not df.empty:
        df["Month"] = df["Date"].dt.to_period("M").astype(str)
        df = df.groupby("Month")["Amount"].sum().reset_index()
    return df

# Show expense trend analysis
def show_expense_trend_analysis(df):
    st.subheader("📅 Expense Trend Analysis")
    if len(df) < 2:
        st.warning("Not enough data to determine trends.")
        return
    trend_analysis = []
    for i in range(1, len(df)):
        prev = df.iloc[i - 1]
        curr = df.iloc[i]
        change = curr['Amount'] - prev['Amount']
        percent = (change / prev['Amount']) * 100 if prev['Amount'] != 0 else 0
        if change > 0:
            trend_analysis.append(f"📈 {curr['Month']}: Increase of ₹{change:.2f} ({percent:.2f}%) compared to {prev['Month']}")
        elif change < 0:
            trend_analysis.append(f"📉 {curr['Month']}: Decrease of ₹{-change:.2f} ({-percent:.2f}%) compared to {prev['Month']}")
        else:
            trend_analysis.append(f"➡️ {curr['Month']}: No change compared to {prev['Month']}")
    for analysis in trend_analysis:
        st.markdown(f"- {analysis}")

# Calculate financial health score
def calculate_financial_health(invoice_text):
    # Define some high-risk and low-risk categories
    high_risk_keywords = [
        "coffee", "snack", "entertainment", "delivery", "uber",
        "lunch", "hotel", "flight", "restaurant", "shopping",
        "netflix", "swiggy", "zomato"
    ]
    low_risk_keywords = [
        "grocery", "utility", "rent", "mortgage", "salary", "tax", "insurance"
    ]
    
    risk_score = 0
    low_risk_count = 0
    high_risk_count = 0
    total_lines = 0
    risky_items = []
    low_risk_items = []
    
    for line in invoice_text.splitlines():
        line = line.strip().lower()
        if not line:
            continue
        total_lines += 1
        
        if any(keyword in line for keyword in high_risk_keywords):
            risk_score += 1
            high_risk_count += 1
            risky_items.append(line)
        elif any(keyword in line for keyword in low_risk_keywords):
            low_risk_count += 1
            low_risk_items.append(line)

    # Calculate the risk ratio and score
    if total_lines == 0:
        return 100, "🟢 Healthy", "No risky spending patterns detected.", "No invoice content found to analyze."

    risk_ratio = risk_score / total_lines
    low_risk_ratio = low_risk_count / total_lines
    score = max(0, 100 - int(risk_ratio * 100))

    # Generate dynamic explanation based on the actual content
    explanation = []
    
    if risk_score == 0:
        explanation.append("No high-risk spending detected.")
    else:
        explanation.append(f"Detected {high_risk_count} high-risk spending items: {', '.join(risky_items)}.")
    
    if low_risk_count == 0:
        explanation.append("No low-risk, essential spending detected.")
    else:
        explanation.append(f"Detected {low_risk_count} low-risk spending items: {', '.join(low_risk_items)}.")
    
    if risk_score > 0 and low_risk_count == 0:
        status = "🔴 Risky Spending"
        tip = "Consider reducing non-essential expenses like dining out, entertainment, and shopping."
    elif risk_score > low_risk_count:
        status = "🟡 Needs Attention"
        tip = "Balance essential and non-essential spending better. Consider cutting down on discretionary spending."
    else:
        status = "🟢 Healthy"
        tip = "Good balance between essential and non-essential expenses."

    # Combine all explanation pieces
    explanation_message = "\n".join(explanation)
    
    return score, status, tip, explanation_message


# Helper function to create the PDF content
def generate_pdf(score, status, tip, explanation, analysis):
    # Create a byte buffer to hold the PDF data
    pdf_buffer = BytesIO()
    
    # Create a PDF object using reportlab
    c = canvas.Canvas(pdf_buffer, pagesize=letter)
    width, height = letter  # Default letter size
    
    # Set font
    c.setFont("Helvetica", 12)

    # Add content to the PDF
    c.drawString(100, height - 40, f"📊 Financial Health Analysis")
    c.drawString(100, height - 60, f"Score: {score}/100 - {status}")
    c.drawString(100, height - 80, f"Tip: {tip}")

    # Add Reason Behind Score
    c.drawString(100, height - 120, f"📝 Reason Behind Your Score:")
    text_object = c.beginText(100, height - 140)
    text_object.setFont("Helvetica", 10)
    for line in explanation.splitlines():
        text_object.textLine(line)
    c.drawText(text_object)

    # Add Gemini AI Analysis
    c.drawString(100, height - 220, f"📊 Gemini AI Analysis:")
    text_object = c.beginText(100, height - 240)
    for line in analysis.splitlines():
        text_object.textLine(line)
    c.drawText(text_object)
    
    # Finalize PDF and save it to buffer
    c.showPage()
    c.save()
    
    # Move buffer cursor to the beginning
    pdf_buffer.seek(0)
    
    return pdf_buffer


# Page config
st.set_page_config(page_title="🧾 Invoice Analyzer", page_icon="📈", layout="wide")
inject_custom_css()

# Load Lottie animations
lottie_json = load_lottie_file("asset/budget.json")
lottie_json_how = load_lottie_file("asset/how.json")
lottie_json_meter = load_lottie_file("asset/meter.json")

# Header
st.markdown(""" 
    <style>
        @keyframes fadeInSlideUp {
            0% { opacity: 0; transform: translateY(30px); }
            100% { opacity: 1; transform: translateY(0); }
        }
        .centered-banner {
            display: flex; flex-direction: column; align-items: center; justify-content: center;
            text-align: center; height: 30vh; animation: fadeInSlideUp 1.2s ease-out; margin-bottom: 20px;
        }
        .centered-banner h1 {
            font-size: 3rem; font-weight: bold;
            background: linear-gradient(to right, #00c6ff, #0072ff);
            -webkit-background-clip: text; color: transparent; margin-bottom: 0.5rem;
        }
        .centered-banner p {
            font-size: 1.3rem; color: #cccccc; margin-top: 0;
        }
    </style>
    <div class="centered-banner">
        <h1>Smart Budget Insight</h1>
        <p>Transform invoices into clear financial insights, powered by Gemini AI.</p>
    </div>
""", unsafe_allow_html=True)

st_lottie(lottie_json, height=250, key="intro-animation")

# Layout
left_column, right_column = st.columns([1, 2])

with left_column:
    st.lottie(lottie_json_how, height=200, key="how_animation")
    st.markdown("### 🛠️ How It Works")
    st.markdown(""" 
    - 📄 **Upload your invoice**
    - 🧠 **Enter your prompt**
    - 📊 **View categorized expenses and financial insights based on your prompts**
    - 💰 **view your financial health score**
    """)
    st.lottie(lottie_json_meter, height=200, key="meter_animation")

    # Financial Health UI shown in left panel after file upload
    uploaded_file = st.session_state.get("uploaded_file")
    invoice_text = st.session_state.get("invoice_text")
    if uploaded_file and invoice_text:
        st.markdown("### 💡 Financial Health Meter")
        score, status, tip, explanation = calculate_financial_health(invoice_text)
        
        st.markdown(f"{status} — **{score}/100**")
        st.progress(score)
        st.caption(f"💬 {tip}")
        
        # Show the detailed dynamic explanation
        st.markdown("### 📝 Reason Behind Your Score")
        st.markdown(explanation)


# Define a flag to track if the analysis has been done
if 'analysis_done' not in st.session_state:
    st.session_state['analysis_done'] = False

# Layout for right column (where file upload and user prompt are located)
# Layout for right column (where file upload and user prompt are located)
with right_column:
    uploaded_file = st.file_uploader("📂 Upload your invoice (PDF only)", type=["pdf"])
    user_prompt = st.text_area("📝 Enter your custom prompt", placeholder="e.g. Analyze my expenses and summarize monthly spending trends.")
    analyze_button = st.button("🌟 Get Smart Budget Insights")

    if uploaded_file:
        st.success("✅ Invoice uploaded successfully.")
        temp_path = f"temp_{uploaded_file.name}"
        with open(temp_path, "wb") as f:
            f.write(uploaded_file.read())

        with st.spinner("🔍 Extracting text from invoice..."):
            invoice_text = extract_text_from_pdf(temp_path)

        st.session_state["uploaded_file"] = uploaded_file
        st.session_state["invoice_text"] = invoice_text

        if not invoice_text:
            st.error("⚠ No text could be extracted. Try a different PDF.")
        elif not user_prompt.strip():
            st.warning("⚠ Please enter a prompt to analyze the invoice.")
        else:
            # Only analyze if the analysis hasn't been done yet
            if analyze_button and not st.session_state['analysis_done']:
                with st.spinner("🤖 Analyzing with Gemini AI..."):
                    analysis = analyze_invoice_data(invoice_text, user_prompt)

                st.session_state['analysis'] = analysis
                st.session_state['analysis_done'] = True

                # Generate the financial health score and other data
                score, status, tip, explanation = calculate_financial_health(invoice_text)
                st.session_state['score'] = score
                st.session_state['status'] = status
                st.session_state['tip'] = tip
                st.session_state['explanation'] = explanation

                st.markdown("<div class='section'>", unsafe_allow_html=True)
                st.markdown("<h3 class='section-header'>📊 Gemini Analysis</h3>", unsafe_allow_html=True)
                st.markdown(f"<div class='result-item'>{analysis}</div>", unsafe_allow_html=True)
                st.markdown("</div>", unsafe_allow_html=True)
                st.balloons()


    # Generate PDF only after analysis is done
    if st.session_state.get('analysis_done', False):
        # Generate PDF
        pdf_buffer = generate_pdf(
            st.session_state['score'],
            st.session_state['status'],
            st.session_state['tip'],
            st.session_state['explanation'],
            st.session_state['analysis'],
            
        )

        # Add a download button
        st.download_button(
            label="📥 Download Financial Health Report",
            data=pdf_buffer,
            file_name="financial_health_report.pdf",
            mime="application/pdf"
        )

