import streamlit as st
import requests

BACKEND_URL = st.secrets.get("BACKEND_URL", "http://localhost:8000")

st.set_page_config(page_title="RichTTS App", layout="centered")
st.title("RichTTS App")
st.write("Enter text and generate speech.")

@st.cache_data
def fetch_voices():
    try:
        resp = requests.get(f"{BACKEND_URL}/voices", timeout=10)
        if resp.ok:
            return resp.json()
    except Exception:
        pass
    return ["en", "es", "fr", "de"]

voices = fetch_voices()

with st.sidebar:
    language = st.selectbox("Language", options=voices, index=voices.index("en") if "en" in voices else 0)
    slow = st.checkbox("Slow speech")

text = st.text_area("Text", height=200)

col1, col2 = st.columns(2)
if col1.button("Synthesize"):
    if not text.strip():
        st.error("Please enter text")
    else:
        with st.spinner("Generating audio..."):
            try:
                resp = requests.post(f"{BACKEND_URL}/synthesize", json={"text": text, "language": language, "slow": slow}, timeout=60)
                if resp.ok:
                    data = resp.json()
                    audio_url = f"{BACKEND_URL}{data['url']}"
                    st.success("Audio generated")
                    st.audio(audio_url)
                    st.download_button("Download MP3", data=requests.get(audio_url).content, file_name=f"{data['id']}.mp3")
                else:
                    st.error(resp.text)
            except Exception as e:
                st.error(str(e))

if col2.button("Show History"):
    try:
        hist = requests.get(f"{BACKEND_URL}/history", timeout=10)
        if hist.ok:
            st.table(hist.json())
        else:
            st.error("Failed to fetch history")
    except Exception as e:
        st.error(str(e))