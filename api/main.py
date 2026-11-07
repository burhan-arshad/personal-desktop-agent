from typing import Optional

from fastapi import (
    FastAPI,
    HTTPException,
    UploadFile,
    File,
    Form,
)
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from api.runtime import (
    start_agent,
    respond_to_approval,
    get_run,
)

from conversation.memory import (
    start_conversation,
    get_active_conversation,
    get_recent_history,
    save_message,
)

from conversation.understanding import understand_message

from voice.transcription import (
    get_groq_client,
    MODEL_NAME,
)


app = FastAPI(
    title="Personal Desktop AI Agent API",
    version="1.2.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)


MAX_AUDIO_SIZE = 20 * 1024 * 1024  # 20 MB

ASR_PROMPT = (
    "The speaker may use Urdu, Roman Urdu, English, "
    "or a mixture of these languages. "
    "Transcribe the spoken words accurately. "
    "Preserve English technical terms and application names."
)


# =========================
# REQUEST MODELS
# =========================

class ChatRequest(BaseModel):
    instruction: str = Field(min_length=1, max_length=2000)
    conversation_id: str | None = None


class ApprovalRequest(BaseModel):
    approved: bool


class ConversationRequest(BaseModel):
    message: str = Field(min_length=1, max_length=2000)
    conversation_id: Optional[str] = None


# =========================
# HEALTH
# =========================

@app.get("/api/health")
def health():
    return {
        "status": "online",
        "service": "Personal Desktop AI Agent",
    }


# =========================
# DIRECT AGENT CHAT
# =========================

@app.post("/api/chat")
def chat(request: ChatRequest):
    try:
        return start_agent(
            request.instruction,
            conversation_id=request.conversation_id,
        )

    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error))

    except RuntimeError as error:
        raise HTTPException(status_code=409, detail=str(error))

    except Exception as error:
        raise HTTPException(status_code=500, detail=str(error))


# =========================
# CONVERSATION
# =========================

@app.post("/api/conversation")
def conversation(request: ConversationRequest):

    message = request.message.strip()

    if not message:
        raise HTTPException(
            status_code=400,
            detail="Message cannot be empty.",
        )

    try:
        conversation_id = (
            request.conversation_id
            or get_active_conversation()
        )

        history = get_recent_history(
            conversation_id,
            limit=8,
        )

        understanding = understand_message(
            message,
            history=history,
        )

        save_message(
            conversation_id,
            "user",
            message,
        )

        message_type = understanding["type"]

        # Normal conversation
        if message_type == "conversation":

            response = understanding["response"]

            save_message(
                conversation_id,
                "assistant",
                response,
            )

            return {
                "conversation_id": conversation_id,
                "type": "conversation",
                "response": response,
            }

        # Clarification
        if message_type == "clarification":

            response = understanding["clarification_question"]

            save_message(
                conversation_id,
                "assistant",
                response,
            )

            return {
                "conversation_id": conversation_id,
                "type": "clarification",
                "response": response,
            }

        # Desktop action
        if message_type == "action":

            instruction = understanding["instruction"]

            agent_result = start_agent(
                instruction,
                conversation_id=conversation_id,
            )

            return {
                "conversation_id": conversation_id,
                "type": "action",
                "instruction": instruction,
                "agent": agent_result,
            }

        raise ValueError("Unknown understanding type.")

    except ValueError as error:
        raise HTTPException(
            status_code=400,
            detail=str(error),
        )

    except RuntimeError as error:
        raise HTTPException(
            status_code=409,
            detail=str(error),
        )

    except Exception as error:
        raise HTTPException(
            status_code=500,
            detail=str(error),
        )


# =========================
# VOICE TRANSCRIPTION
# =========================

@app.post("/api/voice")
def voice_input(
    audio: UploadFile = File(...),
    conversation_id: Optional[str] = Form(None),
    language: Optional[str] = Form(None),
):
    try:

        # 1. Validate audio file
        if not audio.filename:
            raise HTTPException(
                status_code=400,
                detail="Audio filename is missing.",
            )

        audio.file.seek(0, 2)
        file_size = audio.file.tell()
        audio.file.seek(0)

        if file_size == 0:
            raise HTTPException(
                status_code=400,
                detail="Audio file is empty.",
            )

        if file_size > MAX_AUDIO_SIZE:
            raise HTTPException(
                status_code=413,
                detail="Audio file exceeds the 20 MB limit.",
            )

        # 2. Get Groq client
        client = get_groq_client()

        # 3. Prepare transcription request
        transcription_options = {
            "file": (
                audio.filename,
                audio.file,
                audio.content_type or "application/octet-stream",
            ),
            "model": MODEL_NAME,
            "prompt": ASR_PROMPT,
            "response_format": "json",
            "temperature": 0.0,
        }

        if language:
            transcription_options["language"] = language

        # 4. Transcribe audio
        result = client.audio.transcriptions.create(
            **transcription_options
        )

        transcript = result.text.strip()

        if not transcript:
            raise HTTPException(
                status_code=422,
                detail="No speech could be recognized.",
            )

        # 5. Process transcript through existing conversation pipeline
        conversation_result = conversation(
            ConversationRequest(
                message=transcript,
                conversation_id=conversation_id,
            )
        )

        # 6. Return transcript + conversation response
        return {
            "transcript": transcript,
            "conversation": conversation_result,
        }

    except HTTPException:
        raise

    except Exception as error:
        print(f"[VOICE API ERROR] {error}")

        raise HTTPException(
            status_code=502,
            detail="Voice transcription or processing failed.",
        )

    finally:
        audio.file.close()


# =========================
# CONVERSATION HISTORY
# =========================

@app.get("/api/conversation/{conversation_id}/history")
def conversation_history(conversation_id: str):

    try:
        history = get_recent_history(
            conversation_id,
            limit=100,
        )

        return {
            "conversation_id": conversation_id,
            "messages": history,
        }

    except Exception as error:
        raise HTTPException(
            status_code=500,
            detail=str(error),
        )


# =========================
# NEW CONVERSATION
# =========================

@app.post("/api/conversation/new")
def new_conversation():

    try:
        conversation_id = start_conversation()

        return {
            "conversation_id": conversation_id,
            "status": "created",
        }

    except Exception as error:
        raise HTTPException(
            status_code=500,
            detail=str(error),
        )


# =========================
# AGENT APPROVAL
# =========================

@app.post("/api/agent/{thread_id}/approval")
def approval(thread_id: str, request: ApprovalRequest):

    try:
        return respond_to_approval(
            thread_id,
            request.approved,
        )

    except ValueError as error:
        raise HTTPException(status_code=404, detail=str(error))

    except Exception as error:
        raise HTTPException(status_code=500, detail=str(error))


# =========================
# AGENT STATUS
# =========================

@app.get("/api/agent/{thread_id}")
def agent_status(thread_id: str):

    try:
        return get_run(thread_id)

    except ValueError as error:
        raise HTTPException(status_code=404, detail=str(error))