"""Tests for GitLab provider label mapping."""

import pytest

from spi_agent.gitlab.direct_client import PROVIDER_LABEL_MAPPING


class TestProviderLabelMapping:
    """Test provider to GitLab label mapping."""

    def test_core_maps_to_common_code(self):
        """Test that Core provider maps to Common Code label."""
        assert "Core" in PROVIDER_LABEL_MAPPING
        mapped_labels = PROVIDER_LABEL_MAPPING["Core"]
        assert "Common Code" in mapped_labels
        assert "Core" in mapped_labels  # Fallback

    def test_azure_maps_to_azure(self):
        """Test that Azure provider maps to Azure label."""
        assert "Azure" in PROVIDER_LABEL_MAPPING
        mapped_labels = PROVIDER_LABEL_MAPPING["Azure"]
        assert "Azure" in mapped_labels

    def test_aws_maps_to_aws(self):
        """Test that AWS provider maps to AWS label."""
        assert "AWS" in PROVIDER_LABEL_MAPPING
        mapped_labels = PROVIDER_LABEL_MAPPING["AWS"]
        assert "AWS" in mapped_labels

    def test_gcp_maps_to_gcp(self):
        """Test that GCP provider maps to GCP label."""
        assert "GCP" in PROVIDER_LABEL_MAPPING
        mapped_labels = PROVIDER_LABEL_MAPPING["GCP"]
        assert "GCP" in mapped_labels

    def test_ibm_maps_to_ibm(self):
        """Test that IBM provider maps to IBM label."""
        assert "IBM" in PROVIDER_LABEL_MAPPING
        mapped_labels = PROVIDER_LABEL_MAPPING["IBM"]
        assert "IBM" in mapped_labels

    def test_all_mappings_are_lists(self):
        """Test that all mappings return lists."""
        for provider, labels in PROVIDER_LABEL_MAPPING.items():
            assert isinstance(labels, list), f"{provider} mapping should be a list"
            assert len(labels) > 0, f"{provider} mapping should not be empty"
