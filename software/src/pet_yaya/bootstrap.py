from pathlib import Path
from pet_yaya.adapters.memory_intent import LocalMemoryInterpreter

from pet_yaya.adapters.openai_dialogue import (
    JsonTransport,
    LMStudioChatDialogueEngine,
    OpenAIResponsesDialogueEngine,
    ResilientDialogueEngine,
)
from pet_yaya.adapters.simulator import (
    ConsoleActuator,
    ConservativeSafetyPolicy,
    RuleBasedDialogueEngine,
    VirtualDeviceSafetyPolicy,
)
from pet_yaya.application.orchestrator import PetYayaOrchestrator
from pet_yaya.application.session_manager import SessionManager
from pet_yaya.config import DialogueSettings
from pet_yaya.infrastructure.sqlite import (
    SQLiteDatabase,
    SQLiteGrowthRepository,
    SQLiteMemoryRepository,
    SQLitePendingMemoryRepository,
)
from pet_yaya.ports.contracts import Actuator


def build_simulator(
    database_path: str | Path | None = None,
    actuator: Actuator | None = None,
    dialogue_settings: DialogueSettings | None = None,
    dialogue_transport: JsonTransport | None = None,
) -> PetYayaOrchestrator:
    if database_path is None:
        database_path = (
            Path(__file__).resolve().parents[2] / "data" / "pet_yaya.db"
        )
    database = SQLiteDatabase(database_path)
    session = SessionManager()
    settings = dialogue_settings or DialogueSettings.from_env()
    local_dialogue = RuleBasedDialogueEngine()
    primary_dialogue = None
    primary_provider = "openai"
    selected_model = settings.model
    requires_network = True
    missing_configuration_error = None
    if settings.mode == "local":
        primary_provider = "local"
        selected_model = settings.local_model
        requires_network = False
        primary_dialogue = LMStudioChatDialogueEngine(
            api_key=settings.local_api_token,
            model=settings.local_model,
            base_url=settings.local_base_url,
            timeout_seconds=settings.timeout_seconds,
            transport=dialogue_transport,
        )
    elif settings.mode in {"auto", "openai"}:
        if settings.api_key:
            primary_dialogue = OpenAIResponsesDialogueEngine(
                api_key=settings.api_key,
                model=settings.model,
                base_url=settings.base_url,
                timeout_seconds=settings.timeout_seconds,
                safety_identifier=settings.safety_identifier,
                transport=dialogue_transport,
            )
        elif settings.mode == "openai":
            missing_configuration_error = (
                "未设置 OPENAI_API_KEY，已使用本地规则。"
            )
    dialogue = ResilientDialogueEngine(
        fallback=local_dialogue,
        primary=primary_dialogue,
        mode=settings.mode,
        model=selected_model,
        primary_provider=primary_provider,
        online_provider=(
            (lambda: session.snapshot().online)
            if requires_network
            else (lambda: True)
        ),
        missing_configuration_error=missing_configuration_error,
    )
    safety = VirtualDeviceSafetyPolicy(
        ConservativeSafetyPolicy(), session.snapshot
    )
    return PetYayaOrchestrator(
        dialogue=dialogue,
        memories=SQLiteMemoryRepository(database),
        pending_memories=SQLitePendingMemoryRepository(database),
        growth_repository=SQLiteGrowthRepository(database),
        safety=safety,
        actuator=actuator if actuator is not None else ConsoleActuator(),
        session=session,
        memory_interpreter=LocalMemoryInterpreter(settings, dialogue_transport) if settings.mode == "local" else None,
    )

