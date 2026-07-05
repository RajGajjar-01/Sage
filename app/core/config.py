from pydantic import AliasChoices, Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Environment-driven configuration for the agent, its providers, and the API."""

    # Sandbox
    WORKSPACE: str = "./workspace"
    DB_PATH: str = "./data/agent.db"

    # Groq
    GROQ_API_KEY: str | None = None
    GROQ_MODEL: str = "llama-3.3-70b-versatile"
    GROQ_ENDPOINT: str = "https://api.groq.com/openai/v1/"

    # ZhipuAI (ZAI_* is an accepted alias)
    ZHIPU_API_KEY: str | None = Field(
        default=None, validation_alias=AliasChoices("ZHIPU_API_KEY", "ZAI_API_KEY")
    )
    ZHIPU_MODEL: str = Field(
        default="glm-4.7-flash",
        validation_alias=AliasChoices("ZHIPU_MODEL", "ZAI_MODEL"),
    )
    ZHIPU_ENDPOINT: str = "https://open.bigmodel.cn/api/paas/v4/"

    # Prompt enhancement
    TAVILY_API_KEY: str | None = None

    # Agent loop tuning
    MAX_AGENT_STEPS: int = 25
    DOOM_LOOP_THRESHOLD: int = 3
    SHELL_TIMEOUT_SECONDS: int = 120
    LLM_TIMEOUT_SECONDS: int = 120

    # API
    ALLOWED_ORIGINS: list[str] = ["http://localhost:3000"]

    model_config = SettingsConfigDict(env_ignore_empty=True, extra="ignore")


settings = Settings()
