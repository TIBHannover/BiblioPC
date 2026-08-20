import asyncio
import httpx
import logging
from typing import Tuple, Optional
from auth_base import BaseAuthModule
from config import settings

logger = logging.getLogger("auth_gbv")

class GBVAuthModule(BaseAuthModule):
    def __init__(self):
        # Basis-URL kommt aus der .env-Datei
        self.base_url = settings.paia_base_url

    async def authenticate_user(self, bn: str, pw: str):
        url = f"{self.base_url}/auth/login"
        data = {"username": bn, "password": pw, "grant_type": "password"}
        retries = 3
        backoff = 0.5

        async with httpx.AsyncClient() as client:
            for attempt in range(retries):
                try:
                    response = await client.post(url, json=data, timeout=5.0)
                    if response.status_code == 200:
                        token = response.json().get("access_token")
                        if token:
                            return True, token
                        return False, None
                    # For 4xx errors don't retry
                    if 400 <= response.status_code < 500:
                        return False, None
                    # For 5xx, allow retry
                except httpx.RequestError as e:
                    logger.exception("GBV authenticate_user network error for bn=%s: %s", bn, e)
                    # network error -> retry
                    if attempt < retries - 1:
                        await asyncio.sleep(backoff)
                        backoff *= 2
                        continue
                    return False, None
                # if we reach here, it was a 5xx; retry if attempts left
                if attempt < retries - 1:
                    await asyncio.sleep(backoff)
                    backoff *= 2
                    continue
        return False, None

    async def check_borrower_status(self, bn: str, token: Optional[str]) -> Optional[int]:
        if not token:
            return 1 # Ohne Token standardmäßig als "gesperrt/Fehler" werten
            
        url = f"{self.base_url}/core/{bn}"
        headers = {"Accept": "application/json", "Authorization": f"Bearer {token}"}
        retries = 3
        backoff = 0.5

        async with httpx.AsyncClient() as client:
            for attempt in range(retries):
                try:
                    response = await client.get(url, headers=headers, timeout=5.0)
                    if response.status_code == 200:
                        return response.json().get("status")
                    # 4xx -> likely bad token / auth issue
                    if 400 <= response.status_code < 500:
                        return None
                    # 5xx -> retry
                except httpx.RequestError as e:
                    logger.exception("GBV check_borrower_status network error for bn=%s: %s", bn, e)
                    # Network-related error -> retry
                    if attempt < retries - 1:
                        await asyncio.sleep(backoff)
                        backoff *= 2
                        continue
                    # After retries exhausted, return sentinel to indicate backend failure
                    return -1
                # if 5xx and attempts left, sleep and retry
                if attempt < retries - 1:
                    await asyncio.sleep(backoff)
                    backoff *= 2
                    continue
        # Exhausted retries without success: indicate backend failure
        return -1
            