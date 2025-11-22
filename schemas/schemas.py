from pydantic import BaseModel

class AnalyzeRequest(BaseModel):
    file_url: str

class CompareFeedbackRequest(BaseModel):
    base_csv: str
    target_csv: str