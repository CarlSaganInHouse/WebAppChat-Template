"""
Tests for provider abstractions.

Tests cover:
- OpenAI provider (chat, streaming, usage)
- Ollama provider (chat, streaming, usage)
- Embedding provider
- Error handling
- Tool support
"""

import pytest
from unittest.mock import Mock, MagicMock, patch
from providers.openai_provider import OpenAIProvider
from providers.ollama_provider import OllamaProvider
from providers.embedding_provider import OpenAIEmbeddingProvider


class TestOpenAIProvider:
    """Test OpenAI provider implementation"""

    def test_initialization(self):
        """Test provider initializes with API key"""
        provider = OpenAIProvider(api_key="test-key")
        assert provider.client is not None

    def test_chat_completion_basic(self):
        """Test non-streaming chat completion"""
        provider = OpenAIProvider(api_key="test-key")

        # Mock the OpenAI client response
        mock_response = Mock()
        mock_response.choices = [Mock()]
        mock_response.choices[0].message.content = "Hello!"
        mock_response.usage = Mock(prompt_tokens=10, completion_tokens=5)

        with patch.object(provider.client.chat.completions, 'create', return_value=mock_response):
            messages = [{"role": "user", "content": "Hi"}]
            response = provider.chat_completion(messages, model="gpt-4")

            assert response is not None
            assert response.choices[0].message.content == "Hello!"

    def test_chat_completion_with_temperature(self):
        """Test chat completion with custom temperature"""
        provider = OpenAIProvider(api_key="test-key")
        mock_response = Mock()

        with patch.object(provider.client.chat.completions, 'create', return_value=mock_response) as mock_create:
            messages = [{"role": "user", "content": "Hi"}]
            provider.chat_completion(messages, model="gpt-4", temperature=0.5)

            # Verify temperature was passed
            call_kwargs = mock_create.call_args.kwargs
            assert call_kwargs['temperature'] == 0.5

    def test_chat_completion_with_max_tokens(self):
        """Test chat completion with max_tokens"""
        provider = OpenAIProvider(api_key="test-key")
        mock_response = Mock()

        with patch.object(provider.client.chat.completions, 'create', return_value=mock_response) as mock_create:
            messages = [{"role": "user", "content": "Hi"}]
            provider.chat_completion(messages, model="gpt-4", max_tokens=100)

            call_kwargs = mock_create.call_args.kwargs
            assert call_kwargs['max_tokens'] == 100

    def test_chat_completion_with_tools(self):
        """Test chat completion with tool/function calling"""
        provider = OpenAIProvider(api_key="test-key")
        mock_response = Mock()

        tools = [{"type": "function", "function": {"name": "test"}}]

        with patch.object(provider.client.chat.completions, 'create', return_value=mock_response) as mock_create:
            messages = [{"role": "user", "content": "Hi"}]
            provider.chat_completion(
                messages,
                model="gpt-4",
                tools=tools,
                tool_choice="auto"
            )

            call_kwargs = mock_create.call_args.kwargs
            assert call_kwargs['tools'] == tools
            assert call_kwargs['tool_choice'] == "auto"

    def test_stream_chat_completion(self):
        """Test streaming chat completion"""
        provider = OpenAIProvider(api_key="test-key")

        # Mock streaming response
        mock_chunks = [
            Mock(choices=[Mock(delta=Mock(content="Hello"))]),
            Mock(choices=[Mock(delta=Mock(content=" world"))]),
        ]

        with patch.object(provider.client.chat.completions, 'create', return_value=iter(mock_chunks)):
            messages = [{"role": "user", "content": "Hi"}]
            stream = provider.stream_chat_completion(messages, model="gpt-4")

            chunks = list(stream)
            assert len(chunks) == 2

    def test_get_usage_with_valid_response(self):
        """Test extracting usage from response"""
        provider = OpenAIProvider(api_key="test-key")

        mock_response = Mock()
        mock_response.usage = Mock(prompt_tokens=10, completion_tokens=20)

        input_tokens, output_tokens = provider.get_usage(mock_response)
        assert input_tokens == 10
        assert output_tokens == 20

    def test_get_usage_without_usage_info(self):
        """Test get_usage returns zeros when usage info missing"""
        provider = OpenAIProvider(api_key="test-key")

        mock_response = Mock(spec=[])  # No usage attribute

        input_tokens, output_tokens = provider.get_usage(mock_response)
        assert input_tokens == 0
        assert output_tokens == 0

    def test_supports_tools(self):
        """Test that OpenAI provider supports tools"""
        provider = OpenAIProvider(api_key="test-key")
        assert provider.supports_tools() is True


