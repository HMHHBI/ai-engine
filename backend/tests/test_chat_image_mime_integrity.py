from __future__ import annotations

import base64
from unittest.mock import patch, AsyncMock
import pytest

from app.services.chat_service import ChatApplicationService

# Standard valid magic byte signatures
JPEG_BYTES = b"\xff\xd8\xff\xe0\x00\x10JFIF\x00\x01\x01\x01\x00`\x00`\x00\x00" + b"\x00" * 32
PNG_BYTES = b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR" + b"\x00" * 32
WEBP_BYTES = b"RIFF\x24\x00\x00\x00WEBPVP8 " + b"\x00" * 32


@pytest.mark.asyncio
async def test_prepare_chat_turn_accepts_valid_jpeg_and_passes_verified_mime():
    b64 = base64.b64encode(JPEG_BYTES).decode("ascii")
    with patch("app.services.chat_service.upload_image_to_cloud", return_value="https://cloud.com/jpg.jpg") as mock_upload, \
         patch("app.repositories.chat_repo.ChatRepository.prepare_chat_turn", return_value=None):
        await ChatApplicationService.prepare_chat_turn(
            chat_id=1,
            user_id=1,
            content="Hello",
            image_data_list=[b64],
            image_mime_list=["image/jpeg"],
        )
    mock_upload.assert_called_once_with(b64, "chat_messages", "image/jpeg")


@pytest.mark.asyncio
async def test_prepare_chat_turn_accepts_valid_png_and_passes_verified_mime():
    b64 = base64.b64encode(PNG_BYTES).decode("ascii")
    with patch("app.services.chat_service.upload_image_to_cloud", return_value="https://cloud.com/png.png") as mock_upload, \
         patch("app.repositories.chat_repo.ChatRepository.prepare_chat_turn", return_value=None):
        await ChatApplicationService.prepare_chat_turn(
            chat_id=1,
            user_id=1,
            content="Hello",
            image_data_list=[b64],
            image_mime_list=["image/png"],
        )
    mock_upload.assert_called_once_with(b64, "chat_messages", "image/png")


@pytest.mark.asyncio
async def test_prepare_chat_turn_accepts_valid_webp_and_passes_verified_mime():
    b64 = base64.b64encode(WEBP_BYTES).decode("ascii")
    with patch("app.services.chat_service.upload_image_to_cloud", return_value="https://cloud.com/webp.webp") as mock_upload, \
         patch("app.repositories.chat_repo.ChatRepository.prepare_chat_turn", return_value=None):
        await ChatApplicationService.prepare_chat_turn(
            chat_id=1,
            user_id=1,
            content="Hello",
            image_data_list=[b64],
            image_mime_list=["image/webp"],
        )
    mock_upload.assert_called_once_with(b64, "chat_messages", "image/webp")


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "declared_mime,actual_bytes",
    [
        ("image/jpeg", PNG_BYTES),
        ("image/png", JPEG_BYTES),
        ("image/webp", JPEG_BYTES),
    ],
)
async def test_prepare_chat_turn_rejects_mime_content_mismatch_without_upload(declared_mime, actual_bytes):
    b64 = base64.b64encode(actual_bytes).decode("ascii")
    with patch("app.services.chat_service.upload_image_to_cloud") as mock_upload:
        with pytest.raises(ValueError, match="Image content does not match its declared type"):
            await ChatApplicationService.prepare_chat_turn(
                chat_id=1,
                user_id=1,
                content="Hello",
                image_data_list=[b64],
                image_mime_list=[declared_mime],
            )
    mock_upload.assert_not_called()


@pytest.mark.asyncio
async def test_prepare_chat_turn_rejects_fake_image_bytes():
    fake_bytes = b"this is not an image"
    b64 = base64.b64encode(fake_bytes).decode("ascii")
    with patch("app.services.chat_service.upload_image_to_cloud") as mock_upload:
        with pytest.raises(ValueError, match="Image content does not match its declared type"):
            await ChatApplicationService.prepare_chat_turn(
                chat_id=1,
                user_id=1,
                content="Hello",
                image_data_list=[b64],
                image_mime_list=["image/jpeg"],
            )
    mock_upload.assert_not_called()


@pytest.mark.asyncio
async def test_prepare_chat_turn_rejects_invalid_base64():
    with patch("app.services.chat_service.upload_image_to_cloud") as mock_upload:
        with pytest.raises(ValueError, match="Invalid image base64 data"):
            await ChatApplicationService.prepare_chat_turn(
                chat_id=1,
                user_id=1,
                content="Hello",
                image_data_list=["!!!not-base-64!!!"],
                image_mime_list=["image/jpeg"],
            )
    mock_upload.assert_not_called()


@pytest.mark.asyncio
async def test_prepare_chat_turn_rejects_empty_decoded_bytes():
    empty_b64 = ""
    with patch("app.services.chat_service.upload_image_to_cloud") as mock_upload:
        with pytest.raises(ValueError):
            await ChatApplicationService.prepare_chat_turn(
                chat_id=1,
                user_id=1,
                content="Hello",
                image_data_list=[empty_b64],
                image_mime_list=["image/jpeg"],
            )
    mock_upload.assert_not_called()
