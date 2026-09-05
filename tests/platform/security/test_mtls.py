from pathlib import Path
from unittest.mock import patch

import pytest

from backend.platform.security.mtls import MtlsClientConfig, MtlsConfigurationError


def _config(tmp_path: Path) -> MtlsClientConfig:
    paths = []
    for name in ("ca.pem", "client.pem", "client.key"):
        path = tmp_path / name
        path.write_text("placeholder", encoding="utf-8")
        paths.append(str(path))
    return MtlsClientConfig(
        ca_bundle=paths[0],
        client_cert=paths[1],
        client_key=paths[2],
        timeout_seconds=7.5,
    )


def test_mtls_config_builds_clients_with_explicit_ca_and_client_certificate(tmp_path: Path) -> None:
    config = _config(tmp_path)
    with (
        patch("backend.platform.security.mtls.httpx.AsyncClient") as async_client,
        patch("backend.platform.security.mtls.httpx.Client") as sync_client,
    ):
        config.build_async_client()
        config.build_sync_client()

    async_client.assert_called_once_with(
        verify=config.ca_bundle,
        cert=(config.client_cert, config.client_key),
        timeout=config.timeout_seconds,
    )
    sync_client.assert_called_once_with(
        verify=config.ca_bundle,
        cert=(config.client_cert, config.client_key),
        timeout=config.timeout_seconds,
    )


def test_mtls_config_rejects_relative_or_missing_certificate_paths(tmp_path: Path) -> None:
    with pytest.raises(MtlsConfigurationError, match="MUST_BE_ABSOLUTE"):
        MtlsClientConfig("ca.pem", "client.pem", "client.key")

    missing = tmp_path / "missing.pem"
    with pytest.raises(MtlsConfigurationError, match="NOT_FOUND"):
        MtlsClientConfig(str(missing), str(missing), str(missing))


def test_mtls_config_rejects_non_positive_timeout(tmp_path: Path) -> None:
    config = _config(tmp_path)
    with pytest.raises(MtlsConfigurationError, match="TIMEOUT_MUST_BE_POSITIVE"):
        MtlsClientConfig(
            config.ca_bundle,
            config.client_cert,
            config.client_key,
            timeout_seconds=0,
        )
