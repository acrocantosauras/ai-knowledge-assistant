from app.config import Settings


def test_log_level_is_normalized_to_uppercase() -> None:
    settings = Settings(log_level="Info")

    assert settings.log_level == "INFO"