class TestOllamaProvider:
    """Test Ollama provider implementation"""

    def test_initialization(self):
        """Test provider initializes with host"""
        provider = OllamaProvider(host="http://localhost:11434")
        assert provider.host == "http://localhost:11434"

    def test_initialization_default_host(self):
        """Test provider uses default host"""
        provider = OllamaProvider()
        assert provider.host == "http://localhost:11434"

    def test_chat_completion_basic(self):
        """Test non-streaming chat completion"""
        provider = OllamaProvider()

        mock_response = {
            "message": {"role": "assistant", "content": "Hello!"},
            "prompt_eval_count": 10,
            "eval_count": 5
        }

        with patch('ollama.chat', return_value=mock_response):
            messages = [{"role": "user", "content": "Hi"}]
            response = provider.chat_completion(messages, model="llama3")

            assert response is not None
            assert response["message"]["content"] == "Hello!"

    def test_chat_completion_with_temperature(self):
        """Test chat completion with custom temperature"""
        provider = OllamaProvider()

        with patch('ollama.chat', return_value={}) as mock_chat:
            messages = [{"role": "user", "content": "Hi"}]
            provider.chat_completion(messages, model="llama3", temperature=0.5)

            call_kwargs = mock_chat.call_args.kwargs
            assert call_kwargs['options']['temperature'] == 0.5

    def test_chat_completion_with_max_tokens(self):
        """Test chat completion with max_tokens (mapped to num_predict)"""
        provider = OllamaProvider()

        with patch('ollama.chat', return_value={}) as mock_chat:
            messages = [{"role": "user", "content": "Hi"}]
            provider.chat_completion(messages, model="llama3", max_tokens=100)

            call_kwargs = mock_chat.call_args.kwargs
            assert call_kwargs['options']['num_predict'] == 100

    def test_chat_completion_with_tools_raises_error(self):
        """Test that tools raise NotImplementedError"""
        provider = OllamaProvider()

        tools = [{"type": "function", "function": {"name": "test"}}]
        messages = [{"role": "user", "content": "Hi"}]

        with pytest.raises(NotImplementedError, match="does not support tool"):
            provider.chat_completion(messages, model="llama3", tools=tools)

    def test_stream_chat_completion(self):
        """Test streaming chat completion"""
        provider = OllamaProvider()

        mock_chunks = [
            {"message": {"content": "Hello"}},
            {"message": {"content": " world"}},
        ]

        with patch('ollama.chat', return_value=iter(mock_chunks)):
            messages = [{"role": "user", "content": "Hi"}]
            stream = provider.stream_chat_completion(messages, model="llama3")

            chunks = list(stream)
            assert len(chunks) == 2

    def test_get_usage_with_valid_response(self):
        """Test extracting usage from Ollama response"""
        provider = OllamaProvider()

        response = {
            "prompt_eval_count": 15,
            "eval_count": 25
        }

        input_tokens, output_tokens = provider.get_usage(response)
        assert input_tokens == 15
        assert output_tokens == 25

    def test_get_usage_without_usage_info(self):
        """Test get_usage returns zeros when usage info missing"""
        provider = OllamaProvider()

        response = {"message": {"content": "Hello"}}  # No token counts

        input_tokens, output_tokens = provider.get_usage(response)
        assert input_tokens == 0
        assert output_tokens == 0

    def test_get_usage_with_non_dict_response(self):
        """Test get_usage handles non-dict responses"""
        provider = OllamaProvider()

        response = "invalid response"

        input_tokens, output_tokens = provider.get_usage(response)
        assert input_tokens == 0
        assert output_tokens == 0

    def test_supports_tools(self):
        """Test that Ollama provider does not support tools"""
        provider = OllamaProvider()
        assert provider.supports_tools() is False


class TestOpenAIEmbeddingProvider:
    """Test OpenAI embedding provider"""

    def test_initialization(self):
        """Test provider initializes with API key and model"""
        provider = OpenAIEmbeddingProvider(api_key="test-key", model="text-embedding-3-small")
        assert provider.client is not None
        assert provider.model == "text-embedding-3-small"

    def test_initialization_default_model(self):
        """Test provider uses default model"""
        provider = OpenAIEmbeddingProvider(api_key="test-key")
        assert provider.model == "text-embedding-3-small"

    def test_embed_texts_success(self):
        """Test successful text embedding"""
        provider = OpenAIEmbeddingProvider(api_key="test-key")

        # Mock OpenAI response
        mock_response = Mock()
        mock_response.data = [
            Mock(embedding=[0.1, 0.2, 0.3]),
            Mock(embedding=[0.4, 0.5, 0.6]),
        ]

        with patch.object(provider.client.embeddings, 'create', return_value=mock_response):
            texts = ["Hello", "World"]
            embeddings = provider.embed_texts(texts)

            assert len(embeddings) == 2
            assert embeddings[0] == [0.1, 0.2, 0.3]
            assert embeddings[1] == [0.4, 0.5, 0.6]

    def test_embed_texts_empty_list_raises_error(self):
        """Test that empty text list raises ValueError"""
        provider = OpenAIEmbeddingProvider(api_key="test-key")

        with pytest.raises(ValueError, match="Cannot embed empty text list"):
            provider.embed_texts([])

    def test_get_model_name(self):
        """Test getting model name"""
        provider = OpenAIEmbeddingProvider(api_key="test-key", model="text-embedding-3-large")
        assert provider.get_model_name() == "text-embedding-3-large"

    def test_get_dimension_known_model(self):
        """Test getting dimension for known model"""
        provider = OpenAIEmbeddingProvider(api_key="test-key", model="text-embedding-3-small")
        assert provider.get_dimension() == 1536

    def test_get_dimension_unknown_model(self):
        """Test getting dimension for unknown model returns default"""
        provider = OpenAIEmbeddingProvider(api_key="test-key", model="unknown-model")
        assert provider.get_dimension() == 1536  # Default
