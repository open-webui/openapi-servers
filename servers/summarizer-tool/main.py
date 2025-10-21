from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from summarizers.text_summarizer import TextSummarizer

app = FastAPI(
    title="Summarizing Server",
    version="1.0.0",
    description="Leverages an LLM to summarize data",  
)

summarizers = {
    'TEXT':TextSummarizer()
}


class TextRequest(BaseModel):
    text: str

@app.post("/summarize/text")
def summarize_text(data: TextRequest):
    try:
        result = summarizers['TEXT'].summarize(data.text)
        if 'content' in result:
            return {"status": "success", "summary":result['content']}
        else:
            raise HTTPException(status_code=500, detail=str(result['error']))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
