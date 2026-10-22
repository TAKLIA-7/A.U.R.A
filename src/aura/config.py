"""AURA configuration management."""
from __future__ import annotations
import os
from pathlib import Path
from typing import Optional
from pydantic import BaseModel, Field
from dotenv import load_dotenv

load_dotenv(override=True)


class LLMConfig(BaseModel):
    provider: str = Field(default="gemini")
    model: str = Field(default="gemini-2.0-flash")
    api_key: Optional[str] = Field(default=None)
    base_url: Optional[str] = Field(default=None)
    max_tokens: int = Field(default=4096)
    temperature: float = Field(default=0.7)


class JEVConfig(BaseModel):
    provider: str = Field(default="mock")  # "mock", "openrouter", "jev"
    endpoint: Optional[str] = Field(default=None)
    api_key: Optional[str] = Field(default=None)
    model: str = Field(default="typesafe/jev-1.13")
    timeout_seconds: float = Field(default=10.0)
    mock_mode: bool = Field(default=True)
    max_retries: int = Field(default=2)
    allow_threshold: float = Field(default=0.1)
    block_threshold: float = Field(default=0.9)


class RuntimeConfig(BaseModel):
    data_dir: Path = Field(default=Path("./data"))
    workspace_root: Path = Field(default=Path("."))
    max_agent_turns: int = Field(default=20)
    max_tool_calls: int = Field(default=10)
    agent_timeout_seconds: float = Field(default=120.0)
    log_level: str = Field(default="INFO")
    database_url: Optional[str] = Field(default=None)



class DisplayConfig(BaseModel):
    color_theme: str = Field(default="dark")
    no_color: bool = Field(default=False)
    monitor_refresh_seconds: float = Field(default=2.0)
    tool_display: str = Field(default="grouped")  # "grouped", "emoji", "minimal", "hidden"
    loader_style: str = Field(default="gradient")  # "gradient", "spinner", "minimal"
    input_style: str = Field(default="bordered")   # "bordered", "block", "plain"


