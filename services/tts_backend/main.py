from fastapi import FastAPI, HTTPException
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import List, Optional
from uuid import uuid4
from pathlib import Path
from gtts import gTTS

app = FastAPI(title="RichTTS Backend")

# Allow frontend to call backend from another origin
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

STATIC_DIR = Path(__file__).parent / "static"
HISTORY_FILE = Path(__file__).parent / "history.json"
STATIC_DIR.mkdir(parents=True, exist_ok=True)

try:
    import json
    if not HISTORY_FILE.exists():
        HISTORY_FILE.write_text("[]", encoding="utf-8")
except Exception:
    pass

app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")


class SynthesizeRequest(BaseModel):
    text: str
    language: str = "en"
    slow: bool = False


class SynthesizeResponse(BaseModel):
    url: str
    id: str


@app.get("/voices", response_model=List[str])
def get_voices():
    # Basic list of common gTTS languages; full list available via gtts.langs
    voices = [
        "af","ar","bn","cs","da","de","el","en","en-au","en-uk","en-us",
        "es","es-es","es-us","fi","fr","hi","hu","id","it","ja","ko",
        "nl","no","pl","pt","pt-br","ro","ru","sk","sv","ta","th","tr",
        "uk","vi","zh-CN","zh-TW"
    ]
    return voices


@app.get("/history")
def get_history():
    try:
        import json
        return json.loads(HISTORY_FILE.read_text(encoding="utf-8"))
    except Exception:
        return []


@app.post("/synthesize", response_model=SynthesizeResponse)
def synthesize(req: SynthesizeRequest):
    if not req.text or not req.text.strip():
        raise HTTPException(status_code=400, detail="Text is required")
    try:
        audio_id = str(uuid4())
        filename = f"{audio_id}.mp3"
        filepath = STATIC_DIR / filename
        tts = gTTS(text=req.text, lang=req.language, slow=req.slow)
        tts.save(str(filepath))

        record = {
            "id": audio_id,
            "language": req.language,
            "slow": req.slow,
            "file": filename
        }
        try:
            import json
            hist = json.loads(HISTORY_FILE.read_text(encoding="utf-8"))
            hist.insert(0, record)
            HISTORY_FILE.write_text(json.dumps(hist, ensure_ascii=False, indent=2), encoding="utf-8")
        except Exception:
            pass

        return SynthesizeResponse(url=f"/static/{filename}", id=audio_id)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("services.tts_backend.main:app", host="0.0.0.0", port=8000)