"""Shutdown protocol regression tests; no BLE hardware required."""

import unittest
from unittest.mock import AsyncMock

from pycampchef.commands import GrillCommandClient
from pycampchef.const import ModeName, WsId


class ShutdownTests(unittest.IsolatedAsyncioTestCase):
    async def test_requests_only_standby_on_mode_characteristic(self):
        write = AsyncMock()
        read = AsyncMock()
        commands = GrillCommandClient(write, read)

        await commands.shutdown()

        write.assert_awaited_once_with(WsId.MODE, b"\x00")
        read.assert_not_awaited()

    async def test_transport_failure_is_not_swallowed(self):
        write = AsyncMock(side_effect=ConnectionError("link lost"))
        commands = GrillCommandClient(write, AsyncMock())

        with self.assertRaisesRegex(ConnectionError, "link lost"):
            await commands.shutdown()
        self.assertEqual(write.await_count, 1)

    async def test_readback_decodes_zero_valued_standby(self):
        read = AsyncMock(return_value=b"\x00")
        mode = await GrillCommandClient(AsyncMock(), read).read_mode()
        self.assertEqual(mode.mode, ModeName.STANDBY)
        self.assertIsNone(mode.set_temp_f)
        read.assert_awaited_once_with(WsId.MODE)