class AURAConfig(BaseModel):
    llm: LLMConfig = Field(default_factory=LLMConfig)
    jev: JEVConfig = Field(default_factory=JEVConfig)
    runtime: RuntimeConfig = Field(default_factory=RuntimeConfig)
    display: DisplayConfig = Field(default_factory=DisplayConfig)

    @classmethod
    def from_env(cls) -> "AURAConfig":
        load_dotenv(override=True)
        openrouter_key = os.getenv("OPENROUTER_API_KEY")
        if openrouter_key and ("your-openrouter" in openrouter_key.lower() or "your-key" in openrouter_key.lower() or not openrouter_key.strip()):
            openrouter_key = None

        google_key = os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY") or os.getenv("AURA_LLM_API_KEY")
        if google_key and ("your-" in google_key.lower() or not google_key.strip()):
            google_key = None

        # Determine LLM Provider
        llm_provider = os.getenv("AGENT_PROVIDER") or os.getenv("AURA_LLM_PROVIDER")
        if not llm_provider or (llm_provider == "openrouter" and not openrouter_key) or (llm_provider == "gemini" and not google_key):
            if google_key:
                llm_provider = "gemini"
            elif openrouter_key:
                llm_provider = "openrouter"
            else:
                llm_provider = "mock"

        llm_model = os.getenv("GEMINI_MODEL") or os.getenv("AURA_LLM_MODEL")
        if not llm_model or llm_model == "gemini-2.0-flash":
            llm_model = "gemini-3.5-flash-lite" if llm_provider == "gemini" else ("google/gemini-2.0-flash-001" if llm_provider == "openrouter" else "mock-agent")

        llm_key = openrouter_key if llm_provider == "openrouter" else google_key

        llm = LLMConfig(
            provider=llm_provider,
            model=llm_model,
            api_key=llm_key,
            base_url=os.getenv("AURA_LLM_BASE_URL") or ("https://openrouter.ai/api/v1" if llm_provider == "openrouter" else None),
        )

        # Determine JEV Provider and Mock mode
        decision_engine = (os.getenv("DECISION_ENGINE") or os.getenv("AURA_JEV_PROVIDER") or "").lower()
        jev_api_key = (
            os.getenv("JEV_API_KEY")
            or os.getenv("OPENROUTER_API_KEY")
            or os.getenv("AURA_JEV_API_KEY")
            or os.getenv("JEV_KEY")
            or openrouter_key
        )
        if jev_api_key and ("your-" in jev_api_key.lower() or not jev_api_key.strip()):
            jev_api_key = None

        jev_mock_raw = os.getenv("AURA_JEV_MOCK_MODE")
        if jev_mock_raw is not None:
            jev_mock = jev_mock_raw.lower() not in ("false", "0", "no")
        else:
            jev_mock = False if (jev_api_key or decision_engine in ("jev", "openrouter")) else True

        jev_provider = decision_engine or os.getenv("AURA_JEV_PROVIDER")
        if not jev_provider or jev_provider in ("jev", "openrouter"):
            jev_provider = "openrouter" if (openrouter_key or jev_api_key) else ("openrouter" if decision_engine in ("jev", "openrouter") else "mock")
            if jev_provider == "mock" and not jev_api_key:
                jev_mock = True

        jev_model = os.getenv("JEV_MODEL") or os.getenv("AURA_JEV_MODEL") or "typesafe/jev-1.13"
        jev_timeout = float(os.getenv("JEV_TIMEOUT_SECONDS") or os.getenv("AURA_JEV_TIMEOUT_SECONDS", "10"))
        allow_threshold = float(os.getenv("JEV_ALLOW_THRESHOLD", "0.1"))
        block_threshold = float(os.getenv("JEV_BLOCK_THRESHOLD", "0.9"))

        jev = JEVConfig(
            provider=jev_provider,
            endpoint=os.getenv("AURA_JEV_ENDPOINT") or ("https://openrouter.ai/api/v1" if jev_provider == "openrouter" else None),
            api_key=jev_api_key,
            model=jev_model,
            timeout_seconds=jev_timeout,
            mock_mode=jev_mock,
            allow_threshold=allow_threshold,
            block_threshold=block_threshold,
        )

        data_dir = Path(os.getenv("AURA_DATA_DIR", "./data"))
        db_url = os.getenv("DATABASE_URL")
        runtime = RuntimeConfig(
            data_dir=data_dir,
            workspace_root=Path(os.getenv("AURA_WORKSPACE_ROOT", ".")),
            max_agent_turns=int(os.getenv("MAX_AGENT_TURNS") or os.getenv("AURA_MAX_AGENT_TURNS", "20")),
            max_tool_calls=int(os.getenv("MAX_TOOL_CALLS") or os.getenv("AURA_MAX_TOOL_CALLS", "10")),
            agent_timeout_seconds=float(os.getenv("AURA_AGENT_TIMEOUT_SECONDS", "120")),
            log_level=os.getenv("AURA_LOG_LEVEL", "INFO"),
            database_url=db_url,
        )

        no_color_raw = os.getenv("AURA_NO_COLOR", "false").lower()
        tool_display = os.getenv("AURA_TOOL_DISPLAY", "grouped").lower()
        loader_style = os.getenv("AURA_LOADER_STYLE", "gradient").lower()
        input_style = os.getenv("AURA_INPUT_STYLE", "bordered").lower()
        display = DisplayConfig(
            color_theme=os.getenv("AURA_COLOR_THEME", "dark"),
            no_color=no_color_raw in ("true", "1", "yes"),
            monitor_refresh_seconds=float(os.getenv("AURA_MONITOR_REFRESH_SECONDS", "2")),
            tool_display=tool_display,
            loader_style=loader_style,
            input_style=input_style,
        )
        return cls(llm=llm, jev=jev, runtime=runtime, display=display)

    def ensure_dirs(self) -> None:
        for sub in ("logs", "runs"):
            (self.runtime.data_dir / sub).mkdir(parents=True, exist_ok=True)


_config: Optional[AURAConfig] = None


def get_config() -> AURAConfig:
    global _config
    if _config is None:
        _config = AURAConfig.from_env()
        _config.ensure_dirs()
    return _config
