"""Integration tests for Qdrant vector storage."""
import pytest


@pytest.mark.integration
class TestQdrantVectors:
    def test_vector_insertion(self):
        pytest.skip("Requires Qdrant service")

    def test_similarity_search(self):
        pytest.skip("Requires Qdrant service")

    def test_collection_per_customer(self):
        pytest.skip("Requires Qdrant service")
