from pydantic import BaseModel, Field, validator
from typing import List, Optional

class ParseInput(BaseModel):
    query: str = Field(..., description="The user's query")
    