# Copyright 2022 Kamil Sroka, Holger Pieta

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
import datetime
import struct
import random
from enum import Enum
import logging
logger = logging.getLogger(__name__)
logger.setLevel( logging.INFO )

from toshiba_ac.fcu_state import ToshibaAcFcuState, _NONE_VAL
from toshiba_ac.utils import async_sleep_until_next_multiply_of_minutes

from azure.iot.device import Message
from dataclasses import dataclass

class ToshibaAcDeviceError(Exception):
    pass

@dataclass
class ToshibaAcDeviceEnergyConsumption:
    energy_wh: float
    since: datetime.datetime

class ToshibaAcDeviceCallback:
    def __init__(self):
        self.callbacks = []

    def add(self, callback):
        if callback not in self.callbacks:
            self.callbacks.append(callback)
            return True

        return False

    def remove(self, callback):
        if callback in self.callbacks:
            self.callbacks.remove(callback)
            return True

        return False

    async def __call__(self, *args, **kwargs):
        for callback in self.callbacks:
            asyncs = []
            if asyncio.iscoroutinefunction(callback):
                asyncs.append(callback(*args, **kwargs))
            else:
                callback(*args, **kwargs)

            await asyncio.gather(*asyncs)

class ToshibaAcDevice:
    STATE_RELOAD_PERIOD_MINUTES = 5

    def __init__(self, name, device_id, ac_id, ac_unique_id, initial_ac_state, firmware_version, merit_feature, ac_model_id, amqp_api, http_api):
        self.name = name
        self.device_id = device_id
        self.ac_id = ac_id
        self.ac_unique_id = ac_unique_id
        self.firmware_version = firmware_version
        self.amqp_api = amqp_api
        self.http_api = http_api

        self.cdu = None
        self.fcu = None
        self._supported_merit_a_features = None
        self._supported_merit_b_features = None
        self._is_pure_ion_supported = None
        self._on_state_changed_callback = ToshibaAcDeviceCallback()
        self._on_energy_consumption_changed_callback = ToshibaAcDeviceCallback()
        self._ac_energy_consumption = None
        self._on_power_changed_callback = ToshibaAcDeviceCallback()
        self._ac_power = None
        self._ac_last_energy = None
        self._ac_last_power_update = None

        self.load_supported_merit_features(merit_feature, ac_model_id)

        self.initial_ac_state = initial_ac_state

        self.periodic_reload_state_task = None

    async def connect(self):
        self.fcu_state = ToshibaAcFcuState.from_hex_state( self.initial_ac_state )
        self.fcu_state.name = self.name
        self.fcu_state_delta = self.fcu_state
        await self.load_additional_device_info()
        await self.state_changed()
        self.periodic_reload_state_task = asyncio.create_task(self.periodic_state_reload())

    async def shutdown(self):
        if self.periodic_reload_state_task is not None:
            self.periodic_reload_state_task.cancel()

    async def load_additional_device_info(self):
        additional_info = await self.http_api.get_device_additional_info(self.ac_id)
        self.cdu = additional_info.cdu
        self.fcu = additional_info.fcu

    def load_supported_merit_features(self, merit_feature_hexstring, ac_model_id):
        try:
            merit_byte, = struct.unpack('b', bytes.fromhex(merit_feature_hexstring[:2]))
        except (TypeError, ValueError, struct.error):
            ac_model_id = '1'

        supported_a_features = [ToshibaAcFcuState.AcMeritAFeature.OFF]
        supported_b_features = [ToshibaAcFcuState.AcMeritBFeature.OFF]
        pure_ion = False

        if ac_model_id != '1':
            supported_a_features.append(ToshibaAcFcuState.AcMeritAFeature.HIGH_POWER)
            supported_a_features.append(ToshibaAcFcuState.AcMeritAFeature.ECO)

            floor, _, cdu_silent, pure_ion, fireplace, heating_8c, _, _ = struct.unpack('????????', bytes.fromhex('0' + '0'.join(f'{merit_byte:08b}')))

            if floor:
                supported_a_features.append(ToshibaAcFcuState.AcMeritAFeature.FLOOR)

            if cdu_silent:
                supported_a_features.append(ToshibaAcFcuState.AcMeritAFeature.CDU_SILENT_1)
                supported_a_features.append(ToshibaAcFcuState.AcMeritAFeature.CDU_SILENT_2)

            if fireplace:
                supported_b_features.append(ToshibaAcFcuState.AcMeritBFeature.FIREPLACE_1)
                supported_b_features.append(ToshibaAcFcuState.AcMeritBFeature.FIREPLACE_2)

            if heating_8c:
                supported_a_features.append(ToshibaAcFcuState.AcMeritAFeature.HEATING_8C)

        self._supported_merit_a_features = supported_a_features
        self._supported_merit_b_features = supported_b_features
        self._is_pure_ion_supported = pure_ion

        logger.debug(
            '[{}] Supported merit A features: {}. Supported merit B features: {}. Pure ION supported: {}'.format(
                self.name,
                ", ".join(f.name.title().replace("_", " ") for f in supported_a_features),
                ", ".join(f.name.title().replace("_", " ") for f in supported_b_features),
                pure_ion
            )
        )

    async def periodic_state_reload(self):
        while True:
            delay = self.STATE_RELOAD_PERIOD_MINUTES * 60 + random.randint( -10, 10 )
            logger.debug( f'State reload sleeping for {delay} seconds.')
            await asyncio.sleep( delay )
            await self.request_state_update()

    async def state_reload(self):
        hex_state = await self.http_api.get_device_state(self.ac_id)
        logger.debug(f'[{self.name}] AC state from HTTP: {hex_state}')
        await self.handle_hex_state_update( hex_state )

    async def handle_hex_state_update( self, hex_state ):
        state_update = self.fcu_state.update(hex_state)
        await self.handle_state_update( state_update )

    async def handle_state_update( self, state_update ):
        if state_update:
            self.fcu_state_delta = state_update
            await self.state_changed()

    async def state_changed(self):
        logger.info(f'[{self.name}] Current state: {self.fcu_state}')
        await self.on_state_changed_callback(self)

    async def handle_cmd_fcu_from_ac(self, payload):
        logger.debug(f'[{self.name}] AC state from AMQP: {payload["data"]}')
        await self.handle_hex_state_update( payload['data'] )

    async def handle_cmd_heartbeat(self, payload):
        hb_data = {k : int(v, base=16) for k, v in payload.items()}
        logger.debug(f'[{self.name}] AC heartbeat from AMQP: {hb_data}')
        state_update = ToshibaAcFcuState()
        state_update.ac_indoor_temperature = hb_data[ 'iTemp' ]
        state_update.ac_outdoor_temperature = hb_data[ 'oTemp' ]
        state_update.ac_heatexc_in_temperature = hb_data[ 'fcuTcTemp' ]
        state_update.ac_pipe_in_temperature = hb_data[ 'fcuTcjTemp' ]
        state_update.ac_fan_in_rpm = hb_data[ 'fcuFanRpm' ]
        state_update.ac_comp_out_temperature = hb_data[ 'cduTdTemp' ]
        state_update.ac_comp_in_temperature = hb_data[ 'cduTsTemp' ]
        state_update.ac_heatexc_out_temperature = hb_data[ 'cduTeTemp' ]
        state_update.ac_comp_freq = hb_data[ 'cduCompHz' ]
        state_update.ac_fan_out_rpm = hb_data[ 'cduFanRpm' ]
        state_update.ac_pwm_valve_duty = hb_data[ 'cduPmvPulse' ]
        state_update.ac_iac = hb_data[ 'cduIac' ]
        state_delta = self.fcu_state.update_state( state_update )
        await self.handle_state_update( state_delta )


    async def handle_update_ac_energy_consumption(self, val):
        if self._ac_energy_consumption != val:
            self._ac_energy_consumption = val

            logger.info(f'[{self.name}] Energy consumption: {val}')

            await self.on_energy_consumption_changed_callback(self)

    async def handle_update_ac_power( self, consumption_before, consumption ):
        now = datetime.datetime.now()
        hour = now.hour
        # Get energy from current hour
        current_energy = consumption[hour]['Energy']
        # If hour is 0 we have to look at yesterday
        if hour == 0:
            # For some reasons no data for yesterday
            if consumption_before is None:
                previous_energy = 0
            else:
                # Get last energy from yesterday
                previous_energy = consumption_before[-1]['Energy']
        else:
            # Get energy from last hour
            previous_energy = consumption[hour-1]['Energy']
        # Special handling of first call
        if self._ac_last_energy is None:
            # Take energy of last hour
            energy = current_energy
            # Seconds since start of current hour
            delta_second = now.minute * 60 + now.second
        else:
            # Special handling if we switched hours
            if hour != self._ac_last_power_update.hour:
                # Use final value of last hour, subtract last stored state then add current hour
                energy = previous_energy - self._ac_last_energy + current_energy
            else:
                # Just use current value minus stored value
                energy = current_energy - self._ac_last_energy
            # Seconds since last call
            delta_t = now - self._ac_last_power_update
            delta_second = delta_t.total_seconds()
        # Energy from Wh to J
        energy *= 3600
        # Calculate power in W
        self._ac_power = energy / delta_second
        # Store last energy for next call
        self._ac_last_energy = current_energy
        # Store time of this call for next call
        self._ac_last_power_update = now
        logger.info(f'[{self.name}] Power updated: {self._ac_power} W')
        await self.on_power_changed_callback(self)

    async def request_state_update( self ):
        logger.debug( f"{self.name}: Requesting status" )
        cmd = {
            'sourceId': self.device_id,
            'messageId': '0000000',
            'targetId': [self.ac_unique_id],
            'cmd': 'CMD_GET_STATUS',
            'payload': {},
            'timeStamp': '0000000'
        }
        await self.send_command_to_ac( cmd )

    def create_cmd_fcu_to_ac(self, hex_state):
        return {
            'sourceId': self.device_id,
            'messageId': '0000000',
            'targetId': [self.ac_unique_id],
            'cmd': 'CMD_FCU_TO_AC',
            'payload': {'data': hex_state},
            'timeStamp': '0000000'
        }

    async def send_command_to_ac(self, command):
        msg = Message(str(command))
        msg.custom_properties['type'] = 'mob'
        msg.content_type = "application/json"
        msg.content_encoding = "utf-8"
        await self.amqp_api.send_message(msg)

    async def send_state_to_ac(self, state):
        future_state = ToshibaAcFcuState.from_hex_state(self.fcu_state.encode())
        future_state.update(state.encode())

        # In SAVE mode reported temperatures are 16 degrees higher than actual setpoint (only when heating)
        if state.ac_temperature not in [ToshibaAcFcuState.AcTemperature.NONE, ToshibaAcFcuState.AcTemperature.UNKNOWN]:
            if future_state.ac_mode == ToshibaAcFcuState.AcMode.HEAT:
                if future_state.ac_merit_a_feature == ToshibaAcFcuState.AcMeritAFeature.HEATING_8C:
                    state.ac_temperature = ToshibaAcFcuState.AcTemperature(state.ac_temperature.value + 16)

        if future_state.ac_mode != ToshibaAcFcuState.AcMode.HEAT:
            state.ac_merit_b_feature = ToshibaAcFcuState.AcMeritBFeature.OFF

            if future_state.ac_merit_a_feature in [ToshibaAcFcuState.AcMeritAFeature.HEATING_8C, ToshibaAcFcuState.AcMeritAFeature.FLOOR]:
                state.ac_merit_a_feature = ToshibaAcFcuState.AcMeritAFeature.OFF

        # If we are requesting to turn on, we have to clear self cleaning flag
        if state.ac_status == ToshibaAcFcuState.AcStatus.ON and self.fcu_state.ac_self_cleaning == ToshibaAcFcuState.AcSelfCleaning.ON:
            state.ac_self_cleaning = ToshibaAcFcuState.AcSelfCleaning.OFF

        logger.debug(f'[{self.name}] Sending command: {state}')

        command = self.create_cmd_fcu_to_ac(state.encode())
        await self.send_command_to_ac(command)

    @property
    def ac_status(self):
        return self.fcu_state.ac_status

    async def set_ac_status(self, val):
        state = ToshibaAcFcuState()
        state.ac_status = val

        await self.send_state_to_ac(state)

    @property
    def ac_mode(self):
        return self.fcu_state.ac_mode

    async def set_ac_mode(self, val):
        state = ToshibaAcFcuState()
        state.ac_mode = val

        await self.send_state_to_ac(state)

    @property
    def ac_temperature(self):
        # In SAVE mode reported temperatures are 16 degrees higher than actual setpoint (only when heating)

        ret = self.fcu_state.ac_temperature

        if self.fcu_state.ac_mode == ToshibaAcFcuState.AcMode.HEAT:
            if self.fcu_state.ac_merit_a_feature == ToshibaAcFcuState.AcMeritAFeature.HEATING_8C:
                if self.fcu_state.ac_temperature not in [ToshibaAcFcuState.AcTemperature.NONE, ToshibaAcFcuState.AcTemperature.UNKNOWN]:
                    ret = ToshibaAcFcuState.AcTemperature(self.fcu_state.ac_temperature.value - 16)

        if ret in [ToshibaAcFcuState.AcTemperature.NONE, ToshibaAcFcuState.AcTemperature.UNKNOWN]:
            return None

        return ret.value

    async def set_ac_temperature(self, val):
        state = ToshibaAcFcuState()
        state.ac_temperature = int(val)

        await self.send_state_to_ac(state)

    @property
    def ac_fan_mode(self):
        return self.fcu_state.ac_fan_mode

    async def set_ac_fan_mode(self, val):
        state = ToshibaAcFcuState()
        state.ac_fan_mode = val

        await self.send_state_to_ac(state)

    @property
    def ac_swing_mode(self):
        return self.fcu_state.ac_swing_mode

    async def set_ac_swing_mode(self, val):
        state = ToshibaAcFcuState()
        state.ac_swing_mode = val

        await self.send_state_to_ac(state)

    @property
    def ac_power_selection(self):
        return self.fcu_state.ac_power_selection

    async def set_ac_power_selection(self, val):
        state = ToshibaAcFcuState()
        state.ac_power_selection = val

        await self.send_state_to_ac(state)

    @property
    def ac_merit_b_feature(self):
        return self.fcu_state.ac_merit_b_feature

    async def set_ac_merit_b_feature(self, val):
        if val != ToshibaAcFcuState.AcMeritBFeature.NONE and val not in self.supported_merit_b_features:
            raise ToshibaAcDeviceError(f'Trying to set unsupported merit b feature: {val.name.title().replace("_", " ")}')

        state = ToshibaAcFcuState()
        state.ac_merit_b_feature = val

        await self.send_state_to_ac(state)

    @property
    def ac_merit_a_feature(self):
        return self.fcu_state.ac_merit_a_feature

    async def set_ac_merit_a_feature(self, val):
        if val != ToshibaAcFcuState.AcMeritAFeature.NONE and val not in self.supported_merit_a_features:
            raise ToshibaAcDeviceError(f'Trying to set unsupported merit a feature: {val.name.title().replace("_", " ")}')

        state = ToshibaAcFcuState()
        state.ac_merit_a_feature = val

        await self.send_state_to_ac(state)

    @property
    def ac_air_pure_ion(self):
        return self.fcu_state.ac_air_pure_ion

    async def set_ac_air_pure_ion(self, val):
        if not self.is_pure_ion_supported:
            raise ToshibaAcDeviceError('Pure Ion feature is not supported by this device')
        state = ToshibaAcFcuState()
        state.ac_air_pure_ion = val

        await self.send_state_to_ac(state)

    @property
    def ac_indoor_temperature(self):
        ret = self.fcu_state.ac_indoor_temperature

        if ret in [ToshibaAcFcuState.AcTemperature.NONE, ToshibaAcFcuState.AcTemperature.UNKNOWN]:
            return None

        return ret.value

    @property
    def ac_outdoor_temperature(self):
        ret = self.fcu_state.ac_outdoor_temperature

        if ret in [ToshibaAcFcuState.AcTemperature.NONE, ToshibaAcFcuState.AcTemperature.UNKNOWN]:
            return None

        return ret.value

    @property
    def ac_self_cleaning(self):
        return self.fcu_state.ac_self_cleaning

    @property
    def ac_energy_consumption(self):
        return self._ac_energy_consumption

    @property
    def on_state_changed_callback(self):
        return self._on_state_changed_callback

    @property
    def on_energy_consumption_changed_callback(self):
        return self._on_energy_consumption_changed_callback

    @property
    def supported_merit_a_features(self):
        return self._supported_merit_a_features

    @property
    def supported_merit_b_features(self):
        return self._supported_merit_b_features

    @property
    def is_pure_ion_supported(self):
        return self._is_pure_ion_supported

    @property
    def ac_power( self ):
        return self._ac_power

    @property
    def ac_last_energy( self ):
        return self._ac_last_energy

    @property
    def ac_last_power_update( self ):
        return self._ac_last_power_update

    @property
    def on_power_changed_callback( self ):
        return self._on_power_changed_callback

    def __repr__(self):
        return f'ToshibaAcDevice(name={self.name}, device_id={self.device_id}, ac_id={self.ac_id}, ac_unique_id={self.ac_unique_id})'

    def forJson( self ):#
        res = {}
        for name, val in vars( self.fcu_state_delta ).items():
            # Only add Enums (i.e. status values) and if they are not empty
            if isinstance( val, Enum ) and val.value is not _NONE_VAL and val.name != 'UNKNOWN':
                # Special treatment for temperature and RPM values
                if 'temperature' in name or 'rpm' in name:
                    res[name[1:]] = int( val.name )
                else:
                    res[name[1:]] = val.value
        return res
