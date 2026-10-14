from monitor import agents


def test_empty_model_env_vars_fall_back_to_the_default(monkeypatch):
    """GitHub Actions passes unset variables as empty strings."""
    captured = {}

    class FakeGroq:
        def __init__(self, **kwargs):
            captured.update(kwargs)

    import langchain_groq
    monkeypatch.setattr(langchain_groq, "ChatGroq", FakeGroq)
    monkeypatch.setenv("GROQ_API_KEY", "k")
    monkeypatch.setenv("GROQ_MODEL", "")
    monkeypatch.setenv("MONITOR_GROQ_MODEL", "")
    agents.get_monitor_llm()
    assert captured["model"] == "openai/gpt-oss-120b"

    monkeypatch.setenv("MONITOR_GROQ_MODEL", "small-model")
    agents.get_monitor_llm()
    assert captured["model"] == "small-model"
