from pydantic import BaseModel, Field
from typing import List

class GeneratedCopy(BaseModel):
    headline: str = Field(description="A highly engaging, catchy, and tone-appropriate headline.")
    body: str = Field(description="The main marketing copy body text, tailored to the platform.")
    call_to_action: str = Field(description="A clear and compelling call-to-action (CTA).")
    hashtags: List[str] = Field(default_factory=list, description="A list of 3-5 relevant hashtags for the platform.")
