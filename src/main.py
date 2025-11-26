from fastapi import FastAPI
from fastapi.responses import JSONResponse

app = FastAPI()

@app.post("/synthesize")
async def synthesize(text: str, language: str, speed: int):
    # Use gTTS to generate audio from text
    audio_file = gtts.TextToSpeech(text, language, speed)
    return JSONResponse(content={"audio_file": audio_file})

@app.get("/voices")
async def get_voices():
    # Return list of available languages/accents
    voices = gtts.Voices()
    return JSONResponse(content=voices)

@app.get("/history")
async def get_history():
    # Return metadata for past generations (but no audio files)
    histories = []
    return JSONResponse(content=histories)