# Copyright 2021 Kamil Sroka
# Copyright 2021 Holger Pieta

# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at

#     http://www.apache.org/licenses/LICENSE-2.0

# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

import asyncio
from datetime import datetime
import traceback
import random
import logging
logger = logging.getLogger(__name__)
logger.setLevel( logging.DEBUG )

from toshiba_ac.http_api import ToshibaAcHttpApi
from toshiba_ac.amqp_api import ToshibaAcAmqpApi
from toshiba_ac.device import ToshibaAcDevice
from toshiba_ac.utils import async_sleep_until_next_multiply_of_minutes

class ToshibaAcDeviceManager:
    FETCH_ENERGY_CONSUMPTION_PERIOD_MINUTES = 10

    def __init__( self, loop, username, password, device_id=None, sas_token=None, use_power = False ):
        self.loop = loop
        self.username = username
        self.password = password
        self.http_api = None
        self.reg_info = None
        self.amqp_api = None
        self.device_id = self.username + '_' + (device_id or '3e6e4eb5f0e5aa46')
        self.sas_token = sas_token
        self.devices = {}
        self.periodic_fetch_energy_consumption_task = None
        self.use_power = use_power
        self.lock = asyncio.Lock()

    async def connect(self):
        async with self.lock:
            if not self.http_api:
                try:
                    self.http_api = ToshibaAcHttpApi(self.username, self.password)

                    await self.http_api.connect()

                    if not self.sas_token:
                        self.sas_token = await self.http_api.register_client(self.device_id)

                    self.amqp_api = ToshibaAcAmqpApi(self.sas_token)
                    self.amqp_api.register_command_handler('CMD_FCU_FROM_AC', self.handle_cmd_fcu_from_ac)
                    self.amqp_api.register_command_handler('CMD_HEARTBEAT', self.handle_cmd_heartbeat)
                    await self.amqp_api.connect()

                except BaseException as err:
                    logger.error( 'Something failed while connecting: %s' % err )
                    traceback.print_exc()
                    logger.warning( 'Shutting down' )
                    await self.shutdown()
                    raise

            return self.sas_token

    async def shutdown(self):
        logger.debug( 'Shutting down. Getting lock...' )
        async with self.lock:
            logger.debug( '...got lock' )
            if self.periodic_fetch_energy_consumption_task:
                logger.debug( 'Canceling energy tasks...' )
                self.periodic_fetch_energy_consumption_task.cancel()

            logger.debug( 'Shutting down devices...' )
            await asyncio.gather(*[device.shutdown() for device in self.devices.values()])

            if self.amqp_api:
                logger.debug( 'Shutting down AMQP...' )
                await self.amqp_api.shutdown()
                self.amqp_api = None

            if self.http_api:
                logger.debug( 'Shutting down HTTP...' )
                await self.http_api.shutdown()
                self.http_api = None
        logger.debug( 'Shutdown complete' )

    async def periodic_fetch_energy_consumption(self):
        while True:
            if self.use_power:
                await self.fetch_energies_for_power()
            else:
                await self.fetch_energy_consumption()
            delay = self.FETCH_ENERGY_CONSUMPTION_PERIOD_MINUTES * 60 + random.randint( -10, 10 )
            logger.debug( f'Fetch energy sleeping for {delay} seconds.')
            await asyncio.sleep( delay )

    async def fetch_energy_consumption(self):
        consumptions = await self.http_api.get_devices_energy_consumption( [ac_unique_id for ac_unique_id in self.devices.keys()] )

        logger.debug(f'Power consumption for devices: {consumptions}')

        updates = []

        for ac_unique_id, consumption in consumptions.items():
            update = self.devices[ac_unique_id].handle_update_ac_energy_consumption(consumption)
            updates.append(update)

        await asyncio.gather(*updates)

    async def fetch_energies_for_power(self):
        consumptions = await self.http_api.get_devices_energy_consumption( [ac_unique_id for ac_unique_id in self.devices.keys()], offset_days=0, total=False )
        logger.debug(f'Energy consumption for devices: {consumptions}')
        if datetime.now().hour == 0:
            logger.debug(f'Need more data because we changed days.')
            consumptions_before = await self.http_api.get_devices_energy_consumption( [ac_unique_id for ac_unique_id in self.devices.keys()], offset_days=1, total=False )
            logger.debug(f'Day before power consumption for devices: {consumptions_before}')
        else:
            consumptions_before = None

        updates = []
        for ac_unique_id, consumption in consumptions.items():
            if consumptions_before is None:
                consumption_before = None
            else:
                consumption_before = consumptions_before[ ac_unique_id ]
            update = self.devices[ac_unique_id].handle_update_ac_power( consumption_before, consumption )
            updates.append(update)
        await asyncio.gather(*updates)

    async def get_devices(self):
        async with self.lock:
            if not self.devices:
                devices_info = await self.http_api.get_devices()

                logger.debug(f'Found devices: {devices_info}')

                connects = []

                for device_info in devices_info:
                    device = ToshibaAcDevice(
                        device_info.ac_name,
                        self.device_id,
                        device_info.ac_id,
                        device_info.ac_unique_id,
                        device_info.initial_ac_state,
                        device_info.firmware_version,
                        device_info.merit_feature,
                        device_info.ac_model_id,
                        self.amqp_api,
                        self.http_api
                    )

                    connects.append(device.connect())

                    logger.debug(f'Adding device {device!r}')

                    self.devices[device.ac_unique_id] = device

                await asyncio.gather(*connects)

                if not self.periodic_fetch_energy_consumption_task:
                    self.periodic_fetch_energy_consumption_task = asyncio.create_task( self.periodic_fetch_energy_consumption() )

            return list(self.devices.values())

    def handle_cmd_fcu_from_ac(self, source_id, message_id, target_id, payload, timestamp):
        asyncio.run_coroutine_threadsafe(self.devices[source_id].handle_cmd_fcu_from_ac(payload), self.loop)

    def handle_cmd_heartbeat(self, source_id, message_id, target_id, payload, timestamp):
        asyncio.run_coroutine_threadsafe(self.devices[source_id].handle_cmd_heartbeat(payload), self.loop)
