import streamlit as st
import requests
import os

# Use environment variable or default for backend URL
# For Docker containers, use the service name, for local development use localhost
BACKEND_URL = os.getenv("BACKEND_URL", "http://localhost:8000")

st.set_page_config(page_title="RichTTS App", layout="centered")
st.title("RichTTS App")
st.write("Enter text and generate speech.")

@st.cache_data
def fetch_voices():
    try:
        resp = requests.get(f"{BACKEND_URL}/voices", timeout=10)
        if resp.ok:
            return resp.text.split('\n')
    except Exception as e:
        st.error(f"Failed to fetch voices: {e}")
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
                    audio_id = data['id']
                    
                    st.success("Audio generated")
                    
                    # Display the audio URL for debugging
                    st.info(f"Audio URL: {audio_url}")
                    
                    # Try to play the audio
                    try:
                        st.audio(audio_url, autoplay=True)
                        st.write("✅ Audio player loaded successfully")
                    except Exception as audio_error:
                        st.error(f"Audio playback failed: {audio_error}")
                        st.write(f"Tried URL: {audio_url}")
                    
                    # Download button
                    try:
                        audio_response = requests.get(audio_url)
                        if audio_response.ok:
                            st.download_button(
                                "Download MP3", 
                                data=audio_response.content, 
                                file_name=f"{audio_id}.mp3", 
                                mime="audio/mpeg"
                            )
                        else:
                            st.warning(f"Download failed: {audio_response.status_code}")
                    except Exception as download_error:
                        st.warning(f"Download error: {download_error}")
                        
                else:
                    st.error(f"Synthesis failed: {resp.status_code} - {resp.text}")
            except Exception as e:
                st.error(f"Error: {e}")
                st.write(f"Backend URL: {BACKEND_URL}")

if col2.button("Show History"):
    try:
        hist = requests.get(f"{BACKEND_URL}/history", timeout=10)
        if hist.ok:
            history_data = hist.json()
            st.write(f"Found {len(history_data)} entries in history")
            if history_data:
                st.table(history_data[:10])  # Show first 10 entries
        else:
            st.error(f"Failed to fetch history: {hist.status_code}")
    except Exception as e:
        st.error(f"History error: {e}")