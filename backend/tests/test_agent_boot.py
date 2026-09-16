"""
Boot smoke test.

The default configuration declares eight agent classes. Four of them
(safety, scheduler, whatsapp_monitor, analytics) previously had no
implementation, so the orchestrator crashed with ModuleNotFoundError when it
tried to import them at pool start. This test guards that regression: every
configured agent_class must be importable and instantiable as a BaseAgent.
"""

import importlib

import pytest

from src.agents.base_agent import BaseAgent
from src.config.config import SystemConfig


def _load_class(dotted: str):
    module_path, class_name = dotted.rsplit(".", 1)
    module = importlib.import_module(module_path)
    return getattr(module, class_name)


# Agents whose modules pull in heavy browser/ML deps (selenium, playwright,
# torch, spacy). Their import is validated when those extras are installed;
# here we only assert config declares them with a well-formed dotted path.
_HEAVY_AGENTS = {"account_manager", "interaction", "content_analysis", "conversation"}


def test_config_declares_all_agents_with_wellformed_paths():
    config = SystemConfig()
    assert config.agents, "default config should declare agents"
    for name, agent_cfg in config.agents.items():
        assert agent_cfg.agent_class.count(".") >= 3, name
        module_path, class_name = agent_cfg.agent_class.rsplit(".", 1)
        assert module_path.startswith("src.agents."), name
        assert class_name and class_name[0].isupper(), name


def test_skeleton_agents_import_and_instantiate():
    """The four previously-missing agents must import and instantiate cleanly."""
    config = SystemConfig()
    for name, agent_cfg in config.agents.items():
        if name in _HEAVY_AGENTS:
            continue
        cls = _load_class(agent_cfg.agent_class)
        assert issubclass(cls, BaseAgent), f"{name} is not a BaseAgent"
        instance = cls(agent_id=f"{name}-test", agent_type=name, config=agent_cfg.config)
        assert instance.agent_type == name
        assert isinstance(instance._get_capabilities(), list)


@pytest.mark.parametrize(
    "dotted",
    [
        "src.agents.core.safety_agent.SafetyAgent",
        "src.agents.core.scheduler_agent.SchedulerAgent",
        "src.agents.core.whatsapp_monitor_agent.WhatsAppMonitorAgent",
        "src.agents.core.analytics_agent.AnalyticsAgent",
    ],
)
def test_previously_missing_agents_exist(dotted):
    cls = _load_class(dotted)
    assert issubclass(cls, BaseAgent)
