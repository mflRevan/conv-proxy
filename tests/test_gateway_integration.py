import asyncio
import pytest

from src.config import AppConfig
from src.gateway.client import GatewayClient, GatewayConfig


@pytest.mark.asyncio
async def test_gateway_create_session_and_send():
    cfg = AppConfig.from_env()
    assert cfg.gateway_token, "GATEWAY_TOKEN missing"

    client = GatewayClient(GatewayConfig(
        url=cfg.gateway_url,
        token=cfg.gateway_token,
        origin=cfg.gateway_origin,
    ))

    async def run():
        task = asyncio.create_task(client.connect())
        await client.wait_connected(10)

        agents = await client.list_agents()
        agent_ids = [a.id for a in agents]
        assert 'mule' in agent_ids, "Expected mule agent"

        # Create a new mule session
        created = await client.create_session('mule', message='hello mule')
        session_key = created.get('sessionKey')
        assert session_key and session_key.startswith('agent:mule:'), session_key

        # Send a message to the new session
        await client.send_message(session_key, "sanity check")

        # Fetch history
        history = await client.get_history(session_key, limit=5)
        assert isinstance(history, list)

        await client.disconnect()
        task.cancel()
        try:
            await task
        except Exception:
            pass

    await run()
