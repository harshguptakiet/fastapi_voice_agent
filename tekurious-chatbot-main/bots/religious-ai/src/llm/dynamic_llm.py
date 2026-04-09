import os
from dotenv import load_dotenv

from langchain.prompts import PromptTemplate
from langchain_core.runnables.base import RunnableSequence
from langchain.output_parsers import PydanticOutputParser
from langchain.schema import BasePromptTemplate
from datetime import datetime
from pydantic import BaseModel
from pathlib import Path
import os, yaml, re, random
from utils.common import DHOME
from utils import common

def _load_env():
    # Ensure env is loaded reliably regardless of current working directory.
    base_dir = Path(__file__).resolve().parents[1]
    env_local_path = base_dir / ".env.local"
    env_path = base_dir / ".env"

    # Load base env first (should not override OS env)
    load_dotenv(dotenv_path=env_path, override=False)

    # Then apply local overrides (should override values from .env)
    if env_local_path.exists():
        load_dotenv(dotenv_path=env_local_path, override=True)


# load variables from dotenv file
_load_env()

class LLMEngine:
    def __init__(self, model_name: str, temperature: float = 0, max_tokens: int = 500):
        _load_env()
        
        self.provider = os.getenv("LLM_PROVIDER", "gemini").lower()
        self.temperature = temperature
        self.max_tokens = max_tokens
        self.model_name = model_name or self.get_default_model_name()
        self.api_key = self.get_api_key()
        
        self.llm = None
        self.prompt = None
        self.parser = None
        self.chain = None
        
        self.initialize_llm()
        
    def get_default_model_name(self) -> str:
        if self.provider == "openai":
            # Default to a commonly available model; allow override via env.
            return os.getenv("OPENAI_MODEL") or "gpt-4o-mini"
        if self.provider == "gemini":
            # Gemini API expects model ids like "models/gemini-2.0-flash".
            return os.getenv("GEMINI_MODEL") or "models/gemini-2.0-flash"

        return os.getenv("LLM_MODEL") or "gpt-4o-mini"
    
    def get_api_key(self) -> str:
        return {
            "gemini": os.getenv("GOOGLE_API_KEY"),
            "openai": os.getenv("OPENAI_API_KEY"),
        }.get(self.provider, "")
        
    def initialize_llm(self):
        if self.provider not in {"openai", "gemini"}:
            raise ValueError(
                f"Unsupported LLM provider: {self.provider}. "
                "This service supports only 'openai' and 'gemini'."
            )

        if not self.api_key:
            raise ValueError(
                f"Missing API key for LLM provider '{self.provider}'. "
                "Set the matching environment variable (e.g., GOOGLE_API_KEY / OPENAI_API_KEY)."
            )
        if self.provider == "gemini":
            try:
                from langchain_google_genai import ChatGoogleGenerativeAI
            except ImportError as e:
                raise ImportError(
                    "Missing dependency for Gemini provider. Install 'langchain-google-genai'."
                ) from e
            self.llm = ChatGoogleGenerativeAI(
                model = self.model_name,
                temperature = self.temperature,
                google_api_key = self.api_key,
                max_tokens = self.max_tokens
            )
        elif self.provider == "openai":
            try:
                from langchain_openai import ChatOpenAI
            except ImportError as e:
                raise ImportError(
                    "Missing dependency for OpenAI provider. Install 'langchain-openai'."
                ) from e
            self.llm = ChatOpenAI (
                model = self.model_name,
                temperature = self.temperature,
                openai_api_key = self.api_key,
                max_tokens = self.max_tokens
            )
        else:
            raise ValueError(f"Unsupported LLM provider: {self.provider}")
        
        
# Universally applicable
    def load_prompt(self, prompt_path: Path) -> BasePromptTemplate:
            """
            Loads a custom prompt template from a YAML file.

            :param prompt_path: The file path of the custom prompt template in YAML format.
            """
            prompt_data = {}
            try:
                with open(prompt_path, 'r') as file:
                    prompt_data = yaml.safe_load(file)

                # Extract the prompt content (Assuming the prompt YAML has a field 'template')
                if 'template' not in prompt_data:
                    raise ValueError("YAML file must contain a 'template' field.")
            except FileNotFoundError:
                    print(f"Error: The file at {prompt_path} was not found.")
            except yaml.YAMLError as e:
                print(f"Error parsing YAML file: {e}")
            except Exception as e:
                print(f"An error occurred while loading the prompt: {e}")

            return PromptTemplate(
                    input_variables=prompt_data['input_variables'],
                    template=prompt_data['template']
                )

    def get_llm_sequence(self, prompt: BasePromptTemplate):
        # Create the RunnableSequence
        if not self.parser:
            raise ValueError("Sequence could not be initialized. Please set the output parser and try again.")

        self.chain = RunnableSequence(
            prompt | self.llm | self.parser
        )
        
    def set_output_parser(self, parser: PydanticOutputParser):
        self.parser = parser
        
    def respond(self, query: BaseModel) -> BaseModel:
        """
        Accepts a query, passes it through the chain, and returns the parsed response.

        :param query: The user's input question.
        :return: The parsed response as a QueryResponse object.
        """
        if self.chain is None:
            raise ValueError("Sequence is not initialized. Please load the prompt and initialize the chain.")
        
        #random_number = random.randint(0, 0)
        #self.api_key=GOOGLE_API_KEYS[random_number]
        self.api_key = self.get_api_key()
        self.initialize_llm()

        prompt_inputs = query.dict()
        prompt_inputs["format_instructions"] = self.parser.get_format_instructions()
        
        # Get the final prompt from the template by formatting it
        prompt_text = self.prompt.format(**prompt_inputs)
        prompt_text = self.clean_text_for_logging(prompt_text)
        
        # Log the final prompt
        my_log = {"the_final_prompt": "", "resp": ""}
        my_log["the_final_prompt"] = prompt_text
        my_now = datetime.now()
        folder_name = my_now.strftime("%d-%b-%Y")
        formatted_date = my_now.strftime("%d-%b-%Y--%H-%M-%S-%f")
        log_folder = os.path.join(common.LOGS, "llms", folder_name)

        if not os.path.exists(log_folder):
            os.makedirs(log_folder)
        pfn = os.path.join(log_folder, "scan_" + formatted_date + ".json")
        
        # Run the chain with the input query and return the parsed output
        query = dict(query)
        query["format_instructions"] = self.parser.get_format_instructions()
        response = self.chain.invoke(query)
        my_log["resp"] = str(response)
        
        common.write_to_json_file(pfn, my_log)
        return response

    def clean_text_for_logging(self, text):
        """
        Cleans up special characters, newlines, and Unicode escape sequences from the text.
        
        :param text: The text to clean.
        :return: Cleaned text ready for logging.
        """
        # Replace \n with actual newlines for readability
        cleaned_text = text.replace("\\n", "\n")
        
        # Optionally remove or handle other special characters (e.g., \uf076)
        cleaned_text = re.sub(r"\\u[0-9A-Fa-f]{4}", "", cleaned_text)  # Remove Unicode escape sequences like \uf076
        
        return cleaned_text


def get_llm_engine() -> LLMEngine:

    _load_env()
    
    llm_engine = LLMEngine(
        model_name="",
        temperature=0.0,
        max_tokens = 500
    )
    return llm_engine

 