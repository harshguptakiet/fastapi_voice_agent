from pydantic import BaseModel, Field, validator
from typing import List, Optional

class ParseOutput(BaseModel):
    output: str = Field(default="NA", description="The output of the query")
    reason: str = Field(default="NA", description="The reason of the output provided")
    
    @validator('output', pre=True, always=True)
    def set_default_output(cls, v):
        return v if v is not None else "NA"

    @validator('reason', pre=True, always=True)
    def set_default_reason(cls, v):
        return v if v is not None else "NA"

class GuardrailsOutput(BaseModel):
    output: str = Field(default="NA", description="The output of the query")
    reason: str = Field(default="NA", description="The reason of the output provided")
    
    @validator('output', pre=True, always=True)
    def set_default_output(cls, v):
        return v if v is not None else "NA"

    @validator('reason', pre=True, always=True)
    def set_default_reason(cls, v):
        return v if v is not None else "NA"
