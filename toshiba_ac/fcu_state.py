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

import logging
logger = logging.getLogger(__name__)
logger.setLevel( logging.INFO )

from enum import Enum
import struct

_NONE_VAL = 0xff

class ToshibaAcFcuState:

    AcNumberValue = Enum( 'AcNumberValue', tuple( (str(i), i) for i in range(0, 254)) + (("UNKNOWN", 0x7f), ("NONE", _NONE_VAL),) )

    AcTemperature = Enum('AcTemperature', tuple((str(i-0xff-1), i) for i in range(0x80, 0xff)) + (("-1", 0x7e), ("UNKNOWN", 0x7f)) + tuple((str(i), i) for i in range(0x00, 0x7f)) + (("NONE", _NONE_VAL),))

    AcRPM = Enum( 'AcRPM', tuple( (str(i*10), i) for i in range(0, 254)) + (("UNKNOWN", 0x7f), ("NONE", _NONE_VAL),) )

    class AcNone(Enum):
        NONE = _NONE_VAL

    class AcStatus(Enum):
        ON = 0x30
        OFF = 0x31
        INVALID = 0x02
        NONE = _NONE_VAL

    class AcMode(Enum):
        AUTO = 0x41
        COOL = 0x42
        HEAT = 0x43
        DRY = 0x44
        FAN = 0x45
        INVALID = 0x00
        NONE = _NONE_VAL

    class AcFanMode(Enum):
        AUTO = 0x41
        QUIET = 0x31
        LOW = 0x32
        MEDIUM_LOW = 0x33
        MEDIUM = 0x34
        MEDIUM_HIGH = 0x35
        HIGH = 0x36
        INVALID = 0x00
        NONE = _NONE_VAL

    class AcSwingMode(Enum):
        NOT_USED = 0x31
        SWING_VERTICAL = 0x41
        SWING_HORIZONTAL = 0x42
        SWING_VERTICAL_AND_HORIZONTAL = 0x43
        FIXED_1 = 0x50
        FIXED_2 = 0x51
        FIXED_3 = 0x52
        FIXED_4 = 0x53
        FIXED_5 = 0x54
        INVALID = 0x00
        NONE = _NONE_VAL

    class AcPowerSelection(Enum):
        POWER_50 = 0x32
        POWER_75 = 0x4b
        POWER_100 = 0x64
        NONE = _NONE_VAL

    class AcMeritBFeature(Enum):
        FIREPLACE_1 = 0x02
        FIREPLACE_2 = 0x03
        OFF = 0x00
        NONE = _NONE_VAL

    class AcMeritAFeature(Enum):
        HIGH_POWER = 0x01
        CDU_SILENT_1 = 0x02
        ECO = 0x03
        HEATING_8C = 0x04
        SLEEP_CARE = 0x05
        FLOOR = 0x06
        COMFORT = 0x07
        CDU_SILENT_2 = 0x0a
        OFF = 0x00
        NONE = _NONE_VAL

    class AcAirPureIon(Enum):
        OFF = 0x10
        ON = 0x18
        NONE = _NONE_VAL

    class AcSelfCleaning(Enum):
        ON = 0x18
        OFF = 0x10
        NONE = _NONE_VAL

    class AcTimerMode(Enum):
        OFF = 0x01
        TIMER1 = 0x02
        ON = 0x03
        TIMER2 = 0x04
        ONOFF = 0x05
        TIMER3 = 0x06
        TIMER4 = 0x09
        TIMER5 = 0x0a
        TIMER6 = 0x0b
        NONE = _NONE_VAL

    class AcLed(Enum):
        ON = 0x01
        OFF = 0x02
        NONE = _NONE_VAL

    class AcScheduler(Enum):
        ON = 0x01
        OFF = 0x02
        NONE = _NONE_VAL

    class AcError(Enum):
        OK_0 = 0x00
        OK = 0xfe
        # FAULT_INNER = 0x00 Cannot happen, because 0x00 means OK
        FAULT_COM = 0x01
        FAULT_CTRL_OUTER = 0x02
        FAULT_OTHER_OUTER = 0x03
        FAULT_SERIAL_INNER = 0x04
        FAULT_COMP_OPEN = 0x07
        FAULT_TA_OC = 0x0c
        FAULT_TC_OC = 0x0d
        FAULT_TCJ_OC = 0x0f
        FAULT_FAN_IN_BLOCK = 0x11
        FAULT_CTRL_IN = 0x12
        FAULT_INVT_OVERCUR = 0x14
        FAULT_COMP_SC = 0x16
        FAULT_CTRL_OUT_OVERCUR = 0x17
        FAULT_TE_TS_OC = 0x18
        FAULT_TD_OC = 0x19
        FAULT_FAN_OUT_BLOCK = 0x1a
        FAULT_TE = 0x1b
        FAULT_COMP_BLOCK = 0x1c
        FAULT_COMP_PHASE = 0x1d
        FAULT_TEMP_COMP_117 = 0x1e
        FAULT_COMP_VOLT = 0x1f
        FAULT_HIGH_PRES = 0x21
        FAULT_STATE = 0x34
        FAULT_DESCRPTION = 0x35
        NONE = _NONE_VAL

    @classmethod
    def from_dict_state( cls, input ):
        state = cls()
        for name, val in input.items():
            # skip name attribute, if existing
            if name != 'name':
                if hasattr( state, name ):
                    attr_type = type( getattr( state, name ) )
                    if isinstance( val, str ):
                        new_attr = attr_type[ val ]
                    else:
                        new_attr = attr_type( val )
                    setattr( state, name, new_attr )
                else:
                    logger.warning( f'Skipping non-existing field: {name}.' )
        return state

    @classmethod
    def from_hex_state(cls, hex_state):
        state = cls()
        state.decode(hex_state)
        return state

    def __init__(self):
        self.name = "Unknown"
        self.ac_status = ToshibaAcFcuState.AcStatus.NONE
        self.ac_mode = ToshibaAcFcuState.AcMode.NONE
        self.ac_temperature = ToshibaAcFcuState.AcTemperature.NONE
        self.ac_fan_mode = ToshibaAcFcuState.AcFanMode.NONE
        self.ac_swing_mode = ToshibaAcFcuState.AcSwingMode.NONE
        self.ac_power_selection = ToshibaAcFcuState.AcPowerSelection.NONE
        self.ac_merit_b_feature = ToshibaAcFcuState.AcMeritBFeature.NONE
        self.ac_merit_a_feature = ToshibaAcFcuState.AcMeritAFeature.NONE
        self.ac_air_pure_ion = ToshibaAcFcuState.AcAirPureIon.NONE
        self.ac_indoor_temperature = ToshibaAcFcuState.AcTemperature.NONE
        self.ac_outdoor_temperature = ToshibaAcFcuState.AcTemperature.NONE
        self.ac_error = ToshibaAcFcuState.AcError.NONE
        self.ac_timer_mode = ToshibaAcFcuState.AcTimerMode.NONE
        self.ac_relative_hours = ToshibaAcFcuState.AcNumberValue.NONE
        self.ac_relative_minutes = ToshibaAcFcuState.AcNumberValue.NONE
        self.ac_self_cleaning = ToshibaAcFcuState.AcSelfCleaning.NONE
        self.ac_led = ToshibaAcFcuState.AcLed.NONE
        self.ac_scheduler = ToshibaAcFcuState.AcScheduler.NONE
        self.ac_utc_hours = ToshibaAcFcuState.AcNumberValue.NONE
        self.ac_utc_minutes = ToshibaAcFcuState.AcNumberValue.NONE
        self.ac_heatexc_in_temperature = ToshibaAcFcuState.AcTemperature.NONE
        self.ac_pipe_in_temperature = ToshibaAcFcuState.AcTemperature.NONE
        self.ac_fan_in_rpm = ToshibaAcFcuState.AcRPM.NONE
        self.ac_comp_out_temperature = ToshibaAcFcuState.AcTemperature.NONE
        self.ac_comp_in_temperature = ToshibaAcFcuState.AcTemperature.NONE
        self.ac_heatexc_out_temperature = ToshibaAcFcuState.AcTemperature.NONE
        self.ac_comp_freq = ToshibaAcFcuState.AcNumberValue.NONE
        self.ac_fan_out_rpm = ToshibaAcFcuState.AcRPM.NONE
        self.ac_pwm_valve_duty = ToshibaAcFcuState.AcNumberValue.NONE
        self.ac_iac = ToshibaAcFcuState.AcNumberValue.NONE

    def encode(self):
        data = (self.ac_status,
                self.ac_mode,
                self.ac_temperature,
                self.ac_fan_mode,
                self.ac_swing_mode,
                self.ac_power_selection,
                self.ac_merit_b_feature,
                self.ac_merit_a_feature,
                self.ac_air_pure_ion,
                self.ac_indoor_temperature,
                self.ac_outdoor_temperature,
                self.ac_error,
                self.ac_timer_mode,
                self.ac_relative_hours,
                self.ac_relative_minutes,
                self.ac_self_cleaning,
                self.ac_led,
                self.ac_scheduler,
                self.ac_utc_hours,
                self.ac_utc_minutes)
        encoded = struct.pack('BBBBBBBBBBBBBBBBBBBB', *[prop.value for prop in data]).hex()
        return encoded[:12] + encoded[13] + encoded[15] + encoded[16:] # Merit A/B features are encoded using half bytes but our packing added them as bytes


    def decode(self, hex_state):
        merit_b_pad = 'f' if hex_state[12] == 'f' else '0'
        merit_a_pad = 'f' if hex_state[13] == 'f' else '0'
        extended_hex_state = hex_state[:12] + merit_b_pad + hex_state[12] + merit_a_pad + hex_state[13:] # Merit A/B features are encoded using half bytes but our unpacking expect them as bytes
        data = struct.unpack('BBBBBBBBBBBBBBBBBBBB', bytes.fromhex(extended_hex_state))
        (self.ac_status,
        self.ac_mode,
        self.ac_temperature,
        self.ac_fan_mode,
        self.ac_swing_mode,
        self.ac_power_selection,
        self.ac_merit_b_feature,
        self.ac_merit_a_feature,
        self.ac_air_pure_ion,
        self.ac_indoor_temperature,
        self.ac_outdoor_temperature,
        self.ac_error,
        self.ac_timer_mode,
        self.ac_relative_hours,
        self.ac_relative_minutes,
        self.ac_self_cleaning,
        self.ac_led,
        self.ac_scheduler,
        self.ac_utc_hours,
        self.ac_utc_minutes) = data

    def update(self, hex_state):
        state_update = ToshibaAcFcuState.from_hex_state(hex_state)
        return self.update_state( state_update )

    def update_single_state( self, state_update, last_update, state_name, state_desc ):
        old_state = getattr( self, state_name )
        new_state = getattr( state_update, state_name )
        if new_state not in [ type(new_state).NONE, old_state ]:
            logger.info( f'{self.name}: {state_desc} changed from {old_state.name} to {new_state.name}' )
            setattr( self, state_name, new_state )
            setattr( last_update, state_name, new_state )
            return True
        else:
            return False

    def update_state( self, state_update ):
        last_update = ToshibaAcFcuState()
        changed = False
        changed = self.update_single_state( state_update, last_update, "ac_status", "Status" ) or changed
        changed = self.update_single_state( state_update, last_update, "ac_mode", "Mode" ) or changed
        changed = self.update_single_state( state_update, last_update, "ac_temperature", "Setpoint temperature" ) or changed
        changed = self.update_single_state( state_update, last_update, "ac_fan_mode", "Fan mode" ) or changed
        changed = self.update_single_state( state_update, last_update, "ac_swing_mode", "Swing mode" ) or changed
        changed = self.update_single_state( state_update, last_update, "ac_power_selection", "Power selection" ) or changed
        changed = self.update_single_state( state_update, last_update, "ac_merit_b_feature", "Merit B" ) or changed
        changed = self.update_single_state( state_update, last_update, "ac_merit_a_feature", "Merit A" ) or changed
        changed = self.update_single_state( state_update, last_update, "ac_air_pure_ion", "Pure Ion" ) or changed
        changed = self.update_single_state( state_update, last_update, "ac_indoor_temperature", "Indoor temperature" ) or changed
        changed = self.update_single_state( state_update, last_update, "ac_outdoor_temperature", "Outdoor temperature" ) or changed
        changed = self.update_single_state( state_update, last_update, "ac_error", "Error" ) or changed
        changed = self.update_single_state( state_update, last_update, "ac_timer_mode", "Time Mode" ) or changed
        changed = self.update_single_state( state_update, last_update, "ac_relative_hours", "Relative hours" ) or changed
        changed = self.update_single_state( state_update, last_update, "ac_relative_minutes", "Relative minutes" ) or changed
        changed = self.update_single_state( state_update, last_update, "ac_self_cleaning", "Self cleaning" ) or changed
        changed = self.update_single_state( state_update, last_update, "ac_led", "LED mode" ) or changed
        changed = self.update_single_state( state_update, last_update, "ac_scheduler", "Scheduler" ) or changed
        changed = self.update_single_state( state_update, last_update, "ac_utc_hours", "UTC hours" ) or changed
        changed = self.update_single_state( state_update, last_update, "ac_utc_minutes", "UTC minutes" ) or changed
        changed = self.update_single_state( state_update, last_update, "ac_heatexc_in_temperature", "Indoor heat exchanger temperature" ) or changed
        changed = self.update_single_state( state_update, last_update, "ac_pipe_in_temperature", "Indoor pipe temperature" ) or changed
        changed = self.update_single_state( state_update, last_update, "ac_fan_in_rpm", "Indoor fan RPM" ) or changed
        changed = self.update_single_state( state_update, last_update, "ac_comp_out_temperature", "Compressor outlet temperature" ) or changed
        changed = self.update_single_state( state_update, last_update, "ac_comp_in_temperature", "Compressor inlet temperature" ) or changed
        changed = self.update_single_state( state_update, last_update, "ac_heatexc_out_temperature", "Outdoor heat exchanger temperature" ) or changed
        changed = self.update_single_state( state_update, last_update, "ac_comp_freq", "Compressor frequency" ) or changed
        changed = self.update_single_state( state_update, last_update, "ac_fan_out_rpm", "Outdoor fan RPM" ) or changed
        changed = self.update_single_state( state_update, last_update, "ac_pwm_valve_duty", "Valve PWM duty cycle" ) or changed
        changed = self.update_single_state( state_update, last_update, "ac_iac", "IAC" ) or changed
        return last_update if changed else None

    @property
    def ac_status(self):
        return self._ac_status
    @ac_status.setter
    def ac_status(self, val):
        self._ac_status = ToshibaAcFcuState.AcStatus(val)

    @property
    def ac_mode(self):
        return self._ac_mode
    @ac_mode.setter
    def ac_mode(self, val):
        self._ac_mode = ToshibaAcFcuState.AcMode(val)

    @property
    def ac_temperature(self):
        return self._ac_temperature
    @ac_temperature.setter
    def ac_temperature(self, val):
        self._ac_temperature = ToshibaAcFcuState.AcTemperature(val)

    @property
    def ac_fan_mode(self):
        return self._ac_fan_mode
    @ac_fan_mode.setter
    def ac_fan_mode(self, val):
        self._ac_fan_mode = ToshibaAcFcuState.AcFanMode(val)

    @property
    def ac_swing_mode(self):
        return self._ac_swing_mode
    @ac_swing_mode.setter
    def ac_swing_mode(self, val):
        self._ac_swing_mode = ToshibaAcFcuState.AcSwingMode(val)

    @property
    def ac_power_selection(self):
        return self._ac_power_selection
    @ac_power_selection.setter
    def ac_power_selection(self, val):
        self._ac_power_selection = ToshibaAcFcuState.AcPowerSelection(val)

    @property
    def ac_merit_b_feature(self):
        return self._ac_merit_b_feature
    @ac_merit_b_feature.setter
    def ac_merit_b_feature(self, val):
        self._ac_merit_b_feature = ToshibaAcFcuState.AcMeritBFeature(val)

    @property
    def ac_merit_a_feature(self):
        return self._ac_merit_a_feature
    @ac_merit_a_feature.setter
    def ac_merit_a_feature(self, val):
        self._ac_merit_a_feature = ToshibaAcFcuState.AcMeritAFeature(val)

    @property
    def ac_air_pure_ion(self):
        return self._ac_air_pure_ion
    @ac_air_pure_ion.setter
    def ac_air_pure_ion(self, val):
        self._ac_air_pure_ion = ToshibaAcFcuState.AcAirPureIon(val)

    @property
    def ac_indoor_temperature(self):
        return self._ac_indoor_temperature
    @ac_indoor_temperature.setter
    def ac_indoor_temperature(self, val):
        self._ac_indoor_temperature = ToshibaAcFcuState.AcTemperature(val)

    @property
    def ac_outdoor_temperature(self):
        return self._ac_outdoor_temperature
    @ac_outdoor_temperature.setter
    def ac_outdoor_temperature(self, val):
        self._ac_outdoor_temperature = ToshibaAcFcuState.AcTemperature(val)

    @property
    def ac_error(self):
        return self._ac_error
    @ac_error.setter
    def ac_error(self, val):
        self._ac_error = ToshibaAcFcuState.AcError(val)

    @property
    def ac_timer_mode(self):
        return self._ac_timer_mode
    @ac_timer_mode.setter
    def ac_timer_mode(self, val):
        self._ac_timer_mode = ToshibaAcFcuState.AcTimerMode(val)

    @property
    def ac_relative_hours(self):
        return self._ac_relative_hours
    @ac_relative_hours.setter
    def ac_relative_hours(self, val):
        self._ac_relative_hours = ToshibaAcFcuState.AcNumberValue(val)

    @property
    def ac_relative_minutes(self):
        return self._ac_relative_minutes
    @ac_relative_minutes.setter
    def ac_relative_minutes(self, val):
        self._ac_relative_minutes = ToshibaAcFcuState.AcNumberValue(val)

    @property
    def ac_self_cleaning(self):
        return self._ac_self_cleaning
    @ac_self_cleaning.setter
    def ac_self_cleaning(self, val):
        self._ac_self_cleaning = ToshibaAcFcuState.AcSelfCleaning(val)

    @property
    def ac_led(self):
        return self._ac_led
    @ac_led.setter
    def ac_led(self, val):
        self._ac_led = ToshibaAcFcuState.AcLed(val)

    @property
    def ac_scheduler(self):
        return self._ac_scheduler
    @ac_scheduler.setter
    def ac_scheduler(self, val):
        self._ac_scheduler = ToshibaAcFcuState.AcScheduler(val)

    @property
    def ac_utc_hours(self):
        return self._ac_utc_hours
    @ac_utc_hours.setter
    def ac_utc_hours(self, val):
        self._ac_utc_hours = ToshibaAcFcuState.AcNumberValue(val)

    @property
    def ac_utc_minutes(self):
        return self._ac_utc_minutes
    @ac_utc_minutes.setter
    def ac_utc_minutes(self, val):
        self._ac_utc_minutes = ToshibaAcFcuState.AcNumberValue(val)

    @property
    def ac_heatexc_in_temperature(self):
        return self._ac_heatexc_in_temperature
    @ac_heatexc_in_temperature.setter
    def ac_heatexc_in_temperature(self, val):
        self._ac_heatexc_in_temperature = ToshibaAcFcuState.AcTemperature(val)

    @property
    def ac_pipe_in_temperature(self):
        return self._ac_pipe_in_temperature
    @ac_pipe_in_temperature.setter
    def ac_pipe_in_temperature(self, val):
        self._ac_pipe_in_temperature = ToshibaAcFcuState.AcTemperature(val)

    @property
    def ac_fan_in_rpm(self):
        return self._ac_fan_in_rpm
    @ac_fan_in_rpm.setter
    def ac_fan_in_rpm(self, val):
        self._ac_fan_in_rpm = ToshibaAcFcuState.AcRPM(val)

    @property
    def ac_comp_out_temperature(self):
        return self._ac_comp_out_temperature
    @ac_comp_out_temperature.setter
    def ac_comp_out_temperature(self, val):
        self._ac_comp_out_temperature = ToshibaAcFcuState.AcTemperature(val)

    @property
    def ac_comp_in_temperature(self):
        return self._ac_comp_in_temperature
    @ac_comp_in_temperature.setter
    def ac_comp_in_temperature(self, val):
        self._ac_comp_in_temperature = ToshibaAcFcuState.AcTemperature(val)

    @property
    def ac_heatexc_out_temperature(self):
        return self._ac_heatexc_out_temperature
    @ac_heatexc_out_temperature.setter
    def ac_heatexc_out_temperature(self, val):
        self._ac_heatexc_out_temperature = ToshibaAcFcuState.AcTemperature(val)

    @property
    def ac_comp_freq(self):
        return self._ac_comp_freq
    @ac_comp_freq.setter
    def ac_comp_freq(self, val):
        self._ac_comp_freq = ToshibaAcFcuState.AcNumberValue(val)

    @property
    def ac_fan_out_rpm(self):
        return self._ac_fan_out_rpm
    @ac_fan_out_rpm.setter
    def ac_fan_out_rpm(self, val):
        self._ac_fan_out_rpm = ToshibaAcFcuState.AcRPM(val)

    @property
    def ac_pwm_valve_duty(self):
        return self._ac_pwm_valve_duty
    @ac_pwm_valve_duty.setter
    def ac_pwm_valve_duty(self, val):
        self._ac_pwm_valve_duty = ToshibaAcFcuState.AcNumberValue(val)

    @property
    def ac_iac(self):
        return self._ac_iac
    @ac_iac.setter
    def ac_iac(self, val):
        self._ac_iac = ToshibaAcFcuState.AcNumberValue(val)

    def __str__(self):
        res = f'Status: {self.ac_status.name}'
        res += f', Mode: {self.ac_mode.name}'
        res += f', Temperature: {self.ac_temperature.name}'
        res += f', FanMode: {self.ac_fan_mode.name}'
        res += f', SwingMode: {self.ac_swing_mode.name}'
        res += f', PowerSelection: {self.ac_power_selection.name}'
        res += f', MeritBFeature: {self.ac_merit_b_feature.name}'
        res += f', MeritAFeature: {self.ac_merit_a_feature.name}'
        res += f', AirPureIon: {self.ac_air_pure_ion.name}'
        res += f', IndoorTemperature: {self.ac_indoor_temperature.name}'
        res += f', OutdoorTemperature: {self.ac_outdoor_temperature.name}'
        res += f', Error: {self.ac_error.name}'
        res += f', Timer: {self.ac_timer_mode.name}'
        res += f', RelativeHours: {self.ac_relative_hours.name}'
        res += f', RelativeMinutes: {self.ac_relative_minutes.name}'
        res += f', SelfCleaning: {self.ac_self_cleaning.name}'
        res += f', LED: {self.ac_led.name}'
        res += f', Scheduler: {self.ac_scheduler.name}'
        res += f', UtcHours: {self.ac_utc_hours.name}'
        res += f', UtcMinutes: {self.ac_utc_minutes.name}'
        res += f', IndoorHeatExchangerTemperature: {self.ac_heatexc_in_temperature.name}'
        res += f', IndoorPipeTemperature: {self.ac_pipe_in_temperature.name}'
        res += f', IndoorFanRPM: {self.ac_fan_in_rpm.name}'
        res += f', CompressorOutletTemperature: {self.ac_comp_out_temperature.name}'
        res += f', CompressorInletTemperature: {self.ac_comp_in_temperature.name}'
        res += f', OutdoorHeatExchangerTemperature: {self.ac_heatexc_out_temperature.name}'
        res += f', CompressorFrequency: {self.ac_comp_freq.name}'
        res += f', OutdoorFarnRPM: {self.ac_fan_out_rpm.name}'
        res += f', ValvePwmDutyCycle: {self.ac_pwm_valve_duty.name}'
        res += f', IAC: {self.ac_iac.name}'

        return res

    def forJson( self ):#
        res = {}
        for name, val in vars( self ).items():
            # Only add Enums (i.e. status values) and if they are not empty
            if isinstance( val, Enum ) and val.value is not _NONE_VAL and val.name != 'UNKNOWN':
                # Special treatment for temperature and RPM values
                if 'temperature' in name or 'rpm' in name:
                    res[name[1:]] = int( val.name )
                else:
                    res[name[1:]] = val.value
        return res
