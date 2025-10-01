import pytest
from unittest.mock import AsyncMock, patch
from app.services.chat import stream_chat, UNCERTAINTY_PHRASES, CRAWLER_PHRASES
from app.services.model_registry import ModelInfo
from app.config import Settings

async def async_generator_mock(data):
    for item in data:
        yield item

# Mock settings for testing
@pytest.fixture
def mock_settings():
    settings = Settings(
        ollama_base="http://mock-ollama:11434",
        mixtral_api_key="mock-mixtral-key",
        gemini_api_key="mock-gemini-key",
        gpt_oss_api_key="mock-gpt-oss-key",
        gpt_oss_base_url="http://mock-gpt-oss:8080",
        crawler_enabled=True,
    )
    return settings

# Mock ModelInfo for testing
@pytest.fixture
def mock_model_info():
    return ModelInfo(
        id="ollama/test-model",
        provider="ollama",
        capabilities=["chat"],
    )

@pytest.mark.asyncio
async def test_stream_chat_ollama_success(mock_settings, mock_model_info):
    with patch('app.config.get_settings', return_value=mock_settings):
        with patch('app.services.chat._stream_ollama', new_callable=AsyncMock) as mock_stream_ollama:
            mock_stream_ollama.return_value = async_generator_mock(["Hello", " world!"])

            messages = [{'role': 'user', 'content': 'Hi'}]
            chunks = [chunk async for chunk in stream_chat(mock_model_info, "ollama/test-model", messages, stream=True)]

            assert chunks == ["Hello", " world!"]
            mock_stream_ollama.assert_called_once()

@pytest.mark.asyncio
async def test_stream_chat_with_web_search(mock_settings, mock_model_info):
    with patch('app.config.get_settings', return_value=mock_settings):
        with patch('app.services.chat._get_initial_response', new_callable=AsyncMock) as mock_initial_response:
            mock_initial_response.return_value = f"I don't know, but I will search for it. {UNCERTAINTY_PHRASES[0]}"

            with patch('app.services.chat.web_search.search_web', new_callable=AsyncMock) as mock_search_web:
                mock_search_web.return_value = [
                    {"title": "Result 1", "url": "http://example.com/1", "snippet": "Snippet 1"}
                ]
                with patch('app.services.chat._stream_ollama', new_callable=AsyncMock) as mock_stream_ollama:
                    mock_stream_ollama.return_value = (chunk for chunk in ["Web search response."])

                    messages = [{'role': 'user', 'content': 'What is the capital of France?'}]
                    chunks = [chunk async for chunk in stream_chat(mock_model_info, "ollama/test-model", messages, stream=True)]

                    assert "Ich bin mir nicht sicher, aber ich werde im Web danach suchen...\n\n" in chunks
                    assert "Web search response." in chunks
                    mock_search_web.assert_called_once_with('What is the capital of France?')
                    mock_stream_ollama.assert_called_once()

@pytest.mark.asyncio
async def test_stream_chat_with_crawler_tool(mock_settings, mock_model_info):
    with patch('app.config.get_settings', return_value=mock_settings):
        with patch('app.services.chat._get_initial_response', new_callable=AsyncMock) as mock_initial_response:
            mock_initial_response.return_value = ""
            with patch('app.services.chat.crawler_manager.create_job', new_callable=AsyncMock) as mock_create_job:
                mock_create_job.return_value = AsyncMock(id="job123", status="queued", pages_crawled=0, results=[])
                with patch('app.services.chat.crawler_manager.get_job', new_callable=AsyncMock) as mock_get_job:
                    mock_get_job.side_effect = [
                        AsyncMock(id="job123", status="running", pages_crawled=10, results=[]),
                        AsyncMock(id="job123", status="completed", pages_crawled=20, results=["result1"])
                    ]
                    with patch('app.services.chat.crawler_manager.get_result', new_callable=AsyncMock) as mock_get_result:
                        mock_get_result.return_value = AsyncMock(
                            title="Crawled Page",
                            url="http://crawled.com",
                            excerpt="Excerpt from crawled page",
                            extracted_content_ollama="Ollama extracted content"
                        )
                    with patch('app.services.chat._stream_ollama', new_callable=AsyncMock) as mock_stream_ollama:
                        mock_stream_ollama.return_value = (chunk for chunk in ["Crawler response."])

                        messages = [{'role': 'user', 'content': f'Please crawl this website: http://test.com {CRAWLER_PHRASES[0]}'}]
                        chunks = [chunk async for chunk in stream_chat(mock_model_info, "ollama/test-model", messages, stream=True)]

                        assert "Okay, ich werde versuchen, die angeforderten Informationen zu crawlen...\n\n" in chunks
                        assert "Crawl job job123 gestartet. Status: queued. Bitte warten Sie, während ich die Ergebnisse sammle.\n\n" in chunks
                        assert "Crawl job job123 Status: running. Seiten gecrawlt: 10.\n" in chunks
                        assert "Crawl job job123 Status: completed. Seiten gecrawlt: 20.\n" in chunks
                        assert "Crawling abgeschlossen. Ich analysiere die Ergebnisse...\n\n" in chunks
                        assert "Crawler response." in chunks
                        mock_create_job.assert_called_once()
                        mock_get_job.assert_called()
                        mock_get_result.assert_called_once_with("result1")
                        mock_stream_ollama.assert_called_once()
