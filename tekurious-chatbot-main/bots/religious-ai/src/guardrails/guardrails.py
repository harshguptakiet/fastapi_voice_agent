from langchain.output_parsers import PydanticOutputParser
from llm.output_parser import GuardrailsOutput
#from llm.gemini import get_gemini_engine

from llm.dynamic_llm import get_llm_engine

import os
from pathlib import Path
from llm.input import ParseInput

class Guardrails:
    
    def get_llm_response(self, query: str) -> GuardrailsOutput:
        llm_engine = get_llm_engine()
        prompt_path = Path(__file__).resolve().parents[1] / "prompts" / "input_guardrails.yaml"
        print("prompt_path:", str(prompt_path))
        llm_engine.prompt = llm_engine.load_prompt(prompt_path)
        
        if not llm_engine.prompt:
            raise ValueError(f"Prompt couldn't be assigned to {llm_engine.provider} Engine. Please load the prompt and initialize the chain.")
        
        llm_engine.set_output_parser(PydanticOutputParser(pydantic_object=GuardrailsOutput))
        llm_engine.get_llm_sequence(llm_engine.prompt)
        query_model = ParseInput(query=query)
        
        result = llm_engine.respond(query_model)
        
        return result
        
    """ 
    def get_llm_response(self, query: str ) -> GuardrailsOutput:
        gemini_engine = get_gemini_engine()
        prompt_path = os.path.join("prompts", "input_guardrails.yaml")
        print("prompt_path:", prompt_path)
        gemini_engine.prompt = gemini_engine.load_prompt(Path(prompt_path))

        if not gemini_engine.prompt:
            raise ValueError("Prompt couldn't be assigned to GeminiEngine. Please load the prompt and initialize the chain.")

        gemini_engine.set_output_parser(PydanticOutputParser(pydantic_object=GuardrailsOutput))
        gemini_engine.get_llm_sequence(gemini_engine.prompt)
        query_model = ParseInput(query=query)
        
        result = gemini_engine.respond(query_model)

        return result
    """
    def apply_input_guardrails(self, query: str):
        result = self.get_llm_response(query)
        return result.output, result.reason
