"""
Tests for cryptographic integrity helpers (app/crypto.py).
"""
import pytest

from app.crypto import (
    generate_api_key,
    hash_api_key,
    hash_content,
    sign_content,
    verify_signature,
)


class TestHashContent:
    def test_returns_64_char_hex(self):
        result = hash_content("hello")
        assert len(result) == 64
        assert all(c in "0123456789abcdef" for c in result)

    def test_deterministic(self):
        assert hash_content("same") == hash_content("same")

    def test_different_inputs_produce_different_hashes(self):
        assert hash_content("foo") != hash_content("bar")

    def test_empty_string(self):
        # SHA-256 of "" is a known value
        assert hash_content("") == (
            "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"
        )


class TestSignAndVerify:
    def test_valid_signature_verifies(self):
        sig = sign_content("hello", "secret")
        assert verify_signature("hello", sig, "secret") is True

    def test_wrong_key_fails(self):
        sig = sign_content("hello", "secret")
        assert verify_signature("hello", sig, "wrong_secret") is False

    def test_tampered_content_fails(self):
        sig = sign_content("hello", "secret")
        assert verify_signature("tampered", sig, "secret") is False

    def test_empty_content(self):
        sig = sign_content("", "key")
        assert verify_signature("", sig, "key") is True


class TestGenerateAndHashApiKey:
    def test_generate_returns_64_char_hex(self):
        key = generate_api_key()
        assert len(key) == 64
        assert all(c in "0123456789abcdef" for c in key)

    def test_generate_is_unique(self):
        assert generate_api_key() != generate_api_key()

    def test_hash_api_key_deterministic(self):
        assert hash_api_key("mykey") == hash_api_key("mykey")

    def test_hash_api_key_returns_64_chars(self):
        assert len(hash_api_key("mykey")) == 64
